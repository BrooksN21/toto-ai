"""Bounded optional G1 research computation; never an operator strategy.

The worker is a local Python process, not an agent. Existing four-strategy
authorization and selection remain unchanged. O1 evidence is not a predictor.
"""

from __future__ import annotations

import hashlib
import json
import math
import resource
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

from toto_ai.optimizer.exact_maximin_refinement import (
    EPSILON,
    RefinementBinding,
    RefinementLimits,
    refine_maximin_package,
)
from toto_ai.optimizer.exact_maximin_refinement import (
    POLICY_VERSION as ENGINE_POLICY_VERSION,
)
from toto_ai.optimizer.robust_package import ExposureConstraints
from toto_ai.package.audit import PackageSafetyConfig

POLICY_VERSION = "parallel-g1-research-v1"


@dataclass(frozen=True)
class ParallelG1Config:
    family_refinement: bool = False
    diagnostics: bool = True
    # One evaluation is a raw remove/add pair, before exposure rejection;
    # models multiply projection work, not this count. Keep full-round admission.
    max_swap_evaluations: int = 65_536
    max_accepted_swaps: int = 1
    engine_seconds: float = 50.0
    hard_timeout_seconds: float = 60.0
    reserve_seconds: float = 30.0

    def __post_init__(self):
        if (
            type(self.family_refinement) is not bool
            or type(self.diagnostics) is not bool
        ):
            raise ValueError("family refinement opt-in must be boolean")
        if any(
            type(v) is not int or v <= 0
            for v in (
                self.max_swap_evaluations,
                self.max_accepted_swaps,
            )
        ):
            raise ValueError("positive integer G1 evaluation limits required")
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or v <= 0
            for v in (
                self.engine_seconds,
                self.hard_timeout_seconds,
                self.reserve_seconds,
            )
        ):
            raise ValueError("positive finite G1 runtime limits required")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def run_parallel_g1(
    *,
    initial_coupons,
    control_coupons,
    candidate_coupons,
    probability_models,
    exposure_constraints,
    input_sha256,
    plan_sha256,
    bank,
    effective_budget,
    stake,
    safety_config,
    deadline,
    config=None,
):
    """Return research data or the byte-order-identical initial fallback.

    No deadline means no execution. The publication reserve is subtracted before
    starting a child; timeout kills and reaps that child via subprocess.run.
    All G1 and extra exact candidate/safety checks run inside that same bound.
    """
    fallback = {
        "status": "DISABLED",
        "selected_coupons": list(initial_coupons),
        "operator_compatible": False,
        "automatic_wagering": False,
        "activation_allowed": False,
        "research_only": True,
        "lineage": {
            "policy_version": POLICY_VERSION,
            "strategy_id": "robust-g1-v1",
            "parent_strategy_id": "robust",
            "operator_selection_included": False,
            "authority_status": "RESEARCH_ONLY_PENDING_EXPLICIT_AUTHORIZATION",
        },
    }
    if config is None:
        return fallback
    started = time.monotonic()
    try:
        if not isinstance(config, ParallelG1Config):
            raise ValueError("typed runtime config required")
        if deadline is None or not math.isfinite(deadline):
            return {**fallback, "status": "SKIPPED_DEADLINE_RESERVE"}
        hard = min(
            config.hard_timeout_seconds, deadline - started - config.reserve_seconds
        )
        if hard <= 1:
            return {**fallback, "status": "SKIPPED_DEADLINE_RESERVE"}
        admission = {
            "initial": len(initial_coupons),
            "universe": len(candidate_coupons),
            "models": len(probability_models),
            "round_pairs": len(initial_coupons)
            * (len(candidate_coupons) - len(initial_coupons)),
        }
        fallback["admission"] = admission
        if admission["round_pairs"] > config.max_swap_evaluations:
            return {**fallback, "status": "SKIPPED_EVALUATION_BUDGET"}
        models = {
            name: tuple(tuple(float(v) for v in row) for row in rows)
            for name, rows in sorted(probability_models.items())
        }
        binding = RefinementBinding(
            input_sha256=input_sha256,
            initial_package_sha256=_hash(tuple(initial_coupons)),
            candidate_universe_sha256=_hash(sorted(candidate_coupons)),
            probability_models_sha256=_hash(models),
            exposure_constraints_sha256=_hash(asdict(exposure_constraints)),
            bank=bank,
            effective_budget=effective_budget,
            stake=stake,
            coupon_capacity=len(initial_coupons),
        )
        if (
            not isinstance(plan_sha256, str)
            or len(plan_sha256) != 64
            or set(plan_sha256) - set("0123456789abcdef")
        ):
            raise ValueError("plan SHA256 required")
        request = {
            "initial_coupons": list(initial_coupons),
            "control_coupons": list(control_coupons),
            "candidate_coupons": list(candidate_coupons),
            "probability_models": models,
            "exposure_constraints": asdict(exposure_constraints),
            "binding": asdict(binding),
            "plan_sha256": plan_sha256,
            "safety_config": asdict(safety_config),
            "limits": asdict(
                RefinementLimits(
                    max_swap_evaluations=config.max_swap_evaluations,
                    max_accepted_swaps=config.max_accepted_swaps,
                    time_budget_seconds=min(config.engine_seconds, hard - 0.5),
                )
            ),
            "runtime_contract": asdict(config),
        }
        # Recompute remaining allowance after serialization; never extend deadline.
        raw = _canonical(request)
        timeout = min(hard, deadline - time.monotonic() - config.reserve_seconds)
        if timeout <= 0:
            return {**fallback, "status": "SKIPPED_DEADLINE_RESERVE"}
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "toto_ai.sports_stats.parallel_g1"],
            input=raw,
            text=True,
            stdout=subprocess.PIPE,
            timeout=timeout,
            check=True,
        )
        if len(completed.stdout) > 8_000_000:
            raise ValueError("oversized worker output")
        document = json.loads(completed.stdout)
        if document["request_sha256"] != _hash(request):
            raise ValueError("worker request binding mismatch")
        engine = document["engine"]
        semantic = {
            key: value
            for key, value in engine.items()
            if key not in ("semantic_hash", "elapsed_seconds")
        }
        if engine["semantic_hash"] != _hash(semantic):
            raise ValueError("worker result semantic hash mismatch")
        if engine["status"] not in (
            "REFINED",
            "UNCHANGED",
            "BUDGET_EXHAUSTED",
            "VERIFICATION_FAILED",
        ):
            raise ValueError("unknown worker status")
        if any(
            engine[key] is not False
            for key in (
                "operator_compatible",
                "automatic_wagering",
                "activation_allowed",
            )
        ):
            raise ValueError("worker attempted to change authority flags")
        if (
            engine["input_hashes"]["binding_sha256"] != _hash(asdict(binding))
            or engine["input_hashes"]["budget_sha256"]
            != _hash(engine["budget_summary"])
            or engine["input_hashes"]["config_sha256"]
            != _hash(
                {
                    "policy_version": ENGINE_POLICY_VERSION,
                    "epsilon": EPSILON,
                    **request["limits"],
                }
            )
        ):
            raise ValueError("worker budget/configuration binding mismatch")
        if engine["input_hashes"]["input_sha256"] != input_sha256:
            raise ValueError("worker final-input mismatch")
        for key in (
            "initial_package_sha256",
            "candidate_universe_sha256",
            "probability_models_sha256",
            "exposure_constraints_sha256",
        ):
            if engine["input_hashes"][key] != getattr(binding, key):
                raise ValueError("worker input binding mismatch")
        selected = engine["selected_coupons"]
        if engine["input_hashes"]["selected_package_sha256"] != _hash(selected):
            raise ValueError("worker selected package mismatch")
        if engine["status"] != "REFINED" and selected != list(initial_coupons):
            raise ValueError("non-refined worker changed initial")
        if (
            len(selected) != len(initial_coupons)
            or len(set(selected)) != len(selected)
            or not set(selected) <= set(candidate_coupons)
        ):
            raise ValueError("worker package capacity/universe mismatch")
        if time.monotonic() >= deadline - config.reserve_seconds:
            return {**fallback, "status": "FALLBACK", "reason": "POST_WORKER_DEADLINE"}
        return {
            **document,
            **fallback,
            "status": engine["status"],
            "selected_coupons": selected,
            "binding": asdict(binding),
            "plan_sha256": plan_sha256,
            "wall_seconds": time.monotonic() - started,
            "effective_worker_timeout_seconds": timeout,
            "runtime_contract": asdict(config),
        }
    except Exception as exc:
        return {
            **fallback,
            "status": "FALLBACK",
            "reason": type(exc).__name__,
            "wall_seconds": time.monotonic() - started,
        }


