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
    lock_screen_privacy_backstop,
)


def test_central_lock_screen_backstop_redacts_medication_payload() -> None:
    title, content, redacted = lock_screen_privacy_backstop(
        notification_type="reminder",
        title="替普瑞酮 50mg",
        content="晚餐后服用替普瑞酮胶囊",
        data={"category": "MEDICATION_REMINDER", "medication_name": "替普瑞酮"},
    )

    assert redacted is True
    assert title == "用药提醒"
    assert "替普瑞酮" not in content


def test_central_lock_screen_backstop_redacts_lab_and_diagnosis_payloads() -> None:
    lab_title, lab_content, lab_redacted = lock_screen_privacy_backstop(
        notification_type="health_alert",
        title="中性粒细胞偏低",
        content="请复查血常规",
        data={"rule_id": "labs.neutrophil_low", "lab_name": "中性粒细胞"},
    )
    diagnosis_title, diagnosis_content, diagnosis_redacted = lock_screen_privacy_backstop(
        notification_type="reminder",
        title="胃溃疡复诊",
        content="明天去消化内科",
        data={"diagnosis": "胃溃疡"},
    )

    assert (lab_title, lab_content, lab_redacted) == (
        "化验指标提醒",
        "有一项化验指标需要你关注，打开 App 查看详情。",
        True,
    )
    assert (diagnosis_title, diagnosis_content, diagnosis_redacted) == (
        "健康事项提醒",
        "有一项健康事项需要你关注，打开 App 查看详情。",
        True,
    )


def test_central_lock_screen_backstop_preserves_acute_vital_alert() -> None:
    title, content, redacted = lock_screen_privacy_backstop(
        notification_type="health_alert",
        title="血氧偏低：91%",
        content="若持续偏低或伴呼吸困难，请及时就医。",
        data={"rule_id": "vitals.spo2_low", "metric_key": "spo2_avg"},
    )

    assert redacted is False
    assert title == "血氧偏低：91%"
    assert content == "若持续偏低或伴呼吸困难，请及时就医。"

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
    assert "点「服用」自动打卡" in kwargs["content"]
    # 名称/剂量在 data payload(App 解锁后渲染)
    assert kwargs["data"]["medication_name"] == "二甲双胍"
    assert kwargs["data"]["dosage"] == "500mg"
    assert kwargs["data"]["category"] == "MEDICATION_REMINDER"
    assert kwargs["data"]["reminder_type"] == "medication"
    assert kwargs["data"]["scheduled_date"] == fixed_now.date().isoformat()
    assert kwargs["data"]["scheduled_time"] == cur_hhmm
    assert kwargs["data"]["scheduled_timezone"] == "Asia/Shanghai"
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


# ═══════════════ LLM 文案出口的确定性 backstop(llm_push_backstop) ═══════════════

from app.services.notification.push_privacy import (  # noqa: E402
    GENERIC_LLM_PUSH_TITLE,
    contains_sensitive_name,
    llm_push_backstop,
)


@pytest.mark.parametrize("leaky", [
    "记得服用二甲双胍 500mg",          # 中文药名(DRUG_CLASS_ALIASES)
    "华法林与今天的化验结果有关",        # 中文药名
    "Sertraline 已连续记录 14 天",      # 英文药名,大小写不敏感
    "补充辅酶Q10 有助恢复",             # 补剂名(无空格变体已在 lexicon)
    "今天别忘了维生素D",               # CJK+ASCII 混排空格折叠变体(lexicon 写「维生素 d」)
    "圣约翰草可能影响情绪药物",          # 草药补剂(非食物类,保留在扫描集)
    "早餐后吃氨氯地平,血压更平稳",       # COMMON_DRUG_ALIASES(无专属 safety 规则的常见药)
    "记得吃抗抑郁药,别自行停",           # 诊断可反推的治疗类别词(无具体药名,Tier-5 域)
    "化疗期间注意白细胞",               # 同上(肿瘤域)
    "Ozempic 注射日到了",              # 高知名度品牌名(对抗复审补进 lexicon)
    "Keep taking your statins daily",   # 英文复数(ASCII 尾词可选 s,评审残余补修)
])
def test_llm_backstop_drug_name_genericized(leaky):
    title, content, redacted = llm_push_backstop(
        "健康提醒", leaky, generic_title=GENERIC_LLM_PUSH_TITLE
    )
    assert redacted
    assert content == "有一条为你准备的健康建议,点开查看。"
    for token in ("二甲双胍", "华法林", "ertraline", "辅酶", "维生素", "圣约翰", "氨氯地平"):
        assert token not in title and token not in content


