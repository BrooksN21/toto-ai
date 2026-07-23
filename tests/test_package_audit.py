import csv
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.package.audit import (
    PackageSafetyConfig,
    PackageStrategy,
    build_package_audit,
    evaluate_package_safety,
    parse_package,
    recompute_audit_sha256,
    validate_bank,
    validate_coupons,
)
from toto_ai.package.audit_reports import write_package_audit_reports

DRAWING_4952_PROBABILITIES = (
    (0.43, 0.31, 0.26),
    (0.237623762376, 0.267326732673, 0.495049504951),
    (0.52, 0.28, 0.20),
    (0.277227722772, 0.267326732673, 0.455445544555),
    (0.34, 0.30, 0.36),
    (0.21, 0.28, 0.51),
    (0.48, 0.29, 0.23),
    (0.41, 0.29, 0.30),
    (0.30, 0.26, 0.44),
    (0.48, 0.25, 0.27),
    (0.31, 0.27, 0.42),
    (0.414141414141, 0.252525252525, 0.333333333334),
    (0.41, 0.35, 0.24),
    (0.40, 0.30, 0.30),
    (0.28, 0.28, 0.44),
)


def _coupon(number: int) -> str:
    outcomes = "1X2"
    digits = []
    for _ in range(15):
        number, remainder = divmod(number, 3)
        digits.append(outcomes[remainder])
    return "".join(digits)


def _package(count: int = 4) -> tuple[str, ...]:
    return tuple(_coupon(index) for index in range(count))


