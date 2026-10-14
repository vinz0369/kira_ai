import json
from pathlib import Path
from typing import Any

import pytest

from app.live.director import run_fixture_scenario

SCENARIO_ROOT = Path(__file__).resolve().parents[3] / "harness" / "scenarios"
SCENARIOS = [
    json.loads(path.read_text(encoding="utf-8"))
    for path in sorted(SCENARIO_ROOT.glob("*.json"))
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["id"])
def test_harness_scenario(scenario: dict[str, Any]) -> None:
    result = run_fixture_scenario(scenario)
    for key, expected in scenario["expect"].items():
        assert result[key] == expected, (
            f"{scenario['id']}: expected {key}={expected!r}, got {result[key]!r}"
        )
