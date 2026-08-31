"""Workday microbreak §8.3 deterministic safety gate.

Codex spec §8.3 要求工作间隙微运动(俯卧撑)前过一道**确定性**安全闸门:

    safety:
      readiness_red: choose_mobility_or_rest   # 就绪度红 → 降级到活动/休息,不做俯卧撑
      after_meal_less_than_60_min: avoid_pushup  # 餐后 <60min → 避开俯卧撑,改步行/活动
      acute_symptom: reject                      # 急性红旗症状 → 直接拒绝,不给运动 nudge

边界(R4):微运动建议是 advisory;本闸门只做**确定性安全降级/拒绝**,绝不做医学诊断。
拒绝/降级都带一句简短安全理由(建议/可考虑措辞)。

数据读取走 **targeted query**(就绪度灯 / 最近一条饮食记录时间 / 近 72h 红旗症状),
**不**在 scheduler/请求内调 build_twin(它自开 SessionLocal、忽略传入 db、连真库)。
就绪度复用 recovery_decision.training_decision(scheduler 已有);症状镜像 builder 的
SymptomEntry/IllnessEpisode 读法 + symptoms 安全规则的红旗关键词。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 餐后多久内避开俯卧撑(§8.3 after_meal_less_than_60_min)
POST_MEAL_AVOID_MINUTES = 60

# DietRecord.meal_time 存的是**本地挂钟**(diet.py 直接 strftime("%H:%M"),无 UTC 转换),
# 服务器/Celery 跑 Asia/Shanghai。餐后窗口必须在同一本地挂钟下比较,否则 UTC vs 本地差
# 8 小时会让 meal_dt > now 被过滤掉 → 餐后闸门静默 fail-open(BLOCKING 修复)。
_LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# 急性红旗症状关键词 —— 命中即 reject(不给任何微运动 nudge)。
# 与 safety_guardian/rules/symptoms.py 的急症红线同源(ACS/卒中/呼吸困难/急腹症/大病前兆),
# 这里做去重精选:任何疑似心肺脑/出血/胸痛胸闷的表达都不该在工位做运动。
_ACUTE_SYMPTOM_KEYWORDS: tuple[str, ...] = (
    # 心脏 / 胸部
    "胸痛", "胸闷", "心前区", "胸口痛", "胸口闷", "心悸", "心慌",
    "心跳突然很乱", "心跳很乱", "心律不齐", "乱跳", "心跳漏拍",
    "胸口像被石头压住", "胸口压迫", "胸部压迫", "胸口发紧",
    "心脏像被攥住", "心口像被攥住", "胸口被压着", "胸口压着",
    "心口堵得慌", "心口堵",
    # 卒中 FAST
    "口角歪", "面瘫", "嘴歪", "言语不清", "说话不清", "口齿不清",
    "半身", "单侧无力", "一侧无力", "肢体无力", "突然看不清",
    "突然一只手没劲", "一只手没劲", "视线突然模糊", "突然视线模糊",
    "眼前发黑", "说话大舌头", "大舌头", "一边脸耷拉", "脸耷拉",
    # 呼吸
    "呼吸困难", "喘不上气", "喘不过气", "喘不上来", "喘不过来",
    "透不过气", "无法平卧", "端坐呼吸",
    "口唇发绀", "嘴唇发紫", "憋气严重", "呼吸费力",
    # 急腹症 / 消化道出血(含 symptoms.py acute_abdomen 全部 CRITICAL 关键词)
    "剧烈腹痛", "腹痛难忍", "刀割样腹痛", "板状腹", "腹部僵硬",
    "呕血", "黑便", "便血", "柏油样便", "大便像柏油",
    "咖啡渣样", "吐出来像咖啡渣",
    # 全身警示(含 symptoms.py red_flag_persistent_warning 的高危表现)
    "晕厥", "昏厥", "意识模糊", "持续发热", "反复发烧", "高热不退",
    "异常出血", "体重骤降", "暴瘦",
    "排便有鲜血", "排便鲜血", "大便带血", "便中带血", "鲜血便",
)

_ACUTE_SYMPTOM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:喘|呼吸|透气|吸气|吸).{0,5}(?:不上|不过|不进|困难|费力|憋)"),
    re.compile(r"(?:突然)?.{0,3}(?:一只|一边|一侧|单侧|左|右).{0,3}(?:手|手臂|胳膊|脚|脸|身体).{0,4}(?:没劲|无力|使不上劲|抬不起来|耷拉|麻)"),
    re.compile(r"(?:眼前|视线|视物|看东西).{0,5}(?:发黑|模糊|看不清|糊)"),
    re.compile(r"(?:说话|言语|口齿).{0,4}(?:大舌头|不清|含糊)"),
    re.compile(r"(?:胸口|胸部|心口|心脏).{0,8}(?:压|堵|攥|紧|痛|闷|坐着)"),
    re.compile(r"(?:心跳|心脏).{0,5}(?:乱|漏拍|漏跳|停跳)"),
)


def contains_acute_symptom_language(text: str | None) -> bool:
    """Conservative free-text safety signal shared by pre-routing guards."""
    normalized = str(text or "").strip().lower()
    return bool(normalized) and (
        any(keyword in normalized for keyword in _ACUTE_SYMPTOM_KEYWORDS)
        or any(pattern.search(normalized) for pattern in _ACUTE_SYMPTOM_PATTERNS)
    )


@dataclass(frozen=True)
class MicrobreakGateDecision:
    """§8.3 闸门结论。

    action:
      - "pushups"  正常:可做俯卧撑(green/yellow 各自强度由 scheduler 决定)
      - "mobility" 降级:就绪度红或餐后 <60min → 改活动/步行(避开俯卧撑)
      - "reject"   拒绝:急性红旗症状 → 完全不给微运动 nudge
    """

    action: str                                   # pushups / mobility / reject
    reason: str = ""                              # 简短安全理由(建议/可考虑措辞)
    safety_signals: List[str] = field(default_factory=list)

    @property
    def is_reject(self) -> bool:
        return self.action == "reject"

    @property
    def avoid_pushups(self) -> bool:
        return self.action in {"mobility", "reject"}


def _has_acute_symptom(db: Session, user_id: int) -> Optional[str]:
    """近 72h 是否有急性红旗症状 / 未痊愈急性病 → 返回命中文本(用于理由),否则 None。

    镜像 twin.builder 的 SymptomEntry/IllnessEpisode 读法,但只做 targeted query,
    不构建整个 twin。任一异常都向上抛(fail-loud):安全闸门吞异常=静默放行 = under-alarm 漏洞。
    """
    from app.models.illness import IllnessEpisode
    from app.models.symptom_entry import SymptomEntry

    cutoff = datetime.now(UTC) - timedelta(hours=72)
    recent = (
        db.query(SymptomEntry.description)
        .filter(
            SymptomEntry.user_id == user_id,
            SymptomEntry.occurred_at >= cutoff,
        )
        .order_by(SymptomEntry.occurred_at.desc())
        .limit(20)
        .all()
    )
    active = (
        db.query(IllnessEpisode.name)
        .filter(
            IllnessEpisode.user_id == user_id,
            IllnessEpisode.status.in_(["active", "improving"]),
        )
        .limit(10)
        .all()
    )
    blob_parts = [r[0] for r in recent if r[0]] + [a[0] for a in active if a[0]]
    blob = " ".join(blob_parts)
    if not blob:
        return None
    for kw in _ACUTE_SYMPTOM_KEYWORDS:
        if kw in blob:
            return kw
    return None


def _minutes_since_last_meal(db: Session, user_id: int, *, now_local: datetime, day: date) -> Optional[int]:
    """最近一餐距 now_local 的分钟数;无可定位的近餐 → None。

    全程用**本地挂钟 naive**比较(now_local + meal_time 同一 Asia/Shanghai 挂钟):
      - meal_time(Time, 本地挂钟)→ combine(<餐日>, meal_time) naive
      - 缺 meal_time → 退回 created_at(tz-aware UTC)→ 转本地 naive 近似
    允许 5 分钟时钟抖动容差,避免刚记完的餐被当成未来丢弃。

    午夜边界修复(BLOCKING):清晨(now_local 刚过午夜)做闸门时,昨晚的餐 meal_time(如 23:09)
    combine(今天) 会落到**未来** → 此前被丢弃、退回 created_at(=刚写库的 now)→ 误算「餐后 0 分钟」
    → 绿态也被错降级。修法:① 查询同时覆盖昨天+今天的 record_date(production 跨午夜餐
    record_date=昨天;测试 fixture 用 now_local.date()=今天);② meal_time 的挂钟候选同时尝试
    「餐日」与「餐日-1」两天,取**不晚于 now+skew 的最近一个**;③ meal_time 优先于 created_at,
    二者绝不混用 max(否则刚写库的 created_at≈now 盖过昨晚真实餐时点)。
    """
    from app.models.daily_health import DietRecord

    rows = (
        db.query(DietRecord.meal_time, DietRecord.created_at)
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date.in_([day - timedelta(days=1), day]),
        )
        .all()
    )
    if not rows:
        return None

    skew = timedelta(minutes=5)
    cap = now_local + skew

    def _created_local(created_at: Optional[datetime]) -> Optional[datetime]:
        if not isinstance(created_at, datetime):
            return None
        aware = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
        return aware.astimezone(_LOCAL_TZ).replace(tzinfo=None)  # 转本地 naive

    meal_dts: List[datetime] = []
    for meal_time, created_at in rows:
        chosen: Optional[datetime] = None
        if isinstance(meal_time, time):
            # 挂钟时点可能属于「今天」也可能属于「昨天」(跨午夜)。两天都试,取不晚于 now+skew
            # 的**最近**一个 —— 真实餐时点必在 now 之前;昨晚 23:09 在清晨即落到 day-1。
            valid_wall = [
                c for c in (
                    datetime.combine(day, meal_time),
                    datetime.combine(day - timedelta(days=1), meal_time),
                )
                if c <= cap
            ]
            if valid_wall:
                chosen = max(valid_wall)
        if chosen is None:
            created_local = _created_local(created_at)
            if created_local is not None and created_local <= cap:
                chosen = created_local
        if chosen is not None:
            meal_dts.append(min(chosen, now_local))
    if not meal_dts:
        return None
    last = max(meal_dts)
    return int((now_local - last).total_seconds() // 60)


def evaluate(
    db: Session,
    user_id: int,
    *,
    readiness_tone: str,
    day: date,
    now: Optional[datetime] = None,
) -> MicrobreakGateDecision:
    """跑 §8.3 三分支闸门(优先级:急性症状 reject > 就绪度红降级 > 餐后降级 > 正常)。

    readiness_tone 由 scheduler 的 _readiness_gate 已算出(green/yellow/red),复用不重算。
    now: 可选注入(测试用)。tz-aware → 转本地;naive → 当作本地挂钟。默认取本地当下。
    """
    if now is None:
        now_local = datetime.now(_LOCAL_TZ).replace(tzinfo=None)
    elif now.tzinfo is not None:
        now_local = now.astimezone(_LOCAL_TZ).replace(tzinfo=None)
    else:
        now_local = now
    signals: List[str] = []

    # 1) 急性红旗症状 → reject(最高优先,完全不给微运动 nudge)
    # signal 不带原始关键词(避免日志泄露敏感症状);具体命中词只进 user-facing reason。
    hit = _has_acute_symptom(db, user_id)
    if hit:
        signals.append("acute_symptom")
        return MicrobreakGateDecision(
            action="reject",
            reason=f"检测到急性不适(如「{hit}」),建议先休息并视情况就医,暂不安排工间运动。",
            safety_signals=signals,
        )

    # 2) 就绪度红 → 降级到活动/休息(choose_mobility_or_rest)
    if readiness_tone == "red":
        signals.append("readiness_red")
        return MicrobreakGateDecision(
            action="mobility",
            reason="今日恢复就绪度偏低,建议把俯卧撑换成轻活动或休息。",
            safety_signals=signals,
        )

    # 3) 餐后 <60min → 避开俯卧撑,改步行/活动(avoid_pushup)
    # 餐次查询用**本地**日期(now_local.date()),与本地挂钟比较保持同一时区基准;
    # 不复用入参 day(它来自 caller 的 date.today()=服务器系统 TZ,午夜窗口可能与本地差一天)。
    mins = _minutes_since_last_meal(db, user_id, now_local=now_local, day=now_local.date())
    if mins is not None and mins < POST_MEAL_AVOID_MINUTES:
        signals.append(f"post_meal_{mins}min")
        return MicrobreakGateDecision(
            action="mobility",
            reason=f"距上次进餐约 {mins} 分钟,建议改成轻松步行,可考虑餐后 1 小时再做俯卧撑。",
            safety_signals=signals,
        )

    # 4) 正常 → 维持俯卧撑(强度仍由 readiness tone 决定)
    return MicrobreakGateDecision(action="pushups", reason="", safety_signals=signals)
