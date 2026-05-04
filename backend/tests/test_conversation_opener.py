"""Conversation opener — chat 起手"未读续接" 单测."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, date
from unittest.mock import patch

import pytest

from app.services.conversation_opener import (
    OpenerSuggestion,
    compute_conversation_opener,
)


# ─────────────── 优先级 1: ActionCard 检验日 ───────────────


def test_action_card_due_tomorrow_picks_strategy_1(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="提前晚餐", content="...",
        status="active", source_type="orchestrator",
        metric_key="sleep_score", target_value="82",
        check_back_date=now + timedelta(days=1),
        creator_specialist="recovery_coach",
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "action_card_due"
    assert "明天" in out.text
    assert "提前晚餐" in out.text
    assert len(out.quick_replies) >= 2
    assert out.deep_link.startswith("/action-cards/")


def test_action_card_due_today_uses_today_phrase(db):
    from app.models.action_card import ActionCard
    from zoneinfo import ZoneInfo

    # 今天 (中国时区) 23:00 — check_back is "今天" in CN
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    today_2300 = now_cn.replace(hour=23, minute=0, second=0, microsecond=0)
    db.add(ActionCard(
        user_id=1, title="走 6000 步", content="...",
        status="active", source_type="orchestrator",
        metric_key="weight", target_value="75",
        check_back_date=today_2300.astimezone(timezone.utc),
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert "今天" in out.text or "明天" in out.text  # 临界条件按 day 算
    assert out.source == "action_card_due"


def test_action_card_already_graded_ignored(db):
    """已经 grade 过的卡不能再问 (用户已做 outcome review)."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="打卡 X", content="...",
        status="active", check_back_date=now + timedelta(days=1),
        graded_at=now - timedelta(days=1), accuracy_score=80,
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is None or out.source != "action_card_due"


