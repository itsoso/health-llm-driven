"""§5 推送隐私(AGENTS.md §5.6):锁屏可见的 title/content 不携带药名/补剂名/化验项/诊断。

正反例双向:
- 敏感生产者的可见文本不含具体名称(名称只进 data payload);
- 非敏感类别(vitals/急性)保持原文透传,不被过度泛化(over-redaction 也是 bug)。
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.safety_guardian.schema import Alert, Severity
from app.services.notification.push_privacy import (
    is_sensitive_alert,
    safety_alert_push_text,
)

DRUG = "华法林"
SUPP = "辅酶Q10"


def _alert(category: str, rule_id: str, severity=Severity.HIGH) -> Alert:
    return Alert(
        rule_id=rule_id,
        category=category,
        severity=severity,
        title=f"{DRUG} 与 NSAID 合用出血风险",
        message=f"检测到 {DRUG} 与布洛芬同期使用，出血风险升高。",
    )


# ─────────────────── helper: safety_alert_push_text ───────────────────

@pytest.mark.parametrize("category,rule_id", [
    ("ddi", "ddi.warfarin_nsaid"),
    ("dsi", "dsi.fish_oil_anticoagulant"),
    ("pgx", "pgx.cyp2c19_clopidogrel"),
    ("labs", "labs.liver_enzyme_pattern"),
    ("problem_red_lines", "problem_red_lines.health_problem_red_line"),
])
def test_sensitive_categories_genericized(category, rule_id):
    title, content = safety_alert_push_text(_alert(category, rule_id))
    assert DRUG not in title and DRUG not in content
    assert "布洛芬" not in content
    # 严重度语义仍在(泛化不等于丢失紧急度)
    assert "警告" in title


def test_vitals_alert_passes_through():
    """急性生命体征告警不被过度泛化——数值措辞是时效安全信息。"""
    a = Alert(
        rule_id="vitals.bp_critical",
        category="vitals",
        severity=Severity.CRITICAL,
        title="血压 185/125 达到急症阈值",
        message="收缩压 185 mmHg,建议立即就医。",
    )
    title, content = safety_alert_push_text(a)
    assert "185" in title
    assert "就医" in content


def test_is_sensitive_alert_by_rule_id_prefix_only():
    """只有 rule_id 可用的上下文(ActionCard.source_id)按前缀判别。"""
    assert is_sensitive_alert(rule_id="ddi.warfarin_nsaid")
    assert is_sensitive_alert(rule_id="labs.uric_acid_high")
    assert not is_sensitive_alert(rule_id="vitals.bp_critical")
    assert not is_sensitive_alert(rule_id=None)
    assert not is_sensitive_alert()


# ─────────────────── 用药定时提醒(scan_medication_reminders) ───────────────────

def test_medication_reminder_no_drug_name_on_lock_screen(db):
    from app.models.medication import Medication
    from app.models.user import User
    from app.tasks.notifications import scan_medication_reminders

    user = User(username="med_priv", email="med_priv@example.com",
                hashed_password="x", name="med_priv", is_active=True, is_approved=True)
    db.add(user)
    db.commit()

    # 固定时钟,避免分钟边界 flake
    fixed_now = datetime(2026, 7, 11, 9, 0)
    cur_hhmm = "09:00"
    med = Medication(
        user_id=user.id, name="二甲双胍", dosage="500mg",
        is_active=True, reminder_times=[cur_hhmm],
    )
    db.add(med)
    db.commit()

    calls: list[dict] = []

    class _FakePushService:
        def __init__(self, _db):
            pass

        def send_notification(self, **kwargs):
            calls.append(kwargs)

            async def _ok():
                return {"success": True}

            return _ok()

    def _run_async_sync(coro):
        # 不依赖真实事件循环(其它测试可能污染 asyncio 状态,任务的 per-med
        # try/except 会把 loop 异常吞成 sent=0 假红);只关闭协程防 warning。
        coro.close()
        return {"success": True}

    @contextmanager
    def _session_ctx():
        yield db

    # 注意 patch 目标:直接改任务 run 函数自己的 __globals__,而不是
    # patch("app.tasks.notifications.X")。test_notification_tasks 的 fixture 曾
    # del sys.modules 造成模块重建,而 celery registry 缓存旧 task 对象——其
    # run.__globals__ 指向旧 module dict,按路径 patch 会打空(任务打到真 Postgres)。
    task_fn = scan_medication_reminders.run
    with patch.dict(task_fn.__globals__, {
        "SessionLocal": _session_ctx,
        "get_china_now": lambda: fixed_now,
        "run_async": _run_async_sync,
        "PushService": _FakePushService,
    }):
        result = task_fn()

    assert result["sent"] == 1
    kwargs = calls[0]
    # 锁屏可见文本:无药名、无剂量
    assert "二甲双胍" not in kwargs["title"]
    assert "二甲双胍" not in kwargs["content"]
    assert "500mg" not in kwargs["content"]
    # 名称/剂量在 data payload(App 解锁后渲染)
    assert kwargs["data"]["medication_name"] == "二甲双胍"
    assert kwargs["data"]["dosage"] == "500mg"
    # title 泛化后 dedup 必须有 per 药×日×时点的 rule_id,防同日第二种药被 title 去重吞
    assert str(med.id) in kwargs["data"]["rule_id"]
    assert cur_hhmm in kwargs["data"]["rule_id"]


# ─────────────────── 事件前提醒(_push_body) ───────────────────

def test_pre_event_med_and_supp_body_generic():
    from app.tasks.event_reminders import _push_body

    for kind, name in (("medication", DRUG), ("supplement", SUPP)):
        title, body = _push_body(kind, name, 15)
        assert name not in title and name not in body

    # 会议标题按既有隐私裁定可透传(本人通知,非 LLM 路径)
    _, meeting_body = _push_body("meeting", "季度评审", 10)
    assert "季度评审" in meeting_body


# ─────────────────── 依从提醒(nudge_text) ───────────────────

def test_adherence_nudge_no_card_title():
    from app.services.adherence_watch import AtRiskCard, nudge_text

    card = AtRiskCard(1, f"补充{SUPP} 12 周", "supplement", "overdue", 5, 110)
    t, m = nudge_text(card)
    assert SUPP not in t and SUPP not in m
    t2, m2 = nudge_text(AtRiskCard(1, f"服用{DRUG}", "med", "midway_risk", 20, 70))
    assert DRUG not in t2 and DRUG not in m2


# ─────────────────── 家庭日报(推送版折叠) ───────────────────

def test_family_push_lines_collapse_med_and_review_names():
    from app.services.family_daily_check import (
        _MED_TODO_PREFIX,
        _REVIEW_OVERDUE_PREFIX,
        _REVIEW_UPCOMING_PREFIX,
        _push_safe_lines,
        generate_member_message,
    )

    todos = [
        f"{_MED_TODO_PREFIX}{DRUG} 2.5mg",
        f"{_MED_TODO_PREFIX}二甲双胍 500mg",
        f"{_REVIEW_UPCOMING_PREFIX}(3天后): 胃镜复查",
        "今日饮水仅 600ml，记得多喝水",
    ]
    alerts = [f"{_REVIEW_OVERDUE_PREFIX} 5 天: 肝功能复查"]

    safe_todos = _push_safe_lines(todos)
    safe_alerts = _push_safe_lines(alerts)
    joined = "\n".join(safe_todos + safe_alerts)
    for leak in (DRUG, "二甲双胍", "胃镜", "肝功能"):
        assert leak not in joined
    # 计数行仍传达"有事要做"
    assert "2 项用药" in joined
    # 非敏感行透传
    assert "记得多喝水" in joined

    msg = generate_member_message(
        {"name": "爸爸", "alerts": alerts, "todos": todos}
    )
    assert msg is not None
    for leak in (DRUG, "二甲双胍", "胃镜", "肝功能"):
        assert leak not in msg


# ─────────────────── 家庭周报(推送只给计数级摘要) ───────────────────

@pytest.mark.asyncio
async def test_weekly_digest_push_no_indicator_names(db):
    from app.services import family_weekly_digest as fwd
    from app.services.notification.push_service import PushService

    fake_digest = {
        "digest_text": "📊 周报\n👤 爸爸\n  ⚠️ 体检异常: 糖化血红蛋白 7.2% (2026-07-01)",
        "total_concerns": 1,
        "members": [],
    }
    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(fwd, "generate_weekly_digest", return_value=fake_digest), \
            patch.object(PushService, "send_notification", new=fake_send):
        await fwd.send_weekly_digest(db, owner_user_id=1)

    kwargs = fake_send.call_args.kwargs
    assert "糖化血红蛋白" not in kwargs["content"]
    assert "1 项需关注" in kwargs["content"]


# ─────────────────── Critical 升级再推(escalate) ───────────────────

@pytest.fixture
def patch_wscla_session(db):
    @contextmanager
    def _ctx():
        yield db

    with patch("app.tasks.notifications_wscla.SessionLocal", new=_ctx):
        yield


def _mk_card(db, user_id, source_id, title, content):
    from app.models.action_card import ActionCard

    card = ActionCard(
        user_id=user_id, title=title, content=content,
        card_type="alert", source_type="safety_alert", source_id=source_id,
        severity="critical", status="active",
        push_sent_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    db.add(card)
    db.commit()
    return card


def test_escalation_genericizes_drug_sourced_card(db, patch_wscla_session):
    from app.models.user import User
    from app.services.notification.push_service import PushService
    from app.tasks.notifications_wscla import escalate_critical_unresolved_impl

    user = User(username="esc_priv", email="esc_priv@example.com",
                hashed_password="x", name="esc_priv", is_active=True, is_approved=True)
    db.add(user)
    db.commit()

    _mk_card(db, user.id, "ddi.warfarin_nsaid",
             f"{DRUG} × NSAID 出血风险", f"{DRUG} 与布洛芬同用……")
    _mk_card(db, user.id, "vitals.bp_critical",
             "血压达到急症阈值", "收缩压 185 mmHg")

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        escalate_critical_unresolved_impl()

    assert fake_send.call_count == 2
    by_title = {c.kwargs["title"]: c.kwargs for c in fake_send.call_args_list}
    sensitive = [k for k in by_title if DRUG not in k and "仍有一条" in k]
    passthrough = [k for k in by_title if "血压" in k]
    assert sensitive, f"敏感卡未泛化: {list(by_title)}"
    assert passthrough, f"vitals 卡被过度泛化: {list(by_title)}"
    assert DRUG not in by_title[sensitive[0]]["content"]
