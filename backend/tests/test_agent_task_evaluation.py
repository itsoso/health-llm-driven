"""Offline evaluations consume only synthetic, anonymous task metadata."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.services.agent_task_evaluation import evaluate_tasks


def _id(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _row(attempt="a", **overrides):
    return {
        "scope_id": _id("synthetic-owner"),
        "attempt_id": _id(attempt),
        "revision": "a" * 40,
        "task_type": "supplement_record",
        "attempt_index": 1,
        "technical_status": "succeeded",
        **overrides,
    }


def test_technical_success_is_not_human_verified_success():
    report = evaluate_tasks([
        _row(),
        _row("b", human_verified=True, task_outcome="failed"),
        _row("c", technical_status="waiting_for_user"),
    ])
    group = report["groups"][0]
    assert group["task_outcomes"] == {"satisfied": 0, "failed": 1, "unknown": 2}
    assert group["technical_statuses"]["waiting_for_user"] == 1
    assert group["technical_success_but_verified_failure"] == 1
    assert group["verified_satisfaction_rate"] == 0
    assert group["cost"]["known_subtotal_cny"] is None
    assert group["cost"]["total_cny"] is None


def test_unreviewed_cohort_has_no_semantic_success_rate():
    group = evaluate_tasks([_row()])["groups"][0]
    assert group["verified_satisfaction_rate"] is None
    assert group["verified_task_count"] == 0
    assert group["task_outcomes"]["unknown"] == 1


def test_only_same_owner_revision_and_explicit_logical_id_merge():
    task = _id("task")
    report = evaluate_tasks([
        _row("a", logical_task_id=task, technical_status="failed"),
        _row("b", logical_task_id=task, attempt_index=2,
             human_verified=True, task_outcome="satisfied"),
        _row("c", logical_task_id=task, scope_id=_id("other-owner")),
        _row("d", logical_task_id=task, revision="b" * 40),
        _row("e"), _row("f"),
    ])
    assert report["attempt_count"] == 6
    assert report["revision_scoped_task_count"] == 5
    group = report["groups"][0]
    assert group["attempt_count"] == 5
    assert group["task_count"] == 4
    assert group["task_outcomes"]["satisfied"] == 1
    assert group["unlinked_attempt_count"] == 2


def test_revision_and_task_type_remain_separate():
    report = evaluate_tasks([_row(), _row("b", task_type="diet_photo"),
                             _row("c", revision="b" * 40)])
    assert len(report["groups"]) == 3


def test_missing_latency_and_cost_are_not_zero():
    group = evaluate_tasks([_row(), _row("b", task_elapsed_ms=80, cost_cny=0,
                                         cost_source="priced_usage")])["groups"][0]
    assert group["latency"]["task_elapsed_ms"] == {
        "sample_count": 1, "missing_count": 1, "p50_ms": 80,
        "p95_ms": None, "p95_status": "insufficient_samples",
    }
    assert group["cost"]["known_subtotal_cny"] == 0
    assert group["cost"]["total_cny"] is None
    assert group["cost"]["missing_attempt_count"] == 1
    assert group["cost"]["coverage"] == 0.5


def test_percentiles_are_not_estimated_from_progress_or_retry_sums():
    rows = [_row(str(i), task_elapsed_ms=(i + 1) * 10,
                 verified_content_latency_ms=(i + 1), cost_cny=0.1,
                 cost_source="estimate") for i in range(20)]
    group = evaluate_tasks(rows)["groups"][0]
    assert group["latency"]["task_elapsed_ms"]["p50_ms"] == 105
    assert group["latency"]["task_elapsed_ms"]["p95_ms"] == 190.5
    assert group["latency"]["verified_content_latency_ms"]["p95_ms"] == 19.05
    assert group["cost"]["total_cny"] == 2


def test_cost_overflow_fails_loudly():
    with pytest.raises(ValueError, match="numeric range"):
        evaluate_tasks([_row("a", cost_cny=1e308, cost_source="estimate"),
                        _row("b", cost_cny=1e308, cost_source="estimate")])


def test_tool_failure_and_reviewed_blocks_are_separate_counts():
    group = evaluate_tasks([_row(tool_failures=2, reviewed_appropriate_blocks=3,
                                 unreviewed_blocks=4)])["groups"][0]
    assert group["tool_events"] == {
        "tool_failures": 2, "reviewed_appropriate_blocks": 3, "unreviewed_blocks": 4,
    }


def test_missing_tool_observations_are_not_counted_as_zero_events():
    group = evaluate_tasks([_row(), _row("b", tool_failures=0)])["groups"][0]
    assert group["tool_events"]["tool_failures"] == 0
    assert group["tool_events"]["reviewed_appropriate_blocks"] is None
    assert group["tool_event_coverage"]["tool_failures"] == {
        "observed_attempt_count": 1, "missing_attempt_count": 1,
    }


def test_duplicate_attempt_snapshots_do_not_double_count():
    row = _row(cost_cny=0.3, cost_source="priced_usage")
    report = evaluate_tasks([row, dict(row)])
    assert report["attempt_count"] == 1
    assert report["duplicate_snapshot_count"] == 1
    assert report["groups"][0]["cost"]["total_cny"] == 0.3


@pytest.mark.parametrize("overrides", [
    {"content": "synthetic private content"}, {"user_id": 1},
    {"task_elapsed_ms": float("nan")}, {"cost_cny": -1},
    {"tool_failures": True}, {"technical_status": "made_up"},
    {"revision": "private-name"}, {"task_type": "private-name"},
    {"task_outcome": "satisfied", "human_verified": False},
    {"cost_cny": 0.2},
    {"task_type": []}, {"cost_cny": 0, "cost_source": []},
    {"task_elapsed_ms": 10 ** 1000},
])
def test_invalid_or_sensitive_metadata_fails_closed(overrides):
    with pytest.raises(ValueError):
        evaluate_tasks([_row(**overrides)])


def test_conflicting_attempt_snapshot_and_ambiguous_order_fail_closed():
    with pytest.raises(ValueError):
        evaluate_tasks([_row(), _row(technical_status="failed")])
    with pytest.raises(ValueError):
        evaluate_tasks([_row(logical_task_id=_id("task")),
                        _row("b", logical_task_id=_id("task"))])
    with pytest.raises(ValueError):
        evaluate_tasks([_row(logical_task_id=_id("task")),
                        _row("b", logical_task_id=_id("task"),
                             attempt_index=2, task_type="diet_photo")])


def test_empty_input_retains_explicit_zero_denominators():
    report = evaluate_tasks([])
    assert report["attempt_count"] == 0
    assert report["groups"] == []


def test_cli_outputs_aggregates_without_identity_or_original_fields(tmp_path):
    root = Path(__file__).resolve().parents[2]
    input_file = tmp_path / "tasks.jsonl"
    row = _row()
    input_file.write_text(json.dumps(row) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(root / "scripts/evaluate_agent_tasks.py"),
                             str(input_file)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["attempt_count"] == 1
    assert row["scope_id"] not in result.stdout
    assert row["attempt_id"] not in result.stdout


def test_cli_rejects_private_fields_without_echoing_values(tmp_path):
    root = Path(__file__).resolve().parents[2]
    input_file = tmp_path / "tasks.json"
    input_file.write_text(json.dumps([_row(content="PRIVATE-SYNTHETIC-TEXT")]), encoding="utf-8")
    result = subprocess.run([sys.executable, str(root / "scripts/evaluate_agent_tasks.py"),
                             str(input_file)], capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "PRIVATE-SYNTHETIC-TEXT" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("status", ["queued", "reconciliation_required"])
def test_all_persisted_agent_run_states_are_reportable(status):
    group = evaluate_tasks([_row(technical_status=status)])["groups"][0]
    assert group["technical_statuses"][status] == 1
    assert group["task_outcomes"]["unknown"] == 1


def test_explicit_resolution_statuses_are_distinct_from_technical_and_human_outcomes():
    statuses = ["completed", "no_data", "appropriate_refusal", "blocked", "pending_confirmation"]
    rows = [_row(str(i), resolution_status=status) for i, status in enumerate(statuses)]
    rows.append(_row("unclassified", technical_status="waiting_for_user"))
    group = evaluate_tasks(rows)["groups"][0]
    assert group["resolution_statuses"] == {**dict.fromkeys(statuses, 1), "unknown": 1}
    assert group["task_outcomes"] == {"satisfied": 0, "failed": 0, "unknown": 6}
    assert group["verified_satisfaction_rate"] is None
    assert group["cost"]["total_cny"] is None
    assert group["cost"]["known_subtotal_cny"] is None
    assert group["cost"]["sources"] == {"missing": 6}


def test_resolution_uses_latest_attempt_within_revision_and_preserves_unknown():
    logical = _id("logical")
    rows = [
        _row("a", logical_task_id=logical, resolution_status="blocked"),
        _row("b", logical_task_id=logical, attempt_index=2, resolution_status="no_data"),
        _row("c", logical_task_id=logical, revision="b" * 40,
             technical_status="waiting_for_user"),
    ]
    groups = evaluate_tasks(rows)["groups"]
    assert groups[0]["resolution_statuses"]["no_data"] == 1
    assert groups[0]["resolution_statuses"]["blocked"] == 0
    assert groups[1]["resolution_statuses"]["unknown"] == 1
    assert groups[1]["resolution_statuses"]["pending_confirmation"] == 0


@pytest.mark.parametrize("value", ["diagnosed", "PRIVATE-SYNTHETIC-TEXT", [], None, True])
def test_resolution_is_a_closed_metadata_enum(value):
    with pytest.raises(ValueError, match="invalid or unsupported metadata"):
        evaluate_tasks([_row(resolution_status=value)])
