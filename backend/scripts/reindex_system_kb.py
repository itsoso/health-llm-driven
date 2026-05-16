#!/usr/bin/env python3
"""Refresh system KB searchable text and content hashes."""

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
    parser.add_argument("--actor", default="cli:reindex_system_kb")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.services.system_knowledge_service import reindex_knowledge_documents

    db = SessionLocal()
    try:
        result = reindex_knowledge_documents(db, actor=args.actor)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
