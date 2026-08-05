from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import time
from typing import Any

from toto_ai.optimizer.cover import greedy_cover

REPRESENTATIVE_BRIEF = [
    "1X",
    "12",
    "X2",
    "1X",
    "12",
    "X2",
    "1X",
    "12",
    "X2",
    "1X",
    "1",
    "2",
    "X",
    "1",
    "2",
]


def benchmark_cover(
    brief: list[str] | None = None,
    category: int = 13,
    max_coupons: int = 333,
    profile: bool = False,
    profile_limit: int = 20,
) -> dict[str, Any]:
    target_brief = brief or REPRESENTATIVE_BRIEF
    profiler = cProfile.Profile() if profile else None

    started_at = time.perf_counter()
    if profiler is not None:
        profiler.enable()
    result = greedy_cover(
        brief=target_brief,
        category=category,
        max_coupons=max_coupons,
    )
    if profiler is not None:
        profiler.disable()
    elapsed = time.perf_counter() - started_at

    return {
        "brief": target_brief,
        "category": category,
        "max_coupons": max_coupons,
        "elapsed_seconds": round(elapsed, 6),
        "selected_coupons": len(result["selected_coupons"]),
        "full_variants_count": result["full_variants_count"],
        "covered_variants_count": result["covered_variants_count"],
        "coverage_rate": result["coverage_rate"],
        "profile": _profile_text(profiler, profile_limit) if profiler else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the Cover Engine.")
    parser.add_argument("--category", type=int, default=13)
    parser.add_argument("--max-coupons", type=int, default=333)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--profile-limit", type=int, default=20)
    args = parser.parse_args()

    result = benchmark_cover(
        category=args.category,
        max_coupons=args.max_coupons,
        profile=args.profile,
        profile_limit=args.profile_limit,
    )
    print(f"elapsed_seconds={result['elapsed_seconds']}")
    print(f"full_variants={result['full_variants_count']}")
    print(f"selected_coupons={result['selected_coupons']}")
    print(f"coverage_rate={result['coverage_rate']:.6f}")
    if result["profile"]:
        print(result["profile"])


def _profile_text(profiler: cProfile.Profile, limit: int) -> str:
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).strip_dirs().sort_stats(
        "cumulative"
    ).print_stats(limit)
    return output.getvalue()


if __name__ == "__main__":
    main()
