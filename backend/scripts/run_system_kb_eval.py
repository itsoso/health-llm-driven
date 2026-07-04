#!/usr/bin/env python3
"""Run reviewed system-KB eval_case artifacts and print retrieval metrics.

Default mode (--ephemeral, the default): seeds an in-memory SQLite DB from the
reviewed seed JSONLs by REUSING the real ingest code
(``import_system_kb_artifacts`` + ``reindex_knowledge_documents`` — no parallel
loader), runs the eval, and prints a JSON metrics summary. This is what CI and
baseline/after captures use; it needs no live DB.

Live mode (--live): runs against ``app.database.SessionLocal`` (a real DB that
already has the seed imported). Preserves the original behavior.

Both modes print binary pass/fail + the additive ranked metrics
(recall@5 / recall@10 / MRR) and label which retrieval legs were active.

Honest labeling: the ephemeral backend is SQLite, so the PostgreSQL tsvector FTS
leg (``to_tsvector`` / ``websearch_to_tsquery``) is inactive and the FTS leg falls
back to the precomputed-text scorer. Active legs are reported under
``retrieval_legs`` in the output.

Usage (from backend/):
    python -m scripts.run_system_kb_eval                 # ephemeral, human summary
    python scripts/run_system_kb_eval.py --json          # ephemeral, JSON metrics
    python scripts/run_system_kb_eval.py --json --cases  # + per-case rank rows
    python scripts/run_system_kb_eval.py --live --json   # against live SessionLocal
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Env vars app.config requires, set before importing the app (mirrors conftest).
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ARTIFACT_DIR = ROOT / "data" / "system_kb_v2_seed"


def _register_sqlite_jsonb() -> None:
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001
        """SQLite has no JSONB — degrade to JSON (mirrors tests/conftest.py)."""
        return "JSON"


def _active_retrieval_legs(db) -> dict:
    from app.services.system_knowledge_service import search_knowledge

    plan = (search_knowledge(db, "睡眠", limit=1) or {}).get("retrieval_plan", {})
    return {
        "channels": plan.get("channels"),
        "lexical_backend": plan.get("lexical_backend"),
        "fts_backend": plan.get("fts_backend"),
        "vector_backend": plan.get("vector_backend"),
        "graph_backend": plan.get("graph_backend"),
    }


def _run_ephemeral(artifact_dir: Path, case_ids: list[str] | None) -> dict:
    _register_sqlite_jsonb()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 - register all tables before create_all
    from app.database import Base
    from app.services.system_knowledge_eval import run_system_kb_eval_cases
    from app.services.system_knowledge_importer import import_system_kb_artifacts
    from app.services.system_knowledge_service import reindex_knowledge_documents

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        ingest = import_system_kb_artifacts(db, artifact_dir, actor="eval-runner")
        reindex = reindex_knowledge_documents(db, actor="eval-runner")
        legs = _active_retrieval_legs(db)
        report = run_system_kb_eval_cases(db, case_ids=case_ids or None, limit=200)
    finally:
        db.close()
        engine.dispose()

    report["backend"] = "sqlite:///:memory:"
    report["artifact_dir"] = str(artifact_dir)
    report["ingest"] = ingest
    report["reindex"] = reindex
    report["retrieval_legs"] = legs
    return report


def _run_live(case_ids: list[str] | None) -> dict:
    from app.database import SessionLocal
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    db = SessionLocal()
    try:
        legs = _active_retrieval_legs(db)
        report = run_system_kb_eval_cases(db, case_ids=case_ids or None)
    finally:
        db.close()
    report["backend"] = "live:SessionLocal"
    report["retrieval_legs"] = legs
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--live", action="store_true", help="Run against live SessionLocal instead of ephemeral SQLite.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--cases", action="store_true", help="Include per-case rows in JSON output.")
    args = parser.parse_args(argv)

    if args.live:
        report = _run_live(args.case_id or None)
    else:
        report = _run_ephemeral(Path(args.artifact_dir), args.case_id or None)

    if args.json:
        payload = dict(report)
        if not args.cases:
            payload.pop("cases", None)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        metrics = report.get("metrics", {})
        print(f"system_kb_eval [{report.get('backend')}]: {report['passed']}/{report['total']} pass")
        print(
            f"  recall@5={metrics.get('recall@5')} recall@10={metrics.get('recall@10')} "
            f"mrr={metrics.get('mrr')} "
            f"(measurable_cases={metrics.get('measurable_cases')}, "
            f"targets={metrics.get('measurable_targets')})"
        )
        legs = report.get("retrieval_legs", {})
        print(f"  legs: fts={legs.get('fts_backend')} vector={legs.get('vector_backend')} lexical={legs.get('lexical_backend')}")
        for case in report["cases"]:
            mark = "✓" if case["passed"] else "✗"
            rank = case.get("hit_rank")
            rank_str = f" rank={rank}" if case.get("rank_measurable") else ""
            detail = "" if case["passed"] else f" failures={case['failures']}"
            print(f"  [{mark}] {case['case_id']}{rank_str}{detail}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