class _Progress:
    """Same clock reads with diagnostics on/off; bounded, nonfatal event sink."""

    def __init__(self, *, enabled, clock, sink=None):
        self.enabled, self.clock = enabled, clock
        self.sink = sink or (lambda line: print(line, file=sys.stderr, flush=True))
        self.started = self.last = None
        self.events = self.bytes = 0

    def __call__(self):
        now = self.clock()
        if self.started is None:
            self.started = now
            self.emit("engine_start", now)
        elif self.last is None or now - self.last >= 10:
            self.emit("engine_progress", now)
        return now

    def emit(self, phase, now):
        if not self.enabled or self.events >= 8:
            return
        line = _canonical(
            {
                "event": phase,
                "elapsed_seconds": now
                - (now if self.started is None else self.started),
            }
        )
        size = len(line.encode())
        if size > 256 or self.bytes + size > 2048:
            return
        self.events += 1
        self.bytes += size
        self.last = now
        try:
            self.sink(line)
        except Exception:
            pass


def _worker(request):
    started, cpu_started = time.monotonic(), time.process_time()
    progress = _Progress(
        enabled=request["runtime_contract"]["diagnostics"],
        clock=time.monotonic,
    )
    binding = RefinementBinding(**request["binding"])
    result = refine_maximin_package(
        initial_coupons=request["initial_coupons"],
        candidate_coupons=request["candidate_coupons"],
        probability_models=request["probability_models"],
        exposure_constraints=ExposureConstraints(**request["exposure_constraints"]),
        binding=binding,
        limits=RefinementLimits(**request["limits"]),
        clock=progress,
    )
    engine_done, engine_cpu = time.monotonic(), time.process_time()
    progress.emit("engine_complete", engine_done)
    document = {"request_sha256": _hash(request), "engine": asdict(result)}
    if result.status == "REFINED":
        # Reuse the existing exact/safety/selector implementation, under the
        # outer process timeout. This is a research comparison, not a release.
        from toto_ai.optimizer.parallel_challenger import select_parallel_candidate
        from toto_ai.sports_stats.final_hybrid_comparison import (
            _best_single_coupon_payload,
            _parallel_candidate,
        )

        models = request["probability_models"]
        kwargs = {
            "models": models,
            "probabilities": models["bk"],
            "safety_config": PackageSafetyConfig(**request["safety_config"]),
            "stake": binding.stake,
        }
        control = _parallel_candidate(
            strategy_id="quality-v2",
            coupons=tuple(request["control_coupons"]),
            **kwargs,
        )
        candidate = _parallel_candidate(
            strategy_id="robust-g1-v1",
            coupons=result.selected_coupons,
            **kwargs,
        )
        document["candidate"] = candidate.public_summary()
        original = _parallel_candidate(
            strategy_id="robust",
            coupons=tuple(request["initial_coupons"]),
            **kwargs,
        )
        if control.eligible:
            document["research_selection"] = select_parallel_candidate(
                (control, candidate),
            ).public_summary()
        else:
            document["research_selection"] = {"status": "CONTROL_INELIGIBLE"}
        document["family_candidate_verified"] = (
            candidate.eligible
            and document["research_selection"].get("promoted") is True
            and all(
                new >= old - 1e-12
                for before, after in zip(original.models, candidate.models, strict=True)
                for old, new in (
                    (before.probability_at_least_13, after.probability_at_least_13),
                    (before.probability_at_least_14, after.probability_at_least_14),
                    (before.probability_at_least_15, after.probability_at_least_15),
                )
            )
        )
        document["highest_p13_single_coupon"] = _best_single_coupon_payload(
            result.selected_coupons,
            models["bk"],
            reference_model="bk",
        )
    finished, cpu_finished = time.monotonic(), time.process_time()
    progress.emit("verification_complete", finished)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    document["observability"] = {
        "engine_wall_seconds": engine_done - started,
        "engine_cpu_seconds": engine_cpu - cpu_started,
        "verification_wall_seconds": finished - engine_done,
        "verification_cpu_seconds": cpu_finished - engine_cpu,
        "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "extra_exact_validation_calls": (
            3 * len(request["probability_models"]) if result.status == "REFINED" else 0
        ),
        "progress_events": progress.events,
        "progress_bytes": progress.bytes,
        "logging_limits": {"interval_seconds": 10, "max_events": 8, "max_bytes": 2048},
    }
    return document


