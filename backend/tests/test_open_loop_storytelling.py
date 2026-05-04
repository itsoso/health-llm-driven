"""
P2 故事化测试 — 推送 title/body 必须含"为什么 + 做什么", 不能再只是干瘪事实陈述.

历史 (2026-05-04 前): "🤸 拉伸 断了 61 天" / body "运动「拉伸」连续 61 天未完成. 重建节奏从今天开始."
P2 后: "🏃 拉伸 停了 61 天" / body "61 天没记。断点不可怕，今天补 5 分钟也算 — 先把节奏接回来。"

这些测试守护语气改进不被改回老命令式, 同时验证 cross-data / 行动建议存在.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.tasks.open_loop_manager import (
    _detect_lab_overdue,
    _detect_action_card_due,
    _detect_sync_stale,
    _detect_trend_anomaly,
    _detect_plan_deviation,
)


# ─────────────── lab_overdue ───────────────


def test_lab_overdue_body_contains_action_phrase(db):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    exam = MedicalExam(
        user_id=1, exam_date=date.today() - timedelta(days=210),
        exam_type="blood",
    )
    db.add(exam); db.flush()
    db.add(MedicalExamItem(
        exam_id=exam.id, category="lipid",
        item_name="LDL 胆固醇", item_code="LDL-C",
        value=4.1, unit="mmol/L",
    ))
    db.commit()

    loops = _detect_lab_overdue(db, user_id=1)
    assert len(loops) >= 1
    loop = loops[0]
    # P2 标题不再用命令式 "该复查了" → "是时候复查了" (建议而非命令)
    assert "复查" in loop.title
    assert "该复查" not in loop.title  # 老命令式不能再出现
    # body 必须含具体行动 ("这周抽时间" 等)
    assert "这周" in loop.body or "抽时间" in loop.body or "测一下" in loop.body


# ─────────────── action_card_due ───────────────


def test_action_card_high_score_uses_celebratory_tone(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=1, title="提前晚餐 7 天",
        content="...", source_type="orchestrator",
        check_back_date=now - timedelta(hours=12),
        graded_at=now - timedelta(hours=6),
        accuracy_score=85,
        grading_notes="完成度高", metric_key="sleep_score",
    )
    db.add(card); db.commit()

    loops = _detect_action_card_due(db, user_id=1)
    assert len(loops) == 1
    loop = loops[0]
    # 高分: ✅ 命中 + 鼓励性语气
    assert "命中" in loop.title or "✅" in loop.title
    assert "85" in loop.body
    # body 必须有"为什么/做什么"成分 — 不能只数字
    assert any(kw in loop.body for kw in ["保持", "节奏", "对的", "维持"])


def test_action_card_mid_score_acknowledges_partial(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="减重计划",
        content="...", source_type="orchestrator",
        check_back_date=now - timedelta(hours=12),
        graded_at=now - timedelta(hours=6),
        accuracy_score=55, grading_notes="部分达标",
    ))
    db.commit()

    loops = _detect_action_card_due(db, user_id=1)
    loop = loops[0]
    assert "部分" in loop.title or "⚠️" in loop.title
    # body 不能羞辱用户, 应"调一调"/"看看"等
    assert any(kw in loop.body for kw in ["调", "看看", "可以", "再"])


def test_action_card_low_score_uses_supportive_not_blaming(db):
    """关键: 低分必须用支持性语气, 不能"未达"羞辱用户."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="夜跑 7 天",
        content="...", source_type="orchestrator",
        check_back_date=now - timedelta(hours=12),
        graded_at=now - timedelta(hours=6),
        accuracy_score=20, grading_notes="未达成",
    ))
    db.commit()

    loops = _detect_action_card_due(db, user_id=1)
    loop = loops[0]
    # 关键: 不能羞辱 — body 必须有"自责" 反向词或"建议不合适" 等开放归因
    assert any(kw in loop.body for kw in ["自责", "卡住", "建议", "学到", "不合适", "执行"])


# ─────────────── sync_stale ───────────────


