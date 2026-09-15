import importlib.util
import sys
from pathlib import Path

from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats import v3_parallel

_spec = importlib.util.spec_from_file_location(
    "existing_comparison_fixtures",
    Path(__file__).with_name("test_final_hybrid_g1_integration.py"),
)
_fixtures = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _fixtures
_spec.loader.exec_module(_fixtures)
comparison_input = _fixtures.comparison_input


def test_optional_v3_error_preserves_primary_and_four_strategy_selection(
    comparison_input, monkeypatch
):
    arguments = {**comparison_input, "g1_config": None}
    control, paths = comparison.execute_final_hybrid_comparison(**arguments)
    primary_bytes = paths.baseline_package.read_bytes()
    snapshot = comparison.load_final_input(arguments["final_input_path"])
    snapshot.payload = {"data": {"events": [{"order": i, "id": i} for i in range(15)]}}
    monkeypatch.setattr(
        comparison, "_validate_sports_artifact_identity", lambda **k: None
    )
    seen = []

    def failure(*args, **kwargs):
        seen.append(
            (
                paths.baseline_package.read_bytes() == primary_bytes,
                (Path(arguments["output_dir"]) / "primary-bk-ranking.json").exists(),
            )
        )
        raise ValueError("optional model unavailable")

    monkeypatch.setattr(v3_parallel, "run_v3_parallel_research", failure)
    changed, new_paths = comparison.execute_final_hybrid_comparison(
        **arguments, v3_research_request={"model": "invalid"}
    )
    assert len(seen) == 1
    assert seen[0] == (True, True)
    assert new_paths.baseline_package.read_bytes() == primary_bytes
    assert changed["experimental_selection"] == control["experimental_selection"]
    assert changed["v3_probability_research"]["status"] == "CONTROL_FALLBACK"
    assert "v3_probability_research" not in control
