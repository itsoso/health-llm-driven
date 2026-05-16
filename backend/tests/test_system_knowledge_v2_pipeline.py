from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_pipeline import (
    classify_health_source,
    scan_health_sources,
)
from app.services.system_knowledge_service import lookup_for_twin
from app.services.system_knowledge_service import format_system_knowledge_for_prompt


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