def family_refinement_coupons(
    result,
    *,
    initial_coupons,
    candidate_coupons,
    models,
    bounds,
    input_sha256,
    bank,
    effective_budget,
    stake,
    plan_sha256,
):
    """Validate the immutable worker envelope before existing caller rechecks."""
    try:
        selected = tuple(result["selected_coupons"])
        expected = {
            "input_sha256": input_sha256,
            "initial_package_sha256": _hash(initial_coupons),
            "candidate_universe_sha256": _hash(sorted(candidate_coupons)),
            "probability_models_sha256": _hash(
                {
                    name: tuple(tuple(float(v) for v in row) for row in rows)
                    for name, rows in sorted(models.items())
                }
            ),
            "exposure_constraints_sha256": _hash(asdict(bounds)),
            "bank": bank,
            "effective_budget": effective_budget,
            "stake": stake,
            "coupon_capacity": len(initial_coupons),
        }
        if (
            result["status"] != "REFINED"
            or result["engine"]["status"] != "REFINED"
            or result.get("family_candidate_verified") is not True
            or result["binding"] != expected
            or result["plan_sha256"] != plan_sha256
            or result["engine"]["input_hashes"]["selected_package_sha256"]
            != _hash(selected)
            or len(selected) != len(initial_coupons)
            or len(set(selected)) != len(selected)
            or not set(selected) <= set(candidate_coupons)
            or result["candidate"]["package_sha256"]
            != hashlib.sha256(",".join(selected).encode()).hexdigest()
        ):
            return None
        return selected
    except (KeyError, TypeError, ValueError):
        return None


if __name__ == "__main__":
    print(_canonical(_worker(json.load(sys.stdin))))
