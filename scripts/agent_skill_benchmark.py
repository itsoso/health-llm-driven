#!/usr/bin/env python3
"""Append-only, privacy-minimal benchmark traces for Agent Skill routing."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import statistics
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, Sequence


SCHEMA_VERSION = "agent-skill-run-trace-event.v1"
REPORT_VERSION = "agent-skill-benchmark-report.v1"
ARMS = (
    "transition_v0_observational",
    "router_v1_prospective",
)
TASK_MODES = (
    "analysis",
    "quick_fix",
    "feature",
    "implementation",
    "incident",
    "release",
)
STAGES = (
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
)
OUTCOMES = (
    "pending",
    "pass",
    "fail",
    "blocked",
    "not_applicable",
    "cancelled",
)
EVENT_FIELDS = {
    "schema_version",
    "run_id",
    "task_id",
    "arm",
    "task_mode",
    "stage",
    "outcome",
    "timestamp_utc",
    "sequence",
    "source_sha256",
    "registry_sha256",
    "route_sha256",
    "evidence_sha256",
    "prev_event_sha256",
    "event_sha256",
}
LEGAL_OUTCOMES = {
    "run_started": {"pending"},
    "route_selected": {"pass"},
    "root_cause_identified": {"pass", "fail", "blocked"},
    "red_test_observed": {"pass", "fail", "blocked"},
    "green_test_observed": {"pass", "fail", "blocked"},
    "g3_decided": {"pass", "fail", "blocked", "not_applicable"},
    "g4_decided": {"pass", "fail", "blocked", "not_applicable"},
    "g5_decided": {"pass", "fail", "blocked", "not_applicable"},
    "g6_decided": {"pass", "fail", "blocked", "not_applicable"},
    "manual_intervention": {"not_applicable"},
    "run_finished": {"pass", "fail", "blocked", "cancelled"},
}
METRIC_STAGES = {
    "time_to_route": "route_selected",
    "time_to_root_cause": "root_cause_identified",
    "time_to_red": "red_test_observed",
    "time_to_green": "green_test_observed",
    "time_to_g3": "g3_decided",
    "time_to_g4": "g4_decided",
    "time_to_g5": "g5_decided",
    "time_to_g6": "g6_decided",
    "time_to_finish": "run_finished",
}
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"
)


class BenchmarkError(ValueError):
    """A closed-contract, integrity, or state transition failure."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise BenchmarkError("collector clock must be timezone-aware")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise BenchmarkError("timestamp_utc must be collector UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BenchmarkError("timestamp_utc is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise BenchmarkError("timestamp_utc must be UTC")
    return parsed


def _validate_uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise BenchmarkError(f"{name} must be an opaque canonical UUID4") from exc
    if parsed.version != 4 or value != str(parsed):
        raise BenchmarkError(f"{name} must be an opaque canonical UUID4")
    return value


def _validate_sha256(name: str, value: object, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BenchmarkError(f"{name} must be a lowercase SHA-256 hex digest")


def _canonical_payload(event: dict) -> bytes:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _event_hash(event: dict) -> str:
    return hashlib.sha256(_canonical_payload(event)).hexdigest()


@contextmanager
def _locked(path: Path, *, exclusive: bool, create: bool) -> Iterator[IO[str]]:
    mode = "a+" if create else ("r+" if exclusive else "r")
    try:
        handle = path.open(mode, encoding="utf-8")
    except OSError as exc:
        raise BenchmarkError("explicit trace log is unavailable") from exc
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield handle
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _read_events(handle: IO[str]) -> list[dict]:
    handle.seek(0)
    events: list[dict] = []
    for line_number, raw_line in enumerate(handle, start=1):
        if not raw_line.endswith("\n"):
            raise BenchmarkError(f"trace line {line_number} is not newline-terminated")
        if not raw_line.strip():
            raise BenchmarkError(f"trace line {line_number} is empty")
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"trace line {line_number} is invalid JSON") from exc
        if not isinstance(event, dict):
            raise BenchmarkError(f"trace line {line_number} is not an event object")
        events.append(event)
    _validate_chain(events)
    return events


def _validate_event_shape(event: dict, expected_sequence: int) -> None:
    if set(event) != EVENT_FIELDS:
        raise BenchmarkError(f"event sequence {expected_sequence} has unknown fields")
    if event["schema_version"] != SCHEMA_VERSION:
        raise BenchmarkError(f"event sequence {expected_sequence} has unknown schema")
    _validate_uuid4("run_id", event["run_id"])
    _validate_uuid4("task_id", event["task_id"])
    if not isinstance(event["arm"], str) or event["arm"] not in ARMS:
        raise BenchmarkError(f"event sequence {expected_sequence} has unknown arm")
    if not isinstance(event["task_mode"], str) or event["task_mode"] not in TASK_MODES:
        raise BenchmarkError(
            f"event sequence {expected_sequence} has unknown task_mode"
        )
    if not isinstance(event["stage"], str) or event["stage"] not in STAGES:
        raise BenchmarkError(f"event sequence {expected_sequence} has unknown stage")
    if (
        not isinstance(event["outcome"], str)
        or event["outcome"] not in LEGAL_OUTCOMES[event["stage"]]
    ):
        raise BenchmarkError(f"illegal stage/outcome at sequence {expected_sequence}")
    if type(event["sequence"]) is not int or event["sequence"] != expected_sequence:
        raise BenchmarkError(
            f"event sequence must be contiguous at {expected_sequence}"
        )
    _parse_timestamp(event["timestamp_utc"])
    _validate_sha256("source_sha256", event["source_sha256"])
    _validate_sha256("registry_sha256", event["registry_sha256"])
    _validate_sha256("route_sha256", event["route_sha256"], nullable=True)
    _validate_sha256("evidence_sha256", event["evidence_sha256"], nullable=True)
    _validate_sha256("prev_event_sha256", event["prev_event_sha256"], nullable=True)
    _validate_sha256("event_sha256", event["event_sha256"])


def _validate_chain(events: list[dict]) -> None:
    previous_hash: str | None = None
    previous_timestamp: datetime | None = None
    runs: dict[str, dict] = {}
    route_by_run: dict[str, str | None] = {}
    finished_runs: set[str] = set()

    for expected_sequence, event in enumerate(events, start=1):
        _validate_event_shape(event, expected_sequence)
        if event["prev_event_sha256"] != previous_hash:
            raise BenchmarkError(
                f"previous event hash mismatch at sequence {expected_sequence}"
            )
        if event["event_sha256"] != _event_hash(event):
            raise BenchmarkError(f"event hash mismatch at sequence {expected_sequence}")

        timestamp = _parse_timestamp(event["timestamp_utc"])
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise BenchmarkError(
                f"collector timestamp regressed at sequence {expected_sequence}"
            )

        run_id = event["run_id"]
        stage = event["stage"]
        if stage == "run_started":
            if run_id in runs:
                raise BenchmarkError(f"run {run_id} has duplicate starts")
            if (
                event["route_sha256"] is not None
                or event["evidence_sha256"] is not None
            ):
                raise BenchmarkError("run_started cannot carry route or evidence")
            runs[run_id] = event
            route_by_run[run_id] = None
        else:
            if run_id not in runs:
                raise BenchmarkError(f"run {run_id} has no start event")
            if run_id in finished_runs:
                raise BenchmarkError(f"run {run_id} has events after run_finished")
            start = runs[run_id]
            for field in (
                "task_id",
                "arm",
                "task_mode",
                "source_sha256",
                "registry_sha256",
            ):
                if event[field] != start[field]:
                    raise BenchmarkError(
                        f"run {run_id} changed immutable field {field}"
                    )
            if event["evidence_sha256"] is None:
                raise BenchmarkError(f"stage {stage} requires hashed evidence")

            current_route = route_by_run[run_id]
            if stage == "route_selected":
                if current_route is not None:
                    raise BenchmarkError(f"run {run_id} selected more than one route")
                if event["route_sha256"] is None:
                    raise BenchmarkError("route_selected requires route_sha256")
                route_by_run[run_id] = event["route_sha256"]
            elif event["route_sha256"] != current_route:
                raise BenchmarkError(f"run {run_id} changed route_sha256")

            if (
                start["arm"] == "router_v1_prospective"
                and stage != "route_selected"
                and route_by_run[run_id] is None
                and not _allowed_without_route(stage, event["outcome"])
            ):
                raise BenchmarkError(
                    "router arm requires a hashed route before work marks"
                )
            if stage == "run_finished":
                finished_runs.add(run_id)

        previous_hash = event["event_sha256"]
        previous_timestamp = timestamp


def _allowed_without_route(stage: str, outcome: str) -> bool:
    return stage == "manual_intervention" or (
        stage == "run_finished" and outcome in {"fail", "blocked", "cancelled"}
    )


def _new_event(
    *,
    run_id: str,
    task_id: str,
    arm: str,
    task_mode: str,
    stage: str,
    outcome: str,
    timestamp_utc: str,
    sequence: int,
    source_sha256: str,
    registry_sha256: str,
    route_sha256: str | None,
    evidence_sha256: str | None,
    prev_event_sha256: str | None,
) -> dict:
    event = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "arm": arm,
        "task_mode": task_mode,
        "stage": stage,
        "outcome": outcome,
        "timestamp_utc": timestamp_utc,
        "sequence": sequence,
        "source_sha256": source_sha256,
        "registry_sha256": registry_sha256,
        "route_sha256": route_sha256,
        "evidence_sha256": evidence_sha256,
        "prev_event_sha256": prev_event_sha256,
    }
    event["event_sha256"] = _event_hash(event)
    return event


