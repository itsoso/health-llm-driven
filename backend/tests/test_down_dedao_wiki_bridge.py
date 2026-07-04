from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.services.down_dedao_wiki_bridge import (
    compile_down_dedao_wiki_artifacts,
    write_down_dedao_wiki_artifacts,
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_compile_down_dedao_wiki_artifacts_converts_gene_drug_claims(tmp_path):
    source_root = tmp_path / "down-dedao"
    _write_json(
        source_root / "artifacts" / "gene_knowledge.json",
        {
            "id": "gene_knowledge_v2",
            "type": "gene_knowledge_v2",
            "version": "test-version",
            "entities": {
                "gene": {
                    "CYP2C19": {
                        "entity_id": "CYP2C19",
                        "entity_type": "gene",
                        "title": "CYP2C19",
                        "confidence": 0.86,
                        "evidence_level": "A",
                        "sources": ["cpic:guideline-cyp2c19-clopidogrel"],
                        "last_confirmed": "2026-05-18",
                        "decay_rate": "slow",
                        "body": "# CYP2C19\n\n氯吡格雷活化相关基因。",
                    }
                },
                "drug": {
                    "clopidogrel": {
                        "entity_id": "clopidogrel",
                        "entity_type": "drug",
                        "title": "氯吡格雷",
                        "confidence": 0.84,
                        "evidence_level": "A",
                        "sources": ["cpic:guideline-cyp2c19-clopidogrel"],
                        "last_confirmed": "2026-05-18",
                        "decay_rate": "slow",
                        "body": "# 氯吡格雷\n\n需要 CYP2C19 活化。",
                    }
                },
            },
            "claims": [
                {
                    "claim_id": "c_cyp2c19_clopidogrel_boundary",
                    "entity_type": "gene",
                    "entity_id": "CYP2C19",
                    "title": "CYP2C19 PM 与氯吡格雷无效边界",
                    "confidence": 0.9,
                    "evidence_level": "A",
                    "sources": ["cpic:guideline-cyp2c19-clopidogrel"],
                    "applies_when": [
                        "twin.genetics.CYP2C19_phenotype == 'poor'",
                        "twin.medications has 'clopidogrel'",
                    ],
                    "recommends_lookup": [
                        "entity:drug:clopidogrel",
                        "entity:intervention:caffeine-cutoff",
                    ],
                    "predicate": "contraindicates",
                    "body": "CYP2C19 PM 使用氯吡格雷时需要医生核对替代方案。",
                }
            ],
        },
    )

    result = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "seed",
        now=datetime(2026, 5, 18, tzinfo=UTC),
    )

    assert "entity:gene:CYP2C19" in {entity["doc_id"] for entity in result.entities}
    claim = next(claim for claim in result.claims if claim["doc_id"] == "claim:c_cyp2c19_clopidogrel_boundary")
    assert claim["evidence_level"] == "A"
    assert claim["metadata"]["origin"] == "down-dedao-llm-wiki"
    assert claim["metadata"]["predicate"] == "contraindicates"
    assert claim["metadata"]["review_status"] == "reviewed"
    assert claim["applies_when"] == [
        "twin.genetics.CYP2C19_phenotype == 'poor'",
        "twin.medications has 'clopidogrel'",
    ]
    assert any(
        relation["src_doc_id"] == "entity:gene:CYP2C19"
        and relation["dst_doc_id"] == "claim:c_cyp2c19_clopidogrel_boundary"
        and relation["relation"] == "has_claim"
        for relation in result.relations
    )
    assert any(
        relation["src_doc_id"] == "claim:c_cyp2c19_clopidogrel_boundary"
        and relation["dst_doc_id"] == "entity:drug:clopidogrel"
        and relation["relation"] == "recommends"
        for relation in result.relations
    )
    placeholder = next(
        entity for entity in result.entities if entity["doc_id"] == "entity:intervention:caffeine-cutoff"
    )
    assert placeholder["metadata"]["placeholder"] is True
    assert placeholder["metadata"]["review_status"] == "reviewed"