def _package_4952_like() -> tuple[str, ...]:
    coupons = []
    variable_positions = (1, 2, 3, 5, 6, 8, 9, 10, 12)
    for index in range(166):
        chars = list("211121121111121")
        for variable_index, position in enumerate(variable_positions):
            remainder = (index // (3 ** (variable_index % 5))) % 3
            chars[position] = "1X2"[remainder]
        chars[11] = "1" if index < 163 else ("X" if index < 165 else "2")
        coupons.append("".join(chars))
    return validate_coupons(coupons)


@pytest.mark.parametrize("strategy", list(PackageStrategy))
def test_every_strategy_value_is_auditable(strategy):
    audit = build_package_audit(
        _package(),
        strategy=strategy,
        requested_bank=120,
        target_category=13 if strategy is PackageStrategy.COVER else None,
    )

    assert audit.strategy == strategy.value
    assert audit.bank.used == 120


@pytest.mark.parametrize("bank", [4980, 6000, 9960])
def test_dynamic_positive_stake_multiple_banks(bank):
    metadata = validate_bank(
        requested=bank,
        effective=120,
        stake=30,
        coupon_count=4,
    )

    assert metadata.requested == bank
    assert metadata.effective == 120
    assert metadata.used == 120


@pytest.mark.parametrize(
    ("coupons", "message"),
    [
        ([], "at least one"),
        (["1" * 14], "exactly 15"),
        (["1" * 14 + "A"], "only 1, X, and 2"),
        (["1" * 15, "1" * 15], "unique"),
    ],
)
def test_invalid_coupons_fail_closed(coupons, message):
    with pytest.raises(ValueError, match=message):
        validate_coupons(coupons)


def test_hashes_are_deterministic_and_coupon_sensitive():
    first = build_package_audit(
        _package(),
        strategy="ev",
        requested_bank=120,
    )
    repeated = build_package_audit(
        _package(),
        strategy="ev",
        requested_bank=120,
    )
    changed = build_package_audit(
        (*_package()[:-1], _coupon(8)),
        strategy="ev",
        requested_bank=120,
    )

    assert first.package_sha256 == repeated.package_sha256
    assert first.audit_sha256 == repeated.audit_sha256
    assert changed.package_sha256 != first.package_sha256
    assert changed.audit_sha256 != first.audit_sha256
    assert first.package_sha256 == hashlib.sha256(
        ",".join(_package()).encode()
    ).hexdigest()


def test_cover_contract_and_complexity_limit():
    with pytest.raises(ValueError, match="Target category"):
        build_package_audit(_package(), strategy="cover", requested_bank=120)
    with pytest.raises(ValueError, match=r"variant\*coupon"):
        build_package_audit(
            _package(), strategy="ev", requested_bank=120,
            max_distance_comparisons=1,
        )
    with pytest.raises(ValueError, match="Only cover"):
        build_package_audit(
            _package(), strategy="ev", target_category=13, requested_bank=120
        )


@pytest.mark.parametrize("value", [True, "0.5", float("nan"), float("inf")])
def test_probability_values_are_strict(value):
    rows = [[0.5, 0.3, 0.2] for _ in range(15)]
    rows[0][0] = value
    with pytest.raises(ValueError):
        build_package_audit(
            _package(), strategy="ev", requested_bank=120, probabilities=rows
        )


def test_malformed_csv_reports_line(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("rank,coupon\n1,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        parse_package(path)


def test_exact_coverage_and_guaranteed_category_derivation():
    audit = build_package_audit(
        ["1" * 15],
        strategy="cover",
        target_category=15,
        requested_bank=30,
    )

    assert audit.union_brief_variant_count == 1
    assert audit.minimum_distance_distribution == {0: 1}
    assert audit.worst_minimum_distance == 0
    assert audit.guaranteed_category == 15
    assert all(row["share"] == 1.0 for row in audit.category_coverage.values())
    assert all(row["guarantee"] is True for row in audit.category_coverage.values())


def test_false_cover_target_fails_closed():
    with pytest.raises(ValueError, match="does not verify exactly"):
        build_package_audit(
            ["1" * 15, "X" * 15],
            strategy="cover",
            target_category=15,
            requested_bank=60,
        )


def test_parse_package_accepts_baltbet_semicolon_rows(tmp_path):
    package_path = tmp_path / "baltbet.txt"
    package_path.write_text(
        "30; " + "; ".join("1" * 15) + "\n",
        encoding="utf-8",
    )

    assert parse_package(package_path) == ("1" * 15,)


def test_4952_like_166_coupon_exposure_and_warnings():
    probabilities = [(0.6, 0.3, 0.1)] * 15
    audit = build_package_audit(
        _package_4952_like(),
        strategy="ev",
        requested_bank=6000,
        effective_bank=4980,
        probabilities=probabilities,
    )

    assert audit.bank.coupon_count == 166
    assert audit.bank.used == 4980
    assert audit.fixed_events == (1, 5, 8, 14, 15)
    assert audit.event_exposures[11].counts == {"1": 163, "X": 2, "2": 1}
    assert {warning["code"] for warning in audit.warnings} == {
        "extreme_concentration",
        "fixed_low_probability_outcome",
    }


def test_real_drawing_4952_coupon_fixture_regression():
    fixture = Path(__file__).parent / "fixtures" / "drawing_4952_coupons.txt"
    coupons = tuple(fixture.read_text(encoding="utf-8").splitlines())
    independently_computed_hash = hashlib.sha256(
        ",".join(coupons).encode("utf-8")
    ).hexdigest()
    audit = build_package_audit(
        coupons,
        strategy="ev",
        requested_bank=4980,
        effective_bank=4980,
    )

    assert len(coupons) == 166
    assert audit.bank.used == 4980
    assert audit.union_brief_variant_count == 5184
    assert audit.worst_minimum_distance == 6
    assert audit.guaranteed_hits == 9
    assert audit.guaranteed_category == 9
    assert audit.category_coverage[15]["covered_variants"] == 166
    assert audit.category_coverage[14]["covered_variants"] == 992
    assert audit.category_coverage[13]["covered_variants"] == 2600
    assert audit.event_exposures[11].counts == {"1": 163, "X": 2, "2": 1}
    assert audit.fixed_events == (1, 5, 8, 14, 15)
    assert independently_computed_hash == (
        "3e07537b74d18e8261a71b43394e4ff46fbb20c2bb6cb05fc09461f3ffca90de"
    )
    assert audit.package_sha256 == independently_computed_hash


def test_real_drawing_4952_package_is_not_uploadable_under_safety_gate():
    coupons = tuple(
        (Path(__file__).parent / "fixtures" / "drawing_4952_coupons.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    result = evaluate_package_safety(
        coupons,
        DRAWING_4952_PROBABILITIES,
        config=PackageSafetyConfig(),
    )

    assert result.decision == "NO BET"
    assert result.evaluated_coupons == coupons
    assert result.package_sha256 == hashlib.sha256(
        ",".join(coupons).encode("utf-8")
    ).hexdigest()
    assert result.uploadable_coupons == ()
    assert result.reason_codes == (
        "extreme_concentration",
        "zero_exposure_material_outcome",
    )
    assert {reason["event"] for reason in result.reasons} >= {1, 5, 8, 12, 14, 15}


def test_reports_and_cli_are_deterministic(tmp_path):
    package_path = tmp_path / "package.csv"
    with package_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["rank", "coupon"])
        for index, coupon in enumerate(_package(), start=1):
            writer.writerow([index, coupon])

    audit = build_package_audit(
        parse_package(package_path),
        strategy="hybrid",
        requested_bank=120,
    )
    paths = write_package_audit_reports(audit, tmp_path / "direct")
    first_contents = [path.read_bytes() for path in paths]
    assert [path.read_bytes() for path in write_package_audit_reports(
        audit, tmp_path / "direct"
    )] == first_contents
    assert json.loads(paths[0].read_text())["schema_version"] == 1
    assert "strategy: HYBRID" in paths[2].read_text()

    result = CliRunner().invoke(
        app,
        [
            "package-audit",
            "--package",
            str(package_path),
            "--strategy",
            "hybrid",
            "--bank",
            "120",
            "--report-dir",
            str(tmp_path / "cli"),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["strategy"] == "hybrid"
    assert len(payload["reports"]) == 3


def test_written_json_recomputes_audit_hash(tmp_path):
    audit = build_package_audit(_package(), strategy="ev", requested_bank=120)
    json_path, _, _ = write_package_audit_reports(audit, tmp_path)
    report = json.loads(json_path.read_text(encoding="utf-8"))

    assert report["audit_config"] == audit.audit_config
    assert recompute_audit_sha256(report) == report["audit_sha256"]
    assert recompute_audit_sha256(report["audit_hash_payload"]) == audit.audit_sha256


def _tampered(value):
    if value is None:
        return "tampered"
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value + "-tampered"
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, list):
        return [*value, "tampered"]
    if isinstance(value, dict):
        return value | {"tampered": True}
    raise AssertionError(f"Unhandled audit value type: {type(value)}")


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "strategy",
        "drawing_id",
        "target_category",
        "bank",
        "coupons",
        "package_sha256",
        "union_brief",
        "union_brief_variant_count",
        "event_exposures",
        "fixed_events",
        "near_fixed_events",
        "worst_minimum_distance",
        "guaranteed_hits",
        "guaranteed_category",
        "minimum_distance_distribution",
        "category_coverage",
        "conditional_category_probabilities",
        "union_brief_probability",
        "probability_input_sha256",
        "audit_config",
        "warnings",
    ],
)
def test_recompute_rejects_tampered_hash_bound_displayed_field(field):
    audit = build_package_audit(
        ["1" * 15],
        strategy="cover",
        drawing_id=4952,
        target_category=15,
        requested_bank=30,
        probabilities=[(0.1, 0.4, 0.5)] * 15,
    )
    report = json.loads(json.dumps(audit.to_dict()))
    report[field] = _tampered(report[field])

    with pytest.raises(ValueError, match=field):
        recompute_audit_sha256(report)


def test_recompute_rejects_missing_bound_field_and_wrong_stored_hash():
    audit = build_package_audit(_package(), strategy="ev", requested_bank=120)
    report = json.loads(json.dumps(audit.to_dict()))
    del report["coupons"]
    with pytest.raises(ValueError, match="missing.*coupons"):
        recompute_audit_sha256(report)

    report = json.loads(json.dumps(audit.to_dict()))
    report["audit_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="audit_sha256"):
        recompute_audit_sha256(report)


def _mutate_exposure_counts(audit):
    audit.event_exposures[0].counts["1"] += 1


def _mutate_exposure_percentages(audit):
    audit.event_exposures[0].percentages["1"] += 0.1


def _mutate_distance_distribution(audit):
    audit.minimum_distance_distribution[0] += 1


def _mutate_category_coverage(audit):
    audit.category_coverage[15]["covered_variants"] += 1


def _mutate_conditional_probabilities(audit):
    audit.conditional_category_probabilities[15] += 0.1


def _mutate_audit_config(audit):
    audit.audit_config["near_fixed_share"] = 0.5


def _mutate_serialized_bank(audit):
    audit.audit_hash_payload["bank"]["requested"] += 30


def _mutate_hash_payload_exposure(audit):
    audit.audit_hash_payload["event_exposures"][0]["counts"]["1"] += 1


def _mutate_hash_payload_coverage(audit):
    audit.audit_hash_payload["category_coverage"]["15"]["share"] = 0.0


def _mutate_warning(audit):
    audit.warnings[0]["share"] = 0.0


@pytest.mark.parametrize(
    "mutate",
    [
        _mutate_exposure_counts,
        _mutate_exposure_percentages,
        _mutate_distance_distribution,
        _mutate_category_coverage,
        _mutate_conditional_probabilities,
        _mutate_audit_config,
        _mutate_serialized_bank,
        _mutate_hash_payload_exposure,
        _mutate_hash_payload_coverage,
        _mutate_warning,
    ],
)
def test_report_write_rejects_nested_mutation_before_any_output(tmp_path, mutate):
    audit = build_package_audit(
        ["1" * 15],
        strategy="cover",
        target_category=15,
        requested_bank=30,
        probabilities=[(0.1, 0.4, 0.5)] * 15,
    )
    destination = tmp_path / "reports"
    mutate(audit)

    with pytest.raises(ValueError):
        write_package_audit_reports(audit, destination)

    assert not destination.exists() or not any(destination.iterdir())


def test_existing_bundle_collision_fails_closed(tmp_path):
    audit = build_package_audit(_package(), strategy="ev", requested_bank=120)
    paths = write_package_audit_reports(audit, tmp_path)
    paths[1].write_text("stale\n", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity mismatch"):
        write_package_audit_reports(audit, tmp_path)

    paths[1].write_bytes(
        write_package_audit_reports(audit, tmp_path / "other")[1].read_bytes()
    )
    (paths[0].parent / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity mismatch"):
        write_package_audit_reports(audit, tmp_path)


def test_report_identity_changes_with_audit_inputs(tmp_path):
    probabilities = [[0.5, 0.3, 0.2] for _ in range(15)]
    first = build_package_audit(
        _package(), strategy="ev", requested_bank=150, effective_bank=120,
        probabilities=probabilities,
    )
    changed = build_package_audit(
        _package(), strategy="ev", requested_bank=180, effective_bank=120,
        probabilities=probabilities,
    )

    assert write_package_audit_reports(first, tmp_path)[0].parent != (
        write_package_audit_reports(changed, tmp_path)[0].parent
    )


def test_parse_package_stops_on_first_excess_row(tmp_path):
    path = tmp_path / "large.csv"
    path.write_text(
        "rank,coupon\n1," + _coupon(0) + "\n2," + _coupon(1)
        + "\n3,not-even-validated\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"maximum 1 coupons at line 3"):
        parse_package(path, max_coupons=1)


def test_every_bound_input_changes_audit_hash_independently():
    probabilities = [[0.5, 0.3, 0.2] for _ in range(15)]
    base_kwargs = {
        "coupons": _package(),
        "strategy": "ev",
        "requested_bank": 150,
        "effective_bank": 120,
        "stake": 30,
        "probabilities": probabilities,
        "near_fixed_share": 0.95,
        "low_probability_threshold": 0.2,
        "max_distance_comparisons": 1000,
    }
    baseline = build_package_audit(**base_kwargs)
    changes = [
        {"strategy": "hybrid"},
        {"requested_bank": 180},
        {"effective_bank": 150},
        {"stake": 15},
        {"near_fixed_share": 0.9},
        {"low_probability_threshold": 0.25},
        {"max_distance_comparisons": 1001},
        {"probabilities": [[0.4, 0.4, 0.2], *probabilities[1:]]},
        {"coupons": (*_package()[:-1], _coupon(8))},
    ]
    for change in changes:
        audit = build_package_audit(**(base_kwargs | change))
        assert audit.audit_sha256 != baseline.audit_sha256

    cover_13 = build_package_audit(
        ["1" * 15], strategy="cover", target_category=13, requested_bank=30
    )
    cover_14 = build_package_audit(
        ["1" * 15], strategy="cover", target_category=14, requested_bank=30
    )
    assert cover_13.audit_sha256 != cover_14.audit_sha256
