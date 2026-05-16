from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_pipeline import (
    classify_health_source,
    scan_health_sources,
)
from app.services.system_knowledge_service import lookup_for_twin
from app.services.system_knowledge_service import (
    attach_system_knowledge_evidence,
    format_system_knowledge_for_prompt,
)
from app.orchestrator.schema import SpecialistFinding


def test_lookup_for_twin_matches_boolean_goal_conditions(db):
    db.add(
        KBDocument(
            doc_id="claim:c_weight_waist_tracking",
            doc_type="claim",
            entity_type="intervention",
            entity_id="weight-waist-tracking",
            title="体重和腰围晨起记录",
            summary="减重和代谢风险管理应跟踪体重与腰围趋势。",
            confidence=0.72,
            evidence_level="B",
            applies_when=["twin.goals.weight_loss.active == true"],
            sources=["dedao:fengxue-weight-loss"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        )
    )
    db.commit()

    result = lookup_for_twin(db, {"goals": {"weight_loss": {"active": True}}})

    assert [claim["doc_id"] for claim in result["claims"]] == ["claim:c_weight_waist_tracking"]
    assert result["claims"][0]["matched_conditions"] == [
        "twin.goals.weight_loss.active == true"
    ]


def test_scan_health_sources_filters_relevant_courses(tmp_path):
    root = tmp_path / "down-dedao"
    (root / "冯雪·高血糖医学课" / "PDF").mkdir(parents=True)
    (root / "冯雪·高血糖医学课" / "PDF" / "01 - 血糖为什么升高？.pdf").write_text("x")
    (root / "Python量化投资指南" / "PDF").mkdir(parents=True)
    (root / "Python量化投资指南" / "PDF" / "01 - 回测.pdf").write_text("x")

    sources = scan_health_sources(root)

    assert [source.course_name for source in sources] == ["冯雪·高血糖医学课"]
    assert sources[0].domains == ["metabolic_health"]
    assert sources[0].lesson_count == 1
    assert sources[0].source_key == "dedao:fengxue-gaoxuetang-yixueke"


def test_scan_health_sources_excludes_private_material(tmp_path):
    root = tmp_path / "down-dedao"
    (root / "personal" / "user-3").mkdir(parents=True)
    (root / "personal" / "user-3" / "personal-weight-management.md").write_text(
        "体重 血糖 血脂 尿酸 腰围 睡眠 健康 医学 营养",
        encoding="utf-8",
    )
    (root / "私人健康日志" / "notes").mkdir(parents=True)
    (root / "私人健康日志" / "notes" / "01 - 血糖和体重.md").write_text(
        "血糖 体重 腰围 健康 营养",
        encoding="utf-8",
    )
    (root / "冯雪·高血糖医学课" / "PDF").mkdir(parents=True)
    (root / "冯雪·高血糖医学课" / "PDF" / "01 - 血糖为什么升高？.pdf").write_text("x")

    sources = scan_health_sources(root)

    assert [source.course_name for source in sources] == ["冯雪·高血糖医学课"]


def test_classify_health_source_returns_domain_priority():
    result = classify_health_source("冯雪·高血脂医学课", ["07 - 饮食：怎么吃才能降血脂？.pdf"])

    assert result.is_health is True
    assert result.domains[:2] == ["metabolic_health", "cardiovascular"]
    assert result.priority == 1


def test_import_system_kb_artifacts_is_idempotent(tmp_path, db):
    artifact_dir = tmp_path / "artifacts" / "v2"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "entities.jsonl").write_text(
        '{"doc_id":"entity:condition:metabolic-health","doc_type":"entity",'
        '"entity_type":"condition","entity_id":"metabolic-health","title":"代谢健康",'
        '"summary":"体重、腰围、血糖、血脂和血压的轨迹管理。",'
        '"confidence":0.75,"evidence_level":"B","sources":["system:test"]}\n'
    )
    (artifact_dir / "claims.jsonl").write_text(
        '{"doc_id":"claim:c_weight_waist_tracking","doc_type":"claim",'
        '"entity_type":"intervention","entity_id":"weight-waist-tracking",'
        '"title":"体重和腰围晨起记录","summary":"减重和代谢风险管理应跟踪体重与腰围趋势。",'
        '"confidence":0.72,"evidence_level":"B",'
        '"applies_when":["twin.goals.weight_loss.active == true"],'
        '"sources":["dedao:fengxue-weight-loss"],"decay_rate":"normal"}\n'
    )
    (artifact_dir / "relations.jsonl").write_text(
        '{"src_doc_id":"entity:condition:metabolic-health",'
        '"dst_doc_id":"claim:c_weight_waist_tracking","relation":"has_claim",'
        '"confidence":0.88,"source_claim_id":"claim:c_weight_waist_tracking"}\n'
    )
    (artifact_dir / "manifest.json").write_text('{"version":"2.0","counts":{"claims":1}}\n')

    first = import_system_kb_artifacts(db, artifact_dir, actor="test")
    second = import_system_kb_artifacts(db, artifact_dir, actor="test")

    assert first == {"documents": 2, "edges": 1}
    assert second == {"documents": 2, "edges": 1}
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_weight_waist_tracking").count() == 1


