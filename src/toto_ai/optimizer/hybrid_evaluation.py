from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import StringIO
from pathlib import Path
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.optimizer.brief_backtest import best_coupon_hits
from toto_ai.optimizer.coupon_candidates import (
    generate_candidate_coupons,
    sample_scenarios,
)
from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    top_probability_coupons,
)
from toto_ai.optimizer.direct_package import (
    estimate_package_coverage,
    select_hybrid_package,
)
from toto_ai.optimizer.strategy_backtest import (
    StrategyBacktestRow,
    StrategyConfig,
    StrategyPackage,
    _validate_strategy_config,
)
from toto_ai.optimizer.strategy_diagnostics import (
    STRATEGIES,
    _config_from_manifest,
    _load_development_inputs,
    _load_development_result,
    _validate_frozen_result_fields,
    development_drawing_ids,
    load_frozen_development_rows,
    package_overlap_metrics,
    package_structure_metrics,
)

HYBRID_CORE_FRACTIONS = (0.50, 0.75, 0.90)
HYBRID_FOLD_COUNT = 5
HYBRID_BANK = 5000
HYBRID_STAKE = 30
HYBRID_CATEGORY = 13
HYBRID_MAX_COUPONS = HYBRID_BANK // HYBRID_STAKE
HYBRID_MIN_ADDITIONAL_HIT_13 = 2
HYBRID_MIN_NON_LOSING_FOLDS = 4
HYBRID_STRATEGY_ORDER = (
    "top_probability",
    "hybrid_0.50",
    "hybrid_0.75",
    "hybrid_0.90",
)


@dataclass(frozen=True)
class HybridEvaluationRow:
    drawing_id: int
    drawing_number: int | None
    fold: int
    strategy: str
    core_fraction: float | None
    best_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_size: int
    package_cost: int
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    timed_out: bool
    mean_log_probability: float
    mean_pairwise_hamming: float
    top_intersection_size: int
    top_jaccard: float


@dataclass(frozen=True)
class HybridDecision:
    status: str
    selected_core_fraction: float | None
    passing_core_fractions: tuple[float, ...]
    reason: str


@dataclass(frozen=True)
class HybridEvaluationResult:
    rows: list[HybridEvaluationRow]
    summary: dict[str, object]
    decision: HybridDecision
    manifest: dict[str, object]


