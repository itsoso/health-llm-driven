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
