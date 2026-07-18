"""
Conversation opener — AI 主动续接上次话题, 替代 chat tab 的"白板状态".

WHY (P1 改进点, 2026-05-04 产品规划):
打开 chat 时, 用户当前体验是空白 input + 4 个泛泛建议 chip. 实际生产数据
显示用户每天发 22 条对话 (151/7d) — 对话是绝对主入口, 但 22 个 query 都是
独立的, 没有"上次说到 X, 今天 Y" 的延续感.

opener 把 ActionCard 检验日 / anomaly_alert / case_thread / memory_fact 四类
已有信号转成"续接式"开场白 + 1-3 个 quick reply chip.

设计选择 — 不调 LLM:
- 模板式拼接, ≤ 100ms 返回 (纯 SQL + 字符串)
- 措辞会有点机械但 ship 后 7d 看用户感受再决定加 LLM 润色
- 模板优于"机械感"的代价: 第一版用户能立刻看到, 而不是等 2-5s LLM 转圈

签名: compute_conversation_opener(db, user_id) → Optional[OpenerSuggestion]

返回 None 表示当前没信号 — 前端退化到现有 SUGGESTIONS chip.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.services.memory_snippet import sanitize_memory_snippet

logger = logging.getLogger(__name__)

CHINA_TZ = ZoneInfo("Asia/Shanghai")

# ── card title 人性化 ──
# 尾部软化/礼貌语 (opener 模板已自带追问, 这些是噪声)
_TITLE_TRAILING_SUFFIXES = ("，请注意", ",请注意", "，请留意", "请注意", "请留意")
# 括号内阈值说明 (全角/半角) — "（阈值 95%）" / "(阈值 95%)"
_TITLE_THRESHOLD_PAREN = re.compile(r"[（(]\s*阈值[^）)]*[）)]")
# 开头的 [内部指标键] 前缀: 只吃 ASCII 字母/数字/下划线的 key (如 [spo2_avg]/[hrv]);
# 不误伤中文方括号内容 (如 「血压」类人话不会命中, 且我们只剥行首这一个)。
_TITLE_METRIC_KEY_PREFIX = re.compile(r"^\s*[\[［]\s*[A-Za-z][A-Za-z0-9_]*\s*[\]］]\s*")
# 截断时优先切在这些子句边界之后
_TITLE_CLAUSE_BOUNDARY = "，,。；;、"
_TITLE_MAX_LEN = 24
_NON_ACTION_TITLE_EXACT = {
    "已为您记录",
    "已记录",
    "记录成功",
    "已保存",
    "保存成功",
    "已写入",
    "写入成功",
    "已确认",
    "确认成功",
}
_NON_ACTION_TITLE_PATTERNS = (
    re.compile(r"^已为(你|您)?记录$"),
    re.compile(r"^(已|已经)?(帮你|帮您)?(记录|保存|写入|确认)(成功|好了|完成)?$"),
    re.compile(r"^(早餐|午餐|晚餐|加餐|夜宵|饮食|用药|补剂|运动|体重|血压|血糖)已记录$"),
    re.compile(r"^已记录(早餐|午餐|晚餐|加餐|夜宵|饮食|用药|补剂|运动|体重|血压|血糖)?(\d+项)?$"),
)


def humanize_card_title(title: str) -> str:
    """把带告警措辞的原始标题整形成能内联进 opener 模板的短语。

    e.g. "血氧饱和度偏低：94.0%（阈值 95%），请注意" → "血氧饱和度偏低：94.0%"

    - 剥尾部"，请注意"/"请注意"礼貌语
    - 剥括号内阈值说明 (（阈值…）/(阈值…))
    - 去尾部悬挂标点
    - 超 ~24 字在子句边界截断 + 省略号
    纯字符串, 不改 source/quick_replies/priority 契约。
    """
    if not title:
        return ""
    s = title.strip()
    # 存量兜底: 剥掉标题开头的 [内部指标键] 前缀 (如 "[spo2_avg] 血氧…" → "血氧…")。
    # 新卡已不再拼这个前缀 (anomaly_detection_service), 但 DB 里旧卡仍带 —— 绝不漏进用户文本。
    s = _TITLE_METRIC_KEY_PREFIX.sub("", s).strip()
    # 阈值括号 (可能在中间)
    s = _TITLE_THRESHOLD_PAREN.sub("", s)
    # 尾部礼貌语 (反复剥, 处理 "…（阈值…），请注意" 剥括号后新暴露的尾巴)
    changed = True
    while changed:
        changed = False
        s = s.strip()
        for suf in _TITLE_TRAILING_SUFFIXES:
            if s.endswith(suf):
                s = s[: -len(suf)]
                changed = True
    # 去尾部悬挂标点/空白
    s = s.rstrip("，,。；;、：: ").strip()
    if len(s) <= _TITLE_MAX_LEN:
        return s
    # 超长 → 在子句边界截 (窗口内最后一个边界符之后)
    window = s[:_TITLE_MAX_LEN]
    last_boundary = max((window.rfind(b) for b in _TITLE_CLAUSE_BOUNDARY), default=-1)
    if last_boundary >= 6:
        return window[:last_boundary].rstrip("，,。；;、：: ") + "…"
    return window.rstrip("，,。；;、：: ") + "…"


def _is_non_action_title(title: str) -> bool:
    """Return True for system receipt/status labels that are not user actions."""
    s = (title or "").strip()
    if not s:
        return True
    # Status labels often arrive decorated ("已记录✅", "午餐已记录"). Keep only
    # letters and digits for classification so presentation glyphs never turn a
    # write receipt into an action to follow up.
    compact = "".join(ch for ch in s if ch.isalnum())
    if compact in _NON_ACTION_TITLE_EXACT:
        return True
    return any(pattern.match(compact) for pattern in _NON_ACTION_TITLE_PATTERNS)


# Cold-start quick-reply actions. Items carrying one of these are handled by
# LOCAL client navigation (photo picker / weight sheet / device link) instead of
# being sent as chat text — see the C1 cold-start contract. Kept as a closed set
# so the mobile client can exhaustively switch on it.
COLD_START_ACTIONS = ("photo_meal", "record_weight", "connect_device")


@dataclass
class OpenerQuickReply:
    """A quick-reply chip that navigates locally instead of sending text.

    Serializes to {"label": ..., "action": ...}. `action` is one of
    COLD_START_ACTIONS. Plain-string quick replies (the existing behavior) stay
    strings; only cold-start action chips use this structured shape.
    """
    label: str                                      # 用户视角人话 ("拍一张今天的饭")
    action: str                                     # COLD_START_ACTIONS 之一


# A quick reply is either a plain string (send-as-text, existing behavior) or an
# OpenerQuickReply (local-navigation, cold-start). asdict() serializes both.
QuickReply = Union[str, OpenerQuickReply]


@dataclass
class OpenerSuggestion:
    """一条 chat opener 建议. 序列化给前端 (asdict)."""
    text: str                                       # AI 主动开场白 (≤ 80 字)
    source: str                                     # 'action_card_due' / 'anomaly' / 'case_thread' / 'memory_fact' / 'cold_start'
    source_id: Optional[int] = None                 # 对应记录 id, 前端 deep link
    quick_replies: List[QuickReply] = field(default_factory=list)  # 1-3 个一键回复 chip
    deep_link: Optional[str] = None                 # 点开场白卡片本身跳哪
    priority: int = 0                               # 越大越先展示 (内部排序用)


# ─────────────── cold-start: synthesized onboarding opener ───────────────

# 小巴 (边牧人格) 自我介绍 + 一个具体的第一步邀请。确定性模板 (无 LLM), 供
# 零数据新用户走既有 opener 通道拿到非空开场白。严禁量化/命令式健康处方 —
# 全是"记录一件小事"的邀请, 守 guidance_validator 红线 (无剂量/无祈使饮食/无训练指令)。
_COLD_START_OPENER_TEXT = (
    "嗨，我是小巴，你的健康参谋 🐾。这里还看不到你的健康数据，"
    "我们从记录一件小事开始吧——拍张今天的饭、记一下体重，或连上你的手表，"
    "有了第一笔，我就能陪你一起往下看。"
)


def synthesize_cold_start_opener() -> OpenerSuggestion:
    """Deterministic onboarding opener for a zero-data (cold-start) user.

    No DB reads, no LLM — a stable synthetic greeting so a brand-new user sees a
    warm first-step invitation instead of a blank chat. The three quick replies
    carry an `action` (COLD_START_ACTIONS) so the client handles them via LOCAL
    navigation (open photo picker / weight sheet / device link) rather than
    sending text. Persona: 小巴, a faithful, gentle border collie (🐾); the copy
    stays invitational — no quantified or imperative health prescription.
    """
    return OpenerSuggestion(
        text=_COLD_START_OPENER_TEXT,
        source="cold_start",
        source_id=None,
        quick_replies=[
            OpenerQuickReply(label="拍一张今天的饭", action="photo_meal"),
            OpenerQuickReply(label="记一下体重", action="record_weight"),
            OpenerQuickReply(label="连接手表数据", action="connect_device"),
        ],
        deep_link=None,
        priority=100,
    )


def compute_conversation_opener(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    按优先级试 4 类信号, 返回最高优先级的 opener. 都没命中返回 None.

    优先级:
        1. ActionCard 检验日 ≤ 2 天 (priority=100)
        2. 24h 内 anomaly_alert 未确认 (priority=80)
        3. 登记慢病/结节的随访到期/逾期 (priority=70)
        4. 7 天内 case_thread 有更新 (priority=60)
        5. 7 天内新写入 memory_fact (优先级最低, priority=40)
    """
    # 旁路: 任何错误返回 None, 前端退化到 SUGGESTIONS
    try:
        opener = (
            _try_action_card_due(db, user_id)
            or _try_recent_anomaly(db, user_id)
            or _try_problem_followup_due(db, user_id)
            or _try_active_case_thread(db, user_id)
            or _try_recent_memory_fact(db, user_id)
        )
        return opener
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[conversation_opener] compute failed (bypass): {e}")
        return None