def seal_hybrid_development(
    session: Session,
    manifest: dict[str, object],
    frozen_csv_path: str | Path,
    output_manifest_path: str | Path,
    output_csv_path: str | Path,
    *,
    code_version: str,
) -> tuple[Path, Path]:
    if not code_version:
        raise ValueError("Hybrid seal code version is required.")
    source_csv_path = Path(frozen_csv_path).resolve()
    manifest_path = Path(output_manifest_path).resolve()
    csv_path = Path(output_csv_path).resolve()
    if len({source_csv_path, manifest_path, csv_path}) != 3:
        raise ValueError("Hybrid seal source and output paths must be distinct.")

    development_ids = development_drawing_ids(manifest)
    assign_chronological_folds(development_ids)
    config = _config_from_manifest(manifest)
    _validate_hybrid_protocol(config)
    frozen_rows = load_frozen_development_rows(
        frozen_csv_path,
        manifest,
        stop_after_development_prefix=True,
    )
    canonical_csv = _canonical_development_csv(frozen_rows, development_ids)
    input_hash = _development_input_hash(session, development_ids)
    result_hasher = sha256()
    for drawing_id in development_ids:
        _update_result_hash(
            result_hasher,
            drawing_id,
            _load_development_result(session, drawing_id),
        )

    sealed_manifest = dict(manifest)
    sealed_manifest["hybrid_development_seal"] = {
        "schema_version": 1,
        "development_drawing_count": len(development_ids),
        "development_csv_sha256": sha256(canonical_csv).hexdigest(),
        "development_input_sha256": input_hash,
        "development_result_sha256": result_hasher.hexdigest(),
        "hybrid_protocol_sha256": _hybrid_protocol_hash(config),
        "hybrid_code_version": code_version,
    }
    manifest_bytes = (
        json.dumps(sealed_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_atomic_artifact_pair(
        ((csv_path, canonical_csv), (manifest_path, manifest_bytes))
    )
    return manifest_path, csv_path


def run_hybrid_evaluation(
    session: Session,
    manifest: dict[str, object],
    frozen_csv_path: str | Path,
    progress_callback=None,
) -> HybridEvaluationResult:
    development_ids = development_drawing_ids(manifest)
    folds = assign_chronological_folds(development_ids)
    config = _config_from_manifest(manifest)
    _validate_hybrid_protocol(config)
    frozen_rows = load_frozen_development_rows(frozen_csv_path, manifest)
    seal = _hybrid_development_seal(manifest, len(development_ids))
    canonical_csv = _canonical_development_csv(frozen_rows, development_ids)
    if sha256(canonical_csv).hexdigest() != seal["development_csv_sha256"]:
        raise ValueError("Hybrid development CSV hash does not match.")
    if _hybrid_protocol_hash(config) != seal["hybrid_protocol_sha256"]:
        raise ValueError("Hybrid development protocol hash does not match.")
    if _development_input_hash(session, development_ids) != seal[
        "development_input_sha256"
    ]:
        raise ValueError("Hybrid development input hash does not match.")
    rows = []
    result_hasher = sha256()

    for drawing_index, drawing_id in enumerate(development_ids, start=1):
        if progress_callback is not None:
            progress_callback(
                {
                    "drawing_id": drawing_id,
                    "drawing_index": drawing_index,
                    "drawing_total": len(development_ids),
                }
            )
        probabilities, _analyses = _load_development_inputs(session, drawing_id)
        packages = _build_hybrid_packages(probabilities, drawing_id, config)
        _validate_hybrid_package_set(packages, config, len(probabilities))
        packages_by_strategy = {package.strategy: package for package in packages}
        top_package = packages_by_strategy["top_probability"]
        top_frozen = frozen_rows[(drawing_id, "top_probability")]
        _verify_top_package_hash(top_package, top_frozen, drawing_id)

        result_string = _load_development_result(session, drawing_id)
        _update_result_hash(result_hasher, drawing_id, result_string)
        top_best_hits = best_coupon_hits(top_package.coupons, result_string)
        _validate_frozen_result_fields(top_frozen, top_best_hits)

        drawing = session.get(Drawing, drawing_id)
        if drawing is None:
            raise ValueError(f"Development drawing {drawing_id} was not found.")
        rows.extend(
            _build_hybrid_evaluation_rows(
                drawing_id=drawing_id,
                drawing_number=drawing.number,
                fold=folds[drawing_id],
                packages=packages,
                probabilities=probabilities,
                result_string=result_string,
                stake=config.stake,
            )
        )

    if result_hasher.hexdigest() != seal["development_result_sha256"]:
        raise ValueError("Hybrid development result hash does not match.")
    summary = summarize_hybrid_evaluation(rows)
    decision = decide_hybrid_experiment(summary)
    return HybridEvaluationResult(rows, summary, decision, manifest)


def write_hybrid_evaluation_reports(
    result: HybridEvaluationResult,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    csv_path, markdown_path = hybrid_evaluation_report_paths(
        result.manifest,
        report_dir,
    )
    output_dir = csv_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    config = _config_from_manifest(result.manifest)
    stem = csv_path.stem
    temporary_paths: list[Path] = []
    backup_paths: dict[Path, Path | None] = {}
    publication_started = False

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            delete=False,
            dir=output_dir,
            prefix=f".{stem}.",
            suffix=".csv.tmp",
        ) as csv_output:
            csv_temp_path = Path(csv_output.name)
            temporary_paths.append(csv_temp_path)
            writer = csv.DictWriter(
                csv_output,
                fieldnames=list(HybridEvaluationRow.__dataclass_fields__),
            )
            writer.writeheader()
            writer.writerows(
                asdict(row) for row in _ordered_hybrid_evaluation_rows(result)
            )

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=output_dir,
            prefix=f".{stem}.",
            suffix=".md.tmp",
        ) as markdown_output:
            markdown_temp_path = Path(markdown_output.name)
            temporary_paths.append(markdown_temp_path)
            markdown_output.write(_render_hybrid_markdown(result, config))

        for final_path in (csv_path, markdown_path):
            if not final_path.exists():
                backup_paths[final_path] = None
                continue
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=output_dir,
                prefix=f".{stem}.",
                suffix=f"{final_path.suffix}.bak.tmp",
            ) as backup_output:
                backup_path = Path(backup_output.name)
            temporary_paths.append(backup_path)
            shutil.copy2(final_path, backup_path)
            backup_paths[final_path] = backup_path

        publication_started = True
        csv_temp_path.replace(csv_path)
        temporary_paths.remove(csv_temp_path)
        markdown_temp_path.replace(markdown_path)
        temporary_paths.remove(markdown_temp_path)
    except Exception:
        if publication_started:
            for final_path in (csv_path, markdown_path):
                backup_path = backup_paths[final_path]
                if backup_path is None:
                    final_path.unlink(missing_ok=True)
                else:
                    os.replace(backup_path, final_path)
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)
        raise

    for temporary_path in temporary_paths:
        temporary_path.unlink(missing_ok=True)

    return csv_path, markdown_path


