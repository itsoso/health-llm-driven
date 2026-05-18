from __future__ import annotations

import json
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
                    "recommends_lookup": ["entity:drug:clopidogrel"],
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


def test_compile_down_dedao_wiki_artifacts_imports_topic_pages_without_long_content_or_private_notes(tmp_path):
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
    long_paid_text = "这一段模拟课程正文，不能原样进入 serving artifact。" * 20
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
    assert "课程正文" not in json.dumps(page, ensure_ascii=False)
    assert result.skipped_private == ["articles_personal-health-trends.json"]


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
