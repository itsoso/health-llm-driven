#!/usr/bin/env python3
"""Persistent workflow trace ledger for Reva development harness runs.

This is intentionally small and file-backed: any agent can append JSONL events,
recover after interruption, and enforce a hard token budget without depending on
Claude/Codex-specific runtime state.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any


DEFAULT_RUN_DIR = Path("docs/_generated/harness-runs")


def _write_json(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def _append(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"workflow trace not found: {path}")
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _budget_tokens(events: list[dict[str, Any]]) -> int | None:
    if not events:
        return None
    value = events[0].get("budget_tokens")
    return int(value) if value is not None else None


def _total_tokens(events: list[dict[str, Any]]) -> int:
    return sum(int(e.get("tokens") or 0) for e in events)


def _next_sequence(events: list[dict[str, Any]]) -> int:
    return max((int(e.get("sequence", -1)) for e in events), default=-1) + 1


def _event_key(event: dict[str, Any]) -> str | None:
    task_id = event.get("task_id")
    if task_id:
        return f"task:{task_id}"
    agent = event.get("agent")
    if agent:
        return f"agent:{agent}"
    return None


def _append_checked_event(run_path: Path, base_event: dict[str, Any]) -> int:
    events = _read_events(run_path)
    tokens = int(base_event.get("tokens") or 0)
    budget = _budget_tokens(events)
    projected = _total_tokens(events) + tokens
    clean_event = {
        k: v for k, v in {
            "sequence": _next_sequence(events),
            **base_event,
            "tokens": tokens,
        }.items()
        if v is not None
    }
    if budget is not None and projected > budget:
        budget_event = {
            "sequence": clean_event["sequence"],
            "event": "budget_exceeded",
            "requested_event": clean_event.get("event"),
            "budget_tokens": budget,
            "projected_tokens": projected,
            "agent": clean_event.get("agent"),
            "task_id": clean_event.get("task_id"),
            "phase": clean_event.get("phase"),
            "status": clean_event.get("status") or "blocked",
            "message": clean_event.get("message"),
            "tokens": tokens,
        }
        _append(run_path, {k: v for k, v in budget_event.items() if v is not None})
        _write_json({"ok": False, "reason": "budget_exceeded", "projected_tokens": projected})
        return 2
    _append(run_path, clean_event)
    _write_json({"ok": True, "sequence": clean_event["sequence"], "total_tokens": projected})
    return 0


def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    started = events[0] if events else {}
    budget = _budget_tokens(events)
    total = _total_tokens(events)
    checkpoints = [e for e in events if e.get("event") == "checkpoint"]
    spawns = [e for e in events if e.get("event") == "spawn"]
    verdicts = [e for e in events if e.get("event") == "verdict"]
    closed = {key for key in (_event_key(v) for v in verdicts) if key}
    open_spawns = [s for s in spawns if (_event_key(s) not in closed)]
    agents = sorted({str(e["agent"]) for e in events if e.get("agent")})
    summary = {
        "run_id": started.get("run_id"),
        "kind": started.get("kind"),
        "dossier": started.get("dossier"),
        "event_count": len(events),
        "total_tokens": total,
        "budget_tokens": budget,
        "budget_remaining": None if budget is None else budget - total,
        "latest_checkpoint": checkpoints[-1] if checkpoints else None,
        "agents": agents,
        "spawn_count": len(spawns),
        "verdict_count": len(verdicts),
        "open_agents": sorted({str(e["agent"]) for e in open_spawns if e.get("agent")}),
        "open_tasks": sorted({str(e["task_id"]) for e in open_spawns if e.get("task_id")}),
    }
    return summary


def cmd_init(args: argparse.Namespace) -> int:
    run_id = args.run_id or uuid.uuid4().hex[:12]
    run_dir = Path(args.run_dir)
    run_path = run_dir / f"{run_id}.jsonl"
    if run_path.exists() and not args.force:
        raise FileExistsError(f"workflow trace already exists: {run_path}")
    event = {
        "sequence": 0,
        "event": "run_started",
        "run_id": run_id,
        "kind": args.kind,
        "dossier": args.dossier,
        "budget_tokens": args.budget_tokens,
        "label": args.label,
    }
    if run_path.exists():
        run_path.unlink()
    _append(run_path, event)
    _write_json({"run_id": run_id, "run_path": str(run_path)})
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    return _append_checked_event(Path(args.run), {
        "event": args.event,
        "phase": args.phase,
        "agent": args.agent,
        "task_id": args.task_id,
        "status": args.status,
        "tokens": args.tokens,
        "message": args.message,
    })


def cmd_spawn(args: argparse.Namespace) -> int:
    return _append_checked_event(Path(args.run), {
        "event": "spawn",
        "phase": args.phase,
        "agent": args.agent,
        "task_id": args.task_id,
        "status": args.status,
        "tokens": args.tokens,
        "message": args.message,
    })


def cmd_verdict(args: argparse.Namespace) -> int:
    return _append_checked_event(Path(args.run), {
        "event": "verdict",
        "phase": args.phase,
        "agent": args.agent,
        "task_id": args.task_id,
        "status": args.status,
        "tokens": args.tokens,
        "message": args.message,
    })


def cmd_summary(args: argparse.Namespace) -> int:
    _write_json(_summarize(_read_events(Path(args.run))))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reva harness workflow JSONL trace ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a persistent workflow run ledger")
    init.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    init.add_argument("--run-id")
    init.add_argument("--kind", required=True)
    init.add_argument("--dossier")
    init.add_argument("--budget-tokens", type=int)
    init.add_argument("--label")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    event = sub.add_parser("event", help="append a workflow event")
    event.add_argument("--run", required=True)
    event.add_argument("--event", required=True)
    event.add_argument("--phase")
    event.add_argument("--agent")
    event.add_argument("--task-id")
    event.add_argument("--status")
    event.add_argument("--tokens", type=int, default=0)
    event.add_argument("--message")
    event.set_defaults(func=cmd_event)

    spawn = sub.add_parser("spawn", help="append a typed subagent/task spawn event")
    spawn.add_argument("--run", required=True)
    spawn.add_argument("--agent", required=True)
    spawn.add_argument("--task-id")
    spawn.add_argument("--phase")
    spawn.add_argument("--status", default="started")
    spawn.add_argument("--tokens", type=int, default=0)
    spawn.add_argument("--message")
    spawn.set_defaults(func=cmd_spawn)

    verdict = sub.add_parser("verdict", help="append a typed subagent/task verdict event")
    verdict.add_argument("--run", required=True)
    verdict.add_argument("--agent", required=True)
    verdict.add_argument("--task-id")
    verdict.add_argument("--phase")
    verdict.add_argument("--status", required=True, choices=["passed", "failed", "blocked", "completed", "needs_changes"])
    verdict.add_argument("--tokens", type=int, default=0)
    verdict.add_argument("--message")
    verdict.set_defaults(func=cmd_verdict)

    summary = sub.add_parser("summary", help="print workflow run summary as JSON")
    summary.add_argument("--run", required=True)
    summary.set_defaults(func=cmd_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
