"""Conversation opener — chat 起手"未读续接" 单测."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, date
from unittest.mock import patch

import pytest

from app.services.conversation_opener import (
    OpenerSuggestion,
    compute_conversation_opener,
    humanize_card_title,
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


def test_action_card_due_humanizes_noisy_alert_title(db):
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1,
        title="血氧饱和度偏低：94.0%（阈值 95%），请注意",
        content="...",
        status="active",
        source_type="orchestrator",
        check_back_date=now,
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)

    assert out is not None
    assert "血氧饱和度偏低：94.0%" in out.text
    assert "阈值" not in out.text
    assert "请注意" not in out.text


def test_humanize_card_title_shortens_long_clause_at_boundary():
    title = "长期高强度训练安排需要调整，结合最近睡眠和 HRV 明显恢复不足，请注意"

    out = humanize_card_title(title)

    assert out == "长期高强度训练安排需要调整…"


def test_humanize_card_title_strips_fullwidth_threshold_paren():
    out = humanize_card_title("血氧饱和度偏低：94.0%（阈值 95%），请注意")
    assert out == "血氧饱和度偏低：94.0%"


def test_humanize_card_title_strips_halfwidth_threshold_paren():
    out = humanize_card_title("血氧饱和度偏低：94.0%(阈值 95%),请注意")
    assert out == "血氧饱和度偏低：94.0%"


def test_humanize_card_title_noop_on_clean_title():
    # 已经干净的标题不该被动到
    assert humanize_card_title("提前晚餐") == "提前晚餐"
    assert humanize_card_title("走 6000 步") == "走 6000 步"


def test_humanize_card_title_strips_bare_polite_suffix():
    assert humanize_card_title("血压偏高：165/102，请注意") == "血压偏高：165/102"


def test_humanize_card_title_empty_returns_empty():
    assert humanize_card_title("") == ""
    assert humanize_card_title("   ") == ""


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


def test_action_card_with_self_reported_adherence_ignored(db):
    """用户已在小巴 opener 反馈过做没做, 不应继续展示同一张复盘卡."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="检查夜间血氧", content="...",
        status="active", source_type="orchestrator",
        metric_key="spo2_avg", target_value="95",
        check_back_date=now,
        adherence_kind="self_reported",
        adherence_confidence=70,
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


def test_action_card_with_user_decision_ignored(db):
    """用户点过调整/接受/拒绝后, opener 不再用这张卡反复追问."""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="暂停训练", content="...",
        status="active", source_type="orchestrator",
        check_back_date=now,
        user_decision="adjusted",
        decided_at=now,
    ))
    db.commit()

    assert compute_conversation_opener(db, user_id=1) is None


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


def test_recent_memory_fact_sanitizes_json_blob_before_opener(db):
    from app.models.memory_fact import MemoryFact

    now = datetime.now(timezone.utc)
    db.add(MemoryFact(
        user_id=1,
        tier="semantic",
        subject="你",
        predicate="has_condition",
        object_value='{"药品":"按说明书需要时服用。", "注意事项": "有肝病时慎用，出现不适及时就医。"}',
        confidence=0.8,
        sources=[],
        last_reinforced_at=now - timedelta(days=2),
    ))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)

    assert out is not None
    assert "按说明书需要时服用" in out.text
    assert "注意事项" not in out.text
    assert "{" not in out.text


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


# ─────────────── C1 cold-start: synthesized onboarding opener ───────────────


def test_synthesize_cold_start_opener_shape_and_actions():
    """Deterministic synthetic opener: source=cold_start, 3 action quick replies
    matching the contract's COLD_START_ACTIONS, asdict-serializable."""
    from dataclasses import asdict
    from app.services.conversation_opener import (
        COLD_START_ACTIONS,
        synthesize_cold_start_opener,
    )

    out = synthesize_cold_start_opener()
    assert out.source == "cold_start"
    assert out.source_id is None
    assert out.text and "小巴" in out.text  # 小巴 self-intro
    assert [qr.action for qr in out.quick_replies] == list(COLD_START_ACTIONS)

    d = asdict(out)
    assert [q["action"] for q in d["quick_replies"]] == list(COLD_START_ACTIONS)
    assert all(q["label"] for q in d["quick_replies"])


def test_synthesize_cold_start_opener_is_deterministic():
    """No DB / no RNG — two calls are byte-identical."""
    from dataclasses import asdict
    from app.services.conversation_opener import synthesize_cold_start_opener

    assert asdict(synthesize_cold_start_opener()) == asdict(synthesize_cold_start_opener())