# ─────────────── strategy 1: ActionCard due ───────────────


def _try_action_card_due(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    Active ActionCard 检验日距今 ≤ 2 天 (但还没 graded). 这是 trust loop 用户最该
    回答的问题: "你做了吗 / 效果如何?"
    """
    from app.models.action_card import ActionCard

    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=2)

    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.status == "active",
            ActionCard.check_back_date.isnot(None),
            ActionCard.check_back_date <= soon,
            ActionCard.graded_at.is_(None),
            ActionCard.adherence_confidence.is_(None),
            ActionCard.user_decision.is_(None),
        )
        .order_by(ActionCard.check_back_date.asc())
        .limit(10)
        .all()
    )
    if not cards:
        return None
    for card in cards:
        # 卡标题可能是告警文案 ("…（阈值 95%），请注意"), 内联前人性化。
        # 系统回执 ("已为您记录") 不是行动目标, 不能套"检验日"模板。
        title = humanize_card_title((card.title or "").strip()[:40])
        if _is_non_action_title(title):
            continue

        # 距 check_back 还有几天 (中国时间)
        chk = card.check_back_date
        if chk.tzinfo is None:
            chk = chk.replace(tzinfo=timezone.utc)
        days_until = max(0, (chk.astimezone(CHINA_TZ).date() - datetime.now(CHINA_TZ).date()).days)

        if days_until == 0:
            text = f"「{title}」今天到复盘时间了。当前更接近哪种情况？"
            quick_replies = ["已完成", "还没完成", "需要调整"]
        elif days_until == 1:
            text = f"明天复盘「{title}」。现在进展顺利吗？"
            quick_replies = ["按计划进行", "遇到阻碍", "调整计划"]
        else:  # 2
            text = f"距「{title}」复盘还有 {days_until} 天。要按原计划继续，还是现在调整？"
            quick_replies = ["按计划进行", "遇到阻碍", "调整计划"]

        return OpenerSuggestion(
            text=text,
            source="action_card_due",
            source_id=card.id,
            quick_replies=quick_replies,
            deep_link=f"/action-cards/{card.id}",
            priority=100,
        )
    return None


# ─────────────── strategy 2: recent anomaly ───────────────


def _try_recent_anomaly(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    24h 内 critical / warning anomaly_alert, 未 acknowledged 也未 suppressed.
    info 级跳过 (噪声).
    """
    from app.models.anomaly_alert import AnomalyAlert

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).date()

    alert = (
        db.query(AnomalyAlert)
        .filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.detection_date >= cutoff,
            AnomalyAlert.severity.in_(["warning", "critical"]),
            AnomalyAlert.is_suppressed == False,  # noqa: E712
            AnomalyAlert.acknowledged == False,  # noqa: E712
        )
        .order_by(AnomalyAlert.severity.desc(), AnomalyAlert.detection_date.desc())
        .first()
    )
    if not alert:
        return None

    metric_label = _metric_human(alert.metric_name)
    val = alert.current_value
    val_str = f"{val:.0f}" if val is not None and val == int(val) else f"{val:.1f}" if val is not None else "?"

    text = f"你昨天 {metric_label} {val_str}，比平时{_deviation_word(alert.deviation_pct)}，现在感觉怎么样？"

    return OpenerSuggestion(
        text=text,
        source="anomaly",
        source_id=alert.id,
        quick_replies=["还好 / 已恢复", "确实不太对", "分析一下原因"],
        deep_link=f"/trace/anomaly_{alert.id}",
        priority=80,
    )


