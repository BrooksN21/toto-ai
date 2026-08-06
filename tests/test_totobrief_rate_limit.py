import json
import socket
import ssl
import subprocess
import sys

import pytest
import requests

from toto_ai.api.client import TotoBriefClient
from toto_ai.api.rate_limit import (
    RequestDiagnostic,
    TotoBriefRequestCoordinator,
    TotoBriefRequestError,
    classify_transport_error,
)


class FakeClock:
    def __init__(self, value=1_000.0):
        self.value = float(value)
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self.payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class SequenceSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def coordinator(tmp_path, clock, diagnostics=None, **kwargs):
    return TotoBriefRequestCoordinator(
        state_path=tmp_path / "rate.json",
        minimum_interval=kwargs.pop("minimum_interval", 2.0),
        max_retries=kwargs.pop("max_retries", 2),
        backoff_base=kwargs.pop("backoff_base", 1.0),
        backoff_cap=kwargs.pop("backoff_cap", 30.0),
        jitter_ratio=0.0,
        clock=clock,
        sleep=clock.sleep,
        random=lambda: 0.0,
        diagnostic_callback=(diagnostics.append if diagnostics is not None else None),
        allowed_root=tmp_path,
        **kwargs,
    )


def test_page_then_immediate_detail_429_retry_after_eventually_succeeds(tmp_path):
    clock = FakeClock()
    diagnostics = []
    session = SequenceSession(
        [
            FakeResponse(200, {"data": [{"id": 11970}]}),
            FakeResponse(429, headers={"Retry-After": "5"}),
            FakeResponse(200, {"data": {"id": 11970, "events": []}}),
        ]
    )
    client = TotoBriefClient(
        session=session,
        coordinator=coordinator(tmp_path, clock, diagnostics),
    )

    assert client.drawings()["data"][0]["id"] == 11970
    assert client.drawing_info(11970)["data"]["id"] == 11970

    assert len(session.calls) == 3
    assert clock.sleeps == [2.0, 5.0]
    retry = [item for item in diagnostics if item.event == "retry"]
    assert retry == [
        RequestDiagnostic(
            event="retry",
            endpoint="/drawing-info/11970",
            attempt=1,
            wait_seconds=5.0,
            status_code=429,
            reason="Retry-After",
        )
    ]


def test_repeated_429_exhausts_cleanly_with_safe_diagnostics(tmp_path):
    clock = FakeClock()
    diagnostics = []
    session = SequenceSession([FakeResponse(429), FakeResponse(429)])
    client = TotoBriefClient(
        session=session,
        coordinator=coordinator(
            tmp_path,
            clock,
            diagnostics,
            minimum_interval=0,
            max_retries=1,
        ),
    )

    with pytest.raises(TotoBriefRequestError, match="HTTP 429 after 2 attempt") as exc:
        client.drawing_info(11970)

    assert exc.value.endpoint == "/drawing-info/11970"
    assert exc.value.attempts == 2
    assert [item.event for item in diagnostics].count("failure") == 1
    assert all("totobrief.com" not in (item.reason or "") for item in diagnostics)


def test_tls_verification_failure_is_classified_and_redacted(tmp_path):
    clock = FakeClock()
    secret = "super-secret-token"
    original = requests.exceptions.SSLError(
        "certificate verify failed "
        f"https://totobrief.com/path?api_key={secret} "
        f"Authorization: Bearer {secret}"
    )
    limiter = coordinator(
        tmp_path,
        clock,
        minimum_interval=0,
        max_retries=0,
    )

    with pytest.raises(TotoBriefRequestError) as captured:
        limiter.request(lambda: (_ for _ in ()).throw(original), endpoint="/safe")

    error = captured.value
    assert error.category == "ssl_verify"
    assert error.attempts == 1
    assert error.__cause__ is original
    assert error.exception_chain == ("SSLError",)
    assert secret not in error.original_transport_message
    assert "Authorization: Bearer" not in error.original_transport_message
    assert "api_key=" not in error.original_transport_message


