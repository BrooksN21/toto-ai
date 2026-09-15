"""Observed feature availability is not reviewed training authority."""

from toto_ai.sports_stats.v3_probability import CORE_NAMES, FEATURE_NAMES


def _family(name):
    if name.startswith("difference_"):
        return "symmetric_differences"
    for marker in ("standings", "recency", "venue", "independent_opponent"):
        if marker in name:
            return marker
    if "opponent_adjusted" in name:
        return "independent_opponent"
    if "opponent_rolling" in name:
        return "legacy_target_opponent_form"
    if "last_7" in name or "last_14" in name:
        return "congestion"
    if "rest_days" in name or "days_since" in name:
        return "rest"
    return "bookmaker" if name.startswith("bk_") else "rolling"


def feature_disposition(row):
    """Describe A2/A3 core and A4/A5 partial features without issuing authority.

    scope_verified remains the caller's independently reviewed common entity
    proof. It is never inferred from league IDs, names, labels or computability.
    This report does not evaluate F4, grant training/release or fit any model.
    """
    values = row["features"]
    if set(values) != set(FEATURE_NAMES):
        raise ValueError("predictor allowlist")
    common_reasons = []
    if row["source_rejected"]:
        common_reasons.append("SOURCE_REJECTED")
    if not row["exact_target"]:
        common_reasons.append("EXACT_TARGET_MISSING")
    if min(row["prior_counts"]) == 0:
        common_reasons.append("BOTH_HISTORY_REQUIREMENT_NOT_MET")
    common = not common_reasons
    core_missing = [n for n in CORE_NAMES if values[n] is None]
    optional_missing = [
        n for n in FEATURE_NAMES if n not in CORE_NAMES and values[n] is None
    ]
    families = {}
    for name in FEATURE_NAMES:
        family = families.setdefault(_family(name), {"observed": [], "missing": []})
        family["missing" if values[name] is None else "observed"].append(name)
    proof = row["scope_verified"] is True
    return {
        "common_source_valid": common,
        "common_rejection_reasons": common_reasons,
        "core_numeric_complete": not core_missing,
        "core_source_computable": common and not core_missing,
        "core_missing": core_missing,
        "optional_missing": optional_missing,
        "families": families,
        "common_entity_scope_proof": "VERIFIED" if proof else "NOT_ESTABLISHED",
        "A2_A3": {
            "numeric_policy": "ALL_CORE_COMPLETE",
            "input_contract_satisfied": common and proof and not core_missing,
        },
        "A4_A5": {
            "numeric_policy": "TRAIN_FOLD_IMPUTATION_AND_MISSING_INDICATORS",
            "input_contract_satisfied": common
            and proof
            and any(values[n] is not None for n in FEATURE_NAMES),
        },
        "training_authorized": False,
        "evaluation_authorized": False,
        "activation_allowed": False,
    }
