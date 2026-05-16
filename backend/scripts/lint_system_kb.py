#!/usr/bin/env python3
"""Print a system KB lint report as JSON."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-issues", action="store_true")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.services.system_knowledge_service import lint_knowledge_base

    db = SessionLocal()
    try:
        report = lint_knowledge_base(db)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        issue_count = sum(report["summary"].values())
        return 1 if args.fail_on_issues and issue_count else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
