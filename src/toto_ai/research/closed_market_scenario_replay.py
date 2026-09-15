"""Inactive finished-source scenarios, never historical forecasting evidence.

prepare reads original RAW once and excludes labels. generate reads ONLY the
sealed allowlisted DTO. score alone reads separate labels after output freeze.
Neither this module nor its artifacts are used by the operational scheduler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import signal
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.collector.lifecycle import RawArchive, RawArchiveRecord
from toto_ai.ev.drawing import effective_selection_budget, ev_input_from_payload
from toto_ai.ev.models import EVConfig, EVInput, EVSurface
from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.ev.runtime import RuntimeBudget, runtime_scope
from toto_ai.ev.ternary import compute_ev_components, materialize_ev_surface
from toto_ai.optimizer.robust_package import select_robust_package
from toto_ai.optimizer.strategy_historical_benchmark import score_coupon_package
from toto_ai.optimizer.uncertainty_package import (
    build_uncertainty_models,
    control_relative_exposure_constraints,
    select_uncertainty_package,
)
from toto_ai.research.native_quality_core import select_numeric_candidate
from toto_ai.research.raw_package_replay import (
    _canonical,
    _digest,
    _object,
    _sha,
    _timestamp,
    _write_exclusive,
)
from toto_ai.totobrief_time import parse_totobrief_timestamp

DOMAIN = "POST_EVENT_MARKET_SCENARIO_UNVERIFIED_ASOF"
FALSE_FLAGS = (
    "operator_compatible",
    "automatic_wagering",
    "fit_eligible",
    "release_eligible",
)
FLAGS = dict.fromkeys(FALSE_FLAGS, False)
QUOTE_KEYS = {f"{p}_{s}" for p in ("bk", "pool") for s in ("win_1", "draw", "win_2")}
MARKET_KEYS = {"id", "number", "pool_sum", "jackpot", "events"}
EVENT_KEYS = {"id", "order", "quotes"}
ARMS = ("quality-v2", "quality-v3", "robust-market-only")
OPTIONS = {
    "top_count": 2000,
    "candidate_sample_count": 4000,
    "mutation_limit": 2000,
    "selection_sample_count": 10000,
}
NORMALIZATION = (
    "native ev_input_from_payload: normalized BK + native pool/stake crowd smoothing"
)
SEED = "TOTOAI-RESUME-20260915-closed-market-scenario-v1"


def seal(d: dict) -> dict:
    return dict(d, sha256=_digest(d))


def checked(d: dict) -> dict:
    body = {k: v for k, v in d.items() if k != "sha256"}
    if d.get("sha256") != _digest(body):
        raise ValueError("semantic hash mismatch")
    return d


def file_hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _config() -> EVConfig:
    return EVConfig(
        bank=4980,
        stake=30,
        effective_budget=4980,
        mode="playable",
        package_safety_enabled=True,
        package_provenance_required=True,
    )


@dataclass(frozen=True)
class ScenarioInput:
    ev: EVInput
    config: EVConfig
    input_sha256: str
    seed: str


def validate_input(d: dict) -> ScenarioInput:
    checked(d)
    if set(d) != {
        "schema_version",
        "evidence_domain",
        "quote_available_at",
        "source_closed_at",
        "captured_at",
        "market",
        "bank",
        "stake",
        "config",
        "normalization",
        "seed_protocol",
        "sha256",
        *FALSE_FLAGS,
    }:
        raise ValueError("scenario input allowlist")
    if (
        d["schema_version"] != 1
        or d["evidence_domain"] != DOMAIN
        or d["quote_available_at"] is not None
        or any(d[k] is not False for k in FALSE_FLAGS)
        or d["bank"] != 4980
        or d["stake"] != 30
        or d["normalization"] != NORMALIZATION
        or d["seed_protocol"] != SEED
        or d["config"] != asdict(_config())
    ):
        raise ValueError("scenario domain/config cannot be promoted or changed")
    captured = _timestamp(d["captured_at"])
    if captured < _timestamp(d["source_closed_at"]):
        raise ValueError("finished-source capture cannot be backdated before closure")
    m = d["market"]
    if set(m) != MARKET_KEYS or len(m["events"]) != 15:
        raise ValueError("market allowlist/event count")
    if any(type(m[k]) is not int or m[k] <= 0 for k in ("id", "number")):
        raise ValueError("drawing identity")
    if [e.get("order") for e in m["events"]] != list(range(15)):
        raise ValueError("ordered events required; no implicit permutation")
    ids = [e.get("id") for e in m["events"]]
    if len(set(ids)) != 15 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("unique fixture identities required")
    for e in m["events"]:
        if set(e) != EVENT_KEYS or set(e["quotes"]) != QUOTE_KEYS:
            raise ValueError("event/quote allowlist")
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or v <= 0
            for v in e["quotes"].values()
        ):
            raise ValueError("finite positive complete probability triples required")
    ev = ev_input_from_payload(
        {"data": m},
        fetched_at=captured.isoformat(),
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    if (
        effective_selection_budget(requested_bank=4980, pool_sum=ev.pool_sum, stake=30)
        != 4980
    ):
        raise ValueError("pool cap does not support requested166/4980")
    return ScenarioInput(ev, _config(), d["sha256"], _digest([SEED, d["sha256"]]))


def extract(ref: dict) -> dict:
    """Only extraction sees RAW labels. None enter returned DTO or random seed."""
    p, mp = Path(ref["latest_raw_path"]), Path(ref["latest_metadata_path"])
    _object(p)
    meta = _object(mp, max_bytes=16384)
    if (
        file_hash(p) != _sha(ref["file_sha256"])
        or ref["db_payload_sha256"] != ref["file_sha256"]
    ):
        raise ValueError("raw hash mismatch")
    if (
        meta.get("drawing_id") != ref["id"]
        or meta.get("drawing_number") != ref["number"]
        or meta.get("captured_at") != ref["latest_capture"]
        or meta.get("payload_sha256") != ref["file_sha256"]
        or meta.get("source") != "totobrief-network"
        or meta.get("lifecycle_status") != "finished"
        or meta.get("source_endpoint") != f"/drawing-info/{ref['id']}"
    ):
        raise ValueError("RAW metadata/identity/capture mismatch")
    snap = _sha(meta["snapshot_sha256"])
    if p.name != snap + ".json" or mp != p.with_name(snap + ".meta.json"):
        raise ValueError("archive path identity mismatch")
    rec = RawArchiveRecord(
        **{
            k: meta[k]
            for k in (
                "snapshot_sha256",
                "payload_sha256",
                "metadata_sha256",
                "drawing_id",
                "drawing_number",
                "captured_at",
                "source",
                "source_endpoint",
                "lifecycle_status",
            )
        },
        payload_path=p,
        metadata_path=mp,
        created=False,
    )
    data = RawArchive(p.parent.parent).load(rec)["data"]
    if (
        data.get("id") != ref["id"]
        or data.get("number") != ref["number"]
        or data.get("name") != "baltbet-main"
        or data.get("status") != "finished"
    ):
        raise ValueError("finished payload identity mismatch")
    # Positive allowlist: no names, scores, results, status, norm or payments.
    market = {k: data.get(k) for k in MARKET_KEYS - {"events"}}
    market["events"] = [
        {
            "id": e.get("id"),
            "order": e.get("order"),
            "quotes": {k: e.get("quotes", {}).get(k) for k in QUOTE_KEYS},
        }
        for e in data["events"]
    ]
    doc = seal(
        {
            "schema_version": 1,
            "evidence_domain": DOMAIN,
            "quote_available_at": None,
            "captured_at": meta["captured_at"],
            "source_closed_at": parse_totobrief_timestamp(
                data.get("ended_at"), community="baltbet-main", field_name="ended_at"
            ).isoformat(),
            "market": market,
            "bank": 4980,
            "stake": 30,
            "config": asdict(_config()),
            "normalization": NORMALIZATION,
            "seed_protocol": SEED,
            **FLAGS,
        }
    )
    validate_input(doc)
    return doc


@dataclass(frozen=True)
class BoundSurface:
    surface: EVSurface
    input_sha256: str
    config_sha256: str
    surface_sha256: str


def _surface_hash(s: EVSurface) -> str:
    h = hashlib.sha256(
        _canonical(
            [
                s.event_count,
                s.probability_mass,
                s.crowd_mass,
                s.minimum_denominator,
                str(s.gross_ev.dtype),
                s.gross_ev.shape,
            ]
        )
    )
    h.update(memoryview(s.gross_ev).cast("B"))
    return h.hexdigest()


def build_surface(i: ScenarioInput) -> BoundSurface:
    s = materialize_ev_surface(
        compute_ev_components(i.ev), i.ev.possible_winnings, i.ev.jackpot
    )
    return BoundSurface(s, i.input_sha256, _digest(asdict(i.config)), _surface_hash(s))


def validate_surface(b: BoundSurface, i: ScenarioInput) -> None:
    if (
        b.input_sha256 != i.input_sha256
        or b.config_sha256 != _digest(asdict(i.config))
        or b.surface_sha256 != _surface_hash(b.surface)
        or b.surface.event_count != 15
        or b.surface.gross_ev.size != 3**15
    ):
        raise ValueError("RAW/config/surface binding mismatch")


def code_hashes() -> dict:
    root = Path(__file__).resolve().parents[1]
    names = (
        "research/closed_market_scenario_replay.py",
        "research/native_quality_core.py",
        "ev/ternary.py",
        "ev/drawing.py",
        "ev/models.py",
        "ev/package.py",
        "ev/package_quality.py",
        "optimizer/uncertainty_package.py",
        "optimizer/robust_package.py",
    )
    return {n: file_hash(root / n) for n in names}


def prepare(context: Path, output: Path) -> Path:
    rows = _object(context)["rows"]
    if [r["number"] for r in rows] != list(range(4999, 5007)):
        raise ValueError("exact eight-drawing roster required")
    docs = [extract(r) for r in rows]  # Validate all before any output is written.
    output.mkdir(parents=True, exist_ok=False)
    refs = []
    for r, doc in zip(rows, docs, strict=True):
        name = f"input-{r['number']}.json"
        digest = _write_exclusive(output / name, doc)
        refs.append(
            {
                "drawing": r["number"],
                "drawing_id": r["id"],
                "input": name,
                "input_file_sha256": digest,
                "input_sha256": doc["sha256"],
                "raw": r["latest_raw_path"],
                "raw_sha256": r["file_sha256"],
                "metadata": r["latest_metadata_path"],
                "metadata_file_sha256": file_hash(Path(r["latest_metadata_path"])),
            }
        )
    manifest = seal(
        {
            "schema_version": 1,
            "evidence_domain": DOMAIN,
            **FLAGS,
            "roster": refs,
            "code": code_hashes(),
            "config": asdict(_config()),
            "options": OPTIONS,
            "seed_protocol": SEED,
            "context_file_sha256": file_hash(context),
        }
    )
    _write_exclusive(output / "manifest.json", manifest)
    return output / "manifest.json"


def load_manifest(path: Path, *, for_scoring: bool = False) -> dict:
    m = checked(_object(path))
    current = code_hashes()
    # Archived generation stays bound to its ORIGINAL code and frozen receipt.
    # A reporting-only revision must not force regeneration or restamp archives.
    allowed = {"research/closed_market_scenario_replay.py"} if for_scoring else set()
    code_ok = set(m["code"]) == set(current) and all(
        _sha(m["code"][name]) == current[name] or name in allowed for name in current
    )
    if (
        m["evidence_domain"] != DOMAIN
        or not code_ok
        or m["config"] != asdict(_config())
        or m["options"] != OPTIONS
        or m["seed_protocol"] != SEED
        or any(m[k] is not False for k in FALSE_FLAGS)
        or [r["drawing"] for r in m["roster"]] != list(range(4999, 5007))
    ):
        raise ValueError("frozen manifest/code/protocol mismatch")
    return m


def _load_input(root: Path, ref: dict) -> tuple[dict, ScenarioInput]:
    if ref["input"] != f"input-{ref['drawing']}.json":
        raise ValueError("input filename binding mismatch")
    p = root / ref["input"]
    d = _object(p)
    if file_hash(p) != ref["input_file_sha256"] or d["sha256"] != ref["input_sha256"]:
        raise ValueError("input file binding mismatch")
    i = validate_input(d)
    if i.ev.drawing_number != ref["drawing"] or i.ev.drawing_id != ref["drawing_id"]:
        raise ValueError("manifest fixture identity mismatch")
    return d, i


def generate(manifest_path: Path, drawing: int, max_seconds: int = 600) -> dict:
    """No external surface, RAW path or label loader is accepted by the generator."""
    if not 1 <= max_seconds <= 600:
        raise ValueError("per-draw wall budget must be1..600seconds")
    m = load_manifest(manifest_path)
    ref = next(r for r in m["roster"] if r["drawing"] == drawing)
    doc, i = _load_input(manifest_path.parent, ref)
    out = manifest_path.parent / f"drawing-{drawing}"
    if out.exists():
        frozen, _ = verify_frozen(out)
        if (
            frozen["input_sha256"] != i.input_sha256
            or frozen["manifest_sha256"] != m["sha256"]
        ):
            raise ValueError("resume binding mismatch")
        return frozen  # Never regenerate an already recorded attempt.
    out.mkdir()
    _write_exclusive(out / "input.json", doc)
    start, cpu = time.perf_counter(), time.process_time()
    deadline = start + max_seconds
    packages, phase = {}, "surface"
    stop = threading.Event()

    def note(**detail):
        event = {
            "drawing": drawing,
            "phase": phase,
            "wall_seconds": time.perf_counter() - start,
            "cpu_seconds": time.process_time() - cpu,
            "pid": __import__("os").getpid(),
            **detail,
        }
        print(json.dumps(event), flush=True)
        with (out / "progress.jsonl").open("a") as stream:
            stream.write(json.dumps(event) + "\n")

    def heartbeat():
        while not stop.wait(30):
            note(status="RUNNING")

    def timeout_handler(signum, frame):
        raise TimeoutError("scenario hard wall deadline")

    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, max_seconds)
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    status, error = "COMPLETE_SCENARIO", None
    try:
        with runtime_scope(
            RuntimeBudget(deadline=deadline, progress=lambda e: note(native=e))
        ):
            note(status="START")
            bound = build_surface(i)
            validate_surface(bound, i)
            _write_exclusive(
                out / "surface-binding.json",
                {
                    "input_sha256": i.input_sha256,
                    "config_sha256": bound.config_sha256,
                    "surface_sha256": bound.surface_sha256,
                    "seed": i.seed,
                    "normalization": NORMALIZATION,
                    **FLAGS,
                },
            )

            def save_arm(name, coupons, native_info):
                values = tuple(coupons)
                if (
                    len(values) != 166
                    or len(set(values)) != 166
                    or any(len(c) != 15 or set(c) - set("1X2") for c in values)
                ):
                    raise ValueError(
                        f"{name}: incomplete/nonunique166 package; no padding"
                    )
                record = {
                    "evidence_domain": DOMAIN,
                    **FLAGS,
                    "input_sha256": i.input_sha256,
                    "bank": 4980,
                    "stake": 30,
                    "arm": name,
                    "coupons": values,
                    "native": native_info,
                    "equivalence": "NATIVE_HELPERS_CASE_SPECIFIC_PARITY_ONLY",
                }
                packages[name] = _write_exclusive(out / (name + ".json"), record)
                note(status="ARM_FROZEN", arm=name, coupons=len(values))

            phase = "quality-v2"
            control = select_numeric_candidate(
                bound.surface,
                config=i.config,
                probabilities=i.ev.true_probabilities,
                seed_material=i.seed,
            )
            save_arm(phase, control.coupons, asdict(control))
            del bound
            constraints = control_relative_exposure_constraints(
                i.ev.true_probabilities,
                control_coupons=control.coupons,
                package_size=166,
                floor_scale=i.config.package_exposure_floor_scale,
                floor_exponent=i.config.package_exposure_floor_exponent,
                near_fixed_share=i.config.package_near_fixed_share,
            )
            phase = "quality-v3"
            v3 = select_uncertainty_package(
                bk_probabilities=i.ev.true_probabilities,
                category=13,
                max_coupons=166,
                anchor_coupons=control.coupons,
                seed_material=i.seed,
                exposure_constraints=constraints,
                fallback_coupons=control.coupons,
                deadline=deadline,
                **OPTIONS,
            )
            if v3.timed_out:
                raise TimeoutError("quality-v3 native timed_out")
            save_arm(phase, v3.selected_coupons, asdict(v3))
            phase = "robust-market-only"
            robust = select_robust_package(
                candidates=tuple(
                    dict.fromkeys((*control.coupons, *v3.selected_coupons))
                ),
                probability_models=build_uncertainty_models(i.ev.true_probabilities),
                category=13,
                max_coupons=166,
                sample_count=10000,
                seed_material=i.seed,
                exposure_constraints=constraints,
                fallback_coupons=control.coupons,
                deadline=deadline,
            )
            if robust.timed_out:
                raise TimeoutError("robust native timed_out")
            save_arm(phase, robust.selected_coupons, asdict(robust))
    except (ValueError, TimeoutError) as exc:
        status, error = "PARTIAL_SCENARIO", f"{type(exc).__name__}: {exc}"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        stop.set()
        thread.join(timeout=2)
    frozen = seal(
        {
            "status": status,
            "evidence_domain": DOMAIN,
            **FLAGS,
            "drawing": drawing,
            "input_sha256": i.input_sha256,
            "input_file_sha256": file_hash(out / "input.json"),
            "manifest_sha256": m["sha256"],
            "packages": packages,
            "last_phase": phase,
            "error": error,
            "wall_seconds": time.perf_counter() - start,
            "cpu_seconds": time.process_time() - cpu,
            "maxrss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "frozen_before_labels": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_exclusive(out / "frozen.json", frozen)
    verify_frozen(out)
    note(status=status, error=error)
    return frozen


def verify_frozen(directory: Path) -> tuple[dict, dict]:
    if not (directory / "frozen.json").is_file():
        raise ValueError("unfrozen generation; labels must not be loaded")
    f = checked(_object(directory / "frozen.json"))
    if (
        f.get("frozen_before_labels") is not True
        or f["evidence_domain"] != DOMAIN
        or any(f[k] is not False for k in FALSE_FLAGS)
    ):
        raise ValueError("invalid generation authority/freeze")
    doc = _object(directory / "input.json")
    i = validate_input(doc)
    if (
        file_hash(directory / "input.json") != f["input_file_sha256"]
        or i.input_sha256 != f["input_sha256"]
        or i.ev.drawing_number != f["drawing"]
        or set(f["packages"]) - set(ARMS)
    ):
        raise ValueError("frozen input/package roster mismatch")
    values = {}
    for arm, digest in f["packages"].items():
        p = directory / (arm + ".json")
        v = _object(p)
        if (
            file_hash(p) != digest
            or v["input_sha256"] != i.input_sha256
            or v["arm"] != arm
            or v["bank"] != 4980
            or v["stake"] != 30
            or v["evidence_domain"] != DOMAIN
            or any(v[k] is not False for k in FALSE_FLAGS)
        ):
            raise ValueError("frozen package hash/budget/binding mismatch")
        coupons = tuple(v["coupons"])
        if (
            len(coupons) != 166
            or len(set(coupons)) != 166
            or any(len(c) != 15 or set(c) - set("1X2") for c in coupons)
        ):
            raise ValueError("invalid frozen coupons")
        values[arm] = coupons
    return f, values


def score_frozen(directory: Path, load_labels) -> dict:
    f, packages = verify_frozen(directory)
    i = validate_input(_object(directory / "input.json"))
    label = load_labels()
    if label["drawing"] != f["drawing"] or label["drawing_id"] != i.ev.drawing_id:
        raise ValueError("label drawing identity mismatch")
    actual = label["actual"]
    rows = []
    for arm in ARMS:
        if arm not in packages:
            rows.append({"arm": arm, "status": "NOT_COMPLETED", "reason": f["error"]})
            continue
        coupons = packages[arm]
        ordered_equal = coupons == packages.get("quality-v2")
        equal = arm != "quality-v2" and set(coupons) == set(
            packages.get("quality-v2", ())
        )
        rows.append(
            {
                "arm": arm,
                "status": "SCORED_SCENARIO",
                "same_as_control": equal,
                "same_order_as_control": arm != "quality-v2" and ordered_equal,
                "fallback_reason": "UNKNOWN_NOT_EXPOSED_BY_NATIVE_RESULT"
                if equal
                else None,
                "actual": asdict(
                    score_coupon_package(
                        strategy_id=arm, coupons=coupons, actual=actual
                    )
                ),
                "common_bk_P13_P14_P15": exact_category_probabilities(
                    coupons, i.ev.true_probabilities
                ),
                "roi": None,
            }
        )
    rows += [
        {"arm": "sports-shadow", "status": "NOT_RUN_MISSING_SPORTS"},
        {"arm": "Sports-v3", "status": "NOT_RUN_NO_FIT"},
    ]
    return {
        "evidence_domain": DOMAIN,
        **FLAGS,
        "drawing": f["drawing"],
        "rows": rows,
        "labels": label,
        "frozen_sha256": f["sha256"],
        "roi": None,
        "probability_assumption": (
            "independent events; exact coupon-union probability, "
            "not summed coupon chances"
        ),
    }


def score_batch(manifest_path: Path, db: Path) -> Path:
    m = load_manifest(manifest_path, for_scoring=True)
    ready = []
    for ref in m["roster"]:
        directory = manifest_path.parent / f"drawing-{ref['drawing']}"
        f, _ = verify_frozen(
            directory
        )  # ALL8 attempts must be frozen before first label read.
        if (
            f["manifest_sha256"] != m["sha256"]
            or f["input_sha256"] != ref["input_sha256"]
        ):
            raise ValueError("batch freeze binding mismatch")
        ready.append((ref, directory))
    batch = []
    with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for ref, directory in ready:

            def labels(ref=ref):
                row = connection.execute(
                    "SELECT actual,snapshot_sha256,retrieved_at,payload_sha256 "
                    "FROM drawing_result_snapshots WHERE drawing_id=? "
                    "AND drawing_number=? AND complete=1 AND event_count=15 "
                    "ORDER BY retrieved_at DESC LIMIT 1",
                    (ref["drawing_id"], ref["drawing"]),
                ).fetchone()
                if row is None or row[3] != ref["raw_sha256"]:
                    raise ValueError("complete same-RAW labels missing")
                return {
                    "drawing": ref["drawing"],
                    "drawing_id": ref["drawing_id"],
                    "actual": row[0],
                    "snapshot_sha256": row[1],
                    "retrieved_at": row[2],
                }

            batch.append(score_frozen(directory, labels))
    output = manifest_path.parent / "comparison.json"
    _write_exclusive(
        output,
        {
            "evidence_domain": DOMAIN,
            **FLAGS,
            "drawings": batch,
            "generation_code": m["code"],
            "scoring_code": code_hashes(),
            "manifest_sha256": m["sha256"],
            "roi": None,
        },
    )
    lines = [
        "# SCENARIO ONLY — post-event quotes, as-of unknown",
        "",
        "Not a causal backtest, fit dataset or wagering recommendation.",
        "",
        "|Draw|Arm|Best hits|P13+ model %|Status|",
        "|---|---|---|---|---|",
    ]
    for item in batch:
        for row in item["rows"]:
            a = row.get("actual", {})
            lines.append(
                (
                    f"|{item['drawing']}|{row['arm']}|{a.get('best_hits', '—')}|"
                    f"{100 * row['common_bk_P13_P14_P15'][0]:.6f}|{row['status']}|"
                )
                if "actual" in row
                else f"|{item['drawing']}|{row['arm']}|—|—|{row['status']}|"
            )
    (manifest_path.parent / "comparison.md").write_text("\n".join(lines) + "\n")
    return output


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "generate", "score"))
    p.add_argument("--context", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--drawing", type=int)
    p.add_argument("--max-seconds", type=int, default=600)
    p.add_argument("--db", type=Path)
    a = p.parse_args()
    if a.command == "prepare":
        print(prepare(a.context, a.output))
    elif a.command == "generate":
        r = generate(a.manifest, a.drawing, a.max_seconds)
        print(
            json.dumps(
                {"drawing": a.drawing, "status": r["status"], "error": r["error"]}
            )
        )
        return 0 if r["status"] == "COMPLETE_SCENARIO" else 2
    else:
        print(score_batch(a.manifest, a.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
