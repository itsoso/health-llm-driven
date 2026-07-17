"""R4 · 主动触达统一 Gatekeeper 决策 + CRITICAL/safety 硬红线 + fail-open + ships-OFF。

对抗重点(路线图验收):CRITICAL/safety 类别**永远 bypass**,即便超预算 + enforce 模式。
observe 模式即使超预算也 suppress=False(投递逐字节不变)。计数只数当日 SENT 真投递。
"""
from datetime import timedelta

import pytest

from app.services.notification import gatekeeper as gk
from app.services.notification.gatekeeper import gate_proactive_notification
from app.utils.timezone import get_china_now


@pytest.fixture()
def _user(db):
    from app.models.user import User
    u = User(name="ntf_u", username="ntf_u", email="ntf@t.co", hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _seed_sent(db, user_id: int, notification_type: str, n: int, *, when=None):
    """写 n 条当日 SENT 的 NotificationLog(默认 sent_at=北京今天正午)。"""
    from app.models.notification import NotificationLog, NotificationStatus
    sent_at = when or get_china_now().replace(hour=12, minute=0, second=0, microsecond=0)
    for i in range(n):
        db.add(NotificationLog(
            user_id=user_id, notification_type=notification_type, channel="ios_apns",
            title=f"t{i}", status=NotificationStatus.SENT.value, sent_at=sent_at,
        ))
    db.commit()


@pytest.fixture(autouse=True)
def _reset_mode(monkeypatch):
    # 每测试后恢复默认,避免跨测试污染
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "off", raising=False)


# ── ships-OFF ────────────────────────────────────────────────────────

def test_off_mode_is_zero_behavior(db, _user):
    """默认 off:连 db 都不碰,恒 allow-不拦。"""
    gk.settings.notification_gatekeeper_mode = "off"
    o = gate_proactive_notification(None, _user.id, "daily_insights", "info")
    assert o.suppress is False and o.decision == "off"


def test_ships_off_by_default():
    from app.config import Settings
    assert Settings.model_fields["notification_gatekeeper_mode"].default == "off"


# ── 观测模式:算+记,绝不拦 ───────────────────────────────────────────

def test_observe_over_budget_would_drop_but_not_suppress(db, _user, monkeypatch):
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "observe", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 2)  # insight budget=2 → 第3条超
    o = gate_proactive_notification(db, _user.id, "daily_insights", "info")
    assert o.count_today == 2 and o.budget == 2
    assert o.decision == "would_drop" and o.reason == "over_budget"
    assert o.suppress is False  # 观测模式绝不实际拦(投递逐字节不变)


def test_observe_within_budget_allows(db, _user, monkeypatch):
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "observe", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 1)  # 1 < 2
    o = gate_proactive_notification(db, _user.id, "daily_insights", "info")
    assert o.decision == "allow" and o.suppress is False and o.count_today == 1


# ── 强制模式:超预算非 critical 才真拦 ────────────────────────────────

def test_enforce_over_budget_suppresses(db, _user, monkeypatch):
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 2)
    o = gate_proactive_notification(db, _user.id, "daily_insights", "info")
    assert o.decision == "drop" and o.reason == "over_budget" and o.suppress is True


def test_enforce_within_budget_allows(db, _user, monkeypatch):
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 1)
    o = gate_proactive_notification(db, _user.id, "daily_insights", "info")
    assert o.decision == "allow" and o.suppress is False


# ── 硬红线:CRITICAL / safety 永远 bypass(即便 enforce + 超预算)────────

def test_critical_severity_never_suppressed_even_over_budget(db, _user, monkeypatch):
    """对抗:enforce 模式 + 远超预算 + severity=critical → 恒不拦。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 99)  # 疯狂超预算
    o = gate_proactive_notification(db, _user.id, "daily_insights", "critical")
    assert o.suppress is False and o.reason == "critical_bypass"


def test_safety_category_never_suppressed_even_over_budget(db, _user, monkeypatch):
    """对抗:health_alert(safety 类别)即便 info 级 + enforce → 永不限额。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "health_alert", 99)
    o = gate_proactive_notification(db, _user.id, "health_alert", "info")
    assert o.suppress is False and o.reason == "critical_bypass"


def test_reminder_unbudgeted_never_suppressed(db, _user, monkeypatch):
    """用户排程类(reminder,budget=None)不限额:enforce 也不拦。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "reminder", 50)
    o = gate_proactive_notification(db, _user.id, "reminder", "info")
    assert o.suppress is False and o.reason == "unbudgeted"


def test_unmapped_type_is_failsafe_unbudgeted(db, _user, monkeypatch):
    """fail-safe 白名单:未映射的 notification_type 落 'other',恒不限额(可能是新安全类型)。
    enforce 模式 + 大量已发也不拦 —— 防将来新增安全类型没进 map 时被静默丢弃(under-alarm)。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    o = gate_proactive_notification(db, _user.id, "some_future_safety_type", "info")
    assert o.category == "other" and o.suppress is False and o.reason == "unbudgeted"