def test_llm_backstop_drug_in_title_only_replaces_both():
    """药名可能只在 title:任一命中,title/content 一起泛化。"""
    title, content, redacted = llm_push_backstop(
        f"{DRUG}用药提示", "详情点开查看", generic_title=GENERIC_LLM_PUSH_TITLE
    )
    assert redacted
    assert DRUG not in title
    assert title == GENERIC_LLM_PUSH_TITLE


def test_llm_backstop_keeps_deterministic_title_when_generic_title_none():
    """generic_title=None 表示 title 是确定性常量(🌅 早安),命中只换 content。"""
    title, content, redacted = llm_push_backstop(
        "🌅 早安", "记得吃二甲双胍", generic_content="今天的健康早报准备好了,点开收听。"
    )
    assert redacted
    assert title == "🌅 早安"
    assert content == "今天的健康早报准备好了,点开收听。"


@pytest.mark.parametrize("benign", [
    "今天步数 12000,睡眠 7.5 小时,状态不错,继续保持",
    "地铁通勤 30 分钟,顺路买了大蒜和西柚",       # 铁⊂地铁(去歧义名单)+ 食物类补剂豁免
    "记得按时服药,并在睡前完成拉伸",             # 类别级提及(动词不入名称集)
    "复查编号 AB123 已登记,April 的体检安排出来了",  # ASCII 锚点:b12⊄AB123;pril 在去歧义名单
    "环境湿度偏高,鼻炎症状可能加重,出门戴口罩",     # 症状措辞非药名
    "HRV 52ms 恢复良好,今天适合中等强度训练",
    "睡前一杯助眠茶,少刷手机",                   # 助眠茶⊅助眠药(类别词不误伤生活文案)
    "周末去温泉放松疗养一下",                    # 放松疗养⊅放疗
    "今天精神状态不错,继续保持",                  # 精神状态⊅精神科
])
def test_llm_backstop_benign_text_passes_through_unchanged(benign):
    """防 over-redaction:不点名药/补剂的文案必须逐字节透传。"""
    title, content, redacted = llm_push_backstop(
        "健康提醒", benign, generic_title=GENERIC_LLM_PUSH_TITLE
    )
    assert not redacted
    assert title == "健康提醒"
    assert content == benign


def test_llm_backstop_scan_failure_fails_closed_and_never_drops():
    """TIGHTEN-only:扫描器炸了 → 泛化文案照发,绝不 raise / 丢推送。"""
    import app.services.notification.push_privacy as pp

    with patch.object(pp, "contains_sensitive_name", side_effect=RuntimeError("boom")):
        title, content, redacted = pp.llm_push_backstop(
            "标题", "任意内容", generic_title=GENERIC_LLM_PUSH_TITLE
        )
    assert redacted
    assert title == GENERIC_LLM_PUSH_TITLE
    assert content == pp.GENERIC_LLM_PUSH_CONTENT


def test_contains_sensitive_name_empty_and_none():
    assert not contains_sensitive_name(None)
    assert not contains_sensitive_name("")


# ─────────────────── 出口 1:agent_loop 主动通知 ───────────────────

def _agent_loop_llm(json_text: str):
    class _FakeProvider:
        async def chat(self, **kwargs):
            return json_text

    return _FakeProvider()


async def _run_agent_loop_notify(db, message: str, title: str = "健康提醒"):
    import json as _json

    from app.services import agent_loop
    from app.services.notification.push_service import PushService

    llm_json = _json.dumps(
        {"action": "notify", "title": title, "message": message, "severity": "info"},
        ensure_ascii=False,
    )
    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(agent_loop, "_build_context", return_value="ctx"), \
            patch.object(agent_loop, "_check_push_limit", return_value=True), \
            patch.object(agent_loop, "_increment_push_count"), \
            patch("app.services.llm.factory.create_llm_provider",
                  return_value=_agent_loop_llm(llm_json)), \
            patch("app.services.notification.evidence_policy."
                  "build_notification_evidence_data_for_user",
                  side_effect=lambda _db, **kw: kw.get("existing_data") or {}), \
            patch.object(PushService, "send_notification", new=fake_send):
        result = await agent_loop.post_sync_reasoning(
            db, user_id=1, twin=None, anomaly_alerts=[], safety_report=None
        )
    assert result["action"] == "notify"
    assert fake_send.call_count == 1
    return fake_send.call_args.kwargs


@pytest.mark.asyncio
async def test_agent_loop_notify_with_drug_name_redacted(db):
    kwargs = await _run_agent_loop_notify(
        db, "记得服用二甲双胍 500mg,晚饭后一次", title="二甲双胍提醒"
    )
    assert "二甲双胍" not in kwargs["title"]
    assert "二甲双胍" not in kwargs["content"]
    # 原文只进 data payload(App 解锁后应用内渲染)
    assert kwargs["data"]["full_title"] == "二甲双胍提醒"
    assert "二甲双胍" in kwargs["data"]["full_content"]


