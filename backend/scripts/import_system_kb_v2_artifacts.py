#!/usr/bin/env python3
"""Import reviewed system KB V2 artifacts into the serving database."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def import_artifacts_and_optionally_reindex(
    db,
    artifact_dir: str,
    *,
    actor: str,
    skip_reindex: bool = False,
) -> dict[str, Any]:
    from app.services.system_knowledge_importer import import_system_kb_artifacts

    counts = import_system_kb_artifacts(db, artifact_dir, actor=actor)
    reindex_report = None
    if not skip_reindex:
        from app.services.system_knowledge_service import run_system_kb_reindex_report

        reindex_report = run_system_kb_reindex_report(
            db,
            actor=actor,
            changed_document_ids=counts.get("changed_document_ids", []),
        )
    return {"import": counts, "reindex": reindex_report}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / "data" / "system_kb_v2_seed"),
        help="Directory containing manifest.json and JSONL artifacts.",
    )
    parser.add_argument("--actor", default="deploy:system_kb_v2")
    parser.add_argument(
        "--skip-reindex",
        action="store_true",
        help="Import reviewed artifacts without rebuilding serving search indexes.",
    )
    args = parser.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        result = import_artifacts_and_optionally_reindex(
            db,
            args.artifact_dir,
            actor=args.actor,
            skip_reindex=args.skip_reindex,
        )
        counts = result["import"]
        proof = counts.get("proof") or {}
        print(
            "imported system KB V2 artifacts: "
            f"{counts['documents']} documents, {counts['edges']} edges, "
            f"changed={len(counts.get('changed_document_ids', []))}, "
            f"deleted={len(counts.get('deleted_document_ids', []))}, "
            f"proof={proof.get('mode', 'off')}:{proof.get('decision', 'unknown')}"
        )
        reindex = result["reindex"]
        if reindex is None:
            print("skipped system KB reindex")
        else:
            reindex_counts = reindex["reindex"]
            pgvector = reindex["pgvector"]
            print(
                "reindexed system KB: "
                f"{reindex_counts['documents']} documents, "
                f"{reindex_counts['dense_vectors']} dense vectors, "
                f"backend={pgvector.get('current_vector_backend')}"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
