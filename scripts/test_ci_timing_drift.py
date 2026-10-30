"""Timing drift must be observable without granting release or write authority."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_ci_pytest_timing_drift.py"
SCOPE_SCRIPT = ROOT / "scripts/check_ci_timing_observation_scope.py"
WORKFLOW = ROOT / ".github/workflows/ci-timing-drift.yml"


def _module():
    spec = importlib.util.spec_from_file_location("ci_timing_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope_module():
    spec = importlib.util.spec_from_file_location("ci_timing_scope", SCOPE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _catalog(*, run_ids=(100,), seconds=(2.0, 8.0)):
    runs = [
        {
            "run_id": run_id,
            "head_sha": f"{run_id:040x}"[-40:],
            "measurement": "successful_attempt_process_wall_seconds",
            "sample_count": 2,
            "process_sample_count": 2,
            "excluded_timeout_seconds": 0.0,
        }
        for run_id in run_ids
    ]
    return {
        "worker_count": 2,
        "timing_source": {
            **runs[-1],
            "aggregation": "maximum",
            "runs": runs,
        },
        "deadline_calibration": {"proof": "retained"},
        "shards": [
            {"label": "a", "paths": ["tests/test_a*.py"], "scheduling_seconds": seconds[0]},
            {"label": "b", "paths": ["tests/test_b*.py"], "scheduling_seconds": seconds[1]},
        ],
    }


def _full_jobs(run_id, sha):
    return {
        "total_count": 16,
        "jobs": [
            {
                "name": f"backend-test-balanced-{index:02d}",
                "conclusion": "success",
                "run_attempt": 1,
                "run_id": run_id,
                "head_sha": sha,
            }
            for index in range(1, 17)
        ],
    }


def test_assessment_gates_on_worker_critical_path_and_staleness():
    module = _module()
    current = _catalog(run_ids=(100,), seconds=(2.0, 8.0))
    observed = _catalog(run_ids=(400,), seconds=(2.1, 10.1))

    report = module.assess(
        current,
        observed,
        successful_full_run_ids=[400, 300, 200, 100],
        current_run_id=400,
        current_head_sha=f"{400:040x}",
        worker_count=2,
        max_slower_ratio=0.20,
        max_runs_since_source=3,
    )

    assert report["release_authority"] is False
    assert report["predicted_critical_seconds"] == 8.0
    assert report["observed_critical_seconds"] == 10.1
    assert report["slower_ratio"] == pytest.approx(0.2625)
    assert report["runs_since_source"] == 3
    assert report["drift_exceeded"] is True
    assert report["catalog_stale"] is True
    assert report["status"] == "REVIEW_REQUIRED"


def test_assessment_accepts_recent_catalog_and_ignores_short_shard_ratio_noise():
    module = _module()
    current = _catalog(run_ids=(300,), seconds=(1.0, 8.0))
    observed = _catalog(run_ids=(400,), seconds=(1.8, 8.5))

    report = module.assess(
        current,
        observed,
        successful_full_run_ids=[400, 300],
        current_run_id=400,
        current_head_sha=f"{400:040x}",
        worker_count=2,
        max_slower_ratio=0.20,
        max_runs_since_source=3,
    )

    assert report["largest_shard_slower_ratio"] == pytest.approx(0.8)
    assert report["slower_ratio"] == pytest.approx(0.0625)
    assert report["drift_exceeded"] is False
    assert report["catalog_stale"] is False
    assert report["status"] == "CURRENT"


def test_assessment_rejects_policy_or_run_inventory_mismatch():
    module = _module()
    current = _catalog()
    observed = _catalog(run_ids=(400,))
    observed["shards"][0]["paths"] = ["tests/test_changed.py"]
    with pytest.raises(ValueError, match="execution policy"):
        module.assess(
            current,
            observed,
            successful_full_run_ids=[400, 100],
            current_run_id=400,
            current_head_sha=f"{400:040x}",
            worker_count=2,
            max_slower_ratio=0.2,
            max_runs_since_source=3,
        )
    with pytest.raises(ValueError, match="current run"):
        module.assess(
            current,
            _catalog(run_ids=(400,)),
            successful_full_run_ids=[300, 100],
            current_run_id=400,
            current_head_sha=f"{400:040x}",
            worker_count=2,
            max_slower_ratio=0.2,
            max_runs_since_source=3,
        )


def test_assessment_rejects_observation_not_bound_to_current_run():
    module = _module()
    with pytest.raises(ValueError, match="observed timing source"):
        module.assess(
            _catalog(run_ids=(100,)),
            _catalog(run_ids=(399,)),
            successful_full_run_ids=[400, 100],
            current_run_id=400,
            current_head_sha=f"{400:040x}",
            worker_count=2,
            max_slower_ratio=0.2,
            max_runs_since_source=3,
        )


def test_full_run_inventory_requires_exact_successful_first_attempt_workers():
    module = _module()
    sha = f"{400:040x}"
    run = {
        "databaseId": 400,
        "headSha": sha,
        "workflowName": "CI",
        "headBranch": "main",
        "status": "completed",
        "conclusion": "success",
        "attempt": 1,
    }
    jobs = {400: _full_jobs(400, sha)}
    assert module.successful_full_run_ids([run], jobs) == [400]

    run["headBranch"] = "topic"
    assert module.successful_full_run_ids([run], jobs) == []
    run["headBranch"] = "main"

    jobs[400]["jobs"][0]["conclusion"] = "failure"
    assert module.successful_full_run_ids([run], jobs) == []
    jobs[400] = _full_jobs(400, sha)
    jobs[400]["jobs"].pop()
    with pytest.raises(ValueError, match="incomplete job inventory"):
        module.successful_full_run_ids([run], jobs)


def test_observation_scope_skips_docs_only_and_requires_complete_successful_matrix():
    module = _scope_module()
    assert module.is_full_backend_run({"jobs": []}, worker_count=16) is False
    assert module.is_full_backend_run({
        "jobs": [{"name": "backend-test-${{ matrix.label }}", "conclusion": "skipped"}]
    }, worker_count=16) is False

    jobs = _full_jobs(400, f"{400:040x}")
    assert module.is_full_backend_run(jobs, worker_count=16) is True
    jobs["jobs"].pop()
    with pytest.raises(ValueError, match="incomplete backend timing matrix"):
        module.is_full_backend_run(jobs, worker_count=16)

    jobs = _full_jobs(400, f"{400:040x}")
    jobs["jobs"][0]["conclusion"] = "failure"
    with pytest.raises(ValueError, match="successful backend timing matrix"):
        module.is_full_backend_run(jobs, worker_count=16)


def test_cli_writes_report_before_review_required_exit(tmp_path):
    catalog = tmp_path / "catalog.json"
    observed = tmp_path / "observed.json"
    runs = tmp_path / "runs.json"
    jobs_dir = tmp_path / "jobs"
    output = tmp_path / "report.json"
    jobs_dir.mkdir()
    sha = f"{400:040x}"
    catalog.write_text(json.dumps(_catalog(run_ids=(100,), seconds=(2.0, 8.0))))
    observed.write_text(json.dumps(_catalog(run_ids=(400,), seconds=(2.0, 10.0))))
    runs.write_text(json.dumps([
        {"databaseId": run_id, "headSha": sha, "headBranch": "main", "workflowName": "CI", "status": "completed",
         "conclusion": "success", "attempt": 1}
        for run_id in (400, 300, 200, 100)
    ]))
    for run_id in (400, 300, 200, 100):
        (jobs_dir / f"{run_id}.json").write_text(json.dumps(_full_jobs(run_id, sha)))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--catalog", str(catalog),
            "--observed", str(observed),
            "--current-run-id", "400",
            "--recent-runs", str(runs),
            "--jobs-dir", str(jobs_dir),
            "--workers", "2",
            "--max-slower-ratio", "0.2",
            "--max-runs-since-source", "3",
            "--output", str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(output.read_text())["status"] == "REVIEW_REQUIRED"
    assert "review required" in result.stderr.lower()


def test_workflow_is_read_only_exact_run_observer():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert workflow["on"] == {"workflow_run": {"workflows": ["CI"], "types": ["completed"]}}
    job = workflow["jobs"]["assess"]
    condition = job["if"]
    assert "conclusion == 'success'" in condition
    assert "head_branch == 'main'" in condition
    assert "run_attempt == 1" in condition
    checkout = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"
    bodies = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "github.event.workflow_run.id" in bodies
    assert "github.event.workflow_run.head_sha" in bodies
    assert "--resource logs" in bodies
    assert "check_ci_timing_observation_scope.py" in bodies
    assert "check_ci_pytest_timing_drift.py" in bodies
    assert bodies.count("github_actions_read_retry.py") == 4
    assert "gh api" not in bodies
    assert "gh run list" not in bodies
    assert not any(token in bodies for token in ("git push", "gh workflow run", "gh variable set"))
    scope = next(step for step in job["steps"] if step.get("id") == "scope")
    assert '--run-id "$RUN_ID"' in scope["run"]
    assert "--resource jobs" in scope["run"]
    gated_steps = {
        step["name"]: step
        for step in job["steps"]
        if step.get("name") in {
            "Collect exact successful run timing evidence",
            "Assess placement drift without updating main",
            "Upload bounded timing observation",
        }
    }
    assert set(gated_steps) == {
        "Collect exact successful run timing evidence",
        "Assess placement drift without updating main",
        "Upload bounded timing observation",
    }
    assert gated_steps["Collect exact successful run timing evidence"]["if"] == (
        "${{ steps.scope.outputs.eligible == 'true' }}"
    )
    assert gated_steps["Assess placement drift without updating main"]["if"] == (
        "${{ steps.scope.outputs.eligible == 'true' }}"
    )
    assert gated_steps["Upload bounded timing observation"]["if"] == (
        "${{ always() && steps.scope.outputs.eligible == 'true' }}"
    )
