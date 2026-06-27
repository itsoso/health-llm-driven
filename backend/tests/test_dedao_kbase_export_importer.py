from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.services.dedao_kbase_export_importer import compile_dedao_kbase_export_artifacts
from app.services.system_knowledge_ingest import validate_artifact_review_gate


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_export(source_root: Path) -> None:
    _write_json(
        source_root / "artifacts" / "system_kb_export.json",
        {
            "schema_id": "llm-wiki-v2-system-kb-export",
            "version": "export-v1",
            "source": "dedao-kbase",
            "source_repo": "git@github.com:example/dedao-kbase.git",
            "source_commit": "abc1234",
            "compiled_at": "2026-06-27T10:00:00+00:00",
            "pages": [
                {
                    "id": "articles_sleep-caffeine",
                    "title": "咖啡因与睡眠",
                    "summary": "咖啡因可能影响睡眠潜伏期。",
                    "content": "转化后的摘要，不包含大段课程原文。",
                    "source_file": "wiki/articles/sleep-caffeine.md",
                    "content_hash": "page-hash",
                    "license_scope": "internal_transformed_claims",
                    "review_status": "draft",
                }
            ],
            "entities": [
                {
                    "doc_id": "entity:intervention:caffeine-cutoff",
                    "entity_type": "intervention",
                    "entity_id": "caffeine-cutoff",
                    "title": "咖啡因截止时间",
                    "summary": "睡眠敏感人群应设置咖啡因截止时间。",
                    "body": "用于解释睡眠和刺激物暴露的边界。",
                    "sources": ["dedao:sleep-course"],
                    "metadata": {
                        "license_scope": "internal_transformed_claims",
                        "review_status": "draft",
                    },
                }
            ],
            "claims": [
                {
                    "claim_id": "c_sleep_caffeine_cutoff",
                    "entity_type": "intervention",
                    "entity_id": "caffeine-cutoff",
                    "title": "咖啡因截止时间支持睡眠管理",
                    "summary": "晚间咖啡因摄入可能影响睡眠。",
                    "body": "只用于健康管理建议。",
                    "sources": ["dedao:sleep-course"],
                    "recommends_lookup": ["entity:intervention:caffeine-cutoff"],
                    "metadata": {
                        "license_scope": "internal_transformed_claims",
                        "review_status": "draft",
                    },
                }
            ],
            "relations": [
                {
                    "src_doc_id": "entity:intervention:caffeine-cutoff",
                    "dst_doc_id": "claim:c_sleep_caffeine_cutoff",
                    "relation": "has_claim",
                    "confidence": 0.72,
                    "source_claim_id": "claim:c_sleep_caffeine_cutoff",
                    "metadata": {"review_status": "draft"},
                }
            ],
        },
    )


def test_compile_dedao_kbase_export_reads_only_system_export_and_preserves_source_metadata(tmp_path):
    source_root = tmp_path / "dedao-kbase"
    _write_export(source_root)
    _write_json(
        source_root / "artifacts" / "concepts_extra-not-in-export.json",
        {
            "id": "concepts_extra-not-in-export",
            "title": "不应被导入的旁路 artifact",
            "content": "这个文件不在 system_kb_export.json 中。",
        },
    )

    result = compile_dedao_kbase_export_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "seed",
        now=datetime(2026, 6, 27, 11, tzinfo=UTC),
    )

    assert [page["doc_id"] for page in result.pages] == ["page:ak-kbase:articles_sleep-caffeine"]
    assert [claim["doc_id"] for claim in result.claims] == ["claim:c_sleep_caffeine_cutoff"]
    claim_metadata = result.claims[0]["metadata"]
    assert claim_metadata["origin"] == "dedao-kbase-export"
    assert claim_metadata["source_repo"] == "git@github.com:example/dedao-kbase.git"
    assert claim_metadata["source_commit"] == "abc1234"
    assert claim_metadata["source_path"] == "wiki/articles/sleep-caffeine.md"
    assert result.manifest["ingest"]["pipeline"] == "dedao_kbase_export_v1"
    assert result.manifest["ingest"]["review_status"] == "draft"


def test_ingest_dedao_kbase_export_cli_writes_draft_then_promotes_after_review(tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    source_root = tmp_path / "dedao-kbase"
    artifact_dir = tmp_path / "system-kb-artifacts"
    _write_export(source_root)

    draft_run = subprocess.run(
        [
            sys.executable,
            str(backend_root / "scripts" / "ingest_dedao_kbase_export.py"),
            "--source-root",
            str(source_root),
            "--artifact-dir",
            str(artifact_dir),
            "--write",
            "--json-summary",
        ],
        cwd=backend_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert draft_run.returncode == 0, draft_run.stderr
    draft_summary = json.loads(draft_run.stdout)
    assert draft_summary["mode"] == "write_draft"
    assert draft_summary["draft_manifest"]["serving_allowed"] is False
    assert _json(artifact_dir / "draft_manifest.json")["status"] == "draft"
    assert validate_artifact_review_gate(artifact_dir)["serving_allowed"] is False
    claim = _jsonl(artifact_dir / "claims.jsonl")[0]
    assert claim["metadata"]["review_status"] == "draft"

    reviewed_run = subprocess.run(
        [
            sys.executable,
            str(backend_root / "scripts" / "ingest_dedao_kbase_export.py"),
            "--source-root",
            str(source_root),
            "--artifact-dir",
            str(artifact_dir),
            "--write",
            "--promote-reviewed",
            "--reviewer",
            "clinician:test",
            "--json-summary",
        ],
        cwd=backend_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert reviewed_run.returncode == 0, reviewed_run.stderr
    reviewed_summary = json.loads(reviewed_run.stdout)
    assert reviewed_summary["mode"] == "write_reviewed"
    assert reviewed_summary["review"]["serving_allowed"] is True
    assert validate_artifact_review_gate(artifact_dir)["serving_allowed"] is True
    reviewed_claim = _jsonl(artifact_dir / "claims.jsonl")[0]
    assert reviewed_claim["metadata"]["review_status"] == "reviewed"
    assert reviewed_claim["metadata"]["reviewed_by"] == "clinician:test"