def hybrid_evaluation_report_paths(
    manifest: dict[str, object],
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    config = _config_from_manifest(manifest)
    last = int(manifest["last"])
    stem = f"hybrid_evaluation_development_last_{last}_bank_{config.bank}"
    output_dir = Path(report_dir)
    return output_dir / f"{stem}.csv", output_dir / f"{stem}.md"


def _ordered_hybrid_evaluation_rows(
    result: HybridEvaluationResult,
) -> list[HybridEvaluationRow]:
    drawing_order = {
        drawing_id: index
        for index, drawing_id in enumerate(development_drawing_ids(result.manifest))
    }
    strategy_order = {
        strategy: index for index, strategy in enumerate(HYBRID_STRATEGY_ORDER)
    }
    try:
        return sorted(
            result.rows,
            key=lambda row: (
                drawing_order[row.drawing_id],
                strategy_order[row.strategy],
            ),
        )
    except KeyError as error:
        raise ValueError(
            "Hybrid evaluation rows do not match the frozen manifest."
        ) from error


def _render_hybrid_markdown(
    result: HybridEvaluationResult,
    config: StrategyConfig,
) -> str:
    summary = result.summary
    strategies = summary["strategies"]
    ordered_rows = _ordered_hybrid_evaluation_rows(result)
    rows_by_strategy = {
        strategy: [row for row in ordered_rows if row.strategy == strategy]
        for strategy in HYBRID_STRATEGY_ORDER
    }
    top_total = strategies["top_probability"]["total"]
    failure_count = summary["failure_count"]
    lines = [
        "# Hybrid Development Evaluation",
        "",
        "## Configuration",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| manifest last | {_format_hybrid_report_value(result.manifest['last'])} |",
        (
            "| manifest holdout size | "
            f"{_format_hybrid_report_value(result.manifest['holdout_size'])} |"
        ),
        (
            "| Development drawings | "
            f"{_format_hybrid_report_value(summary['drawing_count'])} |"
        ),
    ]
    lines.extend(
        f"| {field_name} | {_format_hybrid_report_value(value)} |"
        for field_name, value in asdict(config).items()
    )
    lines.extend(
        [
            "",
            f"Development drawings: {summary['drawing_count']}",
            "",
            "## Total Strategy Metrics",
            "",
            "| Strategy | 13+ | 14+ | 15 | Average best hits |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        _hybrid_metrics_table_rows(strategies, "total")
    )

    for fold in range(1, HYBRID_FOLD_COUNT + 1):
        lines.extend(
            [
                "",
                f"## Fold {fold} Metrics",
                "",
                "| Strategy | 13+ | 14+ | 15 | Average best hits |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(_hybrid_metrics_table_rows(strategies, "folds", fold))

    lines.extend(
        [
            "",
            "## Structural Metrics",
            "",
            (
                "| Strategy | Average package size | Average package cost | "
                "Average estimated coverage | Mean log probability | "
                "Mean pairwise Hamming distance | Top intersection | Top Jaccard | "
                "Average runtime seconds | Timeouts |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for strategy in HYBRID_STRATEGY_ORDER:
        strategy_rows = rows_by_strategy[strategy]
        lines.append(
            "| {strategy} | {package_size} | {package_cost} | {coverage} | "
            "{log_probability} | {hamming} | {intersection} | {jaccard} | "
            "{runtime} | {timeouts} |".format(
                strategy=strategy,
                package_size=_format_hybrid_report_value(
                    mean(row.package_size for row in strategy_rows)
                ),
                package_cost=_format_hybrid_report_value(
                    mean(row.package_cost for row in strategy_rows)
                ),
                coverage=_format_hybrid_report_value(
                    mean(row.estimated_coverage for row in strategy_rows)
                ),
                log_probability=_format_hybrid_report_value(
                    mean(row.mean_log_probability for row in strategy_rows)
                ),
                hamming=_format_hybrid_report_value(
                    mean(row.mean_pairwise_hamming for row in strategy_rows)
                ),
                intersection=_format_hybrid_report_value(
                    mean(row.top_intersection_size for row in strategy_rows)
                ),
                jaccard=_format_hybrid_report_value(
                    mean(row.top_jaccard for row in strategy_rows)
                ),
                runtime=_format_hybrid_report_value(
                    mean(row.runtime_seconds for row in strategy_rows)
                ),
                timeouts=_format_hybrid_report_value(
                    sum(row.timed_out for row in strategy_rows)
                ),
            )
        )

    lines.extend(
        [
            "",
            "## Failure Counts",
            "",
            f"Operational failures: {failure_count}",
            "",
            "## GO Predicate Evaluation",
            "",
            (
                "| Core fraction | Additional 13+ hits (>= 2) | "
                "Non-losing folds (>= 4) | Average best-hit delta (>= 0) | "
                "Operational failures (= 0) | All predicates |"
            ),
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for fraction in HYBRID_CORE_FRACTIONS:
        strategy = strategies[f"hybrid_{fraction:.2f}"]
        total = strategy["total"]
        additional_hits = total["hit_13"] - top_total["hit_13"]
        non_losing_folds = strategy["non_losing_folds"]
        best_hit_delta = total["average_best_hits"] - top_total["average_best_hits"]
        predicates = (
            additional_hits >= HYBRID_MIN_ADDITIONAL_HIT_13,
            non_losing_folds >= HYBRID_MIN_NON_LOSING_FOLDS,
            best_hit_delta >= 0,
            failure_count == 0,
        )
        additional_status = _go_predicate_status(predicates[0])
        non_losing_status = _go_predicate_status(predicates[1])
        best_hits_status = _go_predicate_status(predicates[2])
        failure_status = _go_predicate_status(predicates[3])
        all_status = _go_predicate_status(all(predicates))
        lines.append(
            f"| {fraction:.2f} | {additional_hits} ({additional_status}) | "
            f"{non_losing_folds} ({non_losing_status}) | "
            f"{_format_hybrid_report_value(best_hit_delta)} ({best_hits_status}) | "
            f"{failure_count} ({failure_status}) | {all_status} |"
        )

    selected_fraction = (
        "none"
        if result.decision.selected_core_fraction is None
        else f"{result.decision.selected_core_fraction:.2f}"
    )
    passing_fractions = (
        "none"
        if not result.decision.passing_core_fractions
        else ", ".join(
            f"{fraction:.2f}" for fraction in result.decision.passing_core_fractions
        )
    )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Decision: {result.decision.status}",
            f"Selected core fraction: {selected_fraction}",
            f"Passing core fractions: {passing_fractions}",
            f"Reason: {result.decision.reason}",
            "",
            (
                "Warning: This development-only result is not independent "
                "evidence and provides no profitability evidence."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _hybrid_metrics_table_rows(
    strategies: dict[str, object],
    scope: str,
    fold: int | None = None,
) -> list[str]:
    rows = []
    for strategy in HYBRID_STRATEGY_ORDER:
        metrics = strategies[strategy][scope]
        if fold is not None:
            metrics = metrics[fold]
        rows.append(
            f"| {strategy} | {_format_hybrid_report_value(metrics['hit_13'])} | "
            f"{_format_hybrid_report_value(metrics['hit_14'])} | "
            f"{_format_hybrid_report_value(metrics['hit_15'])} | "
            f"{_format_hybrid_report_value(metrics['average_best_hits'])} |"
        )
    return rows


def _go_predicate_status(passed: bool) -> str:
    return "pass" if passed else "fail"


def _format_hybrid_report_value(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _canonical_development_csv(
    frozen_rows: dict[tuple[int, str], StrategyBacktestRow],
    development_ids: list[int],
) -> bytes:
    output = StringIO(newline="")
    fieldnames = list(StrategyBacktestRow.__dataclass_fields__)
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for drawing_id in development_ids:
        for strategy in STRATEGIES:
            writer.writerow(asdict(frozen_rows[(drawing_id, strategy)]))
    return output.getvalue().encode("utf-8")


def _hybrid_development_seal(
    manifest: dict[str, object],
    development_count: int,
) -> dict[str, object]:
    seal = manifest.get("hybrid_development_seal")
    required = {
        "schema_version",
        "development_drawing_count",
        "development_csv_sha256",
        "development_input_sha256",
        "development_result_sha256",
        "hybrid_protocol_sha256",
        "hybrid_code_version",
    }
    if not isinstance(seal, dict) or set(seal) != required:
        raise ValueError("A complete hybrid development seal is required.")
    if seal["schema_version"] != 1:
        raise ValueError("Unsupported hybrid development seal version.")
    if seal["development_drawing_count"] != development_count:
        raise ValueError("Hybrid development seal drawing count does not match.")
    hash_fields = required - {
        "schema_version",
        "development_drawing_count",
        "hybrid_code_version",
    }
    for field_name in hash_fields:
        value = seal[field_name]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("A complete hybrid development seal is required.")
    if not isinstance(seal["hybrid_code_version"], str) or not seal[
        "hybrid_code_version"
    ]:
        raise ValueError("A complete hybrid development seal is required.")
    return seal


def _hybrid_protocol_hash(config: StrategyConfig) -> str:
    payload = {
        "config": asdict(config),
        "core_fractions": list(HYBRID_CORE_FRACTIONS),
        "fold_count": HYBRID_FOLD_COUNT,
        "strategy_order": list(HYBRID_STRATEGY_ORDER),
        "go_criteria": {
            "minimum_additional_hit_13": HYBRID_MIN_ADDITIONAL_HIT_13,
            "minimum_non_losing_folds": HYBRID_MIN_NON_LOSING_FOLDS,
            "require_average_best_hits_not_lower": True,
            "require_zero_operational_failures": True,
        },
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _development_input_hash(session: Session, development_ids: list[int]) -> str:
    payload = []
    for drawing_id in development_ids:
        drawing = session.execute(
            select(Drawing.id, Drawing.number).where(Drawing.id == drawing_id)
        ).one_or_none()
        if drawing is None:
            raise ValueError(f"Development drawing {drawing_id} was not found.")
        events = session.execute(
            select(Event.id, Event.event_order)
            .where(Event.drawing_id == drawing_id)
            .order_by(Event.event_order)
        ).all()
        quotes = session.execute(
            select(
                Quote.event_order,
                Quote.pool_win_1,
                Quote.pool_draw,
                Quote.pool_win_2,
                Quote.bk_win_1,
                Quote.bk_draw,
                Quote.bk_win_2,
            )
            .where(Quote.drawing_id == drawing_id)
            .order_by(Quote.event_order)
        ).all()
        event_orders = [event.event_order for event in events]
        quote_orders = [quote.event_order for quote in quotes]
        expected_orders = list(range(15))
        if event_orders != expected_orders or quote_orders != expected_orders:
            raise ValueError(f"Development drawing {drawing_id} is not eligible.")
        payload.append(
            {
                "drawing_id": drawing.id,
                "drawing_number": drawing.number,
                "events": [
                    {
                        "event_id": event.id,
                        "event_order": event.event_order,
                        "pool": [
                            quote.pool_win_1,
                            quote.pool_draw,
                            quote.pool_win_2,
                        ],
                        "bk": [
                            quote.bk_win_1,
                            quote.bk_draw,
                            quote.bk_win_2,
                        ],
                    }
                    for event, quote in zip(events, quotes, strict=True)
                ],
            }
        )
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _update_result_hash(hasher, drawing_id: int, result_string: str) -> None:
    hasher.update(
        _canonical_json_bytes(
            {"drawing_id": drawing_id, "result_string": result_string}
        )
    )
    hasher.update(b"\n")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_atomic_artifact_pair(
    artifacts: tuple[tuple[Path, bytes], tuple[Path, bytes]],
) -> None:
    temporary_paths: list[Path] = []
    rendered: list[tuple[Path, Path]] = []
    backups: dict[Path, Path | None] = {}
    publication_started = False

    try:
        for final_path, content in artifacts:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=final_path.parent,
                prefix=f".{final_path.name}.",
                suffix=".tmp",
            ) as output:
                output.write(content)
                temporary_path = Path(output.name)
            temporary_paths.append(temporary_path)
            rendered.append((temporary_path, final_path))

        for _, final_path in rendered:
            if not final_path.exists():
                backups[final_path] = None
                continue
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=final_path.parent,
                prefix=f".{final_path.name}.",
                suffix=".bak.tmp",
            ) as backup_output:
                backup_path = Path(backup_output.name)
            temporary_paths.append(backup_path)
            shutil.copy2(final_path, backup_path)
            backups[final_path] = backup_path

        publication_started = True
        for temporary_path, final_path in rendered:
            temporary_path.replace(final_path)
            temporary_paths.remove(temporary_path)
    except Exception:
        if publication_started:
            for _, final_path in rendered:
                backup_path = backups.get(final_path)
                if backup_path is None:
                    final_path.unlink(missing_ok=True)
                    continue
                backup_path.replace(final_path)
                if backup_path in temporary_paths:
                    temporary_paths.remove(backup_path)
        raise
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)


def _validate_hybrid_protocol(config: StrategyConfig) -> None:
    if (
        config.bank,
        config.stake,
        config.category,
        config.max_coupons,
    ) != (
        HYBRID_BANK,
        HYBRID_STAKE,
        HYBRID_CATEGORY,
        HYBRID_MAX_COUPONS,
    ):
        raise ValueError(
            "Hybrid evaluation requires the fixed protocol: bank=5000, "
            "stake=30, category=13."
        )
    _validate_strategy_config(config)


def _build_hybrid_packages(
    probabilities: ProbabilityMatrix,
    drawing_id: int,
    config: StrategyConfig,
    time_func=None,
) -> list[StrategyPackage]:
    if time_func is None:
        time_func = time.perf_counter
    started = time_func()
    deadline = (
        None
        if config.timeout_per_drawing is None
        else started + config.timeout_per_drawing
    )

    top_started = time_func()
    top_coupons = top_probability_coupons(
        probabilities,
        limit=config.max_coupons,
    )
    _ensure_hybrid_deadline(deadline, time_func)
    top_package = StrategyPackage(
        strategy="top_probability",
        coupons=list(top_coupons),
        estimated_coverage=0.0,
        candidate_count=len(top_coupons),
        runtime_seconds=time_func() - top_started,
        timed_out=False,
    )
    _validate_hybrid_package(top_package, config, len(probabilities))

    candidate_seed = config.seed ^ drawing_id ^ 0xC3C3
    candidates = generate_candidate_coupons(
        probabilities,
        max_coupons=config.max_coupons,
        top_count=config.top_count,
        sample_count=config.candidate_samples,
        mutation_limit=config.mutation_limit,
        seed=candidate_seed,
    )
    _ensure_hybrid_deadline(deadline, time_func)
    optimization_seed = config.seed ^ drawing_id ^ 0xA5A5
    optimization_scenarios = sample_scenarios(
        probabilities,
        count=config.optimization_samples,
        seed=optimization_seed,
    )
    _ensure_hybrid_deadline(deadline, time_func)
    validation_seed = config.seed ^ drawing_id ^ 0x5A5A
    validation_scenarios = sample_scenarios(
        probabilities,
        count=config.validation_samples,
        seed=validation_seed,
    )
    _ensure_hybrid_deadline(deadline, time_func)
    top_package = StrategyPackage(
        strategy=top_package.strategy,
        coupons=top_package.coupons,
        estimated_coverage=estimate_package_coverage(
            top_coupons,
            validation_scenarios,
            config.category,
        ),
        candidate_count=top_package.candidate_count,
        runtime_seconds=top_package.runtime_seconds,
        timed_out=top_package.timed_out,
    )
    _ensure_hybrid_deadline(deadline, time_func)

    packages = [top_package]
    for core_fraction in HYBRID_CORE_FRACTIONS:
        _ensure_hybrid_deadline(deadline, time_func)
        selection_started = time_func()
        selected = select_hybrid_package(
            candidates=candidates,
            scenarios=optimization_scenarios,
            probabilities=probabilities,
            category=config.category,
            max_coupons=config.max_coupons,
            top_coupons=top_coupons,
            core_fraction=core_fraction,
            deadline=deadline,
            time_func=time_func,
        )
        _ensure_hybrid_deadline(deadline, time_func)
        hybrid_package = StrategyPackage(
            strategy=f"hybrid_{core_fraction:.2f}",
            coupons=list(selected.selected_coupons),
            estimated_coverage=0.0,
            candidate_count=len(candidates),
            runtime_seconds=time_func() - selection_started,
            timed_out=selected.timed_out,
        )
        _validate_hybrid_package(hybrid_package, config, len(probabilities))
        packages.append(
            StrategyPackage(
                strategy=hybrid_package.strategy,
                coupons=hybrid_package.coupons,
                estimated_coverage=estimate_package_coverage(
                    hybrid_package.coupons,
                    validation_scenarios,
                    config.category,
                ),
                candidate_count=hybrid_package.candidate_count,
                runtime_seconds=hybrid_package.runtime_seconds,
                timed_out=hybrid_package.timed_out,
            )
        )
        _ensure_hybrid_deadline(deadline, time_func)
    return packages


def _ensure_hybrid_deadline(deadline, time_func) -> None:
    if deadline is not None and time_func() >= deadline:
        raise ValueError("Hybrid package generation exceeded its deadline.")


def _validate_hybrid_package_set(
    packages: list[StrategyPackage],
    config: StrategyConfig,
    coupon_length: int,
) -> None:
    expected_strategies = (
        "top_probability",
        *(f"hybrid_{fraction:.2f}" for fraction in HYBRID_CORE_FRACTIONS),
    )
    if len(packages) != len(expected_strategies) or {
        package.strategy for package in packages
    } != set(expected_strategies):
        raise ValueError("Hybrid package strategy identities are invalid.")
    for package in packages:
        _validate_hybrid_package(package, config, coupon_length)


def _validate_hybrid_package(
    package: StrategyPackage,
    config: StrategyConfig,
    coupon_length: int,
) -> None:
    package_cost = len(package.coupons) * config.stake
    if package_cost > config.bank:
        raise ValueError("Hybrid package exceeds the configured budget.")
    if len(package.coupons) != config.max_coupons:
        raise ValueError(
            f"Hybrid package must contain exactly {config.max_coupons} coupons."
        )
    if len(set(package.coupons)) != len(package.coupons):
        raise ValueError("Hybrid package must contain unique coupons.")
    if any(len(coupon) != coupon_length for coupon in package.coupons):
        raise ValueError("Hybrid package must contain valid coupon shapes.")
    if any(set(coupon) - set(OUTCOMES) for coupon in package.coupons):
        raise ValueError("Hybrid package must contain valid coupon outcomes.")
    if package.timed_out:
        raise ValueError("Hybrid package generation timed out.")


def _verify_top_package_hash(
    top_package: StrategyPackage,
    frozen_row,
    drawing_id: int,
) -> None:
    actual_hash = sha256(",".join(top_package.coupons).encode("utf-8")).hexdigest()
    if actual_hash != frozen_row.package_hash:
        raise ValueError(f"Development top package hash mismatch for {drawing_id}.")


def _build_hybrid_evaluation_rows(
    drawing_id: int,
    drawing_number: int | None,
    fold: int,
    packages: list[StrategyPackage],
    probabilities: ProbabilityMatrix,
    result_string: str,
    stake: int,
) -> list[HybridEvaluationRow]:
    core_fractions = {
        "top_probability": None,
        **{
            f"hybrid_{fraction:.2f}": fraction
            for fraction in HYBRID_CORE_FRACTIONS
        },
    }
    packages_by_strategy = {package.strategy: package for package in packages}
    top_coupons = packages_by_strategy["top_probability"].coupons
    rows = []
    for package in packages:
        best_hits = best_coupon_hits(package.coupons, result_string)
        structure = package_structure_metrics(package.coupons, probabilities)
        overlap = package_overlap_metrics(
            top_coupons,
            package.coupons,
            probabilities,
        )
        rows.append(
            HybridEvaluationRow(
                drawing_id=drawing_id,
                drawing_number=drawing_number,
                fold=fold,
                strategy=package.strategy,
                core_fraction=core_fractions[package.strategy],
                best_hits=best_hits,
                hit_13=best_hits >= 13,
                hit_14=best_hits >= 14,
                hit_15=best_hits == 15,
                package_size=len(package.coupons),
                package_cost=len(package.coupons) * stake,
                estimated_coverage=package.estimated_coverage,
                candidate_count=package.candidate_count,
                runtime_seconds=package.runtime_seconds,
                timed_out=package.timed_out,
                mean_log_probability=structure.mean_log_probability,
                mean_pairwise_hamming=structure.mean_pairwise_hamming,
                top_intersection_size=overlap.intersection_size,
                top_jaccard=overlap.jaccard,
            )
        )
    return rows


def assign_chronological_folds(drawing_ids: list[int]) -> dict[int, int]:
    if len(drawing_ids) % HYBRID_FOLD_COUNT:
        raise ValueError(
            "Development drawings must form five equal chronological folds."
        )
    fold_size = len(drawing_ids) // HYBRID_FOLD_COUNT
    if fold_size == 0:
        raise ValueError(
            "Development drawings must form five equal chronological folds."
        )
    return {
        drawing_id: index // fold_size + 1
        for index, drawing_id in enumerate(drawing_ids)
    }


def summarize_hybrid_evaluation(rows: list[HybridEvaluationRow]) -> dict[str, object]:
    strategy_names = (
        "top_probability",
        *(f"hybrid_{fraction:.2f}" for fraction in HYBRID_CORE_FRACTIONS),
    )
    rows_by_strategy = {strategy: [] for strategy in strategy_names}
    for row in rows:
        if row.strategy not in rows_by_strategy:
            raise ValueError(f"Unsupported hybrid evaluation strategy: {row.strategy}")
        rows_by_strategy[row.strategy].append(row)

    _validate_hybrid_evaluation_rows(rows_by_strategy)

    strategies = {
        strategy: _summarize_strategy(strategy_rows)
        for strategy, strategy_rows in rows_by_strategy.items()
    }
    top_folds = strategies["top_probability"]["folds"]
    for fraction in HYBRID_CORE_FRACTIONS:
        strategy = strategies[f"hybrid_{fraction:.2f}"]
        folds = strategy["folds"]
        strategy["strictly_winning_folds"] = sum(
            folds[fold]["hit_13"] > top_folds[fold]["hit_13"]
            for fold in range(1, HYBRID_FOLD_COUNT + 1)
        )
        strategy["non_losing_folds"] = sum(
            folds[fold]["hit_13"] >= top_folds[fold]["hit_13"]
            for fold in range(1, HYBRID_FOLD_COUNT + 1)
        )

    return {
        "drawing_count": len({row.drawing_id for row in rows}),
        "failure_count": sum(row.timed_out for row in rows),
        "strategies": strategies,
    }


def _validate_hybrid_evaluation_rows(
    rows_by_strategy: dict[str, list[HybridEvaluationRow]],
) -> None:
    expected_fractions = {
        "top_probability": None,
        **{
            f"hybrid_{fraction:.2f}": fraction
            for fraction in HYBRID_CORE_FRACTIONS
        },
    }
    seen_pairs = set()
    for strategy, strategy_rows in rows_by_strategy.items():
        expected_fraction = expected_fractions[strategy]
        for row in strategy_rows:
            if row.fold not in range(1, HYBRID_FOLD_COUNT + 1):
                raise ValueError("Hybrid evaluation fold must be in 1..5.")
            if expected_fraction is None:
                if row.core_fraction is not None:
                    raise ValueError(
                        "top_probability rows must have core_fraction=None."
                    )
            elif row.core_fraction != expected_fraction:
                raise ValueError(
                    f"{strategy} rows must have core_fraction={expected_fraction:.2f}."
                )
            pair = (strategy, row.drawing_id)
            if pair in seen_pairs:
                raise ValueError(
                    "Hybrid evaluation requires exactly one row per "
                    "(strategy, drawing_id)."
                )
            seen_pairs.add(pair)

    top_rows = rows_by_strategy["top_probability"]
    top_drawing_ids = {row.drawing_id for row in top_rows}
    for strategy_rows in rows_by_strategy.values():
        if {row.drawing_id for row in strategy_rows} != top_drawing_ids:
            raise ValueError(
                "All hybrid evaluation strategies must have identical drawing ID sets."
            )

    expected_folds = assign_chronological_folds(
        [row.drawing_id for row in top_rows]
    )
    expected_fold_size = len(top_drawing_ids) // HYBRID_FOLD_COUNT
    top_fold_drawing_ids = {
        fold: {row.drawing_id for row in top_rows if row.fold == fold}
        for fold in range(1, HYBRID_FOLD_COUNT + 1)
    }
    for fold, drawing_ids in top_fold_drawing_ids.items():
        if not drawing_ids:
            raise ValueError(f"Hybrid evaluation fold {fold} must not be empty.")
    for drawing_ids in top_fold_drawing_ids.values():
        if len(drawing_ids) != expected_fold_size:
            raise ValueError("Hybrid evaluation folds must be equal-sized.")

    for _strategy, strategy_rows in rows_by_strategy.items():
        for fold in range(1, HYBRID_FOLD_COUNT + 1):
            drawing_ids = {
                row.drawing_id for row in strategy_rows if row.fold == fold
            }
            if drawing_ids != top_fold_drawing_ids[fold]:
                raise ValueError(
                    "Each fold must contain the same drawing IDs across all "
                    "hybrid evaluation strategies."
                )
        for row in strategy_rows:
            if row.fold != expected_folds[row.drawing_id]:
                raise ValueError(
                    "Hybrid evaluation rows must use the chronological fold "
                    "assignment."
                )


def decide_hybrid_experiment(summary: dict[str, object]) -> HybridDecision:
    strategies = summary["strategies"]
    top_strategy = strategies["top_probability"]
    top_total = top_strategy["total"]
    top_average_best_hits = top_total["average_best_hits"]
    failure_count = summary["failure_count"]

    passing_fractions = tuple(
        fraction
        for fraction in HYBRID_CORE_FRACTIONS
        if failure_count == 0
        and _passes_go_predicate(
            strategies[f"hybrid_{fraction:.2f}"],
            top_total["hit_13"],
            top_average_best_hits,
        )
    )
    if not passing_fractions:
        reason = (
            "Operational failures were recorded."
            if failure_count
            else "No hybrid core fraction met every GO predicate."
        )
        return HybridDecision(
            status="STOP",
            selected_core_fraction=None,
            passing_core_fractions=(),
            reason=reason,
        )

    selected_fraction = max(
        passing_fractions,
        key=lambda fraction: _decision_rank(
            strategies[f"hybrid_{fraction:.2f}"], fraction
        ),
    )
    return HybridDecision(
        status="GO",
        selected_core_fraction=selected_fraction,
        passing_core_fractions=passing_fractions,
        reason=(
            "Selected the highest-ranked hybrid core fraction under the approved "
            "GO criteria."
        ),
    )


def _summarize_strategy(rows: list[HybridEvaluationRow]) -> dict[str, object]:
    folds = {
        fold: _summarize_rows([row for row in rows if row.fold == fold])
        for fold in range(1, HYBRID_FOLD_COUNT + 1)
    }
    return {
        "total": _summarize_rows(rows),
        "folds": folds,
        "average_mean_log_probability": (
            mean(row.mean_log_probability for row in rows) if rows else None
        ),
    }


def _summarize_rows(rows: list[HybridEvaluationRow]) -> dict[str, int | float | None]:
    return {
        "hit_13": sum(row.hit_13 for row in rows),
        "hit_14": sum(row.hit_14 for row in rows),
        "hit_15": sum(row.hit_15 for row in rows),
        "average_best_hits": mean(row.best_hits for row in rows) if rows else None,
    }


def _passes_go_predicate(
    strategy: dict[str, object],
    top_total_13: int,
    top_average_best_hits: float,
) -> bool:
    total = strategy["total"]
    return (
        total["hit_13"] >= top_total_13 + HYBRID_MIN_ADDITIONAL_HIT_13
        and strategy["non_losing_folds"] >= HYBRID_MIN_NON_LOSING_FOLDS
        and total["average_best_hits"] >= top_average_best_hits
    )


def _decision_rank(strategy: dict[str, object], fraction: float) -> tuple[object, ...]:
    total = strategy["total"]
    return (
        total["hit_13"],
        strategy["strictly_winning_folds"],
        strategy["non_losing_folds"],
        total["average_best_hits"],
        strategy["average_mean_log_probability"],
        fraction,
    )
