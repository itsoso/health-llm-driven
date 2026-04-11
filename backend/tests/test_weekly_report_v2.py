"""Weekly Report V2 升级版 - 单元测试

核心能力:
- cross_reference_engine: 拉 active audits/consultations, 计算 action 执行证据
- verify_active_predictions: 复用 health_consultation_service 做 prediction 中期校验
- gene_alignment_score: 基因-行为匹配规则引擎
"""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.daily_health import DietRecord, ExerciseRecord, GarminData
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.health_consultation import ConsultationItem, HealthConsultation
from app.models.supplement_audit import SupplementAudit, SupplementAuditItem
from app.models.user import User
from app.services.weekly_report_service import weekly_report_service


@pytest.fixture
def test_user(db):
    u = User(username="weekly_test", email="weekly_test@example.com", hashed_password="x", name="Weekly Test")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def week_range():
    # 2026-04-06 (Mon) ~ 2026-04-12 (Sun)
    return (date(2026, 4, 6), date(2026, 4, 12))


# ======================= Cross-reference engine =======================

def test_cross_reference_pulls_active_audits_and_consultations(db, test_user, week_range):
    week_start, week_end = week_range

    # 建 1 个 active audit + 2 个 pending items
    audit = SupplementAudit(
        user_id=test_user.id, version=1, title="Test Audit",
        triggered_by="manual", rationale_markdown="#", status="active",
    )
    db.add(audit)
    db.flush()
    db.add(SupplementAuditItem(
        audit_id=audit.id, user_id=test_user.id, action_type="add",
        title="加 Taurine", rationale_markdown="#", status="pending",
    ))
    db.add(SupplementAuditItem(
        audit_id=audit.id, user_id=test_user.id, action_type="add",
        title="加 Curcumin", rationale_markdown="#", status="completed",  # 不应出现在 pending 列表
    ))

    # 建 1 个 active consultation + 2 个 pending actions
    consult = HealthConsultation(
        user_id=test_user.id, version=1, title="Test Consult",
        consultation_type="symptom_advisory", triggered_by="manual",
        rationale_markdown="#", status="active",
    )
    db.add(consult)
    db.flush()
    db.add(ConsultationItem(
        consultation_id=consult.id, user_id=test_user.id,
        item_type="action", item_code="A1", title="Garmin HRV 采集",
        content_markdown="#", meta={}, status="pending",
    ))
    db.add(ConsultationItem(
        consultation_id=consult.id, user_id=test_user.id,
        item_type="action", item_code="A2", title="避免酒精饮食",
        content_markdown="#", meta={}, status="pending",
    ))
    db.commit()

    result = weekly_report_service.cross_reference_engine(
        db, test_user.id, week_start, week_end
    )

    assert audit.id in result["linked_audit_ids"]
    assert consult.id in result["linked_consultation_ids"]
    assert len(result["supplement_audit_items"]) == 1  # 只有 pending
    assert len(result["consultation_actions"]) == 2
    assert result["summary"]["total"] == 3  # 1 audit + 2 consult actions


def test_evidence_hrv_done_when_data_exists(db, test_user, week_range):
    week_start, week_end = week_range

    # 建 consultation action "Garmin HRV 采集"
    consult = HealthConsultation(
        user_id=test_user.id, version=1, title="C",
        consultation_type="symptom_advisory", triggered_by="manual",
        rationale_markdown="#", status="active",
    )
    db.add(consult)
    db.flush()
    db.add(ConsultationItem(
        consultation_id=consult.id, user_id=test_user.id,
        item_type="action", item_code="A1", title="Garmin HRV 采集",
        content_markdown="#", meta={}, status="pending",
    ))
    # 塞本周 3 天有 HRV 数据
    for i, d in enumerate([week_start, week_start + timedelta(days=2), week_start + timedelta(days=4)]):
        db.add(GarminData(
            user_id=test_user.id, record_date=d,
            steps=5000, hrv=45.0 + i,
        ))
    db.commit()

    result = weekly_report_service.cross_reference_engine(
        db, test_user.id, week_start, week_end
    )
    action = result["consultation_actions"][0]
    assert action["evidence"]["verdict"] == "done"
    assert "3 天" in action["evidence"]["note"]


