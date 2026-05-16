#!/usr/bin/env python3
"""Import reviewed system KB V2 artifacts into the serving database."""

from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / "data" / "system_kb_v2_seed"),
        help="Directory containing manifest.json and JSONL artifacts.",
    )
    parser.add_argument("--actor", default="deploy:system_kb_v2")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.services.system_knowledge_importer import import_system_kb_artifacts

    db = SessionLocal()
    try:
        counts = import_system_kb_artifacts(db, args.artifact_dir, actor=args.actor)
        print(f"imported system KB V2 artifacts: {counts['documents']} documents, {counts['edges']} edges")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
