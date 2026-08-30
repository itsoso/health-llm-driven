from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent_skill_benchmark.py"
SCHEMA = ROOT / "docs" / "governance" / "agent-skill-run-trace-event.schema.json"
ARMS = {"transition_v0_observational", "router_v1_prospective"}
TASK_MODES = {
    "analysis",
    "quick_fix",
    "feature",
    "implementation",
    "incident",
    "release",
}
STAGES = {
    "run_started",
    "route_selected",
    "root_cause_identified",
    "red_test_observed",
    "green_test_observed",
    "g3_decided",
    "g4_decided",
    "g5_decided",
    "g6_decided",
    "manual_intervention",
    "run_finished",
}
SHA = {
    "source": "1" * 64,
    "registry": "2" * 64,
    "route": "3" * 64,
    "evidence": "4" * 64,
}


@pytest.fixture(autouse=True)
def _isolate_twin_cache():
    """Override the repository Redis fixture for this pure file-contract suite."""
    yield


@pytest.fixture(autouse=True)
def _noop_twin_cache():
    """Avoid runtime Twin cache patching in benchmark collector tests."""
    yield


def _load_module():
    spec = importlib.util.spec_from_file_location("agent_skill_benchmark", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _event_hash(event: dict) -> str:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _start_cli(
    log: Path,
    *,
    arm: str = "router_v1_prospective",
    task_mode: str = "quick_fix",
) -> dict:
    result = _run(
        "start",
        "--log",
        str(log),
        "--arm",
        arm,
        "--task-mode",
        task_mode,
        "--source-sha256",
        SHA["source"],
        "--registry-sha256",
        SHA["registry"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _mark_cli(
    log: Path,
    run_id: str,
    stage: str,
    outcome: str = "pass",
    *,
    route_sha256: str | None = None,
) -> dict:
    args = [
        "mark",
        "--log",
        str(log),
        "--run-id",
        run_id,
        "--stage",
        stage,
        "--outcome",
        outcome,
        "--evidence-sha256",
        SHA["evidence"],
    ]
    if route_sha256 is not None:
        args += ["--route-sha256", route_sha256]
    result = _run(*args)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _complete_run(
    benchmark,
    log: Path,
    *,
    arm: str,
    task_mode: str = "quick_fix",
    omit_stages: frozenset[str] = frozenset(),
) -> dict:
    started = benchmark.start_run(
        log,
        arm=arm,
        task_mode=task_mode,
        source_sha256=SHA["source"],
        registry_sha256=SHA["registry"],
    )
    if arm == "router_v1_prospective":
        benchmark.mark_run(
            log,
            run_id=started["run_id"],
            stage="route_selected",
            outcome="pass",
            evidence_sha256=SHA["evidence"],
            route_sha256=SHA["route"],
        )
    for stage in ("g3_decided", "g4_decided", "g5_decided", "g6_decided"):
        if stage not in omit_stages:
            benchmark.mark_run(
                log,
                run_id=started["run_id"],
                stage=stage,
                outcome="pass",
                evidence_sha256=SHA["evidence"],
            )
    if "run_finished" not in omit_stages:
        benchmark.mark_run(
            log,
            run_id=started["run_id"],
            stage="run_finished",
            outcome="pass",
            evidence_sha256=SHA["evidence"],
        )
    return started


def test_trace_schema_is_closed_opaque_and_contains_no_free_text_channels():
    assert SCHEMA.is_file()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["$id"] == "agent-skill-run-trace-event.v1"
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert set(properties["arm"]["enum"]) == ARMS
    assert set(properties["task_mode"]["enum"]) == TASK_MODES
    assert set(properties["stage"]["enum"]) == STAGES
    assert properties["run_id"]["pattern"] == properties["task_id"]["pattern"]
    assert "[1-5]" not in properties["run_id"]["pattern"]
    assert "4" in properties["run_id"]["pattern"]

    assert {
        "source_sha256",
        "registry_sha256",
        "route_sha256",
        "evidence_sha256",
        "prev_event_sha256",
        "event_sha256",
    } <= set(properties)
    for name in (
        "source_sha256",
        "registry_sha256",
        "event_sha256",
    ):
        assert properties[name]["pattern"] == "^[0-9a-f]{64}$"

    serialized = json.dumps(schema).lower()
    for forbidden in (
        '"prompt"',
        '"health_text"',
        '"path"',
        '"reason"',
        '"notes"',
        '"description"',
        '"duration_ms"',
    ):
        assert forbidden not in serialized


def test_start_requires_an_explicit_log_path_and_never_writes_to_cwd(tmp_path: Path):
    result = _run(
        "start",
        "--arm",
        "router_v1_prospective",
        "--task-mode",
        "quick_fix",
        "--source-sha256",
        SHA["source"],
        "--registry-sha256",
        SHA["registry"],
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert list(tmp_path.iterdir()) == []


def test_start_cli_and_api_require_an_explicit_closed_task_mode(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    missing_cli_mode = _run(
        "start",
        "--log",
        str(log),
        "--arm",
        "router_v1_prospective",
        "--source-sha256",
        SHA["source"],
        "--registry-sha256",
        SHA["registry"],
    )

    assert missing_cli_mode.returncode != 0
    assert not log.exists() or log.read_bytes() == b""

    invalid_cli_mode = _run(
        "start",
        "--log",
        str(log),
        "--arm",
        "router_v1_prospective",
        "--task-mode",
        "bugfix",
        "--source-sha256",
        SHA["source"],
        "--registry-sha256",
        SHA["registry"],
    )
    assert invalid_cli_mode.returncode != 0
    assert not log.exists() or log.read_bytes() == b""

    benchmark = _load_module()
    with pytest.raises(TypeError):
        benchmark.start_run(
            log,
            arm="router_v1_prospective",
            source_sha256=SHA["source"],
            registry_sha256=SHA["registry"],
        )
    with pytest.raises(benchmark.BenchmarkError, match="task_mode"):
        benchmark.start_run(
            log,
            arm="router_v1_prospective",
            task_mode="bugfix",
            source_sha256=SHA["source"],
            registry_sha256=SHA["registry"],
        )
    assert not log.exists() or log.read_bytes() == b""


def test_start_generates_opaque_uuid4_ids_timestamp_sequence_and_hash(tmp_path: Path):
    log = tmp_path / "trace.jsonl"

    emitted = _start_cli(log)
    records = _events(log)

    assert records == [emitted]
    assert uuid.UUID(emitted["run_id"]).version == 4
    assert uuid.UUID(emitted["task_id"]).version == 4
    assert emitted["run_id"] == str(uuid.UUID(emitted["run_id"]))
    assert emitted["task_id"] == str(uuid.UUID(emitted["task_id"]))
    assert emitted["sequence"] == 1
    assert emitted["stage"] == "run_started"
    assert emitted["outcome"] == "pending"
    assert emitted["task_mode"] == "quick_fix"
    assert emitted["timestamp_utc"].endswith("Z")
    assert emitted["route_sha256"] is None
    assert emitted["evidence_sha256"] is None
    assert emitted["prev_event_sha256"] is None
    assert emitted["event_sha256"] == _event_hash(emitted)


def test_supplied_run_and_task_ids_must_be_canonical_uuid4(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    result = _run(
        "start",
        "--log",
        str(log),
        "--arm",
        "router_v1_prospective",
        "--task-mode",
        "quick_fix",
        "--run-id",
        "meal-two-bowls",
        "--task-id",
        str(uuid.uuid4()).upper(),
        "--source-sha256",
        SHA["source"],
        "--registry-sha256",
        SHA["registry"],
    )

    assert result.returncode != 0
    assert not log.exists() or log.read_bytes() == b""


def test_mark_only_appends_and_extends_the_global_hash_chain(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    started = _start_cli(log)
    prefix = log.read_bytes()

    emitted = _mark_cli(
        log,
        started["run_id"],
        "route_selected",
        route_sha256=SHA["route"],
    )
    records = _events(log)

    assert log.read_bytes().startswith(prefix)
    assert len(records) == 2
    assert emitted == records[-1]
    assert emitted["sequence"] == 2
    assert emitted["run_id"] == started["run_id"]
    assert emitted["task_id"] == started["task_id"]
    assert emitted["task_mode"] == started["task_mode"]
    assert emitted["route_sha256"] == SHA["route"]
    assert emitted["evidence_sha256"] == SHA["evidence"]
    assert emitted["prev_event_sha256"] == started["event_sha256"]
    assert emitted["event_sha256"] == _event_hash(emitted)


def test_cli_has_no_raw_reason_path_or_caller_duration_channel(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    started = _start_cli(log)

    result = _run(
        "mark",
        "--log",
        str(log),
        "--run-id",
        started["run_id"],
        "--stage",
        "root_cause_identified",
        "--outcome",
        "pass",
        "--evidence-sha256",
        SHA["evidence"],
        "--reason",
        "changed two bowls",
        "--source-path",
        "/private/health-record",
        "--duration-ms",
        "1",
    )

    assert result.returncode != 0
    assert len(_events(log)) == 1


def test_router_arm_cannot_record_work_before_a_hashed_route(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    started = _start_cli(log)

    result = _run(
        "mark",
        "--log",
        str(log),
        "--run-id",
        started["run_id"],
        "--stage",
        "root_cause_identified",
        "--outcome",
        "pass",
        "--evidence-sha256",
        SHA["evidence"],
    )

    assert result.returncode != 0
    assert "route" in result.stderr.lower()
    assert len(_events(log)) == 1


def test_router_failure_can_finish_blocked_without_inventing_a_route_hash(
    tmp_path: Path,
):
    log = tmp_path / "trace.jsonl"
    started = _start_cli(log)

    finished = _mark_cli(log, started["run_id"], "run_finished", "blocked")

    assert finished["route_sha256"] is None
    assert finished["outcome"] == "blocked"


def test_report_durations_are_derived_only_from_collector_timestamps(tmp_path: Path):
    benchmark = _load_module()
    log = tmp_path / "trace.jsonl"
    task_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    first = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    moments = iter(
        first + timedelta(seconds=value) for value in (0, 2, 5, 8, 13, 21, 34)
    )
    benchmark._utc_now = lambda: next(moments)

    benchmark.start_run(
        log,
        arm="router_v1_prospective",
        task_mode="quick_fix",
        source_sha256=SHA["source"],
        registry_sha256=SHA["registry"],
        run_id=run_id,
        task_id=task_id,
    )
    benchmark.mark_run(
        log,
        run_id=run_id,
        stage="route_selected",
        outcome="pass",
        evidence_sha256=SHA["evidence"],
        route_sha256=SHA["route"],
    )
    benchmark.mark_run(
        log,
        run_id=run_id,
        stage="root_cause_identified",
        outcome="pass",
        evidence_sha256=SHA["evidence"],
    )
    benchmark.mark_run(
        log,
        run_id=run_id,
        stage="red_test_observed",
        outcome="pass",
        evidence_sha256=SHA["evidence"],
    )
    benchmark.mark_run(
        log,
        run_id=run_id,
        stage="green_test_observed",
        outcome="pass",
        evidence_sha256=SHA["evidence"],
    )
    benchmark.mark_run(
        log,
        run_id=run_id,
        stage="g5_decided",
        outcome="pass",
        evidence_sha256=SHA["evidence"],
    )
    benchmark.mark_run(
        log,
        run_id=run_id,
        stage="g6_decided",
        outcome="pass",
        evidence_sha256=SHA["evidence"],
    )

    report = benchmark.build_report(log)
    metrics = report["arms"]["router_v1_prospective"]["duration_metrics_ms"]

    assert metrics["time_to_route"]["median"] == 2_000
    assert metrics["time_to_root_cause"]["median"] == 5_000
    assert metrics["time_to_red"]["median"] == 8_000
    assert metrics["time_to_green"]["median"] == 13_000
    assert metrics["time_to_g5"]["median"] == 21_000
    assert metrics["time_to_g6"]["median"] == 34_000
    assert all("duration" not in event for event in _events(log))


def test_success_durations_use_first_pass_and_ignore_failed_only_stages(
    tmp_path: Path,
):
    benchmark = _load_module()
    log = tmp_path / "trace.jsonl"
    first = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    moments = iter(
        first + timedelta(seconds=value) for value in (0, 1, 3, 5, 8, 13, 21)
    )
    benchmark._utc_now = lambda: next(moments)

    started = benchmark.start_run(
        log,
        arm="transition_v0_observational",
        task_mode="quick_fix",
        source_sha256=SHA["source"],
        registry_sha256=SHA["registry"],
    )
    for stage, outcome in (
        ("root_cause_identified", "fail"),
        ("root_cause_identified", "pass"),
        ("g4_decided", "fail"),
        ("g4_decided", "pass"),
        ("g5_decided", "fail"),
        ("run_finished", "fail"),
    ):
        benchmark.mark_run(
            log,
            run_id=started["run_id"],
            stage=stage,
            outcome=outcome,
            evidence_sha256=SHA["evidence"],
        )

    metrics = benchmark.build_report(log)["arms"]["transition_v0_observational"][
        "duration_metrics_ms"
    ]

    assert metrics["time_to_root_cause"]["median"] == 3_000
    assert metrics["time_to_g4"]["median"] == 8_000
    assert metrics["time_to_g5"]["sample_count"] == 0
    assert metrics["time_to_finish"]["sample_count"] == 0


def test_report_never_claims_superiority_with_pending_g6(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    for arm in sorted(ARMS):
        started = _start_cli(log, arm=arm)
        if arm == "router_v1_prospective":
            _mark_cli(
                log,
                started["run_id"],
                "route_selected",
                route_sha256=SHA["route"],
            )

    result = _run("report", "--log", str(log))
    assert result.returncode == 0, result.stdout + result.stderr
    comparison = json.loads(result.stdout)["comparison"]

    assert comparison["status"] == "insufficient_evidence"
    assert comparison["superiority_claim"] is False
    assert comparison["winner"] is None
    assert "g6_unresolved" in comparison["blocking_reason_codes"]


def test_report_never_claims_superiority_from_one_run_per_arm(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    for arm in sorted(ARMS):
        started = _start_cli(log, arm=arm)
        if arm == "router_v1_prospective":
            _mark_cli(
                log,
                started["run_id"],
                "route_selected",
                route_sha256=SHA["route"],
            )
        _mark_cli(log, started["run_id"], "g6_decided")

    result = _run("report", "--log", str(log))
    assert result.returncode == 0, result.stdout + result.stderr
    comparison = json.loads(result.stdout)["comparison"]

    assert comparison["status"] == "insufficient_evidence"
    assert comparison["superiority_claim"] is False
    assert comparison["winner"] is None
    assert "minimum_sample_size_not_met" in comparison["blocking_reason_codes"]


def test_report_is_insufficient_when_task_mode_distributions_do_not_match(
    tmp_path: Path,
):
    benchmark = _load_module()
    log = tmp_path / "trace.jsonl"
    for _ in range(5):
        _complete_run(
            benchmark,
            log,
            arm="transition_v0_observational",
            task_mode="quick_fix",
        )
    for index in range(5):
        _complete_run(
            benchmark,
            log,
            arm="router_v1_prospective",
            task_mode="incident" if index == 0 else "quick_fix",
        )

    comparison = benchmark.build_report(log)["comparison"]

    assert comparison["status"] == "insufficient_evidence"
    assert "task_mode_distribution_mismatch" in comparison["blocking_reason_codes"]
    assert comparison["audit"]["task_mode_distribution_matched"] is False
    assert comparison["audit"]["task_mode_counts"] == {
        "transition_v0_observational": {
            mode: 5 if mode == "quick_fix" else 0 for mode in sorted(TASK_MODES)
        },
        "router_v1_prospective": {
            mode: (4 if mode == "quick_fix" else 1 if mode == "incident" else 0)
            for mode in sorted(TASK_MODES)
        },
    }


def test_report_is_insufficient_for_unfinished_or_unresolved_gate_runs(
    tmp_path: Path,
):
    benchmark = _load_module()
    log = tmp_path / "trace.jsonl"
    all_missing = frozenset(
        {
            "g3_decided",
            "g4_decided",
            "g5_decided",
            "g6_decided",
            "run_finished",
        }
    )
    for arm in sorted(ARMS):
        for index in range(5):
            _complete_run(
                benchmark,
                log,
                arm=arm,
                omit_stages=all_missing if index == 0 else frozenset(),
            )

    report = benchmark.build_report(log)
    comparison = report["comparison"]

    assert comparison["status"] == "insufficient_evidence"
    assert set(comparison["blocking_reason_codes"]) >= {
        "unfinished_run",
        "g3_unresolved",
        "g4_unresolved",
        "g5_unresolved",
        "g6_unresolved",
    }
    for arm in ARMS:
        assert report["arms"][arm]["unfinished_count"] == 1
        assert report["arms"][arm]["unresolved_stage_counts"] == {
            "g3_decided": 1,
            "g4_decided": 1,
            "g5_decided": 1,
            "g6_decided": 1,
        }


def test_balanced_five_per_arm_is_only_descriptive_and_auditable_by_task_mode(
    tmp_path: Path,
):
    benchmark = _load_module()
    log = tmp_path / "trace.jsonl"
    for arm in sorted(ARMS):
        for _ in range(5):
            _complete_run(benchmark, log, arm=arm, task_mode="quick_fix")

    report = benchmark.build_report(log)
    comparison = report["comparison"]

    assert comparison == {
        "status": "descriptive_only",
        "superiority_claim": False,
        "winner": None,
        "reason_code": "automatic_superiority_not_supported",
        "blocking_reason_codes": [],
        "audit": {
            "minimum_runs_per_arm": 5,
            "run_counts": {arm: 5 for arm in sorted(ARMS)},
            "task_mode_counts": {
                arm: {
                    mode: 5 if mode == "quick_fix" else 0 for mode in sorted(TASK_MODES)
                }
                for arm in sorted(ARMS)
            },
            "task_mode_distribution_matched": True,
            "unfinished_counts": {arm: 0 for arm in sorted(ARMS)},
            "unresolved_stage_counts": {
                arm: {
                    "g3_decided": 0,
                    "g4_decided": 0,
                    "g5_decided": 0,
                    "g6_decided": 0,
                }
                for arm in sorted(ARMS)
            },
        },
    }
    for arm in ARMS:
        assert report["arms"][arm]["task_mode_counts"]["quick_fix"] == 5
        mode_report = report["arms"][arm]["task_modes"]["quick_fix"]
        assert mode_report["run_count"] == 5
        assert mode_report["duration_metrics_ms"]["time_to_g5"]["sample_count"] == 5


def test_report_rejects_a_tampered_event_chain(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    _start_cli(log)
    record = _events(log)[0]
    record["arm"] = "transition_v0_observational"
    log.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = _run("report", "--log", str(log))

    assert result.returncode != 0
    assert "hash" in result.stderr.lower()


def test_report_rejects_non_collector_timestamp_shape_even_with_a_valid_hash(
    tmp_path: Path,
):
    log = tmp_path / "trace.jsonl"
    _start_cli(log)
    record = _events(log)[0]
    record["timestamp_utc"] = "2026-08-20T12:00:00Z"
    record["event_sha256"] = _event_hash(record)
    log.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = _run("report", "--log", str(log))

    assert result.returncode != 0
    assert "timestamp" in result.stderr.lower()


@pytest.mark.parametrize(
    ("stage", "outcome"),
    [
        ("run_started", "pass"),
        ("g6_decided", "pending"),
        ("manual_intervention", "pass"),
        ("run_finished", "pending"),
    ],
)
def test_mark_rejects_illegal_stage_outcome_pairs(
    tmp_path: Path, stage: str, outcome: str
):
    log = tmp_path / "trace.jsonl"
    started = _start_cli(log, arm="transition_v0_observational")

    result = _run(
        "mark",
        "--log",
        str(log),
        "--run-id",
        started["run_id"],
        "--stage",
        stage,
        "--outcome",
        outcome,
        "--evidence-sha256",
        SHA["evidence"],
    )

    assert result.returncode != 0
    assert len(_events(log)) == 1