def test_claim_titles_are_prefixed_with_linked_entity_context(tmp_path):
    # Two source batches instantiate the SAME boilerplate claim title against the
    # same entity. The bridge must prefix them with the entity's display title so
    # they read "力量训练:减重阶段需要力量训练" instead of a bare generic title.
    source_root = tmp_path / "down-dedao"
    _write_json(
        source_root / "artifacts" / "gene_knowledge.json",
        {"id": "gene_knowledge_v2", "version": "t", "entities": {}, "claims": []},
    )
    _write_json(
        source_root / "artifacts" / "system_kb_export.json",
        {
            "version": "test-export",
            "entities": [
                {
                    "doc_id": "entity:intervention:strength-training",
                    "entity_type": "intervention",
                    "entity_id": "strength-training",
                    "title": "力量训练",
                    "summary": "力量训练实体页。",
                    "body": "力量训练用于保护功能能力。",
                }
            ],
            "claims": [
                {
                    "claim_id": "c_batch_a_strength_training",
                    "entity_type": "intervention",
                    "entity_id": "strength-training",
                    "title": "减重阶段需要力量训练保护功能能力",
                    "summary": "力量训练保护功能能力。",
                    "body": "健康管理建议。",
                    "sources": ["dedao:batch-a"],
                },
                {
                    "claim_id": "c_batch_b_strength_training",
                    "entity_type": "intervention",
                    "entity_id": "strength-training",
                    "title": "减重阶段需要力量训练保护功能能力",
                    "summary": "力量训练保护功能能力。",
                    "body": "健康管理建议。",
                    "sources": ["dedao:batch-b"],
                },
            ],
        },
    )

    result = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "seed",
        now=datetime(2026, 5, 18, tzinfo=UTC),
    )

    titles = {claim["doc_id"]: claim["title"] for claim in result.claims}
    assert titles["claim:c_batch_a_strength_training"] == "力量训练:减重阶段需要力量训练保护功能能力"
    assert titles["claim:c_batch_b_strength_training"] == "力量训练:减重阶段需要力量训练保护功能能力"


def test_claim_title_contextualization_is_idempotent_and_falls_back_to_entity_id(tmp_path):
    # No entity doc for the linkage -> fall back to the raw entity_id; and a title
    # already carrying its prefix must not be prefixed twice.
    source_root = tmp_path / "down-dedao"
    _write_json(
        source_root / "artifacts" / "gene_knowledge.json",
        {"id": "gene_knowledge_v2", "version": "t", "entities": {}, "claims": []},
    )
    _write_json(
        source_root / "artifacts" / "system_kb_export.json",
        {
            "version": "test-export",
            "entities": [],
            "claims": [
                {
                    "claim_id": "c_no_entity_doc",
                    "entity_type": "biomarker",
                    "entity_id": "HbA1c",
                    "title": "HbA1c 适合作为 8-12 周复查闭环",
                    "body": "健康管理建议。",
                },
                {
                    "claim_id": "c_already_prefixed",
                    "entity_type": "biomarker",
                    "entity_id": "HbA1c",
                    "title": "HbA1c:HbA1c 适合作为 8-12 周复查闭环",
                    "body": "健康管理建议。",
                },
            ],
        },
    )

    result = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "seed",
        now=datetime(2026, 5, 18, tzinfo=UTC),
    )
    titles = {claim["doc_id"]: claim["title"] for claim in result.claims}
    assert titles["claim:c_no_entity_doc"] == "HbA1c:HbA1c 适合作为 8-12 周复查闭环"
    # already-prefixed stays single-prefixed (idempotent)
    assert titles["claim:c_already_prefixed"] == "HbA1c:HbA1c 适合作为 8-12 周复查闭环"