@pytest.mark.asyncio
async def test_agent_loop_notify_benign_message_passes_through(db):
    msg = "今天走了 12000 步,比过去一周平均多 20%,继续保持"
    kwargs = await _run_agent_loop_notify(db, msg, title="步数进展")
    assert kwargs["title"] == "步数进展"
    assert kwargs["content"] == msg
    assert "full_content" not in kwargs["data"]


# ─────────────────── 出口 2/3/4:早安 / 周聊 / 今日健康复盘 ───────────────────

def _sync_run_async(coro):
    """无事件循环地驱动"不 await 真 IO"的协程(fake analyze / fake send)。"""
    if not hasattr(coro, "send"):
        return coro
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("fake coroutine awaited real IO")


class _RecordingPushService:
    calls: list = []

    def __init__(self, _db):
        pass

    def send_notification(self, **kwargs):
        _RecordingPushService.calls.append(kwargs)

        async def _ok():
            return {"success": True}

        return _ok()


def _mk_garmin_user(db, username: str):
    from app.models.user import GarminCredential, User

    user = User(username=username, email=f"{username}@example.com",
                hashed_password="x", name=username, is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    cred = GarminCredential(user_id=user.id, garmin_email=f"{username}@g.com",
                            encrypted_password="x", sync_enabled=True,
                            credentials_valid=True)
    db.add(cred)
    db.commit()
    return user


@pytest.mark.parametrize("script,expect_generic", [
    ("睡眠 7 小时 20 分,HRV 52ms,状态不错,今天适合轻松跑,加油", False),
    ("血压平稳。记得早餐后服用氨氯地平,并观察是否头晕。", True),
])
def test_morning_summary_backstop(db, script, expect_generic):
    from app.tasks.notifications import send_morning_health_summary

    user = _mk_garmin_user(db, f"morning_{'g' if expect_generic else 'p'}")
    _RecordingPushService.calls = []

    @contextmanager
    def _ctx():
        yield db

    task_fn = send_morning_health_summary.run
    with patch.dict(task_fn.__globals__, {
        "SessionLocal": _ctx,
        "run_async": _sync_run_async,
        "PushService": _RecordingPushService,
    }), patch("app.services.briefing_voice_script.build_voice_script",
              return_value=script):
        result = task_fn()

    assert result["sent_count"] == 1, f"推送被丢弃(违反 TIGHTEN-only): user={user.id}"
    kwargs = _RecordingPushService.calls[0]
    assert kwargs["title"] == "🌅 早安"  # 确定性 title 不动
    if expect_generic:
        assert kwargs["content"] == "今天的健康早报准备好了,点开收听。"
        assert "氨氯地平" not in kwargs["content"]
    else:
        assert kwargs["content"] == script[:200]


def test_weekly_invite_backstop_redacts_drug_script(db):
    from app.tasks.notifications import send_weekly_review_invite

    _mk_garmin_user(db, "weekly_g")
    _RecordingPushService.calls = []

    @contextmanager
    def _ctx():
        yield db

    task_fn = send_weekly_review_invite.run
    with patch.dict(task_fn.__globals__, {
        "SessionLocal": _ctx,
        "run_async": _sync_run_async,
        "PushService": _RecordingPushService,
    }), patch("app.services.weekly_review_voice_script.build_weekly_review_voice_script",
              return_value=f"这周跑了 3 次。另外你开始记录{DRUG}了,下周继续。"):
        result = task_fn()

    assert result["sent_count"] == 1
    kwargs = _RecordingPushService.calls[0]
    assert DRUG not in kwargs["content"]
    assert kwargs["content"] == "本周的健康回顾准备好了,点开聊聊。"


# ─────────────────── 出口 5:每日计划提醒(LLM 生成的计划项 title) ───────────────────

@pytest.mark.parametrize("item_title,expect_generic", [
    ("快走 30 分钟", False),
    ("早餐后服用维生素D 2000IU", True),  # smart_plan LLM 可能生成点名补剂的条目
])
def test_plan_morning_reminder_backstop(db, item_title, expect_generic):
    from datetime import date as _date, timedelta as _timedelta

    from app.models.smart_plan import PlanItem, WeeklyPlan
    from app.models.user import User
    from app.tasks import notifications as notif

    user = User(username=f"plan_{'g' if expect_generic else 'p'}",
                email=f"plan_{'g' if expect_generic else 'p'}@example.com",
                hashed_password="x", name="plan", is_active=True, is_approved=True)
    db.add(user)
    db.commit()

    today = _date.today()
    week_start = today - _timedelta(days=today.weekday())
    plan = WeeklyPlan(user_id=user.id, week_start=week_start, status="active")
    plan.items.append(PlanItem(day_of_week=today.weekday() + 1, category="health",
                               title=item_title, is_completed=False))
    db.add(plan)
    db.commit()

    @contextmanager
    def _ctx():
        yield db

    _RecordingPushService.calls = []
    task_fn = notif.send_plan_morning_reminder.run
    with patch.dict(task_fn.__globals__, {
        "SessionLocal": _ctx,
        "run_async": _sync_run_async,
        "PushService": _RecordingPushService,
        "_today_weather_text": lambda _city: "",
        "_get_user_city": lambda _db, _uid: None,
    }):
        result = task_fn()

    assert result["sent_count"] == 1, "推送被丢弃(违反 TIGHTEN-only)"
    kwargs = _RecordingPushService.calls[0]
    if expect_generic:
        assert "维生素" not in kwargs["content"]
        assert "1 项计划待完成" in kwargs["content"]  # 计数级信息保留
    else:
        assert item_title in kwargs["content"]


@pytest.mark.parametrize("item_title,expect_generic", [
    ("午餐多吃蔬菜", False),
    ("补充辅酶Q10 一粒", True),
])
def test_plan_item_reminders_backstop(db, item_title, expect_generic):
    """分时提醒(第三个消费 LLM 计划项 title 的任务)同样必须过 backstop。"""
    from datetime import date as _date, datetime as _datetime, timedelta as _timedelta

    from app.models.smart_plan import PlanItem, WeeklyPlan
    from app.models.user import User
    from app.tasks import notifications as notif

    user = User(username=f"pitem_{'g' if expect_generic else 'p'}",
                email=f"pitem_{'g' if expect_generic else 'p'}@example.com",
                hashed_password="x", name="pitem", is_active=True, is_approved=True)
    db.add(user)
    db.commit()

    today = _date.today()
    week_start = today - _timedelta(days=today.weekday())
    plan = WeeklyPlan(user_id=user.id, week_start=week_start, status="active")
    # diet 类别在 09:00 无档期,用 health(09:00)
    plan.items.append(PlanItem(day_of_week=today.weekday() + 1, category="health",
                               title=item_title, is_completed=False))
    db.add(plan)
    db.commit()

    @contextmanager
    def _ctx():
        yield db

    fixed_now = _datetime(today.year, today.month, today.day, 9, 0)
    _RecordingPushService.calls = []
    task_fn = notif.send_plan_item_reminders.run
    with patch.dict(task_fn.__globals__, {
        "SessionLocal": _ctx,
        "run_async": _sync_run_async,
        "PushService": _RecordingPushService,
        "get_china_now": lambda: fixed_now,
        "_today_weather_text": lambda _city: "",
        "_get_user_city": lambda _db, _uid: None,
    }):
        result = task_fn()

    assert result["sent_count"] == 1, "推送被丢弃(违反 TIGHTEN-only)"
    kwargs = _RecordingPushService.calls[0]
    if expect_generic:
        assert "辅酶" not in kwargs["content"]
        assert "1 项计划待完成" in kwargs["content"]
    else:
        assert item_title in kwargs["content"]


@pytest.mark.parametrize("aggregation,expect_generic", [
    ("今天步数达标,睡眠稍短,明天早点休息", False),
    ("血糖偏高,建议继续服用二甲双胍并控制主食", True),
])
def test_daily_insight_backstop(db, aggregation, expect_generic):
    from datetime import date as _date

    from app.models.daily_health import GarminData
    from app.tasks import notifications as notif

    user = _mk_garmin_user(db, f"insight_{'g' if expect_generic else 'p'}")
    today = _date(2026, 7, 12)
    db.add(GarminData(user_id=user.id, record_date=today, steps=12000))
    db.commit()

    class _FakeAnalyzeClient:
        def __init__(self):
            pass

        async def analyze(self, _prompt):
            return {"aggregation": aggregation}

    @contextmanager
    def _ctx():
        yield db

    _RecordingPushService.calls = []
    with patch.object(notif, "SessionLocal", new=_ctx), \
            patch.object(notif, "run_async", new=_sync_run_async), \
            patch.object(notif, "PushService", new=_RecordingPushService), \
            patch("app.services.multi_model_analyze.MultiModelAnalyzeClient",
                  new=_FakeAnalyzeClient):
        notif._generate_daily_insight_for_user(user.id, today)

    assert len(_RecordingPushService.calls) == 1, "推送被丢弃(违反 TIGHTEN-only)"
    kwargs = _RecordingPushService.calls[0]
    assert kwargs["title"] == "📊 今日健康复盘"
    if expect_generic:
        assert "二甲双胍" not in kwargs["content"]
        assert kwargs["content"] == "今日健康复盘已生成,点开查看。"
        assert "二甲双胍" in kwargs["data"]["full_content"]
    else:
        assert kwargs["content"] == aggregation
        assert "full_content" not in kwargs["data"]
