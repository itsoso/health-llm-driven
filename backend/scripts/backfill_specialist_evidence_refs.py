#!/usr/bin/env python
"""Backfill specialist audit evidence refs.

Default mode is dry-run. Use --apply to write deterministic patches.
"""

from __future__ import annotations

import argparse
import json

from app.database import SessionLocal
from app.services.specialist_evidence_backfill import backfill_specialist_evidence_refs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="persist backfill changes")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = backfill_specialist_evidence_refs(
            db,
            dry_run=not args.apply,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