def test_compile_down_dedao_wiki_artifacts_imports_topic_pages_with_licensed_content_and_skips_private_notes(tmp_path):
    source_root = tmp_path / "down-dedao"
    _write_json(
        source_root / "artifacts" / "gene_knowledge.json",
        {
            "id": "gene_knowledge_v2",
            "version": "test-version",
            "entities": {},
            "claims": [],
        },
    )
    long_paid_text = "这一段模拟已授权课程正文，可以进入 serving artifact。" * 20
    _write_json(
        source_root / "artifacts" / "concepts_allergic-rhinitis.json",
        {
            "id": "concepts_allergic-rhinitis",
            "title": "过敏性鼻炎（Allergic Rhinitis）",
            "summary": "过敏性鼻炎的症状、过敏原、用药疗程和就医边界。",
            "content": long_paid_text,
            "layer": 2,
            "conditions": ["allergic_rhinitis"],
            "tags": ["过敏", "鼻炎", "呼吸道"],
            "source": "ak-kbase",
            "source_file": "concepts/allergic-rhinitis.md",
            "sources_referenced": ["raw/papers/allergy.pdf"],
            "confidence_score": 0.9,
        },
    )
    _write_json(
        source_root / "artifacts" / "articles_personal-health-trends.json",
        {
            "id": "articles_personal-health-trends",
            "title": "个人健康趋势",
            "summary": "私人内容",
            "content": "用户个人纵向数据",
        },
    )

    result = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "seed",
        now=datetime(2026, 5, 18, tzinfo=UTC),
    )

    assert [page["doc_id"] for page in result.pages] == ["page:ak-kbase:concepts_allergic-rhinitis"]
    page = result.pages[0]
    assert page["entity_type"] == "concept"
    assert page["entity_id"] == "concepts_allergic-rhinitis"
    assert page["metadata"]["conditions"] == ["allergic_rhinitis"]
    assert "课程正文" in page["body"]
    assert page["metadata"]["license_scope"] == "licensed_transformed_content"
    assert result.skipped_private == ["articles_personal-health-trends.json"]


def test_compile_down_dedao_wiki_artifacts_absorbs_system_export_and_replaces_placeholders(tmp_path):
    source_root = tmp_path / "down-dedao"
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "entities.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "entity:intervention:caffeine-cutoff",
                "doc_type": "entity",
                "entity_type": "intervention",
                "entity_id": "caffeine-cutoff",
                "title": "caffeine cutoff",
                "metadata": {"origin": "down-dedao-llm-wiki", "placeholder": True},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        source_root / "artifacts" / "system_kb_export.json",
        {
            "version": "test-export",
            "pages": [
                {
                    "id": "articles_sleep-caffeine",
                    "title": "咖啡因与睡眠",
                    "summary": "咖啡因影响睡眠潜伏期。",
                    "content": "完整课程正文：下午晚些时候摄入咖啡因可能影响睡眠。",
                    "source_file": "articles/sleep-caffeine.md",
                    "license_scope": "licensed_transformed_content",
                    "content_hash": "abc123",
                }
            ],
            "entities": [
                {
                    "doc_id": "entity:intervention:caffeine-cutoff",
                    "entity_type": "intervention",
                    "entity_id": "caffeine-cutoff",
                    "title": "咖啡因截止时间",
                    "summary": "睡眠敏感人群应设置咖啡因截止时间。",
                    "body": "正式实体页：咖啡因截止时间用于解释睡眠和刺激物暴露的边界。",
                    "confidence": 0.74,
                    "evidence_level": "C",
                    "metadata": {"license_scope": "licensed_transformed_content"},
                }
            ],
            "claims": [
                {
                    "claim_id": "c_articles_sleep_caffeine_overview",
                    "entity_type": "article",
                    "entity_id": "articles_sleep-caffeine",
                    "title": "咖啡因与睡眠概览",
                    "summary": "该页解释咖啡因与睡眠的关系。",
                    "body": "页面概览 claim。",
                    "metadata": {
                        "derived_from_page": "page:ak-kbase:articles_sleep-caffeine",
                        "license_scope": "licensed_transformed_content",
                    },
                },
                {
                    "claim_id": "c_sleep_caffeine_cutoff",
                    "entity_type": "intervention",
                    "entity_id": "caffeine-cutoff",
                    "title": "咖啡因截止时间支持睡眠管理",
                    "summary": "晚间咖啡因摄入可能影响睡眠。",
                    "body": "只用于健康管理建议。",
                    "recommends_lookup": ["entity:intervention:caffeine-cutoff"],
                }
            ],
            "relations": [
                {
                    "src_doc_id": "page:ak-kbase:articles_sleep-caffeine",
                    "dst_doc_id": "claim:c_sleep_caffeine_cutoff",
                    "relation": "has_claim",
                    "confidence": 0.7,
                    "source_claim_id": "claim:c_sleep_caffeine_cutoff",
                }
            ],
        },
    )

    result = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=seed_dir,
        now=datetime(2026, 5, 19, tzinfo=UTC),
    )

    assert result.pages[0]["body"].startswith("完整课程正文")
    assert result.pages[0]["metadata"]["content_hash"] == "abc123"
    entity = next(item for item in result.entities if item["doc_id"] == "entity:intervention:caffeine-cutoff")
    assert entity["title"] == "咖啡因截止时间"
    assert entity["metadata"].get("placeholder") is not True
    assert any(
        relation["src_doc_id"] == "page:ak-kbase:articles_sleep-caffeine"
        and relation["dst_doc_id"] == "claim:c_articles_sleep_caffeine_overview"
        for relation in result.relations
    )
    assert not any(entity["doc_id"] == "entity:article:articles_sleep-caffeine" for entity in result.entities)
    assert any(
        relation["src_doc_id"] == "page:ak-kbase:articles_sleep-caffeine"
        and relation["dst_doc_id"] == "claim:c_sleep_caffeine_cutoff"
        for relation in result.relations
    )


