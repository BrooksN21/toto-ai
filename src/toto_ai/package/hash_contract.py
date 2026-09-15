"""Explicit ordered coupon hashes; file-byte hashes are a separate contract."""

import hashlib
from collections.abc import Sequence

ORDERED_LF_V1 = "sha256:ordered-coupons:utf8:lf-terminated:v1"
ORDERED_COMMA_V1 = "sha256:ordered-coupons:utf8:comma-separated:v1"


def _validate(coupons: Sequence[str]) -> None:
    if isinstance(coupons, (str, bytes)) or any(
        not isinstance(c, str) or len(c) != 15 or set(c) - set("1X2") for c in coupons
    ):
        raise ValueError("invalid ordered coupon sequence")


def ordered_lf_sha256(coupons: Sequence[str]) -> str:
    _validate(coupons)
    return hashlib.sha256(
        "".join(f"{c}\n" for c in coupons).encode("utf-8")
    ).hexdigest()


def ordered_comma_sha256(coupons: Sequence[str]) -> str:
    _validate(coupons)
    return hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()


def validate_baseline_hashes(report: dict, coupons: tuple[str, ...], archive_hash: str):
    """Legacy native reports mean LF only, never 'try either matching hash'."""
    baseline = report.get("baseline")
    if not isinstance(baseline, dict):
        raise ValueError("parallel baseline hash contract missing")
    canonical = ordered_comma_sha256(coupons)
    if canonical != archive_hash:
        raise ValueError("parallel control/archive coupon hash mismatch")
    if "package_sha256_semantics" not in baseline:
        if (
            report.get("schema_version") != 1
            or report.get("artifact_class")
            != "FINAL_INPUT_BOUND_GOAL_SPORTS_HYBRID_COMPARISON"
            or "canonical_package_sha256" in baseline
            or "canonical_package_sha256_semantics" in baseline
        ):
            raise ValueError("unsupported legacy parallel hash contract")
    elif (
        baseline["package_sha256_semantics"] != ORDERED_LF_V1
        or baseline.get("canonical_package_sha256_semantics") != ORDERED_COMMA_V1
        or baseline.get("canonical_package_sha256") != canonical
    ):
        raise ValueError("parallel baseline hash semantics mismatch")
    if baseline.get("package_sha256") != ordered_lf_sha256(coupons):
        raise ValueError("parallel baseline ordered coupon hash mismatch")