def test_tls_handshake_reset_is_distinct_from_certificate_verification(tmp_path):
    clock = FakeClock()
    original = requests.exceptions.SSLError(
        ssl.SSLError("TLS handshake EOF after connection reset")
    )
    limiter = coordinator(
        tmp_path,
        clock,
        minimum_interval=0,
        max_retries=0,
    )

    with pytest.raises(TotoBriefRequestError) as captured:
        limiter.request(
            lambda: (_ for _ in ()).throw(original),
            endpoint="/drawing-info/1",
        )

    assert captured.value.category == "ssl_handshake"
    assert captured.value.exception_chain[0] == "SSLError"


@pytest.mark.parametrize(
    ("cause", "expected"),
    (
        (socket.gaierror(socket.EAI_NONAME, "name not known"), "dns"),
        (requests.Timeout("read timed out"), "timeout"),
        (requests.ConnectionError("connection refused"), "connect"),
    ),
)
def test_transport_categories_follow_exception_chain(cause, expected):
    wrapper = requests.ConnectionError("request failed")
    wrapper.__cause__ = cause

    assert classify_transport_error(wrapper) == expected


def test_client_keeps_tls_verification_enabled_for_injected_session():
    session = SequenceSession([FakeResponse(200, {"data": []})])
    session.verify = False
    client = TotoBriefClient(session=session)

    assert client.session.verify is True
    client.drawings()
    assert client.session.verify is True


def test_shared_state_enforces_interval_between_independent_coordinators(tmp_path):
    clock = FakeClock()
    first = coordinator(tmp_path, clock, minimum_interval=3, max_retries=0)
    second = coordinator(tmp_path, clock, minimum_interval=3, max_retries=0)

    first.request(lambda: FakeResponse(200), endpoint="/first")
    second.request(lambda: FakeResponse(200), endpoint="/second")

    assert clock.sleeps == [3.0]
    state = json.loads((tmp_path / "rate.json").read_text())
    assert state["last_request_at"] == 1003.0
    assert state["written_at"] == 1003.0


def test_state_lock_enforces_interval_across_real_processes(tmp_path):
    script = """
import pathlib
import sys
import time
from toto_ai.api.rate_limit import TotoBriefRequestCoordinator

class Response:
    status_code = 200
    headers = {}
    def raise_for_status(self):
        return None

state, output = sys.argv[1:]
coordinator = TotoBriefRequestCoordinator(
    state_path=state,
    allowed_root=pathlib.Path(state).parent,
    minimum_interval=0.2,
    max_retries=0,
    jitter_ratio=0,
)
def request():
    pathlib.Path(output).write_text(str(time.time()))
    return Response()
coordinator.request(request, endpoint="/cross-process")
"""
    state = tmp_path / "shared.json"
    outputs = [tmp_path / "one.txt", tmp_path / "two.txt"]
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(state), str(output)])
        for output in outputs
    ]
    for process in processes:
        assert process.wait(timeout=10) == 0

    observed = sorted(float(path.read_text()) for path in outputs)
    assert observed[1] - observed[0] >= 0.18


def test_corrupt_state_waits_conservatively_and_is_replaced(tmp_path):
    clock = FakeClock()
    diagnostics = []
    (tmp_path / "rate.json").write_text("not-json")
    limiter = coordinator(tmp_path, clock, diagnostics, minimum_interval=2)

    limiter.request(lambda: FakeResponse(200), endpoint="/safe")

    assert clock.sleeps == [2.0]
    assert any(item.event == "state-recovered" for item in diagnostics)
    assert json.loads((tmp_path / "rate.json").read_text())["schema_version"] == 2