def test_write_down_dedao_wiki_artifacts_is_idempotent(tmp_path):
    source_root = tmp_path / "down-dedao"
    _write_json(
        source_root / "artifacts" / "gene_knowledge.json",
        {
            "id": "gene_knowledge_v2",
            "version": "test-version",
            "entities": {
                "gene": {
                    "CYP2D6": {
                        "entity_id": "CYP2D6",
                        "entity_type": "gene",
                        "title": "CYP2D6",
                        "confidence": 0.86,
                        "evidence_level": "A",
                        "sources": ["cpic:guideline-cyp2d6-opioids"],
                        "last_confirmed": "2026-05-18",
                        "decay_rate": "slow",
                    }
                }
            },
            "claims": [
                {
                    "claim_id": "c_cyp2d6_pm_opioid_boundary",
                    "entity_type": "gene",
                    "entity_id": "CYP2D6",
                    "title": "CYP2D6 PM 与可待因/曲马多边界",
                    "confidence": 0.9,
                    "evidence_level": "A",
                    "sources": ["cpic:guideline-cyp2d6-opioids"],
                    "applies_when": ["twin.genetics.CYP2D6_phenotype == 'poor'"],
                    "recommends_lookup": ["entity:drug:codeine"],
                    "body": "CYP2D6 PM 不应把可待因/曲马多作为默认止痛方案。",
                }
            ],
        },
    )
    output = tmp_path / "seed"

    first = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        now=datetime(2026, 5, 18, tzinfo=UTC),
    )
    first_counts = write_down_dedao_wiki_artifacts(first, output)
    second = compile_down_dedao_wiki_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        now=datetime(2026, 5, 18, tzinfo=UTC),
    )
    second_counts = write_down_dedao_wiki_artifacts(second, output)

    assert first_counts["claims"] == 1
    assert second.diff["claims_added"] == 0
    assert second_counts["claims"] == 1
    assert len(_jsonl(output / "claims.jsonl")) == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["down_dedao_wiki"]["skipped_private"] == []


def test_absorb_down_dedao_wiki_cli_blocks_gene_claim_quality_gate_violations(tmp_path):
    source_root = tmp_path / "down-dedao"
    _write_json(
        source_root / "artifacts" / "gene_knowledge.json",
        {
            "id": "gene_knowledge_v2",
            "version": "bad-claim",
            "entities": {"gene": {"CYP2D6": {"entity_id": "CYP2D6"}}},
            "claims": [
                {
                    "claim_id": "c_bad_cyp2d6_claim",
                    "entity_id": "CYP2D6",
                    "title": "CYP2D6 loose claim",
                    "body": "这是一个缺少适用条件和临床限制的 loose claim。",
                }
            ],
            "gene_rules": {},
            "snp_registry": {},
        },
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/absorb_down_dedao_wiki.py",
            "--source-root",
            str(source_root),
            "--artifact-dir",
            str(tmp_path / "seed"),
            "--json-summary",
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    summary = json.loads(result.stdout)
    assert summary["gene_knowledge_audit"]["quality_gates"]["claims_missing_applies_when"] == [
        "c_bad_cyp2d6_claim"
    ]
    assert summary["gene_knowledge_audit"]["quality_gates"]["claims_missing_boundary"] == [
        "c_bad_cyp2d6_claim"
    ]