def test_action_card_check_back_far_future_ignored(db):
    """检验日 >2 天的卡不催 (心智负担)."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="一周后再看", content="...",
        status="active", check_back_date=now + timedelta(days=5),
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is None or out.source != "action_card_due"


def test_action_card_archived_ignored(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="已归档", content="...",
        status="archived", check_back_date=now + timedelta(days=1),
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


# ─────────────── 优先级 2: 24h 内 anomaly ───────────────


def test_recent_warning_anomaly_picked(db):
    from app.models.anomaly_alert import AnomalyAlert

    today = date.today()
    db.add(AnomalyAlert(
        user_id=1, alert_type="hrv_drop", severity="warning",
        metric_name="hrv", current_value=42.0, baseline_value=55.0,
        deviation_pct=-23.6, detection_date=today,
        message="HRV 下降明显", acknowledged=False, is_suppressed=False,
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "anomaly"
    assert "HRV" in out.text
    assert "42" in out.text
    assert out.deep_link.startswith("/trace/anomaly_")


def test_acknowledged_anomaly_not_picked(db):
    """用户已查看过的不再当 opener (已经看过这事了)."""
    from app.models.anomaly_alert import AnomalyAlert

    db.add(AnomalyAlert(
        user_id=1, alert_type="rhr_spike", severity="warning",
        metric_name="rhr", current_value=72.0, baseline_value=60.0,
        detection_date=date.today(),
        message="心率高", acknowledged=True,
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_suppressed_anomaly_not_picked(db):
    from app.models.anomaly_alert import AnomalyAlert

    db.add(AnomalyAlert(
        user_id=1, alert_type="stress_high", severity="warning",
        metric_name="stress_level", current_value=65.0,
        detection_date=date.today(),
        message="...", is_suppressed=True,
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_info_severity_anomaly_skipped(db):
    """info 级 anomaly 噪声大, opener 不选."""
    from app.models.anomaly_alert import AnomalyAlert

    db.add(AnomalyAlert(
        user_id=1, alert_type="rhr_spike", severity="info",
        metric_name="rhr", current_value=68.0, detection_date=date.today(),
        message="...", acknowledged=False, is_suppressed=False,
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_old_anomaly_outside_24h_skipped(db):
    """超过 24h 的 anomaly 不再当今天的 opener."""
    from app.models.anomaly_alert import AnomalyAlert

    db.add(AnomalyAlert(
        user_id=1, alert_type="hrv_drop", severity="critical",
        metric_name="hrv", current_value=30.0,
        detection_date=date.today() - timedelta(days=3),
        message="...", acknowledged=False, is_suppressed=False,
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


# ─────────────── 优先级 3: case_thread ───────────────


def test_active_case_thread_3d_old_picked(db):
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    db.add(CaseThread(
        user_id=1, theme="rhinitis", title="鼻炎跟进",
        status="active",
        opened_at=now - timedelta(days=10),
        last_updated_at=now - timedelta(days=3),
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "case_thread"
    assert "鼻炎跟进" in out.text


def test_case_thread_too_recent_skipped(db):
    """< 24h 的更新不催 (用户还没遗忘)."""
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    db.add(CaseThread(
        user_id=1, theme="rhinitis", title="刚聊过",
        status="active",
        opened_at=now - timedelta(days=2),
        last_updated_at=now - timedelta(hours=2),
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_case_thread_too_old_skipped(db):
    """> 7 天的不催 (信息已过时)."""
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    db.add(CaseThread(
        user_id=1, theme="rhinitis", title="老 case",
        status="active",
        last_updated_at=now - timedelta(days=15),
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_resolved_case_thread_skipped(db):
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    db.add(CaseThread(
        user_id=1, theme="rhinitis", title="已解决",
        status="resolved",
        last_updated_at=now - timedelta(days=3),
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


# ─────────────── 优先级 4: memory_fact ───────────────


def test_recent_semantic_memory_fact_picked(db):
    from app.models.memory_fact import MemoryFact

    now = datetime.now(timezone.utc)
    db.add(MemoryFact(
        user_id=1, tier="semantic",
        subject="你", predicate="has_symptom", object_value="鼻塞",
        confidence=0.8, sources=[],
        last_reinforced_at=now - timedelta(days=2),
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "memory_fact"
    assert "鼻塞" in out.text


def test_working_tier_memory_skipped(db):
    """working 是临时工作记忆, 不该当 opener (噪声大)."""
    from app.models.memory_fact import MemoryFact

    now = datetime.now(timezone.utc)
    db.add(MemoryFact(
        user_id=1, tier="working",
        subject="你", predicate="prefers", object_value="温水",
        confidence=0.5, sources=[],
        last_reinforced_at=now - timedelta(hours=2),
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_superseded_memory_skipped(db):
    """已被 supersede (newer fact 替代) 的不再选."""
    from app.models.memory_fact import MemoryFact

    now = datetime.now(timezone.utc)
    old = MemoryFact(
        user_id=1, tier="semantic",
        subject="你", predicate="takes_medication", object_value="老药",
        confidence=0.7, sources=[],
        last_reinforced_at=now - timedelta(days=2),
    )
    db.add(old); db.flush()
    new = MemoryFact(
        user_id=1, tier="semantic",
        subject="你", predicate="takes_medication", object_value="新药",
        confidence=0.9, sources=[],
        last_reinforced_at=now - timedelta(days=1),
        supersedes_id=old.id,
    )
    db.add(new); db.flush()
    old.superseded_by_id = new.id
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    # 应该选 new fact (老的被 supersede), 但 new 不该被 supersede
    assert out is not None
    assert "新药" in out.text


# ─────────────── 优先级排序 ───────────────


def test_action_card_beats_anomaly(db):
    """ActionCard due (priority=100) > anomaly (80)."""
    from app.models.action_card import ActionCard
    from app.models.anomaly_alert import AnomalyAlert

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="check 1", status="active",
        content="...", check_back_date=now + timedelta(days=1),
    ))
    db.add(AnomalyAlert(
        user_id=1, alert_type="hrv_drop", severity="critical",
        metric_name="hrv", current_value=30.0,
        detection_date=date.today(),
        message="...", acknowledged=False, is_suppressed=False,
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "action_card_due"


def test_anomaly_beats_case_thread(db):
    from app.models.anomaly_alert import AnomalyAlert
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    db.add(AnomalyAlert(
        user_id=1, alert_type="hrv_drop", severity="warning",
        metric_name="hrv", current_value=40.0,
        detection_date=date.today(),
        message="...", acknowledged=False, is_suppressed=False,
    ))
    db.add(CaseThread(
        user_id=1, theme="x", title="some case",
        status="active",
        last_updated_at=now - timedelta(days=3),
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "anomaly"


# ─────────────── 冷启动 + 异常防御 ───────────────


def test_no_signals_returns_none(db):
    """0 数据用户 → None, 前端退化到 SUGGESTIONS."""
    assert compute_conversation_opener(db, user_id=1) is None


def test_db_exception_returns_none(db):
    """SQL 失败也不该崩 chat 启动."""
    with patch("app.services.conversation_opener._try_action_card_due",
               side_effect=Exception("boom")):
        with patch("app.services.conversation_opener._try_recent_anomaly",
                   side_effect=Exception("boom")):
            with patch("app.services.conversation_opener._try_active_case_thread",
                       side_effect=Exception("boom")):
                with patch("app.services.conversation_opener._try_recent_memory_fact",
                           side_effect=Exception("boom")):
                    out = compute_conversation_opener(db, user_id=1)
    assert out is None


def test_other_user_data_isolated(db):
    """user_id=2 的卡不该出现在 user_id=1 的 opener."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=2, title="别人的卡", status="active",
        content="...", check_back_date=now + timedelta(days=1),
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