def test_stale_state_is_ignored_without_wait(tmp_path):
    clock = FakeClock(10_000)
    (tmp_path / "rate.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "written_at": 1_000,
                "last_request_at": 1_000,
                "blocked_until": None,
                "block_source": None,
            }
        )
    )
    limiter = coordinator(
        tmp_path,
        clock,
        minimum_interval=2,
        state_ttl_seconds=100,
    )

    limiter.request(lambda: FakeResponse(200), endpoint="/stale")

    assert clock.sleeps == []


def test_final_exhausted_429_persists_long_retry_after_for_next_process(tmp_path):
    clock = FakeClock()
    first = coordinator(
        tmp_path,
        clock,
        minimum_interval=0,
        max_retries=0,
        maximum_wait_seconds=10,
    )

    with pytest.raises(TotoBriefRequestError, match="HTTP 429"):
        first.request(
            lambda: FakeResponse(429, headers={"Retry-After": "3600"}),
            endpoint="/drawing-info/1",
        )

    state = json.loads((tmp_path / "rate.json").read_text())
    assert state["blocked_until"] == 4600.0
    assert state["block_source"] == "retry-after"
    assert state["written_at"] == 1000.0

    calls = []
    second = coordinator(
        tmp_path,
        clock,
        minimum_interval=0,
        max_retries=0,
        maximum_wait_seconds=10,
    )
    with pytest.raises(TotoBriefRequestError, match="shared wait") as exc:
        second.request(
            lambda: calls.append(True) or FakeResponse(200),
            endpoint="/drawing-info/2?api_key=secret",
        )

    assert calls == []
    assert exc.value.endpoint == "/drawing-info/2"
    assert exc.value.status_code == 429
    assert json.loads((tmp_path / "rate.json").read_text())["blocked_until"] == 4600.0


def test_retry_after_larger_than_backoff_cap_is_honored_when_within_wait_bound(
    tmp_path,
):
    clock = FakeClock()
    responses = iter(
        [
            FakeResponse(429, headers={"Retry-After": "20"}),
            FakeResponse(200),
        ]
    )
    limiter = coordinator(
        tmp_path,
        clock,
        minimum_interval=0,
        max_retries=1,
        backoff_cap=2,
        maximum_wait_seconds=30,
    )

    limiter.request(lambda: next(responses), endpoint="/long")

    assert clock.sleeps == [20.0]


def test_backoff_jitter_never_exceeds_configured_cap(tmp_path):
    clock = FakeClock()
    limiter = TotoBriefRequestCoordinator(
        state_path=tmp_path / "rate.json",
        allowed_root=tmp_path,
        minimum_interval=0,
        max_retries=1,
        backoff_base=10,
        backoff_cap=10,
        jitter_ratio=1,
        clock=clock,
        sleep=clock.sleep,
        random=lambda: 1,
    )
    responses = iter([FakeResponse(500), FakeResponse(200)])

    limiter.request(lambda: next(responses), endpoint="/cap")

    assert clock.sleeps == [10.0]


def test_chunked_transport_error_retries_without_url_or_query_leak(tmp_path):
    clock = FakeClock()
    diagnostics = []
    secret_url = "https://totobrief.com/path?api_key=do-not-print"
    session = SequenceSession(
        [
            requests.exceptions.ChunkedEncodingError(
                f"broken response from {secret_url}"
            ),
            FakeResponse(200, {"data": []}),
        ]
    )
    client = TotoBriefClient(
        session=session,
        coordinator=coordinator(
            tmp_path,
            clock,
            diagnostics,
            minimum_interval=0,
            max_retries=1,
        ),
    )

    assert client.get_json("/path?api_key=do-not-print") == {"data": []}

    rendered = " ".join(
        [
            *(str(item) for item in diagnostics),
        ]
    )
    assert "do-not-print" not in rendered
    assert "https://" not in rendered
    assert any(item.reason == "ChunkedEncodingError" for item in diagnostics)


def test_rate_state_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        TotoBriefRequestCoordinator(
            state_path=link / "rate.json",
            allowed_root=tmp_path,
        )