def test_cold_start_opener_text_and_labels_pass_guidance_red_lines():
    """R4: the persona copy must not contain quantified/imperative diet or
    imperative movement prescriptions (guidance_validator must NOT flag it)."""
    from app.services.conversation_opener import synthesize_cold_start_opener
    from app.services.guidance_validator import sanitize_guidance

    out = synthesize_cold_start_opener()
    assert sanitize_guidance(out.text).flagged is False
    for qr in out.quick_replies:
        assert sanitize_guidance(qr.label).flagged is False


def test_cold_start_source_ignored_by_opener_quick_reply_handler(db):
    """A cold-start quick reply is handled by LOCAL client navigation; if the
    client ever POSTs one as opener context, the ActionCard side-effect handler
    must ignore it (source != action_card_due) — no accidental state change."""
    from app.services.opener_quick_reply import apply_opener_quick_reply_context

    ctx = (
        '{"entry": "conversation_opener_quick_reply", "source": "cold_start", '
        '"user_reply": "拍一张今天的饭"}'
    )
    assert apply_opener_quick_reply_context(db, user_id=1, message="hi", extra_context=ctx) is None


# ─────────────── C1 cold-start: is_cold_start_user ───────────────


def test_is_cold_start_user_true_for_zero_data(db):
    from app.services.conversation_starters import is_cold_start_user

    assert is_cold_start_user(db, user_id=1) is True


def test_is_cold_start_user_false_after_a_single_signal(db):
    from datetime import date
    from app.models.daily_health import WaterIntake
    from app.services.conversation_starters import is_cold_start_user

    db.add(WaterIntake(
        user_id=1,
        record_date=date.today(),
        intake_time=datetime.now(timezone.utc),
        amount_ml=250,
        drink_type="water",
    ))
    db.commit()
    assert is_cold_start_user(db, user_id=1) is False


def test_is_cold_start_user_fail_soft_returns_false_on_error(db):
    """Signal collection error → NOT cold-start (safer than injecting a synthetic
    opener onto an established user whose collection transiently failed)."""
    from app.services import conversation_starters as cs

    with patch.object(cs, "_collect_signals", side_effect=Exception("boom")):
        assert cs.is_cold_start_user(db, user_id=1) is False


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


# ─────────────── 优先级 2b: 慢病/结节随访到期 (health_problem) ───────────────


def _add_problem(db, user_id, *, name, risk="P1", next_due=None, what_to_check=None, status="active"):
    from app.models.health_problem import HealthProblem

    p = HealthProblem(
        user_id=user_id,
        name=name,
        risk_level=risk,
        status=status,
        follow_up={"next_due": str(next_due), "what_to_check": what_to_check} if next_due else None,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_overdue_problem_followup_becomes_opener(db):
    """登记慢病的随访逾期 → health_problem opener，续接式复查话题。"""
    p = _add_problem(
        db, 1, name="胃溃疡(Hp 阴性,胃窦后壁)", risk="P1",
        next_due=date.today() - timedelta(days=10), what_to_check="胃镜复查",
    )
    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "health_problem"
    assert out.source_id == p.id
    # 括注剥掉，只留主名
    assert "胃溃疡" in out.text
    assert "(Hp" not in out.text
    assert "到期" in out.text
    assert len(out.quick_replies) >= 2
    assert out.priority == 70


def test_upcoming_problem_followup_uses_prepare_phrasing(db):
    p = _add_problem(
        db, 1, name="甲状腺结节(TI-RADS 3)", risk="P2",
        next_due=date.today() + timedelta(days=5), what_to_check="甲状腺超声",
    )
    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "health_problem"
    assert "甲状腺结节" in out.text
    assert "准备" in out.text


def test_action_card_outranks_problem_followup(db):
    """ActionCard(100) 优先级压过 health_problem(70)。"""
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    db.add(ActionCard(
        user_id=1, title="走 6000 步", content="...", status="active",
        check_back_date=now + timedelta(days=1),
    ))
    _add_problem(db, 1, name="鼻炎", next_due=date.today() - timedelta(days=3))
    db.commit()

    out = compute_conversation_opener(db, user_id=1)
    assert out is not None
    assert out.source == "action_card_due"


def test_problem_without_due_followup_is_not_opener(db):
    """登记了问题但随访没到期(远期) → 不作为 opener(交给 chips 的管理线)。"""
    _add_problem(
        db, 1, name="鼻炎", next_due=date.today() + timedelta(days=90),
    )
    out = compute_conversation_opener(db, user_id=1)
    # 90 天远超 within_days=14 窗口 → 无 opener
    assert out is None or out.source != "health_problem"


def test_problem_followup_isolates_users(db):
    _add_problem(db, 2, name="别人的胃溃疡", next_due=date.today() - timedelta(days=5))
    out = compute_conversation_opener(db, user_id=1)
    assert out is None or out.source != "health_problem"