def _append_event(handle: IO[str], event: dict) -> None:
    handle.seek(0, os.SEEK_END)
    encoded = json.dumps(
        event,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    handle.write(encoded + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _collector_timestamp(events: list[dict]) -> str:
    timestamp = _utc_now()
    if events and timestamp < _parse_timestamp(events[-1]["timestamp_utc"]):
        raise BenchmarkError("collector clock regressed behind the trace head")
    return _format_timestamp(timestamp)


def start_run(
    log_path: Path | str,
    *,
    arm: str,
    task_mode: str,
    source_sha256: str,
    registry_sha256: str,
    run_id: str | None = None,
    task_id: str | None = None,
) -> dict:
    if arm not in ARMS:
        raise BenchmarkError("arm is not in the closed benchmark vocabulary")
    if task_mode not in TASK_MODES:
        raise BenchmarkError("task_mode is not in the closed benchmark vocabulary")
    run_id = run_id or str(uuid.uuid4())
    task_id = task_id or str(uuid.uuid4())
    _validate_uuid4("run_id", run_id)
    _validate_uuid4("task_id", task_id)
    _validate_sha256("source_sha256", source_sha256)
    _validate_sha256("registry_sha256", registry_sha256)
    path = Path(log_path)

    with _locked(path, exclusive=True, create=True) as handle:
        events = _read_events(handle)
        if any(event["run_id"] == run_id for event in events):
            raise BenchmarkError(f"run_id {run_id} already exists")
        event = _new_event(
            run_id=run_id,
            task_id=task_id,
            arm=arm,
            task_mode=task_mode,
            stage="run_started",
            outcome="pending",
            timestamp_utc=_collector_timestamp(events),
            sequence=len(events) + 1,
            source_sha256=source_sha256,
            registry_sha256=registry_sha256,
            route_sha256=None,
            evidence_sha256=None,
            prev_event_sha256=events[-1]["event_sha256"] if events else None,
        )
        _append_event(handle, event)
    return event


def mark_run(
    log_path: Path | str,
    *,
    run_id: str,
    stage: str,
    outcome: str,
    evidence_sha256: str,
    route_sha256: str | None = None,
) -> dict:
    _validate_uuid4("run_id", run_id)
    if stage not in STAGES or stage == "run_started":
        raise BenchmarkError("mark stage is not in the closed mark vocabulary")
    if outcome not in LEGAL_OUTCOMES[stage]:
        raise BenchmarkError("illegal stage/outcome pair")
    _validate_sha256("evidence_sha256", evidence_sha256)
    if stage == "route_selected":
        _validate_sha256("route_sha256", route_sha256)
    elif route_sha256 is not None:
        raise BenchmarkError("route_sha256 is accepted only by route_selected")
    path = Path(log_path)

    with _locked(path, exclusive=True, create=False) as handle:
        events = _read_events(handle)
        run_events = [event for event in events if event["run_id"] == run_id]
        if not run_events:
            raise BenchmarkError(f"run_id {run_id} does not exist")
        if any(event["stage"] == "run_finished" for event in run_events):
            raise BenchmarkError(f"run_id {run_id} is already finished")
        start = run_events[0]
        current_route = next(
            (
                event["route_sha256"]
                for event in reversed(run_events)
                if event["route_sha256"] is not None
            ),
            None,
        )
        if stage == "route_selected":
            if current_route is not None:
                raise BenchmarkError(f"run_id {run_id} already selected a route")
            next_route = route_sha256
        else:
            next_route = current_route
            if (
                start["arm"] == "router_v1_prospective"
                and next_route is None
                and not _allowed_without_route(stage, outcome)
            ):
                raise BenchmarkError(
                    "router arm requires route_selected before work marks"
                )

        event = _new_event(
            run_id=run_id,
            task_id=start["task_id"],
            arm=start["arm"],
            task_mode=start["task_mode"],
            stage=stage,
            outcome=outcome,
            timestamp_utc=_collector_timestamp(events),
            sequence=len(events) + 1,
            source_sha256=start["source_sha256"],
            registry_sha256=start["registry_sha256"],
            route_sha256=next_route,
            evidence_sha256=evidence_sha256,
            prev_event_sha256=events[-1]["event_sha256"],
        )
        _append_event(handle, event)
    return event


def _milliseconds(start: dict, event: dict) -> int:
    delta = _parse_timestamp(event["timestamp_utc"]) - _parse_timestamp(
        start["timestamp_utc"]
    )
    return int(delta.total_seconds() * 1_000)


def _metric_summary(values: list[int]) -> dict:
    if not values:
        return {"sample_count": 0, "median": None, "minimum": None, "maximum": None}
    return {
        "sample_count": len(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


GATE_STAGES = (
    "g3_decided",
    "g4_decided",
    "g5_decided",
    "g6_decided",
)


def _aggregate_report(runs: list[list[dict]]) -> dict:
    metric_values = {metric: [] for metric in METRIC_STAGES}
    resolved_stage_counts = {stage: 0 for stage in GATE_STAGES}
    g6_passed = 0
    finished = 0
    g3_first_pass = 0
    g4_first_pass = 0
    g4_rounds = 0
    manual_interventions = 0

    for events in runs:
        start = events[0]
        for metric, stage in METRIC_STAGES.items():
            matching = next(
                (
                    event
                    for event in events
                    if event["stage"] == stage and event["outcome"] == "pass"
                ),
                None,
            )
            if matching is not None:
                metric_values[metric].append(_milliseconds(start, matching))
        gate_events = {
            stage: [event for event in events if event["stage"] == stage]
            for stage in GATE_STAGES
        }
        for stage, stage_events in gate_events.items():
            if stage_events:
                resolved_stage_counts[stage] += 1
        if gate_events["g6_decided"]:
            if gate_events["g6_decided"][-1]["outcome"] == "pass":
                g6_passed += 1
        if any(event["stage"] == "run_finished" for event in events):
            finished += 1
        g3_events = gate_events["g3_decided"]
        if g3_events and g3_events[0]["outcome"] == "pass":
            g3_first_pass += 1
        g4_events = gate_events["g4_decided"]
        if g4_events and g4_events[0]["outcome"] == "pass":
            g4_first_pass += 1
        g4_rounds += len(g4_events)
        manual_interventions += sum(
            event["stage"] == "manual_intervention" for event in events
        )

    unresolved_stage_counts = {
        stage: len(runs) - count for stage, count in resolved_stage_counts.items()
    }
    return {
        "run_count": len(runs),
        "resolved_stage_counts": resolved_stage_counts,
        "unresolved_stage_counts": unresolved_stage_counts,
        "g6_resolved_count": resolved_stage_counts["g6_decided"],
        "g6_pass_count": g6_passed,
        "g6_unresolved_count": unresolved_stage_counts["g6_decided"],
        "finished_count": finished,
        "unfinished_count": len(runs) - finished,
        "g3_first_pass_count": g3_first_pass,
        "g4_first_pass_count": g4_first_pass,
        "g4_review_round_count": g4_rounds,
        "manual_intervention_count": manual_interventions,
        "duration_metrics_ms": {
            metric: _metric_summary(values) for metric, values in metric_values.items()
        },
    }


def _arm_report(runs: list[list[dict]]) -> dict:
    task_mode_runs = {
        task_mode: [run for run in runs if run[0]["task_mode"] == task_mode]
        for task_mode in TASK_MODES
    }
    return {
        **_aggregate_report(runs),
        "task_mode_counts": {
            task_mode: len(task_mode_runs[task_mode]) for task_mode in TASK_MODES
        },
        "task_modes": {
            task_mode: _aggregate_report(task_mode_runs[task_mode])
            for task_mode in TASK_MODES
        },
    }


def _comparison(arms: dict[str, dict]) -> dict:
    task_mode_counts = {arm: arms[arm]["task_mode_counts"] for arm in ARMS}
    task_mode_distribution_matched = all(
        task_mode_counts[arm] == task_mode_counts[ARMS[0]] for arm in ARMS[1:]
    )
    audit = {
        "minimum_runs_per_arm": 5,
        "run_counts": {arm: arms[arm]["run_count"] for arm in ARMS},
        "task_mode_counts": task_mode_counts,
        "task_mode_distribution_matched": task_mode_distribution_matched,
        "unfinished_counts": {arm: arms[arm]["unfinished_count"] for arm in ARMS},
        "unresolved_stage_counts": {
            arm: arms[arm]["unresolved_stage_counts"] for arm in ARMS
        },
    }
    blockers: list[str] = []
    if any(arms[arm]["run_count"] == 0 for arm in ARMS):
        blockers.append("missing_arm")
    if any(arms[arm]["run_count"] < audit["minimum_runs_per_arm"] for arm in ARMS):
        blockers.append("minimum_sample_size_not_met")
    if not task_mode_distribution_matched:
        blockers.append("task_mode_distribution_mismatch")
    if any(arms[arm]["unfinished_count"] > 0 for arm in ARMS):
        blockers.append("unfinished_run")
    for stage in GATE_STAGES:
        if any(arms[arm]["unresolved_stage_counts"][stage] > 0 for arm in ARMS):
            blockers.append(f"{stage.removesuffix('_decided')}_unresolved")
    if blockers:
        return {
            "status": "insufficient_evidence",
            "superiority_claim": False,
            "winner": None,
            "reason_code": blockers[0],
            "blocking_reason_codes": blockers,
            "audit": audit,
        }
    return {
        "status": "descriptive_only",
        "superiority_claim": False,
        "winner": None,
        "reason_code": "automatic_superiority_not_supported",
        "blocking_reason_codes": [],
        "audit": audit,
    }


def build_report(log_path: Path | str) -> dict:
    path = Path(log_path)
    with _locked(path, exclusive=False, create=False) as handle:
        events = _read_events(handle)

    grouped: dict[str, list[dict]] = {}
    for event in events:
        grouped.setdefault(event["run_id"], []).append(event)
    arm_runs = {
        arm: [run for run in grouped.values() if run[0]["arm"] == arm] for arm in ARMS
    }
    arms = {arm: _arm_report(arm_runs[arm]) for arm in ARMS}
    return {
        "schema_version": REPORT_VERSION,
        "trace_event_count": len(events),
        "trace_head_sha256": events[-1]["event_sha256"] if events else None,
        "arms": arms,
        "comparison": _comparison(arms),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent_skill_benchmark.py")
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("--log", type=Path, required=True)
    start.add_argument("--arm", choices=ARMS, required=True)
    start.add_argument("--task-mode", choices=TASK_MODES, required=True)
    start.add_argument("--source-sha256", required=True)
    start.add_argument("--registry-sha256", required=True)
    start.add_argument("--run-id")
    start.add_argument("--task-id")

    mark = commands.add_parser("mark")
    mark.add_argument("--log", type=Path, required=True)
    mark.add_argument("--run-id", required=True)
    mark.add_argument("--stage", choices=STAGES, required=True)
    mark.add_argument("--outcome", choices=OUTCOMES, required=True)
    mark.add_argument("--evidence-sha256", required=True)
    mark.add_argument("--route-sha256")

    report = commands.add_parser("report")
    report.add_argument("--log", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "start":
            result = start_run(
                args.log,
                arm=args.arm,
                task_mode=args.task_mode,
                source_sha256=args.source_sha256,
                registry_sha256=args.registry_sha256,
                run_id=args.run_id,
                task_id=args.task_id,
            )
        elif args.command == "mark":
            result = mark_run(
                args.log,
                run_id=args.run_id,
                stage=args.stage,
                outcome=args.outcome,
                evidence_sha256=args.evidence_sha256,
                route_sha256=args.route_sha256,
            )
        else:
            result = build_report(args.log)
    except BenchmarkError as exc:
        print(f"agent-skill-benchmark: ERROR {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