def test_format_system_knowledge_for_prompt_is_bounded(db):
    db.add(
        KBDocument(
            doc_id="claim:c_weight_waist_tracking",
            doc_type="claim",
            entity_type="intervention",
            entity_id="weight-waist-tracking",
            title="体重和腰围晨起记录",
            summary="减重和代谢风险管理应跟踪体重与腰围趋势。",
            confidence=0.72,
            evidence_level="B",
            applies_when=["twin.goals.weight_loss.active == true"],
            sources=["dedao:fengxue-weight-loss"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        )
    )
    db.commit()

    prompt_block = format_system_knowledge_for_prompt(
        db,
        {"goals": {"weight_loss": {"active": True}}},
        max_claims=3,
    )

    assert "## 系统知识库相关条目" in prompt_block
    assert "体重和腰围晨起记录" in prompt_block
    assert "claim:c_weight_waist_tracking" in prompt_block
    assert "不替代医生诊断" in prompt_block


def test_lookup_for_twin_matches_longevity_goal_to_aging_hallmark(db):
    db.add_all(
        [
            KBDocument(
                doc_id="entity:aging_hallmark:mitochondrial_dysfunction",
                doc_type="entity",
                entity_type="aging_hallmark",
                entity_id="mitochondrial_dysfunction",
                title="线粒体功能障碍",
                summary="衰老标志之一，用于长期轨迹解释，不直接推出补剂建议。",
                confidence=0.72,
                evidence_level="B",
                sources=["cell:2023-hallmarks-of-aging"],
                last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            ),
            KBDocument(
                doc_id="claim:c_aging_hallmarks_are_trajectory_taxonomy",
                doc_type="claim",
                entity_type="aging_hallmark",
                entity_id="trajectory-taxonomy",
                title="衰老标志只作为轨迹分类框架",
                summary="衰老标志适合组织长期风险和机制沟通，不能直接映射为补剂处方。",
                confidence=0.76,
                evidence_level="B",
                applies_when=["twin.goals.longevity.active == true"],
                recommends_lookup=["entity:aging_hallmark:mitochondrial_dysfunction"],
                sources=["cell:2023-hallmarks-of-aging"],
                last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            ),
        ]
    )
    db.commit()

    result = lookup_for_twin(db, {"goals": {"longevity": {"active": True}}})

    assert [entity["doc_id"] for entity in result["entities"]] == [
        "entity:aging_hallmark:mitochondrial_dysfunction"
    ]
    assert [claim["doc_id"] for claim in result["claims"]] == [
        "claim:c_aging_hallmarks_are_trajectory_taxonomy"
    ]


def test_seed_artifacts_include_fourteen_aging_hallmarks():
    import json
    from pathlib import Path

    artifact_path = Path("backend/data/system_kb_v2_seed/entities.jsonl")
    hallmarks = [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("entity_type") == "aging_hallmark"
    ]

    assert len(hallmarks) == 14
    assert {item["entity_id"] for item in hallmarks} >= {
        "genomic_instability",
        "telomere_attrition",
        "mitochondrial_dysfunction",
        "psychosocial_stress_isolation",
    }


def test_attach_system_knowledge_evidence_adds_claim_refs_to_specialist_findings(db):
    db.add(
        KBDocument(
            doc_id="claim:c_zone2_as_metabolic_base_not_when_recovery_low",
            doc_type="claim",
            entity_type="intervention",
            entity_id="zone2-training",
            title="中等强度有氧是代谢基础但需受恢复状态约束",
            summary="恢复不足时降低训练强度。",
            confidence=0.73,
            evidence_level="B",
            applies_when=["twin.wearable.sleep_duration_hours < 6.5"],
            sources=["dedao:fengxue-weight-loss"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"domain": "movement"},
        )
    )
    db.commit()
    finding = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="今天降低跑步强度",
        findings=[{"title": "降低跑步强度", "action": "今天只做恢复活动"}],
    )

    attach_system_knowledge_evidence(
        db,
        {"wearable": {"sleep_duration_hours": 5.8}},
        [finding],
    )

    assert finding.evidence_refs == ["claim:c_zone2_as_metabolic_base_not_when_recovery_low"]
    assert finding.raw["system_kb_evidence_refs"] == [
        "claim:c_zone2_as_metabolic_base_not_when_recovery_low"
    ]
    assert finding.findings[0]["evidence_refs"] == [
        "claim:c_zone2_as_metabolic_base_not_when_recovery_low"
    ]
