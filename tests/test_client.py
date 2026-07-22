import pytest

from toto_ai.api.client import BASE_URL, TotoBriefClient
from toto_ai.api.rate_limit import TotoBriefRequestError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def test_supported_drawings_requests_supported_drawings_endpoint():
    response = FakeResponse({"data": ["baltbet-main"]})
    session = FakeSession(response)
    client = TotoBriefClient(session=session)

    assert client.supported_drawings() == {"data": ["baltbet-main"]}
    assert session.calls == [
        {
            "url": f"{BASE_URL}/supported-drawings",
            "params": None,
            "timeout": 30,
        }
    ]
    assert response.raise_for_status_called is True


def test_drawings_requests_named_drawings_with_page():
    response = FakeResponse({"data": [{"id": 42}]})
    session = FakeSession(response)
    client = TotoBriefClient(session=session)

    assert client.drawings(name="custom", page=3) == {"data": [{"id": 42}]}
    assert session.calls == [
        {
            "url": f"{BASE_URL}/custom/drawings",
            "params": {"page": 3},
            "timeout": 30,
        }
    ]


def test_drawing_info_requests_drawing_info_endpoint():
    response = FakeResponse({"data": {"id": 17}})
    session = FakeSession(response)
    client = TotoBriefClient(session=session)

    assert client.drawing_info(17) == {"data": {"id": 17}}
    assert session.calls == [
        {
            "url": f"{BASE_URL}/drawing-info/17",
            "params": None,
            "timeout": 30,
        }
    ]


def test_malformed_json_is_sanitized_and_not_retried():
    class MalformedResponse(FakeResponse):
        status_code = 200

        def json(self):
            raise ValueError(
                "malformed body from https://totobrief.com/path?token=secret"
            )

    session = FakeSession(MalformedResponse(None))
    client = TotoBriefClient(session=session)

    with pytest.raises(TotoBriefRequestError, match="malformed JSON") as exc:
        client.get_json("/path?token=secret")

    assert exc.value.endpoint == "/path"
    assert exc.value.attempts == 1
    assert len(session.calls) == 1
    assert "secret" not in str(exc.value)
    assert "https://" not in str(exc.value)