# ── fail-open + 计数正确性 ──────────────────────────────────────────

def test_fail_open_on_count_error(_user, monkeypatch):
    """enforce + 非critical + 计数抛异常(db=None) → fail-open 放行(绝不吞通知)。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    o = gate_proactive_notification(None, _user.id, "daily_insights", "info")
    assert o.suppress is False and o.reason == "error"


def test_count_ignores_non_sent_and_other_days(db, _user, monkeypatch):
    """计数只数当日 SENT:昨天的 / pending 的都不算进预算。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    from app.models.notification import NotificationLog, NotificationStatus
    # 昨天已发 2 条(不该算今天)
    _seed_sent(db, _user.id, "daily_insights", 2,
               when=get_china_now().replace(hour=12) - timedelta(days=1))
    # 今天 1 条 pending(未投递,不算)
    db.add(NotificationLog(user_id=_user.id, notification_type="daily_insights",
                           channel="ios_apns", title="p",
                           status=NotificationStatus.PENDING.value,
                           sent_at=get_china_now()))
    db.commit()
    o = gate_proactive_notification(db, _user.id, "daily_insights", "info")
    assert o.count_today == 0 and o.decision == "allow" and o.suppress is False


def test_count_separates_categories(db, _user, monkeypatch):
    """预算按类别独立:insight 满不影响 summary。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 2)  # insight 满
    o = gate_proactive_notification(db, _user.id, "morning_briefing", "info")  # summary 类别,0 条
    assert o.category == "summary" and o.count_today == 0 and o.suppress is False


# ── 安全评审整改回归(F1/F2/F3)──────────────────────────────────────

def test_f1_severity_whitespace_still_critical(db, _user, monkeypatch):
    """F1:severity 带空白('critical ')也须判 critical → bypass(与 _category_of 的 strip 对齐)。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    _seed_sent(db, _user.id, "daily_insights", 99)
    for sev in ("critical ", " CRITICAL", "Critical\t"):
        o = gate_proactive_notification(db, _user.id, "daily_insights", sev)
        assert o.suppress is False and o.reason == "critical_bypass", sev


def test_f1_mode_normalization_defends_enforce(db, _user, monkeypatch):
    """F1:非法/大小写 mode 归一化 —— 'OFF'/'ENFORCE '/'on' 绝不误入真 enforce 抑制。"""
    _seed_sent(db, _user.id, "daily_insights", 99)
    # 'OFF' 大写 → off(零行为)
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "OFF", raising=False)
    assert gate_proactive_notification(db, _user.id, "daily_insights", "info").decision == "off"
    # 'on'(非法值)→ off,不抑制
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "on", raising=False)
    assert gate_proactive_notification(db, _user.id, "daily_insights", "info").suppress is False
    # 'ENFORCE '(带空白)→ 归一化为 enforce → 超预算真抑制
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "ENFORCE ", raising=False)
    assert gate_proactive_notification(db, _user.id, "daily_insights", "info").suppress is True


def test_f3_nonstr_type_never_raises(db, _user, monkeypatch):
    """F3:非 str 脏 notification_type 绝不让网关抛异常打断投递。off→零行为;enforce→fail-open。"""
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "off", raising=False)
    assert gate_proactive_notification(db, _user.id, 12345, "info").decision == "off"  # 不抛
    monkeypatch.setattr(gk.settings, "notification_gatekeeper_mode", "enforce", raising=False)
    o = gate_proactive_notification(db, _user.id, 12345, "info")  # _category_of 会抛 → fail-open
    assert o.suppress is False and o.reason == "error"


def test_f2_safety_types_are_in_safety_category():
    """F2 漂移守卫(fail-closed):所有已知急性/安全相关 notification_type 必须落 safety 类别,
    且预算类别(insight/summary/advice)里绝不能混入急性类型。将来加安全类型忘归类 → 本测试红。"""
    # 已知必须永不限额的安全/急性类型
    SAFETY_TYPES = {"health_alert", "garmin_sync_failed"}
    for t in SAFETY_TYPES:
        assert gk._category_of(t) == "safety", f"{t} 掉出 safety 类别 = under-alarm 风险"
    # 预算类别绝不含急性关键词类型(防误分类进可抑制类别)
    budgeted = {c for c, b in gk._DAILY_BUDGET.items() if b is not None}
    for t, cat in gk._CATEGORY_BY_TYPE.items():
        if cat in budgeted:
            assert not any(k in t for k in ("alert", "critical", "anomaly", "emergency", "sync_failed")), \
                f"疑似急性类型 {t} 落进可抑制类别 {cat}"
