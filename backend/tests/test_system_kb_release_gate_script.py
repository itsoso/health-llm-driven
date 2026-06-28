"""System KB release-gate CLI contract tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_release_gate_manifest_count_validation_detects_drift(tmp_path):
    from scripts.run_external_health_knowledge_release_gate import validate_artifact_manifest_counts

    artifact_dir = tmp_path / "seed"
    artifact_dir.mkdir()
    (artifact_dir / "entities.jsonl").write_text('{"doc_id":"entity:gene:MTHFR"}\n', encoding="utf-8")
    (artifact_dir / "claims.jsonl").write_text('{"doc_id":"claim:c1"}\n', encoding="utf-8")
    (artifact_dir / "contraindications.jsonl").write_text("", encoding="utf-8")
    (artifact_dir / "eval_cases.jsonl").write_text("", encoding="utf-8")
    (artifact_dir / "relations.jsonl").write_text("", encoding="utf-8")
    (artifact_dir / "pages.jsonl").write_text("", encoding="utf-8")
    (artifact_dir / "protocols.jsonl").write_text("", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(
        '{"counts":{"entities":2,"claims":1,"contraindications":0,"eval_cases":0,"relations":0,"pages":0,"protocols":0}}\n',
        encoding="utf-8",
    )

    report = validate_artifact_manifest_counts(artifact_dir)

    assert report["status"] == "fail"
    assert report["mismatches"] == [
        {"artifact": "entities", "manifest": 2, "actual": 1},
    ]


def test_release_gate_script_runs_jsonl_import_lint_and_eval_against_fresh_sqlite(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    script = backend_root / "scripts" / "run_external_health_knowledge_release_gate.py"
    db_path = tmp_path / "system_kb_release_gate.sqlite3"
    env = {
        **os.environ,
        "PYTHONPATH": str(backend_root),
        "SECRET_KEY": "test-secret-key-32-chars-minimum!!",
        "GARMIN_ENCRYPTION_KEY": "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--database-url",
            f"sqlite:///{db_path}",
            "--reset-db",
            "--json",
        ],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert report["database"]["created_schema"] is True
    assert report["jsonl"]["files"]["claims.jsonl"]["count"] >= 447
    assert report["jsonl"]["duplicate_count"] == 0
    assert report["import"]["documents"] >= 841
    assert report["import"]["edges"] >= 3309
    assert all(value == 0 for value in report["lint"]["summary"].values())
    assert report["eval"]["failed"] == 0
    assert report["eval"]["total"] >= 46