def test_sync_stale_explains_why_not_just_status(db):
    """P2: 不只是"同步可能中断" 数据状态, 要说"AI 给不出判断" 关联用户价值."""
    from app.models.daily_health import GarminData

    db.add(GarminData(
        user_id=1, record_date=date.today() - timedelta(days=5),
        sleep_score=70, hrv=45,
    ))
    db.commit()

    loops = _detect_sync_stale(db, user_id=1)
    assert len(loops) == 1
    loop = loops[0]
    # body 必须解释"为什么这事重要" — "AI 给不出判断" / "影响" 等
    assert any(kw in loop.body for kw in ["AI", "判断", "影响"])
    # 必须有具体动作 — "蓝牙" / "重新登录" 等
    assert any(kw in loop.body for kw in ["蓝牙", "登录", "Connect"])


# ─────────────── trend_anomaly ───────────────


def test_trend_anomaly_includes_concrete_actions(db):
    """P2: HRV 跌不能只说"需关注" — 必须给具体行动 (早睡/降强度/...)."""
    from app.models.daily_health import GarminData

    today = date.today()
    # 前 7 天: HRV 平均 60
    for i in range(8, 15):
        db.add(GarminData(
            user_id=1, record_date=today - timedelta(days=i), hrv=60,
        ))
    # 最近 7 天: HRV 平均 45 (跌 25%)
    for i in range(0, 7):
        db.add(GarminData(
            user_id=1, record_date=today - timedelta(days=i), hrv=45,
        ))
    db.commit()

    loops = _detect_trend_anomaly(db, user_id=1)
    assert len(loops) >= 1
    loop = loops[0]
    # 不能"需关注" 这种含糊词
    assert "需关注" not in loop.body
    # 必须含至少一个具体行动 (早睡/调低/休息)
    assert any(kw in loop.body for kw in ["早睡", "调低", "休息", "减", "降"])


# ─────────────── plan_drift ───────────────


def test_plan_drift_medicine_uses_supportive_tone(db):
    """P2: 漏药严重, 但语气不能命令式 — '今天补一次, 往后我们一起跟'."""
    from app.models.checkin import CheckinTemplate

    db.add(CheckinTemplate(
        user_id=1, name="降压药", category="medicine",
        frequency="daily", is_active=True, is_archived=False,
        last_checkin_date=date.today() - timedelta(days=5),
        icon="💊",
    ))
    db.commit()

    loops = _detect_plan_deviation(db, user_id=1)
    assert len(loops) == 1
    loop = loops[0]
    # title: "漏了 N 天" 比"断了 N 天" 更直接
    assert "漏" in loop.title or "停" in loop.title  # 任一接受
    # body 不能命令式
    assert "重建节奏" not in loop.body
    assert "重建" not in loop.body
    # 必须有支持性: "一起跟"/"补一次"/"今天" 等
    assert any(kw in loop.body for kw in ["一起", "今天", "补", "跟"])


def test_plan_drift_exercise_reduces_burden(db):
    """P2: 运动断点用"今天补 5 分钟也算" 减负担, 不要"重建节奏" 加压."""
    from app.models.checkin import CheckinTemplate

    db.add(CheckinTemplate(
        user_id=1, name="拉伸", category="exercise",
        frequency="daily", is_active=True, is_archived=False,
        last_checkin_date=date.today() - timedelta(days=61),
        icon="🤸",
    ))
    db.commit()

    loops = _detect_plan_deviation(db, user_id=1)
    loop = loops[0]
    # 减负担表达
    assert any(kw in loop.body for kw in ["也算", "5 分钟", "5 分", "断点", "节奏"])
    # 反向: 不应再"重建节奏从今天开始"
    assert "重建节奏" not in loop.body


# ─────────────── 共性检查 ───────────────


def test_common_quality_each_detector_body_not_empty(db):
    """sanity: 任何触发的 OpenLoop body 非空, < 200 字."""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    exam = MedicalExam(
        user_id=1, exam_date=date.today() - timedelta(days=200),
        exam_type="blood",
    )
    db.add(exam); db.flush()
    db.add(MedicalExamItem(
        exam_id=exam.id, item_name="LDL", item_code="LDL", value=4.1,
    ))
    db.commit()

    for loop in _detect_lab_overdue(db, user_id=1):
        assert loop.body
        assert len(loop.body) <= 200, f"body 过长 ({len(loop.body)}字), APNs 不友好"
        assert len(loop.title) <= 40, f"title 过长 ({len(loop.title)}字), APNs 通知栏会截断"