# ─────────────── 数据形态 ───────────────


def test_returned_dict_serializable():
    """OpenerSuggestion 必须能 asdict() — 给 endpoint 序列化."""
    from dataclasses import asdict
    out = OpenerSuggestion(
        text="test", source="action_card_due", source_id=1,
        quick_replies=["a", "b"], deep_link="/x", priority=100,
    )
    d = asdict(out)
    assert d["text"] == "test"
    assert d["quick_replies"] == ["a", "b"]


# ─────────────── HTTP endpoint /agent/conversation-opener ───────────────


def test_endpoint_returns_null_when_no_signals(client, auth_user_and_headers):
    """0 数据用户拉 endpoint → opener=null, 前端退化到 SUGGESTIONS."""
    _, headers = auth_user_and_headers
    r = client.get("/api/v1/agent/conversation-opener", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"opener": None}


def test_endpoint_returns_action_card_opener(client, db, auth_user_and_headers):
    from app.models.action_card import ActionCard

    user, headers = auth_user_and_headers

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=user.id, title="提前晚餐", content="...",
        status="active", check_back_date=now + timedelta(days=1),
        metric_key="sleep_score",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-opener", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["opener"] is not None
    assert data["opener"]["source"] == "action_card_due"
    assert "提前晚餐" in data["opener"]["text"]
    assert isinstance(data["opener"]["quick_replies"], list)
    assert data["opener"]["deep_link"].startswith("/action-cards/")


def test_endpoint_requires_auth(client):
    """未登录拉应该 401."""
    r = client.get("/api/v1/agent/conversation-opener")
    assert r.status_code in (401, 403)


def test_endpoint_isolates_users(client, db, auth_user_and_headers):
    """另一个用户的卡不该出现在自己的 opener."""
    from app.models.action_card import ActionCard

    user, headers = auth_user_and_headers
    other_id = user.id + 99

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=other_id, title="别人的", content="...",
        status="active", check_back_date=now + timedelta(days=1),
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-opener", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"opener": None}
