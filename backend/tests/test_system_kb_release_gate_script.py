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


def test_release_gate_detects_duplicate_claim_titles(tmp_path):
    from scripts.run_external_health_knowledge_release_gate import detect_duplicate_claim_titles

    artifact_dir = tmp_path / "seed"
    artifact_dir.mkdir()
    (artifact_dir / "claims.jsonl").write_text(
        # a & b: identical title+sources -> duplicate; c: same title, different sources -> NOT a duplicate
        '{"doc_id":"claim:a","title":"血压风险管理先识别高钠来源","sources":["dedao:x"]}\n'
        '{"doc_id":"claim:b","title":"血压风险管理先识别高钠来源","sources":["dedao:x"]}\n'
        '{"doc_id":"claim:c","title":"血压风险管理先识别高钠来源","sources":["dedao:y"]}\n',
        encoding="utf-8",
    )

    report = detect_duplicate_claim_titles(artifact_dir)

    assert report["status"] == "fail"
    assert report["duplicate_title_count"] == 1
    assert len(report["duplicates"]) == 1
    assert sorted(report["duplicates"][0]["doc_ids"]) == ["claim:a", "claim:b"]


def test_release_gate_passes_duplicate_titles_when_sources_differ(tmp_path):
    from scripts.run_external_health_knowledge_release_gate import detect_duplicate_claim_titles

    artifact_dir = tmp_path / "seed"
    artifact_dir.mkdir()
    (artifact_dir / "claims.jsonl").write_text(
        '{"doc_id":"claim:a","title":"减重阶段需要力量训练","sources":["dedao:2020-2021"]}\n'
        '{"doc_id":"claim:b","title":"减重阶段需要力量训练","sources":["dedao:2021-2022"]}\n',
        encoding="utf-8",
    )

    report = detect_duplicate_claim_titles(artifact_dir)

    assert report["status"] == "pass"
    assert report["duplicate_title_count"] == 0


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

    # CLI contract test: jsonl/manifest/duplicate-title/lint sections and the full
    # seed import all run against the REAL artifacts, but the eval section is
    # narrowed to a 3-case subset via --case-id. The full 57-case eval takes
    # ~2min locally (jieba + BM25 over 870+ docs) and blows any sane subprocess
    # timeout here; full-eval coverage lives in the CI "System KB retrieval eval
    # (observation mode)" step and in the release-time gate run itself.
    subset_case_ids = [
        "eval:gerd_alarm_features_escalate",  # legacy case (pre-jieba era)
        "eval:zh_statin_muscle_pain",  # zh multi-word query through the jieba path
        "eval:zh_postmeal_glucose_walk_colloquial",  # zh colloquial; needs dedup'd claims
    ]
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--database-url",
            f"sqlite:///{db_path}",
            "--reset-db",
            "--json",
            *[arg for case_id in subset_case_ids for arg in ("--case-id", case_id)],
        ],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert report["database"]["created_schema"] is True
    assert report["jsonl"]["files"]["claims.jsonl"]["count"] >= 447
    assert report["jsonl"]["duplicate_count"] == 0
    assert report["duplicate_titles"]["status"] == "pass"
    assert report["duplicate_titles"]["duplicate_title_count"] == 0
    assert report["import"]["documents"] >= 841
    assert report["import"]["edges"] >= 3309
    assert all(value == 0 for value in report["lint"]["summary"].values())
    assert report["eval"]["failed"] == 0
    assert report["eval"]["total"] == len(subset_case_ids)
