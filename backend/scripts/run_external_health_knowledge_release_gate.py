#!/usr/bin/env python3
"""Release gate for governed external-health knowledge changes.

The gate intentionally imports reviewed artifacts into an isolated SQLite
database for JSONL/import/eval checks, so local or production databases are not
mutated by a PR verification run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = BACKEND_ROOT / "data" / "system_kb_v2_seed"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DOMAIN_FOCUSED_TESTS = (
    "tests/test_gerd_lpr_knowledge.py",
    "tests/test_gastro_medication_safety_knowledge.py",
    "tests/test_diet_sodium_bp_knowledge.py",
    "tests/test_diet_chronic_condition_knowledge.py",
    "tests/test_exercise_acute_knowledge.py",
    "tests/test_exercise_cardiac_recovery_knowledge.py",
    "tests/test_pgx_cyp2c19_knowledge.py",
    "tests/test_pgx_high_risk_knowledge.py",
    "tests/test_pgx_hla_g6pd_knowledge.py",
    "tests/test_pgx_thiopurine_knowledge.py",
    "tests/test_pgx_warfarin_knowledge.py",
    "tests/test_rhinitis_referral_knowledge.py",
    "tests/test_rhinitis_treatment_knowledge.py",
    "tests/test_sleep_insomnia_sedative_knowledge.py",
    "tests/test_sleep_spo2_knowledge.py",
    "tests/test_supplement_safety_knowledge.py",
    "tests/test_system_knowledge_draft_extraction_gate.py",
    "tests/test_system_knowledge_ingest.py",
    "tests/test_system_knowledge_protocol_artifacts.py",
    "tests/test_system_knowledge_vector_backend.py",
)

COMPILEALL_TARGETS = ("app", "scripts", "tests")
DOCUMENT_JSONL_FILES = (
    "pages.jsonl",
    "entities.jsonl",
    "claims.jsonl",
    "protocols.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
)
RELATION_JSONL_FILE = "relations.jsonl"


@dataclass(frozen=True)
class GateStep:
    name: str
    kind: str
    command: list[str] | None = None
    artifact_dir: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "kind": self.kind}
        if self.command is not None:
            payload["command"] = self.command
        if self.artifact_dir is not None:
            payload["artifact_dir"] = self.artifact_dir
        return payload


def build_release_gate_plan(
    *,
    python: str = sys.executable,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    only: set[str] | None = None,
) -> list[GateStep]:
    steps = [
        GateStep(
            name="domain_focused_tests",
            kind="subprocess",
            command=[python, "-m", "pytest", "--no-cov", *DOMAIN_FOCUSED_TESTS],
        ),
        GateStep(
            name="jsonl_lint_import_eval",
            kind="internal",
            artifact_dir=str(artifact_dir),
        ),
        GateStep(
            name="compileall",
            kind="subprocess",
            command=[python, "-m", "compileall", "-q", *COMPILEALL_TARGETS],
        ),
    ]
    if only:
        return [step for step in steps if step.name in only]
    return steps


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path.name}:{line_no}: expected JSON object")
            rows.append(payload)
    return rows


def lint_jsonl_artifacts(artifact_dir: Path) -> dict[str, Any]:
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain a JSON object")

    counts: dict[str, int] = {}
    seen_doc_ids: set[str] = set()
    duplicate_doc_ids: list[str] = []

    for file_name in DOCUMENT_JSONL_FILES:
        path = artifact_dir / file_name
        if not path.exists():
            raise FileNotFoundError(f"missing artifact file: {path}")
        rows = _read_jsonl(path)
        counts[file_name] = len(rows)
        for idx, row in enumerate(rows, start=1):
            doc_id = str(row.get("doc_id") or "").strip()
            if not doc_id:
                raise ValueError(f"{file_name}:{idx}: missing doc_id")
            if doc_id in seen_doc_ids:
                duplicate_doc_ids.append(doc_id)
            seen_doc_ids.add(doc_id)

    relation_path = artifact_dir / RELATION_JSONL_FILE
    if not relation_path.exists():
        raise FileNotFoundError(f"missing artifact file: {relation_path}")
    relation_rows = _read_jsonl(relation_path)
    counts[RELATION_JSONL_FILE] = len(relation_rows)
    for idx, row in enumerate(relation_rows, start=1):
        if not row.get("src_doc_id") or not row.get("dst_doc_id") or not row.get("relation"):
            raise ValueError(f"{RELATION_JSONL_FILE}:{idx}: missing src_doc_id/dst_doc_id/relation")

    if duplicate_doc_ids:
        raise ValueError(f"duplicate doc_id values: {sorted(set(duplicate_doc_ids))}")

    return {"manifest_version": manifest.get("version"), "counts": counts}


def run_jsonl_lint_import_eval_gate(artifact_dir: Path) -> dict[str, Any]:
    lint_report = lint_jsonl_artifacts(artifact_dir)

    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):  # type: ignore[no-untyped-def]
        return "JSON"

    import app.models  # noqa: F401 - register all Base metadata before create_all
    from app.database import Base
    from app.services.system_knowledge_eval import run_system_kb_eval_cases
    from app.services.system_knowledge_importer import import_system_kb_artifacts

    with tempfile.TemporaryDirectory(prefix="system-kb-release-gate-") as tmp:
        db_path = Path(tmp) / "system_kb_release_gate.sqlite3"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        try:
            import_counts = import_system_kb_artifacts(
                db,
                artifact_dir,
                actor="release-gate:external-health-knowledge",
            )
            eval_report = run_system_kb_eval_cases(db)
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()

    if eval_report["total"] <= 0:
        raise RuntimeError("system KB eval runner found zero reviewed eval cases")
    if eval_report["failed"] > 0:
        raise RuntimeError(f"system KB eval failures: {eval_report['failed']}")

    return {
        "lint": lint_report,
        "import": import_counts,
        "eval": {
            "total": eval_report["total"],
            "passed": eval_report["passed"],
            "failed": eval_report["failed"],
        },
    }


def run_subprocess_step(step: GateStep) -> dict[str, Any]:
    if step.command is None:
        raise ValueError(f"step {step.name} has no command")
    started = time.monotonic()
    completed = subprocess.run(step.command, cwd=BACKEND_ROOT)
    return {
        "name": step.name,
        "kind": step.kind,
        "command": step.command,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def run_gate(
    *,
    artifact_dir: Path,
    python: str = sys.executable,
    only: set[str] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for step in build_release_gate_plan(python=python, artifact_dir=artifact_dir, only=only):
        if step.kind == "subprocess":
            result = run_subprocess_step(step)
            results.append(result)
            if result["returncode"] != 0:
                return {"ok": False, "steps": results}
            continue

        started = time.monotonic()
        try:
            detail = run_jsonl_lint_import_eval_gate(artifact_dir)
            results.append(
                {
                    "name": step.name,
                    "kind": step.kind,
                    "returncode": 0,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "detail": detail,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "name": step.name,
                    "kind": step.kind,
                    "returncode": 1,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "error": str(exc),
                }
            )
            return {"ok": False, "steps": results}

    return {"ok": True, "steps": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Reviewed system-KB artifact directory.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        choices=("domain_focused_tests", "jsonl_lint_import_eval", "compileall"),
        help="Run only the selected gate step. Can be passed more than once.",
    )
    args = parser.parse_args()
    only = set(args.only or [])

    if args.dry_run:
        payload = {
            "dry_run": True,
            "steps": [
                step.as_payload()
                for step in build_release_gate_plan(
                    python=sys.executable,
                    artifact_dir=args.artifact_dir,
                    only=only or None,
                )
            ],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for step in payload["steps"]:
                command = " ".join(step.get("command") or ["internal", step["name"]])
                print(f"{step['name']}: {command}")
        return 0

    result = run_gate(artifact_dir=args.artifact_dir, only=only or None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for step in result["steps"]:
            status = "PASS" if step.get("returncode") == 0 else "FAIL"
            print(f"[{status}] {step['name']} ({step.get('duration_seconds', 0)}s)")
            if step.get("error"):
                print(f"  error: {step['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