def test_evidence_alcohol_violation_when_detected(db, test_user, week_range):
    week_start, week_end = week_range

    consult = HealthConsultation(
        user_id=test_user.id, version=1, title="C",
        consultation_type="symptom_advisory", triggered_by="manual",
        rationale_markdown="#", status="active",
    )
    db.add(consult)
    db.flush()
    db.add(ConsultationItem(
        consultation_id=consult.id, user_id=test_user.id,
        item_type="action", item_code="A11", title="避免酒精饮食",
        content_markdown="#", meta={}, status="pending",
    ))
    # 塞本周 1 次啤酒记录
    db.add(DietRecord(
        user_id=test_user.id, record_date=week_start + timedelta(days=3),
        meal_type="dinner", food_name="啤酒 200ml 羊肉 200g",
    ))
    db.commit()

    result = weekly_report_service.cross_reference_engine(
        db, test_user.id, week_start, week_end
    )
    action = result["consultation_actions"][0]
    assert action["evidence"]["verdict"] == "violation"
    assert result["summary"]["evidenced_violation"] == 1


# ======================= Gene alignment scoring =======================

def _mk_variant(user_id, gene, genotype):
    profile = GeneticProfile(user_id=user_id, test_provider="test", test_date=date(2024, 1, 1))
    return profile, GeneticVariant(
        user_id=user_id, gene_name=gene, genotype=genotype, category="nutrition"
    )


def test_gene_alignment_fads1_hit_with_salmon(db, test_user, week_range):
    week_start, week_end = week_range

    profile = GeneticProfile(user_id=test_user.id, test_provider="test", test_date=date(2024, 1, 1))
    db.add(profile)
    db.flush()
    db.add(GeneticVariant(
        user_id=test_user.id, profile_id=profile.id,
        gene_name="FADS1", genotype="TT", category="nutrition",
    ))
    # 本周 3 次三文鱼
    for i, d in enumerate([week_start, week_start + timedelta(days=1), week_start + timedelta(days=3)]):
        db.add(DietRecord(
            user_id=test_user.id, record_date=d,
            meal_type="lunch", food_name=f"三文鱼饭 {i}",
        ))
    db.commit()

    score = weekly_report_service.gene_alignment_score(
        db, test_user.id, week_start, week_end
    )
    assert any(h["gene"] == "FADS1" for h in score["hits"])
    assert score["total"] >= 1
    assert score["pct"] > 0


def test_gene_alignment_aldh2_miss_with_alcohol(db, test_user, week_range):
    week_start, week_end = week_range

    profile = GeneticProfile(user_id=test_user.id, test_provider="test", test_date=date(2024, 1, 1))
    db.add(profile)
    db.flush()
    db.add(GeneticVariant(
        user_id=test_user.id, profile_id=profile.id,
        gene_name="ALDH2", genotype="GA", category="nutrition",
    ))
    # 本周 2 次酒精
    db.add(DietRecord(user_id=test_user.id, record_date=week_start + timedelta(days=1), meal_type="dinner", food_name="啤酒一杯"))
    db.add(DietRecord(user_id=test_user.id, record_date=week_start + timedelta(days=4), meal_type="dinner", food_name="红酒搭配羊排"))
    db.commit()

    score = weekly_report_service.gene_alignment_score(
        db, test_user.id, week_start, week_end
    )
    miss_genes = [m["gene"] for m in score["misses"]]
    assert "ALDH2" in miss_genes


def test_gene_alignment_skip_when_no_variant(db, test_user, week_range):
    """没有基因数据时不 crash, 返回空分数"""
    week_start, week_end = week_range
    score = weekly_report_service.gene_alignment_score(
        db, test_user.id, week_start, week_end
    )
    assert score["total"] == 0
    assert score["max"] == 0
    assert score["hits"] == []
    assert score["misses"] == []


# ======================= Markdown render =======================

def test_render_markdown_safe_with_minimal_data(db, test_user, week_range):
    """验证 markdown 生成不会因字段缺失 crash"""
    from app.models.health_report import HealthReport
    week_start, week_end = week_range
    report = HealthReport(
        user_id=test_user.id, report_type="weekly",
        start_date=week_start, end_date=week_end, title="test",
        health_score=75,
    )
    md = weekly_report_service._render_markdown(
        test_user.id, week_start, week_end, report,
        cross_ref={"consultation_actions": [], "supplement_audit_items": [], "summary": {}, "linked_audit_ids": [], "linked_consultation_ids": []},
        predictions=[],
        gene={"total": 0, "max": 0, "pct": 0, "hits": [], "partial": [], "misses": []},
    )
    assert "本周健康周报" in md
    assert "数据快照" in md
