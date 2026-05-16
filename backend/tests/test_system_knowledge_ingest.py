from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys

from app.services.system_knowledge_ingest import (
    build_pr_style_diff,
    compile_dedao_ingest_artifacts,
    promote_artifact_review_status,
    write_reviewed_artifacts,
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_compile_dedao_ingest_artifacts_extracts_claims_without_raw_course_text(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "冯雪·高血压医学课" / "MD"
    course.mkdir(parents=True)
    (course / "07 - 饮食：怎么吃才能有效降血压？.md").write_text(
        "# 饮食：怎么吃才能有效降血压？\n\n"
        "这一讲讨论盐、钠、蔬菜和家庭血压监测。"
        "这是一段付费课程正文，长度足够长，不能被原样放入 serving artifact。"
        * 4,
        encoding="utf-8",
    )

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "empty-artifacts",
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )

    claim_ids = {claim["doc_id"] for claim in result.claims}
    assert "claim:c_dedao_fengxue_gaoxueya_yixueke_salt_reduction" in claim_ids
    salt_claim = next(claim for claim in result.claims if claim["doc_id"].endswith("salt_reduction"))
    assert salt_claim["metadata"]["license_scope"] == "internal_transformed_claims"
    assert salt_claim["metadata"]["review_status"] == "draft"
    assert salt_claim["applies_when"] == [
        "twin.labs.systolic_bp >= 130",
        "twin.goals.metabolic_health.active == true",
    ]
    assert salt_claim["sources"] == ["dedao:fengxue-gaoxueya-yixueke"]
    assert "付费课程正文" not in json.dumps(salt_claim, ensure_ascii=False)
    assert result.diff["claims_added"] >= 1


def test_compile_dedao_ingest_artifacts_marks_superseded_existing_claim(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "冯雪·高血压医学课" / "MD"
    course.mkdir(parents=True)
    (course / "05 - 延缓：怎么让高血压来得晚一些？.md").write_text(
        "家庭血压趋势、减盐、体重和运动。",
        encoding="utf-8",
    )
    base = tmp_path / "base"
    base.mkdir()
    (base / "claims.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "claim:c_old_bp_home_monitoring",
                "doc_type": "claim",
                "entity_type": "condition",
                "entity_id": "hypertension-risk",
                "title": "血压建议优先基于家庭血压趋势",
                "summary": "旧版本。",
                "confidence": 0.5,
                "evidence_level": "C",
                "sources": ["system:old"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=base,
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )

    new_claim = next(claim for claim in result.claims if claim["title"] == "血压建议优先基于家庭血压趋势")
    assert new_claim["supersedes"] == ["claim:c_old_bp_home_monitoring"]
    archived_old = next(claim for claim in result.archived_claims if claim["doc_id"] == "claim:c_old_bp_home_monitoring")
    assert archived_old["is_archived"] is True
    assert archived_old["metadata"]["superseded_by"] == new_claim["doc_id"]
    assert result.diff["claims_superseded"] == 1


def test_compile_dedao_ingest_artifacts_does_not_supersede_reviewed_claim(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "冯雪·高血压医学课" / "MD"
    course.mkdir(parents=True)
    (course / "05 - 延缓：怎么让高血压来得晚一些？.md").write_text(
        "家庭血压趋势、减盐、体重和运动。",
        encoding="utf-8",
    )
    base = tmp_path / "base"
    base.mkdir()
    (base / "claims.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "claim:c_reviewed_bp_home_monitoring",
                "doc_type": "claim",
                "entity_type": "condition",
                "entity_id": "hypertension-risk",
                "title": "血压建议优先基于家庭血压趋势",
                "summary": "已审核版本。",
                "confidence": 0.76,
                "evidence_level": "B",
                "sources": ["dedao:fengxue-gaoxueya-yixueke"],
                "metadata": {"review_status": "reviewed"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=base,
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )

    new_claim = next(claim for claim in result.claims if claim["title"] == "血压建议优先基于家庭血压趋势")
    assert new_claim["supersedes"] == []
    assert new_claim["metadata"]["candidate_duplicates"] == ["claim:c_reviewed_bp_home_monitoring"]
    assert result.archived_claims == []
    assert result.diff["claims_superseded"] == 0


def test_write_reviewed_artifacts_merges_generated_docs_and_manifest(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "仝卿·营养科学20讲" / "MD"
    course.mkdir(parents=True)
    (course / "07 膳食纤维：人体不需要，也算营养素.md").write_text(
        "膳食纤维、饱腹感、血糖和血脂。",
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    output.mkdir()
    (output / "entities.jsonl").write_text(
        '{"doc_id":"entity:condition:metabolic-health","doc_type":"entity","entity_type":"condition","entity_id":"metabolic-health","title":"代谢健康"}\n',
        encoding="utf-8",
    )

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        course_names=["仝卿·营养科学20讲"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )
    counts = write_reviewed_artifacts(result, output)

    claims = _jsonl(output / "claims.jsonl")
    entities = _jsonl(output / "entities.jsonl")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert any(claim["doc_id"].endswith("fiber_intake") for claim in claims)
    assert any(entity["doc_id"] == "entity:intervention:fiber-intake" for entity in entities)
    assert counts["claims"] == len(claims)
    assert manifest["counts"]["claims"] == len(claims)
    assert manifest["ingest"]["review_status"] == "draft"


def test_promote_artifact_review_status_marks_draft_docs_reviewed_and_writes_manifest(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "仝卿·营养科学20讲" / "MD"
    course.mkdir(parents=True)
    (course / "07 膳食纤维：人体不需要，也算营养素.md").write_text(
        "膳食纤维、饱腹感、血糖和血脂。",
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        course_names=["仝卿·营养科学20讲"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )
    write_reviewed_artifacts(result, output)

    summary = promote_artifact_review_status(
        output,
        reviewer="medical-reviewer@example.com",
        reviewed_at=datetime(2026, 5, 17, 8, 0, tzinfo=UTC),
    )

    claims = _jsonl(output / "claims.jsonl")
    entities = _jsonl(output / "entities.jsonl")
    pages = _jsonl(output / "pages.jsonl")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    review_manifest = json.loads((output / "review_manifest.json").read_text(encoding="utf-8"))

    reviewed_docs = [*claims, *entities, *pages]
    assert reviewed_docs
    assert all(doc["metadata"]["review_status"] == "reviewed" for doc in reviewed_docs)
    assert all(doc["metadata"]["reviewed_by"] == "medical-reviewer@example.com" for doc in reviewed_docs)
    assert manifest["ingest"]["review_status"] == "reviewed"
    assert manifest["review"]["status"] == "reviewed"
    assert manifest["review"]["reviewer"] == "medical-reviewer@example.com"
    assert summary["documents_reviewed"] == len(reviewed_docs)
    assert review_manifest["documents_reviewed"] == len(reviewed_docs)


def test_compile_dedao_ingest_artifacts_is_idempotent_after_write(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "冯雪·高血压医学课" / "MD"
    course.mkdir(parents=True)
    (course / "05 - 延缓：怎么让高血压来得晚一些？.md").write_text(
        "家庭血压趋势、减盐、体重和运动。",
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"

    first = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )
    write_reviewed_artifacts(first, output)
    second = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )

    assert second.diff["claims_added"] == 0
    assert second.diff["claims_superseded"] == 0
    assert second.archived_claims == []


def test_compile_dedao_ingest_artifacts_prefers_existing_same_doc_id_over_draft_duplicate(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "冯雪·高血压医学课" / "MD"
    course.mkdir(parents=True)
    (course / "05 - 延缓：怎么让高血压来得晚一些？.md").write_text(
        "家庭血压趋势、减盐、体重和运动。",
        encoding="utf-8",
    )
    base = tmp_path / "base"
    base.mkdir()
    rows = [
        {
            "doc_id": "claim:c_dedao_fengxue_gaoxueya_yixueke_bp_home_monitoring",
            "doc_type": "claim",
            "entity_type": "condition",
            "entity_id": "hypertension-risk",
            "title": "血压建议优先基于家庭血压趋势",
            "summary": "当前课程已生成 draft。",
            "confidence": 0.76,
            "evidence_level": "B",
            "sources": ["dedao:fengxue-gaoxueya-yixueke"],
            "metadata": {"review_status": "draft"},
        },
        {
            "doc_id": "claim:c_dedao_other_bp_home_monitoring",
            "doc_type": "claim",
            "entity_type": "condition",
            "entity_id": "hypertension-risk",
            "title": "血压建议优先基于家庭血压趋势",
            "summary": "其他课程 draft。",
            "confidence": 0.76,
            "evidence_level": "B",
            "sources": ["dedao:other"],
            "metadata": {"review_status": "draft"},
        },
    ]
    (base / "claims.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=base,
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )

    new_claim = next(claim for claim in result.claims if claim["title"] == "血压建议优先基于家庭血压趋势")
    assert new_claim["supersedes"] == []
    assert "candidate_duplicates" not in new_claim["metadata"]
    assert result.archived_claims == []
    assert result.diff["claims_superseded"] == 0


def test_build_pr_style_diff_reports_artifact_changes_without_mutating_output(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "仝卿·营养科学20讲" / "MD"
    course.mkdir(parents=True)
    (course / "07 膳食纤维：人体不需要，也算营养素.md").write_text(
        "膳食纤维、饱腹感、血糖和血脂。",
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    output.mkdir()

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        course_names=["仝卿·营养科学20讲"],
        now=datetime(2026, 5, 16, tzinfo=UTC),
    )
    diff = build_pr_style_diff(result, output)

    assert "+++ " in diff
    assert "claims.jsonl" in diff
    assert "claim:c_dedao_tongqing_nutrition_20_fiber_intake" in diff
    assert not (output / "claims.jsonl").exists()


def test_ingest_course_cli_supports_dry_run_write_and_review_promotion(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "仝卿·营养科学20讲" / "MD"
    course.mkdir(parents=True)
    (course / "07 膳食纤维：人体不需要，也算营养素.md").write_text(
        "膳食纤维、饱腹感、血糖和血脂。",
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    script = Path(__file__).resolve().parents[1] / "scripts" / "ingest_course.py"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

    dry_run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source-root",
            str(source_root),
            "--artifact-dir",
            str(output),
            "--course",
            "仝卿·营养科学20讲",
            "--dry-run",
            "--json-summary",
            "--no-diff",
        ],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    assert dry_run.returncode == 0, dry_run.stderr
    assert json.loads(dry_run.stdout)["mode"] == "dry_run"
    assert not (output / "claims.jsonl").exists()

    write = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source-root",
            str(source_root),
            "--artifact-dir",
            str(output),
            "--course",
            "仝卿·营养科学20讲",
            "--write",
            "--promote-reviewed",
            "--reviewer",
            "medical-reviewer@example.com",
            "--json-summary",
        ],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    assert write.returncode == 0, write.stderr
    write_summary = json.loads(write.stdout)
    assert write_summary["mode"] == "write"
    assert write_summary["review"]["reviewer"] == "medical-reviewer@example.com"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ingest"]["review_status"] == "reviewed"
    assert (output / "review_manifest.json").exists()
