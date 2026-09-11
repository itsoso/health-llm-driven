#!/usr/bin/env python3
"""Evaluate anonymous attempt snapshots from a local JSON array or JSONL file.

No credentials, database, network, original prompts or conversation text are
accepted. See agent_task_evaluation.py for the closed metadata contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.agent_task_evaluation import evaluate_tasks  # noqa: E402


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local anonymous JSON/JSONL snapshots")
    parser.add_argument("--output", type=Path, help="Aggregate JSON path; default stdout")
    args = parser.parse_args()
    try:
        if args.input.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("input exceeds the 10 MiB metadata limit")
        text = args.input.read_text(encoding="utf-8")
        if text.lstrip().startswith("["):
            records = json.loads(text, object_pairs_hook=_object)
        else:
            records = [json.loads(line, object_pairs_hook=_object)
                       for line in text.splitlines() if line.strip()]
        report = evaluate_tasks(records)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("Unable to read or write valid local task metadata.", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"Task metadata rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