def _metric_human(name: str) -> str:
    return {
        "resting_heart_rate": "静息心率",
        "rhr": "静息心率",
        "hrv": "HRV",
        "sleep_score": "睡眠分",
        "stress_level": "压力值",
        "spo2_avg": "平均血氧",
        "spo2_low": "最低血氧",
        "body_battery": "电量",
    }.get(name, name)


def _deviation_word(pct: Optional[float]) -> str:
    if pct is None:
        return "异常"
    apct = abs(pct)
    if apct < 10:
        return "偏离一点"
    if apct < 25:
        return "明显偏离"
    return "差很多"


# ─────────────── strategy 2b: chronic-problem follow-up due ───────────────


# 结节/分期括注 ("(Hp 阴性,胃窦后壁)") 剥掉再内联进 opener 模板。
_PROBLEM_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")


def _short_problem_name(name: str) -> str:
    s = _PROBLEM_PAREN_RE.sub("", name or "").strip()
    return s.rstrip("，,。；;、：: ").strip()[:18]


def _try_problem_followup_due(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """已登记慢病/结节的随访到期/逾期 → 续接式复查开场白。

    复用 health_problem_service.due_followups(投影到时间线复查项的同一检测),让 opener
    与议程复查一致。慢病/结节随访是 Health OS 与 habit tracker 的分水岭,却此前从不进
    opener —— data-rich 用户 (有登记问题) 打开 chat 拿不到最该续接的复查话题。

    取最紧迫的一条 (due_followups 按 next_due asc → 逾期最久的在前)。
    """
    from app.services import health_problem_service as prob_svc

    fus = prob_svc.due_followups(db, user_id, within_days=14)
    if not fus:
        return None
    fu = fus[0]
    name = _short_problem_name(fu.get("name") or "")
    if not name:
        return None
    overdue = bool(fu.get("overdue"))
    what = (fu.get("what_to_check") or "").strip()
    focus = f"(重点看 {what[:14]})" if what else ""
    if overdue:
        text = f"你「{name}」的复查已经到期了{focus}，安排上了吗？"
        quick_replies = ["帮我安排复查", "已经查了", "看看上次结果"]
    else:
        text = f"你「{name}」快到复查时间了{focus}，要不要提前准备一下？"
        quick_replies = ["帮我准备", "还没到别急", "看看要查什么"]

    return OpenerSuggestion(
        text=text,
        source="health_problem",
        source_id=fu.get("problem_id"),
        quick_replies=quick_replies,
        deep_link=f"/health-problems/{fu.get('problem_id')}" if fu.get("problem_id") else None,
        priority=70,
    )


# ─────────────── strategy 3: active case_thread ───────────────


def _try_active_case_thread(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    最近 3-7 天内有更新的 active case_thread. 如果上次更新 < 24h, 跳过 (太近用户还没遗忘).
    """
    from app.models.clinical_journal import CaseThread

    now = datetime.now(timezone.utc)
    too_recent = now - timedelta(hours=24)
    too_old = now - timedelta(days=7)

    thread = (
        db.query(CaseThread)
        .filter(
            CaseThread.user_id == user_id,
            CaseThread.status == "active",
            CaseThread.last_updated_at <= too_recent,
            CaseThread.last_updated_at >= too_old,
        )
        .order_by(CaseThread.last_updated_at.desc())
        .first()
    )
    if not thread:
        return None

    title = (thread.title or thread.theme or "").strip()[:40]
    if not title:
        return None

    # 距上次更新天数
    last = thread.last_updated_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days_ago = max(1, (now - last).days)

    text = f"上次我们聊到「{title}」({days_ago} 天前)，这两天有变化吗？"

    return OpenerSuggestion(
        text=text,
        source="case_thread",
        source_id=thread.id,
        quick_replies=["好转了", "没变化", "更糟了"],
        deep_link=f"/(tabs)/journal",
        priority=60,
    )


# ─────────────── strategy 4: recent memory_fact ───────────────


def _try_recent_memory_fact(db: Session, user_id: int) -> Optional[OpenerSuggestion]:
    """
    7 天内新写入的 memory_fact (semantic / episodic 层, 跳过 working).
    层 working 是临时短期工作记忆, 不该作为 opener 信号.
    """
    from app.models.memory_fact import MemoryFact

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)

    fact = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.tier.in_(["semantic", "episodic"]),
            MemoryFact.last_reinforced_at >= cutoff,
            MemoryFact.superseded_by_id.is_(None),
        )
        .order_by(MemoryFact.last_reinforced_at.desc())
        .first()
    )
    if not fact:
        return None

    # 简单拼: subject predicate object — "你 提到 鼻炎"
    subj = (fact.subject or "你").strip()[:30]
    from app.services.memory_service import effective_memory_predicate

    pred = _predicate_human(effective_memory_predicate(
        fact.predicate, subject=fact.subject, object_value=fact.object_value, tags=fact.tags or [],
    ))
    # object_value 可能是上游过度提取残留的 JSON blob — serve 前整形。
    # 整形后没剩下有意义内容 → 跳过这条 opener (没线索好过一坨垃圾)。
    obj = sanitize_memory_snippet(fact.object_value, max_len=50)

    if not obj:
        return None

    text = f"{subj} {pred} {obj}，最近还想再聊聊吗？"

    return OpenerSuggestion(
        text=text,
        source="memory_fact",
        source_id=fact.id,
        quick_replies=["想聊", "暂时不用"],
        priority=40,
    )


def _predicate_human(predicate: str) -> str:
    return {
        "has_symptom": "提到症状",
        "takes_medication": "在服用",
        "has_allergy": "对",
        "prefers": "偏好",
        "avoids": "避开",
        "history_of": "有过",
        "responds_to": "对...有反应",
        "observed_change": "观察到变化",
    }.get(predicate, predicate)
