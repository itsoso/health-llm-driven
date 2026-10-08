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
    assert payload["timing_source"]["sample_count"] == len(shards) == 60
    assert payload["timing_source"]["run_id"] == 37793465362
    assignments = matrix.balance_shards(shards, worker_count=16)
    assigned = [label for worker in assignments for label in worker["shards"].split(",")]
    assert sorted(assigned) == sorted(shard["label"] for shard in shards)
    assert max(worker["estimated_seconds"] for worker in assignments) == 356.083
    assert next(shard for shard in shards if shard["label"] == "a-agenda")["estimated_seconds"] == 20.336


def _refresh_module():
    spec = importlib.util.spec_from_file_location(
        "refresh_timings", ROOT / "scripts/refresh_ci_pytest_timings.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _successful_log(label):
    return '\n'.join([
        '[ci-worker] ' + json.dumps({'shard': label}),
        '[ci-shard-timing] ' + json.dumps({
            'attempt': 1, 'duration_ms': 1234, 'outcome': 'pass', 'return_code': 0,
        }),
    ])


def test_refresh_preserves_every_non_timing_policy():
    refresh = _refresh_module()
    original = json.loads(matrix.DEFAULT_CATALOG.read_text())
    before = copy.deepcopy(original)
    logs = [_successful_log(row['label']) for row in original['shards']]
    result = refresh.refresh_catalog(original, logs, run_id=37784722390,
                                     head_sha='be8bd98e10db01241dd0b9e6e4c34181a9061345')
    assert original == before
    assert result['worker_count'] == original['worker_count']
    for old, new in zip(original['shards'], result['shards'], strict=True):
        assert new['scheduling_seconds'] == 1.234
        assert {k: v for k, v in old.items() if k != 'scheduling_seconds'} == {
            k: v for k, v in new.items() if k != 'scheduling_seconds'}
    assert result['timing_source']['sample_count'] == 60


@pytest.mark.parametrize('mutation', [
    lambda logs: logs.pop(),
    lambda logs: logs.append(logs[0]),
    lambda logs: logs.__setitem__(0, logs[0].replace('"pass"', '"fail"')),
    lambda logs: logs.__setitem__(0, logs[0].replace('"return_code": 0', '"return_code": 1')),
    lambda logs: logs.__setitem__(0, logs[0].replace('"attempt": 1', '"attempt": 2')),
    lambda logs: logs.__setitem__(0, logs[0].replace('1234', '0')),
    lambda logs: logs.__setitem__(0, logs[0].replace('1234', 'true')),
    lambda logs: logs.__setitem__(0, logs[0].splitlines()[1]),
    lambda logs: logs.__setitem__(0, logs[0] + '\n[ci-worker] {"shard":"a"}'),
])
def test_refresh_rejects_incomplete_or_failed_samples(mutation):
    refresh = _refresh_module()
    payload = _catalog()
    logs = [_successful_log(row['label']) for row in payload['shards']]
    mutation(logs)
    with pytest.raises(ValueError):
        refresh.refresh_catalog(payload, logs, run_id=37784722390,
                                head_sha='be8bd98e10db01241dd0b9e6e4c34181a9061345')


@pytest.mark.parametrize('run_id,head_sha', [
    (0, 'a' * 40), (True, 'a' * 40), (1, 'bad'), (1, None),
])
def test_refresh_rejects_invalid_source_identity(run_id, head_sha):
    with pytest.raises(ValueError):
        _refresh_module().refresh_catalog(
            _catalog(), [_successful_log('a'), _successful_log('b')],
            run_id=run_id, head_sha=head_sha,
        )


def test_refresh_cli_ignores_aggregate_duplicates_and_keeps_output_on_failure(tmp_path):
    import subprocess
    import sys
    import zipfile

    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'worker_count': 2, **_catalog()}))
    archive = tmp_path / 'logs.zip'
    output = tmp_path / 'updated.json'
    command = [sys.executable, str(ROOT / 'scripts/refresh_ci_pytest_timings.py'),
               '--catalog', str(catalog), '--logs-zip', str(archive),
               '--run-id', '123', '--head-sha', 'a' * 40, '--output', str(output)]
    with zipfile.ZipFile(archive, 'w') as logs:
        for i, label in enumerate(('a', 'b'), 1):
            body = _successful_log(label)
            logs.writestr(f'{i}_backend-test-balanced-{i:02}.txt', body)
            logs.writestr(f'backend-test-balanced-{i:02}/7_Run isolated shards (balanced-{i:02}).txt', body)
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert matrix.load_catalog(output)[0]['scheduling_seconds'] == 1.234
    previous = output.read_bytes()
    with zipfile.ZipFile(archive, 'w') as logs:
        logs.writestr('backend-test-balanced-01/7_Run isolated shards (balanced-01).txt',
                      _successful_log('a'))
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert output.read_bytes() == previous
