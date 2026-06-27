#!/usr/bin/env python3
"""Run reviewed system-KB eval_case artifacts against the local database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    db = SessionLocal()
    try:
        report = run_system_kb_eval_cases(db, case_ids=args.case_id or None)
    finally:
        db.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"system_kb_eval: {report['passed']}/{report['total']} pass")
        for case in report["cases"]:
            mark = "✓" if case["passed"] else "✗"
            detail = "" if case["passed"] else f" failures={case['failures']}"
            print(f"  [{mark}] {case['case_id']}{detail}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
