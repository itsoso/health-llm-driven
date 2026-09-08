"""Scheduling telemetry must not alter test selection or timeout policy."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ci_timing_matrix", ROOT / "backend/scripts/build_ci_pytest_matrix.py"
)
matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matrix)


def test_scheduling_seconds_balance_without_overwriting_deadline_estimates():
    shards = [
        {"label": "a", "estimated_seconds": 90, "scheduling_seconds": 2},
        {"label": "b", "estimated_seconds": 1, "scheduling_seconds": 8},
        {"label": "c", "estimated_seconds": 1, "scheduling_seconds": 3},
    ]
    before = copy.deepcopy(shards)
    result = matrix.balance_shards(shards, worker_count=2)
    assert [row["shards"] for row in result] == ["b", "c,a"]
    assert [row["estimated_seconds"] for row in result] == [8, 5]
    assert shards == before


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "2"])
def test_reject_invalid_scheduling_samples(value):
    with pytest.raises(ValueError, match="positive finite"):
        matrix.balance_shards([
            {"label": "a", "estimated_seconds": 1, "scheduling_seconds": value}
        ], worker_count=1)


def _catalog():
    return {
        "timing_source": {
            "run_id": 34141329002,
            "head_sha": "34e32edc463d87a3331d38d552599d3c164c3db3",
            "measurement": "successful_attempt_process_wall_seconds",
            "sample_count": 2,
            "excluded_timeout_seconds": 180.064,
        },
        "shards": [
            {"label": "a", "estimated_seconds": 90, "scheduling_seconds": 2},
            {"label": "b", "estimated_seconds": 1, "scheduling_seconds": 8},
        ],
    }


@pytest.mark.parametrize("mutation", [
    lambda data: data["shards"][1].pop("scheduling_seconds"),
    lambda data: data["shards"][1].update(label="a"),
    lambda data: data["shards"][1].update(label=""),
    lambda data: data["timing_source"].update(sample_count=1),
    lambda data: data["timing_source"].update(head_sha="bad"),
    lambda data: data["timing_source"].update(run_id=0),
    lambda data: data["timing_source"].update(measurement="junit"),
    lambda data: data["timing_source"].update(excluded_timeout_seconds=-1),
    lambda data: data.pop("timing_source"),
])
def test_refreshed_catalog_rejects_incomplete_or_invalid_provenance(tmp_path, mutation):
    payload = _catalog()
    mutation(payload)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        matrix.load_catalog(path)


def test_refreshed_catalog_accepts_complete_samples(tmp_path):
    payload = _catalog()
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload))
    assert matrix.load_catalog(path) == payload["shards"]


def test_real_catalog_retains_all_shards_and_process_policies():
    payload = json.loads(matrix.DEFAULT_CATALOG.read_text())
    shards = matrix.load_catalog()
    assert payload["timing_source"]["sample_count"] == len(shards) == 56
    assert payload["timing_source"]["run_id"] == 34141329002
    assignments = matrix.balance_shards(shards, worker_count=16)
    assigned = [label for worker in assignments for label in worker["shards"].split(",")]
    assert sorted(assigned) == sorted(shard["label"] for shard in shards)
    assert max(worker["estimated_seconds"] for worker in assignments) == 202.953
    assert next(shard for shard in shards if shard["label"] == "a-agenda")["estimated_seconds"] == 20.336
