"""Pure post-draw attribution for an immutable coupon package."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

OUTCOMES = ("1", "X", "2")
VOID = "VOID"
ATTRIBUTION_COMPLETE = "ATTRIBUTION_COMPLETE"
PENDING_RESULTS = "PENDING_RESULTS"
ANALYSIS_ONLY_LABEL = "EXPIRED — ANALYSIS ONLY — NOT FOR WAGERING"
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_VOID_STATUSES = frozenset({"void"})
_CANCELLED_STATUSES = frozenset({"cancelled", "canceled"})
_POSTPONED_STATUSES = frozenset({"postponed", "postpone", "pst"})


class AttributionIntegrityError(ValueError):
    """Raised when immutable attribution inputs do not agree."""


@dataclass(frozen=True)
class AttributionIdentity:
    """Immutable identity shared by the expected and observed artifacts."""

    drawing_id: int
    drawing_number: int
    plan_id: str
    package_id: str
    final_input_sha256: str
    package_sha256: str
    result_sha256: str


@dataclass(frozen=True)
class AttributionReportPaths:
    """Deterministic report files written for one attribution run."""

    json_path: Path
    csv_path: Path
    markdown_path: Path
    manifest_path: Path
    generation_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "json": str(self.json_path),
            "csv": str(self.csv_path),
            "markdown": str(self.markdown_path),
            "manifest": str(self.manifest_path),
            "generation_sha256": self.generation_sha256,
        }


def build_post_draw_attribution_report(
    *,
    settled_drawing_payload: bytes,
    package_payload: bytes,
    package_archive_payload: bytes,
    final_input_payload: bytes,
    operator_result_payload: bytes,
) -> dict[str, Any]:
    """Build attribution directly from one settled drawing and package artifacts.

    The generated package artifacts are the scheduler's ``package.csv``,
    ``package-archive.json`` and ``final-input.json``. The settled drawing may
    be a raw TotoBrief-style object with a ``data`` object or a normalized
    object with top-level drawing identity and events.

    Missing results are classified from their own raw result/status fields.
    A terminal VOID/cancelled/postponed exclusion requires an explicit ``*``
    result and a reviewed HTTP(S) evidence source. Status-only rows remain
    pending, preserving the existing post-draw settlement boundary.
    """

    package_archive = _validated_package_archive(
        package_archive_payload,
        package_payload=package_payload,
    )
    operator_result = _validated_operator_play(
        operator_result_payload,
        package_payload=package_payload,
        package_archive=package_archive,
    )
    final_input = _json_object(final_input_payload, "final input")
    final_input_sha256 = package_archive["final_input_sha256"]
    plan_id = final_input.get("plan_id")
    if type(plan_id) is not str or not plan_id:
        raise AttributionIntegrityError("final input plan_id is invalid")
    if operator_result["plan_id"] != plan_id:
        raise AttributionIntegrityError("operator result and final input plan mismatch")

    classified = _classified_settled_drawing(settled_drawing_payload)
    expected_drawing_id = package_archive["drawing_id"]
    expected_drawing_number = package_archive["drawing_number"]
    if (
        classified["drawing_id"] != expected_drawing_id
        or classified["drawing_number"] != expected_drawing_number
    ):
        raise AttributionIntegrityError(
            "settled drawing and package artifact identity mismatch"
        )

    result_payload = _canonical_json_bytes(classified["normalized_events"])
    result_sha256 = hashlib.sha256(result_payload).hexdigest()
    expected_identity = AttributionIdentity(
        drawing_id=expected_drawing_id,
        drawing_number=expected_drawing_number,
        plan_id=plan_id,
        package_id=package_archive["archive_manifest_sha256"],
        final_input_sha256=final_input_sha256,
        package_sha256=package_archive["canonical_package_sha256"],
        result_sha256=result_sha256,
    )
    observed_identity = AttributionIdentity(
        drawing_id=classified["drawing_id"],
        drawing_number=classified["drawing_number"],
        plan_id=plan_id,
        package_id=package_archive["archive_manifest_sha256"],
        final_input_sha256=final_input_sha256,
        package_sha256=package_archive["canonical_package_sha256"],
        result_sha256=result_sha256,
    )
    coupons = _package_payload_coupons(package_payload)
    _validate_package_payload(package_payload, coupons, expected_identity)
    frozen_events = _validated_final_input(final_input_payload, expected_identity)
    event_inputs = _attribution_event_inputs(
        classified["events"],
        frozen_events,
    )

    summary = _classification_summary(classified["events"])
    common: dict[str, Any] = {
        "schema_version": 1,
        "analysis_only_label": ANALYSIS_ONLY_LABEL,
        "status": (
            PENDING_RESULTS
            if summary["pending_event_orders"]
            else ATTRIBUTION_COMPLETE
        ),
        "identity": {
            "drawing_id": expected_identity.drawing_id,
            "drawing_number": expected_identity.drawing_number,
            "plan_id": expected_identity.plan_id,
            "package_id": expected_identity.package_id,
            "final_input_sha256": expected_identity.final_input_sha256.lower(),
            "package_sha256": expected_identity.package_sha256.lower(),
            "result_sha256": (
                None
                if summary["pending_event_orders"]
                else expected_identity.result_sha256.lower()
            ),
        },
        "settled_drawing_sha256": hashlib.sha256(
            settled_drawing_payload
        ).hexdigest(),
        "classification_sha256": result_sha256,
        "operator_result_sha256": operator_result["record_sha256"],
        "attribution_scope": "aggregate_only",
        "coupon_count": len(coupons),
        "event_count": len(event_inputs),
        "result_classification": summary,
    }
    if summary["pending_event_orders"]:
        return {
            **common,
            "hit_denominator": None,
            "best_hits": None,
            "missed_positions": [],
            "events": event_inputs,
        }

    attribution = attribute_post_draw(
        expected_identity=expected_identity,
        observed_identity=observed_identity,
        coupons=coupons,
        events=event_inputs,
        package_payload=package_payload,
        final_input_payload=final_input_payload,
        settled_result_payload=result_payload,
    )
    classifications = {row["position"]: row for row in classified["events"]}
    enriched_events = []
    for row in attribution["events"]:
        classification = classifications[row["position"]]
        enriched_events.append(
            {
                **row,
                "result_classification": classification["classification"],
                "terminal_result": classification["terminal"],
                "source_result": classification["source_result"],
                "source_result_status": classification["source_result_status"],
                "reviewed_void_source": classification["reviewed_void_source"],
                "exclusion_reason": (
                    classification["classification"]
                    if classification["excluded_from_hit_denominator"]
                    else None
                ),
            }
        )
    return {
        **common,
        **{
            key: value
            for key, value in attribution.items()
            if key
            not in {
                "identity",
                "best_coupon_rank",
                "best_coupon_ranks",
                "best_coupon_indices",
            }
        },
        "events": enriched_events,
    }


def generate_post_draw_attribution_reports(
    *,
    settled_drawing_file: str | Path,
    package_dir: str | Path,
    operator_result_file: str | Path,
    output_dir: str | Path,
) -> tuple[dict[str, Any], AttributionReportPaths]:
    """Load fixed scheduler artifact names and write deterministic reports."""

    package_root = Path(package_dir)
    settled_payload = _read_regular_file(
        settled_drawing_file,
        "settled drawing",
    )
    package_payload = _read_regular_file(package_root / "package.csv", "package")
    package_archive_payload = _read_regular_file(
        package_root / "package-archive.json",
        "package archive",
    )
    final_input_payload = _read_regular_file(
        package_root / "final-input.json",
        "final input",
    )
    operator_result_payload = _read_regular_file(
        operator_result_file,
        "operator result",
    )
    _validate_operator_artifact_paths(operator_result_payload, package_root)
    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=package_payload,
        package_archive_payload=package_archive_payload,
        final_input_payload=final_input_payload,
        operator_result_payload=operator_result_payload,
    )
    paths = write_post_draw_attribution_reports(report, output_dir=output_dir)
    return report, paths


def write_post_draw_attribution_reports(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> AttributionReportPaths:
    """Write JSON, event CSV and Markdown views atomically."""

    root = Path(output_dir)
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise AttributionIntegrityError("attribution output must be a directory")
    root.mkdir(parents=True, exist_ok=True)
    json_payload = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    files = {
        "post-draw-attribution.json": json_payload,
        "post-draw-attribution-events.csv": _attribution_csv(report).encode("utf-8"),
        "post-draw-attribution.md": _attribution_markdown(report).encode("utf-8"),
    }
    hashes = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in files.items()
    }
    unsigned_manifest = {
        "schema_version": 1,
        "files": hashes,
    }
    generation_sha256 = _sha256_json(unsigned_manifest)
    manifest = {
        **unsigned_manifest,
        "generation_sha256": generation_sha256,
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    generation_dir = root / "generations" / generation_sha256
    _publish_report_generation(
        generation_dir,
        files={**files, "manifest.json": manifest_payload},
    )
    return AttributionReportPaths(
        json_path=generation_dir / "post-draw-attribution.json",
        csv_path=generation_dir / "post-draw-attribution-events.csv",
        markdown_path=generation_dir / "post-draw-attribution.md",
        manifest_path=generation_dir / "manifest.json",
        generation_sha256=generation_sha256,
    )


def _validated_package_archive(
    payload: bytes,
    *,
    package_payload: bytes,
) -> dict[str, Any]:
    document = _json_object(payload, "package archive")
    manifest_sha256 = document.get("archive_manifest_sha256")
    if type(manifest_sha256) is not str or _SHA256.fullmatch(manifest_sha256) is None:
        raise AttributionIntegrityError("package archive manifest SHA-256 is invalid")
    unsigned = dict(document)
    unsigned.pop("archive_manifest_sha256", None)
    if _sha256_final_input_json(unsigned) != manifest_sha256.lower():
        raise AttributionIntegrityError("package archive manifest hash mismatch")
    if document.get("provenance") != "pre_bet_runner":
        raise AttributionIntegrityError(
            "attribution requires a generated pre-bet package archive"
        )
    if document.get("schema_version") != 2:
        raise AttributionIntegrityError(
            "attribution requires an atomic-final package archive"
        )
    for name in ("drawing_id", "drawing_number"):
        value = document.get(name)
        if type(value) is not int or value <= 0:
            raise AttributionIntegrityError(f"package archive {name} is invalid")
    for name in (
        "canonical_package_sha256",
        "source_bytes_sha256",
        "final_input_sha256",
    ):
        value = document.get(name)
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            raise AttributionIntegrityError(f"package archive {name} is invalid")
    if (
        hashlib.sha256(package_payload).hexdigest()
        != document["source_bytes_sha256"].lower()
    ):
        raise AttributionIntegrityError("package source bytes SHA-256 mismatch")
    coupons = _package_payload_coupons(package_payload)
    if _sha256_text(",".join(coupons)) != document[
        "canonical_package_sha256"
    ].lower():
        raise AttributionIntegrityError("package canonical SHA-256 mismatch")
    coupon_count = document.get("coupon_count")
    if type(coupon_count) is not int or coupon_count != len(coupons):
        raise AttributionIntegrityError("package archive coupon count mismatch")
    stake = document.get("stake")
    cost = document.get("cost")
    if (
        type(stake) is not int
        or stake <= 0
        or type(cost) is not int
        or cost != stake * coupon_count
    ):
        raise AttributionIntegrityError("package archive stake/cost mismatch")
    source_path = document.get("source_path")
    if type(source_path) is not str or not source_path:
        raise AttributionIntegrityError("package archive source path is invalid")
    document["archive_manifest_sha256"] = manifest_sha256.lower()
    document["canonical_package_sha256"] = document[
        "canonical_package_sha256"
    ].lower()
    document["final_input_sha256"] = document["final_input_sha256"].lower()
    return document


def _validated_operator_play(
    payload: bytes,
    *,
    package_payload: bytes,
    package_archive: Mapping[str, Any],
) -> dict[str, Any]:
    document = _json_object(payload, "operator result")
    record_sha256 = document.get("record_sha256")
    if type(record_sha256) is not str or _SHA256.fullmatch(record_sha256) is None:
        raise AttributionIntegrityError("operator result record SHA-256 is invalid")
    unsigned = dict(document)
    unsigned.pop("record_sha256", None)
    if _sha256_json(unsigned) != record_sha256.lower():
        raise AttributionIntegrityError("operator result integrity hash mismatch")
    required = {
        "schema_version": 3,
        "operator_status": "FINAL_FRESH",
        "decision": "PLAY",
        "provenance": "FINAL_FRESH",
        "automatic_wagering": False,
        "actionable": True,
        "profitability_proven": False,
    }
    if any(document.get(name) != value for name, value in required.items()):
        raise AttributionIntegrityError(
            "attribution requires scheduler-owned operator PLAY provenance"
        )
    if (
        document.get("drawing_id") != package_archive["drawing_id"]
        or document.get("drawing") != package_archive["drawing_number"]
        or document.get("archive_manifest_sha256")
        != package_archive["archive_manifest_sha256"]
        or document.get("source_package_sha256")
        != hashlib.sha256(package_payload).hexdigest()
        or document.get("selected_count") != package_archive["coupon_count"]
        or document.get("stake") != package_archive["stake"]
        or document.get("selected_cost") != package_archive["cost"]
    ):
        raise AttributionIntegrityError(
            "operator result and package/archive identity mismatch"
        )
    for name in (
        "package_sha256",
        "source_package_sha256",
        "archive_manifest_sha256",
    ):
        value = document.get(name)
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            raise AttributionIntegrityError(f"operator result {name} is invalid")
    plan_id = document.get("plan_id")
    run_id = document.get("run_id")
    if type(plan_id) is not str or not plan_id:
        raise AttributionIntegrityError("operator result plan_id is invalid")
    valid_run_id = (
        type(run_id) is str
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id) is not None
    )
    if not valid_run_id:
        raise AttributionIntegrityError("operator result run_id is invalid")
    release_mode = document.get("release_mode")
    if release_mode == "STANDARD":
        if (
            document.get("release_authorization_path") is not None
            or document.get("release_authorization_sha256") is not None
            or document.get("risk_acknowledged") is not False
        ):
            raise AttributionIntegrityError(
                "operator standard release binding mismatch"
            )
    elif release_mode == "EXPERIMENTAL_MANUAL":
        authorization_sha256 = document.get("release_authorization_sha256")
        if (
            type(document.get("release_authorization_path")) is not str
            or type(authorization_sha256) is not str
            or _SHA256.fullmatch(authorization_sha256) is None
            or document.get("risk_acknowledged") is not True
        ):
            raise AttributionIntegrityError(
                "operator experimental release binding mismatch"
            )
    else:
        raise AttributionIntegrityError("operator release mode is invalid")
    document["record_sha256"] = record_sha256.lower()
    return document


def _validate_operator_artifact_paths(payload: bytes, package_root: Path) -> None:
    document = _json_object(payload, "operator result")
    if package_root.is_symlink() or not package_root.is_dir():
        raise AttributionIntegrityError("package directory must be a regular directory")
    root = package_root.resolve()
    expected = {
        "source_package_path": root / "package.csv",
        "archive_manifest_path": root / "package-archive.json",
        "coupon_path": root / "baltbet-upload.txt",
        "status_path": root / "status.json",
        "marker_path": root / ".bet-ready",
    }
    for name, expected_path in expected.items():
        value = document.get(name)
        if type(value) is not str or Path(value).resolve() != expected_path:
            raise AttributionIntegrityError(
                f"operator result {name} is not bound to package directory"
            )
    if document.get("run_id") != root.name:
        raise AttributionIntegrityError(
            "operator result run_id is not bound to package directory"
        )


def _package_payload_coupons(payload: bytes) -> tuple[str, ...]:
    if type(payload) is not bytes:
        raise AttributionIntegrityError("package payload must be immutable bytes")
    try:
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error) as error:
        raise AttributionIntegrityError(
            "package payload is not valid UTF-8 CSV"
        ) from error
    if not rows:
        raise AttributionIntegrityError("package payload is empty")
    header = [cell.strip().lower() for cell in rows[0]]
    if "coupon" not in header:
        raise AttributionIntegrityError("package payload lacks a coupon column")
    coupon_index = header.index("coupon")
    coupons: list[str] = []
    for line, row in enumerate(rows[1:], start=2):
        if coupon_index >= len(row):
            raise AttributionIntegrityError(
                f"package payload lacks coupon at line {line}"
            )
        coupons.append(row[coupon_index].strip())
    if not coupons:
        raise AttributionIntegrityError("package payload contains no coupons")
    return _validated_coupons(coupons, len(coupons[0]))


def _classified_settled_drawing(payload: bytes) -> dict[str, Any]:
    document = _json_object(payload, "settled drawing")
    raw_data = document.get("data", document)
    if not isinstance(raw_data, Mapping):
        raise AttributionIntegrityError("settled drawing data must be a mapping")
    drawing_id = raw_data.get("id", raw_data.get("drawing_id"))
    drawing_number = raw_data.get("number", raw_data.get("drawing_number"))
    if type(drawing_id) is not int or drawing_id <= 0:
        raise AttributionIntegrityError("settled drawing id is invalid")
    if type(drawing_number) is not int or drawing_number <= 0:
        raise AttributionIntegrityError("settled drawing number is invalid")
    raw_events = raw_data.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise AttributionIntegrityError(
            "settled drawing events must be a non-empty list"
        )

    by_order: dict[int, dict[str, Any]] = {}
    normalized_by_order: dict[int, dict[str, Any]] = {}
    for raw in raw_events:
        if not isinstance(raw, Mapping):
            raise AttributionIntegrityError(
                "settled drawing event must be a mapping"
            )
        order = raw.get("order")
        event_id = raw.get("id", raw.get("event_id"))
        if type(order) is not int or order < 0 or order in by_order:
            raise AttributionIntegrityError(
                "settled drawing event order is invalid"
            )
        if type(event_id) is not int or event_id <= 0:
            raise AttributionIntegrityError("settled drawing event id is invalid")
        classification = _classify_result_event(raw, order=order, event_id=event_id)
        by_order[order] = classification
        normalized = {
            "event_id": event_id,
            "order": order,
            "result": classification["normalized_result"],
            "result_status": (
                "void"
                if classification["excluded_from_hit_denominator"]
                else "resolved"
                if classification["terminal"]
                else "pending"
            ),
            "score": classification["score"],
            "source_result_status": classification["source_result_status"],
            "source_classification": classification["classification"],
        }
        if classification["reviewed_void_source"] is not None:
            normalized["void_source"] = classification["reviewed_void_source"]
        normalized_by_order[order] = normalized
    expected_orders = set(range(len(raw_events)))
    if set(by_order) != expected_orders:
        raise AttributionIntegrityError(
            "settled drawing event orders must be unique and contiguous"
        )
    return {
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "events": [by_order[order] for order in range(len(raw_events))],
        "normalized_events": [
            normalized_by_order[order] for order in range(len(raw_events))
        ],
    }


def _classify_result_event(
    raw: Mapping[str, Any],
    *,
    order: int,
    event_id: int,
) -> dict[str, Any]:
    source_result = raw.get("result")
    if source_result is not None and not isinstance(source_result, str):
        raise AttributionIntegrityError(
            f"settled event {order + 1} result must be a string or null"
        )
    result_token = "" if source_result is None else source_result.strip()
    source_status = _source_result_status(raw)
    status_token = _normalized_status(source_status)
    score = raw.get("score")
    if score is None:
        score = ""
    if not isinstance(score, str):
        raise AttributionIntegrityError(
            f"settled event {order + 1} score must be a string or null"
        )
    score = score.strip()
    evidence_source = _optional_evidence_url(raw.get("void_source"))

    upper_result = result_token.upper()
    terminal = False
    excluded = False
    normalized_result: str | None
    reviewed_void_source: str | None = None
    if upper_result in OUTCOMES:
        if not score:
            raise AttributionIntegrityError(
                f"settled event {order + 1} resolved result lacks a score"
            )
        if status_token in (
            _VOID_STATUSES | _CANCELLED_STATUSES | _POSTPONED_STATUSES
        ):
            raise AttributionIntegrityError(
                f"settled event {order + 1} result/status conflict"
            )
        classification = "resolved"
        normalized_result = upper_result
        terminal = True
        if evidence_source is not None:
            raise AttributionIntegrityError(
                f"settled event {order + 1} resolved result has VOID evidence"
            )
    elif upper_result in {"*", VOID}:
        if score:
            raise AttributionIntegrityError(
                f"settled event {order + 1} excluded result has a score"
            )
        normalized_result = None
        if status_token in _POSTPONED_STATUSES:
            classification = "postponed"
        elif status_token in _CANCELLED_STATUSES:
            classification = "cancelled"
        else:
            classification = "void"
        if (
            status_token
            in (_VOID_STATUSES | _CANCELLED_STATUSES | _POSTPONED_STATUSES)
            and evidence_source is not None
        ):
            terminal = True
            excluded = True
            normalized_result = VOID
            reviewed_void_source = evidence_source
    elif not result_token:
        normalized_result = None
        if status_token in _VOID_STATUSES:
            classification = "void"
        elif status_token in _CANCELLED_STATUSES:
            classification = "cancelled"
        elif status_token in _POSTPONED_STATUSES:
            classification = "postponed"
        else:
            classification = "pending"
    elif result_token.casefold() in (
        _VOID_STATUSES | _CANCELLED_STATUSES | _POSTPONED_STATUSES
    ):
        normalized_result = None
        if result_token.casefold() in _POSTPONED_STATUSES:
            classification = "postponed"
        elif result_token.casefold() in _CANCELLED_STATUSES:
            classification = "cancelled"
        else:
            classification = "void"
    else:
        raise AttributionIntegrityError(
            f"settled event {order + 1} has an unsupported result"
        )

    return {
        "position": order + 1,
        "event_id": event_id,
        "source_result": source_result,
        "source_result_status": source_status,
        "source_evidence_url": evidence_source,
        "reviewed_void_source": reviewed_void_source,
        "classification": classification,
        "terminal": terminal,
        "excluded_from_hit_denominator": excluded,
        "normalized_result": normalized_result,
        "score": score,
    }


def _optional_evidence_url(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise AttributionIntegrityError("VOID evidence source must be an HTTP(S) URL")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 2048
        or any(character.isspace() for character in normalized)
    ):
        raise AttributionIntegrityError("VOID evidence source must be an HTTP(S) URL")
    try:
        parsed = urlsplit(normalized)
    except ValueError as error:
        raise AttributionIntegrityError(
            "VOID evidence source must be an HTTP(S) URL"
        ) from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise AttributionIntegrityError("VOID evidence source must be an HTTP(S) URL")
    return normalized


def _source_result_status(raw: Mapping[str, Any]) -> str | None:
    value = raw.get("result_status")
    if value in (None, ""):
        value = raw.get("status")
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise AttributionIntegrityError(
            "settled drawing result status must be a string or null"
        )
    return value.strip()


def _normalized_status(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _attribution_event_inputs(
    classifications: Sequence[Mapping[str, Any]],
    frozen_events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(classifications) != len(frozen_events):
        raise AttributionIntegrityError("settled and final-input event counts differ")
    rows: list[dict[str, Any]] = []
    for classification, frozen in zip(
        classifications,
        frozen_events,
        strict=True,
    ):
        position = classification["position"]
        if classification["event_id"] != frozen.get("id"):
            raise AttributionIntegrityError(
                f"event {position} settled/final-input identity mismatch"
            )
        name = frozen.get("name")
        if type(name) is not str or " — " not in name:
            raise AttributionIntegrityError(
                f"event {position} frozen team identity is invalid"
            )
        home, away = name.split(" — ", 1)
        row: dict[str, Any] = {
            "position": position,
            "event_id": classification["event_id"],
            "home_team": home,
            "away_team": away,
            "score": classification["score"],
            "result": classification["normalized_result"],
            "result_classification": classification["classification"],
            "terminal_result": classification["terminal"],
            "excluded_from_hit_denominator": classification[
                "excluded_from_hit_denominator"
            ],
            "source_result": classification["source_result"],
            "source_result_status": classification["source_result_status"],
            "source_evidence_url": classification["source_evidence_url"],
            "reviewed_void_source": classification["reviewed_void_source"],
        }
        if classification["normalized_result"] in OUTCOMES:
            quotes = frozen.get("quotes")
            if not isinstance(quotes, Mapping):
                raise AttributionIntegrityError(
                    f"event {position} frozen quotes are invalid"
                )
            row["bk"] = _quotes_probabilities(quotes, "bk", position)
            row["pool"] = _quotes_probabilities(quotes, "pool", position)
        rows.append(row)
    return rows


def _classification_summary(
    events: Sequence[Mapping[str, Any]],
) -> dict[str, list[int]]:
    classifications = ("resolved", "void", "cancelled", "postponed", "pending")
    result = {
        f"{classification}_event_orders": [
            row["position"]
            for row in events
            if row["classification"] == classification
        ]
        for classification in classifications
    }
    result["excluded_event_orders"] = [
        row["position"]
        for row in events
        if row["excluded_from_hit_denominator"]
    ]
    result["pending_event_orders"] = [
        row["position"] for row in events if not row["terminal"]
    ]
    return result


def _read_regular_file(path: str | Path, label: str) -> bytes:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise AttributionIntegrityError(f"{label} must be a regular file")
    try:
        return candidate.read_bytes()
    except OSError as error:
        raise AttributionIntegrityError(f"could not read {label}") from error


def _publish_report_generation(
    generation_dir: Path,
    *,
    files: Mapping[str, bytes],
) -> None:
    generations_root = generation_dir.parent
    if generations_root.exists() and (
        generations_root.is_symlink() or not generations_root.is_dir()
    ):
        raise AttributionIntegrityError(
            "attribution generations root must be a regular directory"
        )
    generations_root.mkdir(parents=True, exist_ok=True)
    if generation_dir.exists():
        _verify_report_generation(generation_dir, files=files)
        return
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{generation_dir.name}.",
            dir=generations_root,
        )
    )
    try:
        for name, payload in files.items():
            _write_staged_report_file(stage / name, payload)
        try:
            stage.replace(generation_dir)
        except FileExistsError:
            _verify_report_generation(generation_dir, files=files)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _write_staged_report_file(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def _verify_report_generation(
    generation_dir: Path,
    *,
    files: Mapping[str, bytes],
) -> None:
    if generation_dir.is_symlink() or not generation_dir.is_dir():
        raise AttributionIntegrityError(
            "attribution generation is not a regular directory"
        )
    if {path.name for path in generation_dir.iterdir()} != set(files):
        raise AttributionIntegrityError("attribution generation file set mismatch")
    for name, expected in files.items():
        path = generation_dir / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise AttributionIntegrityError(
                "attribution generation content mismatch"
            )


def _attribution_csv(report: Mapping[str, Any]) -> str:
    fieldnames = (
        "position",
        "event_id",
        "home_team",
        "away_team",
        "result_classification",
        "terminal_result",
        "excluded_from_hit_denominator",
        "reviewed_void_source",
        "actual_outcome",
        "score",
        "miss",
        "exposure_1",
        "exposure_X",
        "exposure_2",
        "actual_bk_rank",
        "actual_pool_rank",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for event in report.get("events", []):
        exposures = event.get("exposures")
        writer.writerow(
            {
                "position": event.get("position"),
                "event_id": event.get("event_id"),
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "result_classification": event.get("result_classification"),
                "terminal_result": event.get("terminal_result"),
                "excluded_from_hit_denominator": event.get(
                    "excluded_from_hit_denominator"
                ),
                "reviewed_void_source": event.get("reviewed_void_source"),
                "actual_outcome": event.get("actual_outcome"),
                "score": event.get("score"),
                "miss": event.get("miss"),
                "exposure_1": (
                    None if not isinstance(exposures, Mapping) else exposures.get("1")
                ),
                "exposure_X": (
                    None if not isinstance(exposures, Mapping) else exposures.get("X")
                ),
                "exposure_2": (
                    None if not isinstance(exposures, Mapping) else exposures.get("2")
                ),
                "actual_bk_rank": event.get("actual_bk_rank"),
                "actual_pool_rank": event.get("actual_pool_rank"),
            }
        )
    return output.getvalue()


def _attribution_markdown(report: Mapping[str, Any]) -> str:
    identity = report["identity"]
    classification = report["result_classification"]
    lines = [
        f"# Post-draw attribution: drawing {identity['drawing_number']}",
        "",
        f"**{report['analysis_only_label']}**",
        "",
        f"- Status: `{report['status']}`",
        f"- Drawing ID: `{identity['drawing_id']}`",
        f"- Plan: `{identity['plan_id']}`",
        f"- Coupons: {report['coupon_count']}",
        f"- Resolved event orders: {_orders(classification['resolved_event_orders'])}",
        f"- Excluded event orders: {_orders(classification['excluded_event_orders'])}",
        f"- VOID event orders: {_orders(classification['void_event_orders'])}",
        "- Cancelled event orders: "
        f"{_orders(classification['cancelled_event_orders'])}",
        "- Postponed event orders: "
        f"{_orders(classification['postponed_event_orders'])}",
        f"- Pending event orders: {_orders(classification['pending_event_orders'])}",
        "",
    ]
    if report["status"] == ATTRIBUTION_COMPLETE:
        lines.extend(
            [
                f"- Hit denominator: {report['hit_denominator']}",
                f"- Best hits: {report['best_hits']}",
                f"- Missed positions: {_orders(report['missed_positions'])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Attribution is pending because at least one event lacks a terminal",
                "result. A postponed status alone is not converted into VOID.",
                "",
            ]
        )
    lines.extend(
        [
            "## Events",
            "",
            "| # | Event | Classification | Excluded | Actual | Miss |",
            "|---:|---|---|:---:|:---:|:---:|",
        ]
    )
    for event in report["events"]:
        event_name = f"{event.get('home_team', '')} — {event.get('away_team', '')}"
        lines.append(
            "| "
            f"{event['position']} | {event_name} | "
            f"{event.get('result_classification', '')} | "
            f"{'yes' if event.get('excluded_from_hit_denominator') else 'no'} | "
            f"{event.get('actual_outcome') or '—'} | "
            f"{'yes' if event.get('miss') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "Cancelled/VOID events are excluded from hit and miss attribution.",
            "This report does not establish profitability.",
            "",
        ]
    )
    return "\n".join(lines)


def _orders(values: Sequence[int]) -> str:
    return ", ".join(str(value) for value in values) if values else "none"


def attribute_post_draw(
    *,
    expected_identity: AttributionIdentity,
    observed_identity: AttributionIdentity,
    coupons: Sequence[str],
    events: Sequence[Mapping[str, Any]],
    package_payload: bytes,
    final_input_payload: bytes,
    settled_result_payload: bytes,
) -> dict[str, Any]:
    """Attribute package misses using only immutable, caller-supplied bytes.

    Hashes are never trusted as metadata alone. Coupon identity is the SHA-256
    of the UTF-8 comma-joined coupon sequence parsed from ``package_payload``.
    Final-input identity follows its producer contract: SHA-256 of
    deterministic JSON (UTF-8, sorted keys, compact separators and escaped
    non-ASCII) after removing its declared ``snapshot_sha256`` field.
    Settled-result identity uses compact sorted-key JSON without forcing
    non-ASCII escaping. The supplied
    ``coupons`` and ``events`` must agree exactly with those three byte-bound
    artifacts. No input is mutated and no filesystem or database access is
    performed.

    If multiple coupons tie for best score, all signatures and source indices
    are returned. Event-level attribution uses the lexicographically smallest
    best signature, making that attribution independent of package row order.
    """

    identity = _validated_identity(expected_identity, observed_identity)
    ordered_events = _validated_events(events)
    normalized_coupons = _validated_coupons(coupons, len(ordered_events))
    _validate_package_payload(package_payload, normalized_coupons, identity)
    frozen_events = _validated_final_input(final_input_payload, identity)
    settled_events = _validated_settled_results(settled_result_payload, identity)
    _validate_event_bindings(ordered_events, frozen_events, settled_events)

    scored = [_score_coupon(coupon, ordered_events) for coupon in normalized_coupons]
    best_hits = max(scored)
    best_indexes = tuple(
        index for index, hits in enumerate(scored) if hits == best_hits
    )
    best_signatures = tuple(
        sorted({normalized_coupons[index] for index in best_indexes})
    )
    best_coupon = best_signatures[0]
    best_index = normalized_coupons.index(best_coupon)
    best_missed_position_sets = sorted(
        {
            tuple(_coupon_missed_positions(signature, ordered_events))
            for signature in best_signatures
        }
    )
    denominator = sum(event["result"] != VOID for event in ordered_events)

    event_rows: list[dict[str, Any]] = []
    missed_positions: list[int] = []
    probability_rank_misses: list[int] = []
    exposure_concentrations: list[int] = []

    for zero_index, event in enumerate(ordered_events):
        position = event["position"]
        actual = event["result"]
        exposures = {
            outcome: sum(coupon[zero_index] == outcome for coupon in normalized_coupons)
            for outcome in OUTCOMES
        }
        selected = best_coupon[zero_index]
        is_void = actual == VOID
        miss = False if is_void else selected != actual
        actual_count = None if is_void else exposures[actual]
        actual_present = None if is_void else actual_count > 0
        bk = None if is_void else _validated_probabilities(event["bk"], "bk", position)
        pool = (
            None
            if is_void
            else _validated_probabilities(event["pool"], "pool", position)
        )
        bk_rank = None if is_void else _probability_rank(bk, actual)
        pool_rank = None if is_void else _probability_rank(pool, actual)

        if miss:
            missed_positions.append(position)
            if bk_rank is not None and bk_rank > 1:
                probability_rank_misses.append(position)
            if actual_count is not None and actual_count < max(exposures.values()):
                exposure_concentrations.append(position)

        row: dict[str, Any] = {
            "position": position,
            "event_id": event.get("event_id"),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "score": event.get("score"),
            "actual_outcome": actual,
            "void": is_void,
            "excluded_from_hit_denominator": is_void,
            "exposures": exposures,
            "actual_exposure_count": actual_count,
            "actual_outcome_present": actual_present,
            "bk_probabilities": bk,
            "pool_probabilities": pool,
            "actual_bk_rank": bk_rank,
            "actual_pool_rank": pool_rank,
            "best_coupon_miss_count": sum(
                actual != VOID and signature[zero_index] != actual
                for signature in best_signatures
            ),
            "miss": miss,
        }
        event_rows.append(row)

    joint = _joint_missed_coverage(
        normalized_coupons,
        ordered_events,
        missed_positions,
    )
    labels = {
        "probability_rank_miss": probability_rank_misses,
        "exposure_concentration": exposure_concentrations,
        "joint_coverage_gap": missed_positions
        if len(missed_positions) > 1 and joint["all_missed_joint_coverage"] == 0
        else [],
    }
    hit_distribution = Counter(scored)

    return {
        "identity": {
            "drawing_id": identity.drawing_id,
            "drawing_number": identity.drawing_number,
            "plan_id": identity.plan_id,
            "package_id": identity.package_id,
            "final_input_sha256": identity.final_input_sha256.lower(),
            "package_sha256": identity.package_sha256.lower(),
            "result_sha256": identity.result_sha256.lower(),
        },
        "coupon_count": len(normalized_coupons),
        "event_count": len(ordered_events),
        "hit_denominator": denominator,
        "best_hits": best_hits,
        "best_coupon_rank": best_index + 1,
        "best_coupon_ranks": [index + 1 for index in best_indexes],
        "best_coupon_indices": list(best_indexes),
        "all_best_missed_position_sets": [
            list(positions) for positions in best_missed_position_sets
        ],
        "hit_distribution": {
            str(hits): hit_distribution[hits] for hits in sorted(hit_distribution)
        },
        "missed_positions": missed_positions,
        "all_missed_joint_coverage": joint["all_missed_joint_coverage"],
        "at_least_n_missed_coverage": joint["at_least_n_missed_coverage"],
        "labels": labels,
        "events": event_rows,
    }


def _validated_identity(
    expected: AttributionIdentity,
    observed: AttributionIdentity,
) -> AttributionIdentity:
    for label, identity in (("expected", expected), ("observed", observed)):
        for name in ("drawing_id", "drawing_number"):
            value = getattr(identity, name)
            if type(value) is not int or value <= 0:
                raise AttributionIntegrityError(
                    f"{label} {name} must be a positive int"
                )
        for name in ("plan_id", "package_id"):
            value = getattr(identity, name)
            if type(value) is not str or not value:
                raise AttributionIntegrityError(
                    f"{label} {name} must be a non-empty str"
                )
        for name in ("final_input_sha256", "package_sha256", "result_sha256"):
            value = getattr(identity, name)
            if type(value) is not str or _SHA256.fullmatch(value) is None:
                raise AttributionIntegrityError(f"{label} {name} is not SHA-256")

    fields = (
        "drawing_id",
        "drawing_number",
        "plan_id",
        "package_id",
        "final_input_sha256",
        "package_sha256",
        "result_sha256",
    )
    mismatches = [
        name
        for name in fields
        if _identity_value(expected, name) != _identity_value(observed, name)
    ]
    if mismatches:
        raise AttributionIntegrityError(
            "immutable identity mismatch: " + ", ".join(mismatches)
        )
    return expected


def _identity_value(identity: AttributionIdentity, name: str) -> object:
    value = getattr(identity, name)
    if name.endswith("sha256") and isinstance(value, str):
        return value.lower()
    return value


def _validate_package_payload(
    payload: bytes,
    coupons: Sequence[str],
    identity: AttributionIdentity,
) -> None:
    if type(payload) is not bytes:
        raise AttributionIntegrityError("package payload must be immutable bytes")
    try:
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error) as error:
        raise AttributionIntegrityError(
            "package payload is not valid UTF-8 CSV"
        ) from error
    if not rows:
        raise AttributionIntegrityError("package payload is empty")
    header = [cell.strip().lower() for cell in rows[0]]
    if "coupon" not in header:
        raise AttributionIntegrityError("package payload lacks a coupon column")
    coupon_index = header.index("coupon")
    payload_coupons: list[str] = []
    for line, row in enumerate(rows[1:], start=2):
        if coupon_index >= len(row):
            raise AttributionIntegrityError(
                f"package payload lacks coupon at line {line}"
            )
        payload_coupons.append(row[coupon_index].strip())
    parsed = _validated_coupons(payload_coupons, len(coupons[0]))
    if parsed != tuple(coupons):
        raise AttributionIntegrityError(
            "coupon sequence does not match package payload"
        )
    computed = _sha256_text(",".join(parsed))
    if computed != identity.package_sha256.lower():
        raise AttributionIntegrityError("package content SHA-256 mismatch")


def _validated_final_input(
    payload: bytes,
    identity: AttributionIdentity,
) -> list[dict[str, Any]]:
    document = _json_object(payload, "final input")
    declared = document.get("snapshot_sha256")
    if type(declared) is not str or _SHA256.fullmatch(declared) is None:
        raise AttributionIntegrityError(
            "final input declares an invalid snapshot SHA-256"
        )
    unsigned = dict(document)
    unsigned.pop("snapshot_sha256", None)
    computed = _sha256_final_input_json(unsigned)
    if declared.lower() != computed or identity.final_input_sha256.lower() != computed:
        raise AttributionIntegrityError("final input content SHA-256 mismatch")
    _require_exact_identity_field(document, "drawing_id", identity.drawing_id, int)
    _require_exact_identity_field(
        document,
        "drawing_number",
        identity.drawing_number,
        int,
    )
    _require_exact_identity_field(document, "plan_id", identity.plan_id, str)
    frozen_payload = document.get("payload")
    if not isinstance(frozen_payload, Mapping):
        raise AttributionIntegrityError("final input payload must be a mapping")
    detail_hash = document.get("detail_payload_sha256")
    if (
        type(detail_hash) is not str
        or _SHA256.fullmatch(detail_hash) is None
        or detail_hash.lower() != _sha256_final_input_json(frozen_payload)
    ):
        raise AttributionIntegrityError("final input detail payload hash mismatch")
    data = frozen_payload.get("data")
    if not isinstance(data, Mapping):
        raise AttributionIntegrityError("final input data must be a mapping")
    _require_exact_identity_field(data, "id", identity.drawing_id, int)
    _require_exact_identity_field(data, "number", identity.drawing_number, int)
    raw_events = data.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise AttributionIntegrityError("final input events must be a non-empty list")
    result: list[dict[str, Any]] = []
    for order, raw in enumerate(raw_events):
        if not isinstance(raw, Mapping) or type(raw.get("order")) is not int:
            raise AttributionIntegrityError("final input event identity is invalid")
        if raw["order"] != order or type(raw.get("id")) is not int:
            raise AttributionIntegrityError("final input event order/id is invalid")
        result.append(dict(raw))
    return result


def _validated_settled_results(
    payload: bytes,
    identity: AttributionIdentity,
) -> list[dict[str, Any]]:
    if type(payload) is not bytes:
        raise AttributionIntegrityError(
            "settled result payload must be immutable bytes"
        )
    try:
        raw_events = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AttributionIntegrityError(
            "settled result payload is not valid JSON"
        ) from error
    if not isinstance(raw_events, list) or not raw_events:
        raise AttributionIntegrityError(
            "settled result events must be a non-empty list"
        )
    if _sha256_json(raw_events) != identity.result_sha256.lower():
        raise AttributionIntegrityError("settled result content SHA-256 mismatch")
    result: list[dict[str, Any]] = []
    for order, raw in enumerate(raw_events):
        if not isinstance(raw, Mapping):
            raise AttributionIntegrityError("settled result event must be a mapping")
        event = dict(raw)
        if type(event.get("order")) is not int or event["order"] != order:
            raise AttributionIntegrityError("settled result event order is invalid")
        if type(event.get("event_id")) is not int:
            raise AttributionIntegrityError("settled result event id is invalid")
        actual = event.get("result")
        status = event.get("result_status")
        score = event.get("score")
        if actual == VOID:
            source = _optional_evidence_url(event.get("void_source"))
            if status != "void" or score != "" or source is None:
                raise AttributionIntegrityError("settled VOID result is invalid")
        elif (
            actual not in OUTCOMES
            or status != "resolved"
            or type(score) is not str
            or not score.strip()
        ):
            raise AttributionIntegrityError("settled resolved result is invalid")
        result.append(event)
    return result


def _validate_event_bindings(
    events: Sequence[Mapping[str, Any]],
    frozen_events: Sequence[Mapping[str, Any]],
    settled_events: Sequence[Mapping[str, Any]],
) -> None:
    if len(events) != len(frozen_events) or len(events) != len(settled_events):
        raise AttributionIntegrityError("artifact event counts do not agree")
    for index, (event, frozen, settled) in enumerate(
        zip(events, frozen_events, settled_events, strict=True),
        start=1,
    ):
        event_id = event.get("event_id")
        if type(event_id) is not int:
            raise AttributionIntegrityError(f"event {index} id must be an int")
        if event_id != frozen["id"] or event_id != settled["event_id"]:
            raise AttributionIntegrityError(f"event {index} artifact identity mismatch")
        name = frozen.get("name")
        if type(name) is not str or " — " not in name:
            raise AttributionIntegrityError(
                f"event {index} frozen team identity is invalid"
            )
        home, away = name.split(" — ", 1)
        if type(event.get("home_team")) is not str or event["home_team"] != home:
            raise AttributionIntegrityError(f"event {index} home team mismatch")
        if type(event.get("away_team")) is not str or event["away_team"] != away:
            raise AttributionIntegrityError(f"event {index} away team mismatch")
        if event.get("result") != settled["result"]:
            raise AttributionIntegrityError(f"event {index} settled result mismatch")
        if event.get("score") != settled["score"]:
            raise AttributionIntegrityError(f"event {index} settled score mismatch")
        if event["result"] == VOID:
            continue
        quotes = frozen.get("quotes")
        if not isinstance(quotes, Mapping):
            raise AttributionIntegrityError(f"event {index} frozen quotes are invalid")
        expected_bk = _quotes_probabilities(quotes, "bk", index)
        expected_pool = _quotes_probabilities(quotes, "pool", index)
        actual_bk = _validated_probabilities(event["bk"], "bk", index)
        actual_pool = _validated_probabilities(event["pool"], "pool", index)
        if actual_bk != expected_bk or actual_pool != expected_pool:
            raise AttributionIntegrityError(
                f"event {index} frozen probability payload mismatch"
            )


def _quotes_probabilities(
    quotes: Mapping[str, Any],
    prefix: str,
    position: int,
) -> dict[str, float]:
    return _validated_probabilities(
        {
            "1": quotes.get(f"{prefix}_win_1"),
            "X": quotes.get(f"{prefix}_draw"),
            "2": quotes.get(f"{prefix}_win_2"),
        },
        prefix,
        position,
    )


def _json_object(payload: bytes, label: str) -> dict[str, Any]:
    if type(payload) is not bytes:
        raise AttributionIntegrityError(f"{label} payload must be immutable bytes")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AttributionIntegrityError(f"{label} payload is not valid JSON") from error
    if not isinstance(document, dict):
        raise AttributionIntegrityError(f"{label} payload must be a JSON object")
    return document


def _require_exact_identity_field(
    payload: Mapping[str, Any],
    name: str,
    expected: object,
    expected_type: type,
) -> None:
    observed = payload.get(name)
    if type(observed) is not expected_type or observed != expected:
        raise AttributionIntegrityError(f"payload {name} identity mismatch")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_final_input_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validated_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(events, (str, bytes)) or not events:
        raise AttributionIntegrityError("events must be a non-empty sequence")
    copied: list[dict[str, Any]] = []
    for raw in events:
        if not isinstance(raw, Mapping):
            raise AttributionIntegrityError("each event must be a mapping")
        event = dict(raw)
        position = event.get("position")
        if type(position) is not int or position <= 0:
            raise AttributionIntegrityError("event position must be positive")
        result = event.get("result")
        if result is None:
            raise AttributionIntegrityError(
                f"event {position} has an unresolved result; mark it VOID explicitly"
            )
        if result not in (*OUTCOMES, VOID):
            raise AttributionIntegrityError(f"event {position} has invalid result")
        if result != VOID:
            if "bk" not in event or "pool" not in event:
                raise AttributionIntegrityError(
                    f"event {position} lacks frozen bk/pool probabilities"
                )
        copied.append(event)
    copied.sort(key=lambda event: event["position"])
    expected_positions = list(range(1, len(copied) + 1))
    if [event["position"] for event in copied] != expected_positions:
        raise AttributionIntegrityError("event positions must be unique and contiguous")
    return copied


def _validated_coupons(coupons: Sequence[str], event_count: int) -> tuple[str, ...]:
    if isinstance(coupons, (str, bytes)) or not coupons:
        raise AttributionIntegrityError("coupons must be a non-empty sequence")
    normalized: list[str] = []
    for coupon in coupons:
        if not isinstance(coupon, str) or len(coupon) != event_count:
            raise AttributionIntegrityError("coupon length does not match event count")
        if any(outcome not in OUTCOMES for outcome in coupon):
            raise AttributionIntegrityError("coupon contains an invalid outcome")
        normalized.append(coupon)
    return tuple(normalized)


def _validated_probabilities(
    raw: object,
    label: str,
    position: int,
) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise AttributionIntegrityError(
            f"event {position} frozen {label} probabilities must be a mapping"
        )
    result: dict[str, float] = {}
    for outcome in OUTCOMES:
        value = raw.get(outcome)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise AttributionIntegrityError(
                f"event {position} has invalid frozen {label} probability for {outcome}"
            )
        result[outcome] = float(value)
    if sum(result.values()) <= 0:
        raise AttributionIntegrityError(
            f"event {position} frozen {label} probabilities sum to zero"
        )
    return result


def _probability_rank(probabilities: Mapping[str, float], actual: str) -> int:
    actual_probability = probabilities[actual]
    return 1 + sum(
        probability > actual_probability for probability in probabilities.values()
    )


def _score_coupon(coupon: str, events: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        event["result"] != VOID and coupon[index] == event["result"]
        for index, event in enumerate(events)
    )


def _coupon_missed_positions(
    coupon: str,
    events: Sequence[Mapping[str, Any]],
) -> list[int]:
    return [
        index + 1
        for index, event in enumerate(events)
        if event["result"] != VOID and coupon[index] != event["result"]
    ]


def _joint_missed_coverage(
    coupons: Sequence[str],
    events: Sequence[Mapping[str, Any]],
    missed_positions: Sequence[int],
) -> dict[str, Any]:
    if not missed_positions:
        return {
            "all_missed_joint_coverage": len(coupons),
            "at_least_n_missed_coverage": {},
        }
    match_counts = [
        sum(
            coupon[position - 1] == events[position - 1]["result"]
            for position in missed_positions
        )
        for coupon in coupons
    ]
    maximum = len(missed_positions)
    return {
        "all_missed_joint_coverage": sum(count == maximum for count in match_counts),
        "at_least_n_missed_coverage": {
            str(required): sum(count >= required for count in match_counts)
            for required in range(maximum, 0, -1)
        },
    }
