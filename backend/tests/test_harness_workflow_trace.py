from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_trace_module():
    spec = importlib.util.spec_from_file_location(
        "harness_workflow_trace", ROOT / "scripts" / "harness_workflow_trace.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_init_creates_persistent_workflow_ledger(tmp_path, capsys):
    trace = _load_trace_module()

    assert trace.main([
        "init",
        "--run-dir", str(tmp_path),
        "--run-id", "wf-test",
        "--kind", "product-pipeline",
        "--dossier", "docs/dossiers/example.md",
        "--budget-tokens", "1000",
        "--label", "example flow",
    ]) == 0

    out = json.loads(capsys.readouterr().out)
    run_path = Path(out["run_path"])
    events = _read_jsonl(run_path)

    assert run_path.name == "wf-test.jsonl"
    assert events == [{
        "sequence": 0,
        "event": "run_started",
        "run_id": "wf-test",
        "kind": "product-pipeline",
        "dossier": "docs/dossiers/example.md",
        "budget_tokens": 1000,
        "label": "example flow",
    }]


def test_event_appends_trace_and_summary_tracks_budget_and_checkpoint(tmp_path, capsys):
    trace = _load_trace_module()
    trace.main([
        "init",
        "--run-dir", str(tmp_path),
        "--run-id", "wf-test",
        "--kind", "health-harness",
        "--budget-tokens", "500",
    ])
    run_path = tmp_path / "wf-test.jsonl"

    assert trace.main([
        "event",
        "--run", str(run_path),
        "--event", "spawn",
        "--agent", "backend-engineer",
        "--phase", "Phase 2",
        "--status", "started",
        "--tokens", "120",
    ]) == 0
    assert trace.main([
        "event",
        "--run", str(run_path),
        "--event", "checkpoint",
        "--phase", "Phase 3",
        "--status", "qa-ready",
        "--tokens", "30",
    ]) == 0
    assert trace.main(["summary", "--run", str(run_path)]) == 0

    summary = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert summary["run_id"] == "wf-test"
    assert summary["event_count"] == 3
    assert summary["total_tokens"] == 150
    assert summary["budget_remaining"] == 350
    assert summary["latest_checkpoint"]["phase"] == "Phase 3"
    assert summary["agents"] == ["backend-engineer"]


def test_budget_exceeded_is_fail_loud_and_persisted(tmp_path):
    trace = _load_trace_module()
    trace.main([
        "init",
        "--run-dir", str(tmp_path),
        "--run-id", "wf-test",
        "--kind", "health-harness",
        "--budget-tokens", "100",
    ])
    run_path = tmp_path / "wf-test.jsonl"

    assert trace.main([
        "event",
        "--run", str(run_path),
        "--event", "spawn",
        "--agent", "qa-verifier",
        "--tokens", "101",
    ]) == 2

    events = _read_jsonl(run_path)
    assert events[-1]["event"] == "budget_exceeded"
    assert events[-1]["projected_tokens"] == 101
    assert events[-1]["budget_tokens"] == 100
    assert events[-1]["agent"] == "qa-verifier"


def test_typed_spawn_and_verdict_commands_track_open_agents(tmp_path, capsys):
    trace = _load_trace_module()
    trace.main([
        "init",
        "--run-dir", str(tmp_path),
        "--run-id", "wf-test",
        "--kind", "health-harness",
        "--budget-tokens", "500",
    ])
    run_path = tmp_path / "wf-test.jsonl"

    assert trace.main([
        "spawn",
        "--run", str(run_path),
        "--agent", "backend-engineer",
        "--task-id", "task-backend",
        "--phase", "S5",
        "--tokens", "90",
        "--message", "implement API shape",
    ]) == 0
    assert trace.main([
        "spawn",
        "--run", str(run_path),
        "--agent", "qa-verifier",
        "--task-id", "task-qa",
        "--phase", "G3",
        "--tokens", "40",
    ]) == 0
    assert trace.main([
        "verdict",
        "--run", str(run_path),
        "--agent", "backend-engineer",
        "--task-id", "task-backend",
        "--phase", "G3",
        "--status", "passed",
        "--tokens", "20",
    ]) == 0
    assert trace.main(["summary", "--run", str(run_path)]) == 0

    events = _read_jsonl(run_path)
    summary = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert events[1]["event"] == "spawn"
    assert events[1]["task_id"] == "task-backend"
    assert events[3]["event"] == "verdict"
    assert events[3]["task_id"] == "task-backend"
    assert summary["spawn_count"] == 2
    assert summary["verdict_count"] == 1
    assert summary["open_agents"] == ["qa-verifier"]
    assert summary["open_tasks"] == ["task-qa"]


def test_explicit_budget_extension_is_append_only_and_preserves_usage(tmp_path):
    trace = _load_trace_module()
    path = tmp_path / "run.jsonl"
    trace._append(path, {"sequence": 0, "event": "run_started", "budget_tokens": 100})
    trace._append(path, {"sequence": 1, "event": "spawn", "tokens": 100})
    original = path.read_bytes()
    assert trace.main(["extend-budget", "--run", str(path), "--additional-tokens", "50",
                       "--authorization", "Explicit user approval for 50 additional tokens"]) == 0
    assert path.read_bytes().startswith(original)
    summary = trace._summarize(trace._read_events(path))
    assert (summary["total_tokens"], summary["budget_tokens"], summary["budget_remaining"]) == (100, 150, 50)
    assert trace._append_checked_event(path, {"event": "spawn", "tokens": 51}) == 2


def test_invalid_budget_extensions_leave_ledger_unchanged(tmp_path):
    import pytest
    trace = _load_trace_module()
    path = tmp_path / "run.jsonl"
    trace._append(path, {"sequence": 0, "event": "run_started", "budget_tokens": 100})
    original = path.read_bytes()
    for amount, authorization in (("0", "approved"), ("-1", "approved"), ("50", " ")):
        with pytest.raises(ValueError):
            trace.main(["extend-budget", "--run", str(path), "--additional-tokens", amount,
                        "--authorization", authorization])
        assert path.read_bytes() == original


def _delivery_args(path):
    return ["delivery", "--run", str(path), "--candidate-sha", "a" * 40,
            "--target", "ota", "--stage", "publish", "--status", "unknown",
            "--claim-state", "consumed", "--evidence", "docs/reviews/ota-receipt.json"]


def test_delivery_index_preserves_attempts_and_never_grants_release_authority(tmp_path):
    trace = _load_trace_module()
    path = tmp_path / "run.jsonl"
    trace._append(path, {"event": "run_started"})
    for attempt in ("1", "2"):
        assert trace.main(_delivery_args(path) + ["--ci-run-id", "123", "--ci-attempt", attempt]) == 0
    summary = trace._summarize(trace._read_events(path))
    deliveries = summary["delivery_references"]
    assert [item["ci_attempt"] for item in deliveries] == [1, 2]
    assert all(item["authority"] == "unverified_index_only" for item in deliveries)
    assert deliveries[-1]["next_action"] == "inspect_original_receipt_do_not_republish"
    assert "delivery_complete" not in summary


def test_delivery_rejects_invalid_or_sensitive_fields_without_writing(tmp_path):
    import pytest
    trace = _load_trace_module()
    path = tmp_path / "run.jsonl"
    trace._append(path, {"event": "run_started"})
    original = path.read_bytes()
    for extra in (["--candidate-sha", "main"], ["--evidence", "https://host/a?token=secret"],
                  ["--evidence", "docs/reviews/../../.env-online"], ["--ci-attempt", "0"],
                  ["--operation-id", "secret token"], ["--ended-at", "yesterday"]):
        with pytest.raises(ValueError):
            trace.main(_delivery_args(path) + extra)
        assert path.read_bytes() == original


def test_uploaded_and_green_are_only_observations(tmp_path):
    trace = _load_trace_module()
    path = tmp_path / "run.jsonl"
    trace._append(path, {"event": "run_started"})
    assert trace.main(_delivery_args(path) + ["--target", "testflight", "--stage", "upload",
                     "--status", "succeeded", "--claim-state", "unknown"]) == 0
    entry = trace._summarize(trace._read_events(path))["delivery_references"][0]
    assert entry["next_action"] == "verify_original_evidence_and_remaining_gates"


def test_delivery_summary_revalidates_manually_appended_assertions():
    import pytest
    trace = _load_trace_module()
    with pytest.raises(ValueError):
        trace._summarize([{"event": "run_started"}, {"event": "delivery_reference", "status": "complete"}])


def test_packaged_trace_matches_canonical():
    assert (ROOT / "scripts/harness_workflow_trace.py").read_bytes() == (
        ROOT / "plugins/reva-health-harness/scripts/harness_workflow_trace.py").read_bytes()


def test_delivery_retains_receipt_identifiers_and_rejects_reversed_time(tmp_path):
    import pytest
    trace = _load_trace_module()
    path = tmp_path / "run.jsonl"
    trace._append(path, {"event": "run_started"})
    identifier = "12345678-1234-1234-1234-123456789abc"
    args = _delivery_args(path) + ["--operation-id", "c" * 32, "--build-id", identifier,
                                  "--update-id", identifier, "--started-at", "2026-10-10T01:00:00Z",
                                  "--ended-at", "2026-10-10T01:05:00Z"]
    assert trace.main(args) == 0
    observation = trace._summarize(trace._read_events(path))["delivery_references"][0]
    assert observation["build_id"] == observation["update_id"] == identifier
    assert observation["operation_id"] == "c" * 32
    before = path.read_bytes()
    with pytest.raises(ValueError):
        trace.main(args + ["--ended-at", "2026-10-09T01:05:00Z"])
    assert path.read_bytes() == before
