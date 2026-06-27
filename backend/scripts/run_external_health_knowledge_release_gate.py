#!/usr/bin/env python3
"""Run the external-health system KB release gate against a disposable DB."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT_FILES = (
    "entities.jsonl",
    "claims.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
    "relations.jsonl",
)


def _artifact_key(filename: str, row: dict[str, Any]) -> Any:
    if filename == "relations.jsonl":
        return (
            row.get("src_doc_id"),
            row.get("relation"),
            row.get("dst_doc_id"),
            row.get("source_claim_id"),
        )
    return row.get("doc_id")


def lint_jsonl_artifacts(artifact_dir: Path) -> dict[str, Any]:
    """Parse JSONL artifacts and catch duplicate serving keys before DB import."""

    files: dict[str, Any] = {}
    duplicate_count = 0
    parse_errors: list[dict[str, Any]] = []

    for filename in ARTIFACT_FILES:
        path = artifact_dir / filename
        seen: set[Any] = set()
        duplicates: list[dict[str, Any]] = []
        count = 0

        if not path.exists():
            parse_errors.append({"file": filename, "line": None, "error": "missing_file"})
            files[filename] = {"count": 0, "duplicates": duplicates}
            continue

        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                parse_errors.append({"file": filename, "line": lineno, "error": str(exc)})
                continue
            count += 1
            key = _artifact_key(filename, row)
            if key in seen:
                duplicates.append({"line": lineno, "key": repr(key)})
            seen.add(key)

        duplicate_count += len(duplicates)
        files[filename] = {"count": count, "duplicates": duplicates}

    return {
        "files": files,
        "duplicate_count": duplicate_count,
        "parse_errors": parse_errors,
    }


def _register_sqlite_jsonb_compiler() -> None:
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ARG001
        return "JSON"


def _prepare_database(*, reset_db: bool) -> dict[str, Any]:
    _register_sqlite_jsonb_compiler()

    import app.models  # noqa: F401 - register all ORM tables before create_all
    from app.database import Base, engine

    created_schema = False
    if reset_db:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        created_schema = True

    return {
        "dialect": engine.dialect.name,
        "created_schema": created_schema,
        "reset_db": reset_db,
    }


def run_release_gate(
    *,
    artifact_dir: Path,
    reset_db: bool,
    actor: str,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    database_report = _prepare_database(reset_db=reset_db)

    from app.database import SessionLocal
    from app.services.system_knowledge_eval import run_system_kb_eval_cases
    from app.services.system_knowledge_importer import import_system_kb_artifacts
    from app.services.system_knowledge_service import lint_knowledge_base

    jsonl_report = lint_jsonl_artifacts(artifact_dir)

    db = SessionLocal()
    try:
        import_report = import_system_kb_artifacts(db, artifact_dir, actor=actor)
        lint_report = lint_knowledge_base(db)
        eval_report = run_system_kb_eval_cases(db, case_ids=case_ids or None, limit=10_000)
    finally:
        db.close()

    lint_issue_count = sum(int(value or 0) for value in lint_report["summary"].values())
    failed = (
        bool(jsonl_report["parse_errors"])
        or int(jsonl_report["duplicate_count"]) > 0
        or int(import_report.get("skipped_documents") or 0) > 0
        or lint_issue_count > 0
        or int(eval_report.get("failed") or 0) > 0
    )
    return {
        "status": "fail" if failed else "pass",
        "database": database_report,
        "jsonl": jsonl_report,
        "import": import_report,
        "lint": lint_report,
        "eval": eval_report,
    }


def _default_temp_database_url() -> tuple[str, Path]:
    handle = tempfile.NamedTemporaryFile(prefix="system_kb_release_gate_", suffix=".sqlite3", delete=False)
    path = Path(handle.name)
    handle.close()
    return f"sqlite:///{path}", path


def _print_text_report(report: dict[str, Any]) -> None:
    print(f"external_health_knowledge_release_gate: {report['status']}")
    print(
        "  jsonl: "
        f"duplicates={report['jsonl']['duplicate_count']} "
        f"parse_errors={len(report['jsonl']['parse_errors'])}"
    )
    print(
        "  import: "
        f"documents={report['import'].get('documents')} "
        f"edges={report['import'].get('edges')} "
        f"skipped={report['import'].get('skipped_documents')}"
    )
    print(f"  lint: {report['lint']['summary']}")
    print(f"  eval: {report['eval']['passed']}/{report['eval']['total']} pass")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", default=str(ROOT / "data" / "system_kb_v2_seed"))
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--keep-temp-db", action="store_true")
    parser.add_argument("--actor", default="release_gate:external_health_knowledge")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--only",
        choices=["jsonl_lint_import_eval"],
        default="jsonl_lint_import_eval",
        help="Compatibility flag for scripted release gates.",
    )
    args = parser.parse_args()

    temp_db_path: Path | None = None
    database_url = args.database_url
    reset_db = bool(args.reset_db)
    if not database_url:
        database_url, temp_db_path = _default_temp_database_url()
        reset_db = True

    os.environ["DATABASE_URL"] = database_url

    try:
        report = run_release_gate(
            artifact_dir=Path(args.artifact_dir),
            reset_db=reset_db,
            actor=args.actor,
            case_ids=args.case_id,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_text_report(report)
        return 0 if report["status"] == "pass" else 1
    finally:
        if temp_db_path and not args.keep_temp_db:
            try:
                temp_db_path.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
