"""Write 自治层 —— 首切片(Enter-key thesis 第一步:系统首次在无人确认下执行写)。

**范围严格收窄到唯一一种 kind**:`measurement_prompt`(「今天测一下血压/体重」这类
良性、可逆、非医疗、非依从的提醒)。其它一切 kind 永不自治。

R4 / 安全不变量(blocking review 重点):
- **硬 allowlist 仅 {measurement_prompt}** —— medical-grade / adherence_nudge / doctor_booking /
  food_order / alarm_set / reorder_nudge 永不自治(不在 allowlist → 恒走人确认)。
  自治写依从事实会污染 twin.medication.adherence → DDI/PGx/SafetyGuardian(已知地雷),故硬排除。
- **CRITICAL 安全告警活跃 → 抑制自治**:有急症时一切让位,不做任何后台自动写。
- **每用户每日上限**(AUTONOMY_DAILY_CAP)—— 现为**硬保证**:每次执行前在
  `autonomy_daily_counters` 单行上做原子 `UPDATE count=count+1 WHERE count<CAP` 预留额度
  (rowcount 门),并发请求绝不能各算 budget 各执行至多 2×CAP。见 `_reserve_autonomy_slot`。
- **复用 write_intent_service.confirm 的原子认领/回滚/幂等**,不另开第二条执行路径;
  trust_tier=auto 由 confirm 在赢得认领时随 status 原子翻档(不旁路改);
  产物(SmartReminder)可逆(用户可 dismiss)。
- **每条自治执行写一条 audit 记录**(audit.log_autonomous_write):系统首次"无人确认即写"的
  能力须可查询、可审计(治理 NIT-3)。旁路,失败不反噬已执行的写。
- **默认开启**(write_autonomy_enabled=True),可一键关。
- **任何异常 fail-safe**:不自治、留给人确认,绝不假装执行。

安全门档位(CRITICAL-only vs HIGH)—— **给下一个 kind-adder 的判据**:
本切片唯一 kind=measurement_prompt 是良性、可逆、非医疗、非依从的提醒(产物只是一条
SmartReminder),故安全门设 **CRITICAL + failed_rule_count>0**(有急症或筛查不全才抑制),
而非更严的 HIGH —— 对"提醒用户测个血压"这种零副作用动作,用 HIGH 抑制会因大量 HIGH(高
但非急)告警把良性提醒也常态卡死,得不偿失。
**但扩容到更高 stakes 的 kind 前必须重判**:任何会写医疗事实 / 依从 / 触发外部动作 /
财务相邻的 kind(理论上不该进 allowlist,但若将来放宽)应把门提到 **HIGH 也抑制**
(`any(a.severity >= Severity.HIGH ...)`),因为这类自治写的副作用不可逆/有临床下游,
"宁可多让人确认一次"远胜"在 HIGH 风险态下自动写"。改 allowlist 时**同步**在
`_safety_blocks_autonomy` 决定门档并更新本段。

B(承重墙基础设施,2026-06-26)—— **自治面零变化**,只把上面的不变量固化成代码 + 给 C 留接口:
- `NEVER_AUTONOMY_KINDS`:把 PRD #11「临床/剂量/处方/依从/财务永久人确认」从隐式(仅靠 allowlist)
  变成显式硬集合。auto 路径准入 = `kind ∈ runtime allowlist ∧ kind ∉ NEVER`(`_is_auto_eligible`),
  两道正交门:即便有人误把 NEVER kind 加进 allowlist,仍被硬拦。本集合**只增不减**。
- `_GATE_TIER_BY_KIND` + `_gate_tier_for`:每 kind 安全门档位表(measurement_prompt=CRITICAL,默认 HIGH)。
  框架就位 —— 未来任何 kind 默认走更严 HIGH 门;今日仍只 measurement_prompt(CRITICAL),行为不变。
- `runtime_autonomy_allowlist(db, user_id)`:**C 的挣权接入点**。返回有效 allowlist = 静态集 ∪
  该用户经 R16 外环 N-of-1 收敛挣到的 kind。B v1 无收敛数据,恒返回静态 {measurement_prompt}。
  C 升级某干预到自治,就在此处 ∪ per-user graduated kinds —— auto 路径已用本函数,接上即生效。
- 后台 Celery worker(`tasks/write_autonomy_worker.py`):把自动执行从 GET-lazy 路径解耦到后台周期任务。
  逻辑(allowlist/cap/safety gate/priority=low)完全不变,只换了**在哪跑**;cap 原子槽去重保证 bg+GET 不会双写。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.config import settings
from app.models.write_intent import WriteIntent
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

# 唯一允许自治执行的 kind:良性、可逆、非医疗、非依从。扩容须经安全评审 + 本注释更新。
AUTONOMY_ALLOWLIST = frozenset({"measurement_prompt"})
AUTONOMY_DAILY_CAP = 4
_BEIJING = timezone(timedelta(hours=8))

# ───────────── PRD #11 硬编码:这些 kind 永久 manual_confirm,绝不自治(belt-and-suspenders)─────────────
# Write 自治是**挣来的**,不是默认的。临床/剂量/处方/依从/财务/外部动作类写一律永久人确认。
# 这是与 AUTONOMY_ALLOWLIST 正交的**第二道硬门**:即便有人误把下列 kind 加进 allowlist,
# auto 路径仍因 `kind in NEVER_AUTONOMY_KINDS` 被硬拦(见 auto_execute_pending 的 assert)。
# 扩容自治面是 C 的活(经 N-of-1 外环收敛挣到),不是把 kind 从这里移走 —— 本集合只增不减。
#   - adherence_nudge:写依从事实污染 twin.medication.adherence → DDI/PGx/SafetyGuardian
#   - medication_intake_batch:一次确认写入多条服药事实,属于临床/剂量记录
#   - food_order:财务相邻(下单/支付)
#   - doctor_booking:外部动作(挂号)
#   - alarm_set / reorder_nudge / checkup_reminder / recheck_due / hearing_health_task:外部动作 / 物流 / 临床随访
# 任何未来的医疗/剂量/处方 kind 一旦引入,**必须**同时登记进本集合。
NEVER_AUTONOMY_KINDS = frozenset({
    "adherence_nudge",
    "medication_intake_batch",
    "food_order",
    "doctor_booking",
    "alarm_set",
    "reorder_nudge",
    "checkup_reminder",
    "recheck_due",
    "hearing_health_task",
})

# ───────────── 每 kind 安全门档位表(未来框架,allowlist 当前仍仅 measurement_prompt)─────────────
# 自治写前的安全门:failed_rule_count>0(漏判 CRITICAL 风险)恒抑制;此外按本表的 severity 阈值,
# 有任一 alert ≥ 该档则抑制。measurement_prompt(良性、可逆、零副作用)设 CRITICAL —— 仅急症抑制,
# 避免大量 HIGH(高但非急)告警把「提醒测血压」这种零副作用动作常态卡死(首切片行为不变)。
# **默认 HIGH**:任何未来 kind(若挣到自治)默认走更严的 HIGH 门 —— 副作用更重的写,宁可多让人确认。
# 注:这只是「门多严」的框架;「哪些 kind 能自治」仍由 AUTONOMY_ALLOWLIST ∩ ¬NEVER 决定,本表不放宽自治面。
_GATE_TIER_BY_KIND: Dict[str, str] = {"measurement_prompt": "CRITICAL"}
_DEFAULT_GATE_TIER = "HIGH"


def _gate_tier_for(kind: str) -> str:
    """该 kind 的安全门档位名(CRITICAL / HIGH)。未登记 kind → 更严的默认 HIGH。"""
    return _GATE_TIER_BY_KIND.get(kind, _DEFAULT_GATE_TIER)


def autonomy_enabled() -> bool:
    """全局开关(默认 True)。可经 settings.write_autonomy_enabled 一键关。"""
    return bool(getattr(settings, "write_autonomy_enabled", True))


def is_autonomy_allowlisted(kind: str) -> bool:
    return kind in AUTONOMY_ALLOWLIST


def runtime_autonomy_allowlist(db: Session, user_id: int) -> frozenset:
    """**有效自治 allowlist**(C 的挣权接入点)= 静态 AUTONOMY_ALLOWLIST ∪ 该用户经外环收敛挣到的 kind。

    设计意图(B v1 的承重墙接口,今日**零行为变化**):
    - 自治面扩容是 C 的活 —— C 经 R16 外环 N-of-1 收敛证明某干预对**该用户**确有效后,
      把那条 intent 升级为该用户的自治 kind(per-user graduation),通过本函数喂回 auto 路径。
    - **B v1 没有任何收敛数据,故本函数恒返回静态集**({measurement_prompt}),不读任何 per-user 升级表。
      这里就是 C 将来插入「per-user graduated kinds」并集的唯一地方 —— auto 路径已用本函数(见
      auto_execute_pending),C 接上即可,B 今日什么都不改。
    - 即便 C 升级了某 kind,NEVER_AUTONOMY_KINDS 仍是不可逾越的硬底线(临床/剂量/处方/依从/财务永不自治)。
    """
    # B v1:无 per-user 升级数据源,直接返回静态集。C 在此处 ∪ 用户已 graduate 的 kinds。
    return AUTONOMY_ALLOWLIST


def _auto_executed_today(db: Session, user_id: int) -> int:
    """今天(北京日历日)已自治执行(trust_tier='auto', status='executed')的条数。"""
    since = datetime.now(timezone.utc) - timedelta(days=2)  # 粗界限行数,再按北京日历日精确过滤
    rows = (
        db.query(WriteIntent.decided_at)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.trust_tier == "auto",
            WriteIntent.status == "executed",
            WriteIntent.decided_at.isnot(None),
            WriteIntent.decided_at >= since,
        )
        .all()
    )
    today = get_china_today()
    n = 0
    for (dt,) in rows:
        d = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if d.astimezone(_BEIJING).date() == today:
            n += 1
    return n


def _reserve_autonomy_slot(db: Session, user_id: int, day) -> bool:
    """原子预留一个自治执行额度;返回 True=预留成功(未超 CAP),False=今日额度已满。

    **每日上限的硬保证(cap-TOCTOU #3 封口)**:cap 检查与自增在
    `autonomy_daily_counters` 单行上的一条原子 `UPDATE count=count+1 WHERE count<CAP`
    里完成(行锁串行化并发预留)—— 两个并发 GET /write-intents 绝不能各算出 budget=4
    各执行 4(→ 2×CAP)。每条实际执行前都先在这里预留;预留成功数 ≤ CAP 即执行数 ≤ CAP。

    计数行首次创建时**用今日已自治执行的真实行数(_auto_executed_today)做种子**,使计数器
    在部署当天 / 已有历史执行时仍是权威(否则计数从 0 起,叠加历史真实执行会越过 CAP)。
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.autonomy_daily_counter import AutonomyDailyCounter

    # 确保今日计数行存在(种子=今日真实已执行数,跨部署/历史仍权威)。并发创建撞主键 →
    # SAVEPOINT 只回滚这条 INSERT,行已被别人建,继续走原子条件自增。
    row = (
        db.query(AutonomyDailyCounter)
        .filter(AutonomyDailyCounter.user_id == user_id, AutonomyDailyCounter.day == day)
        .first()
    )
    if row is None:
        seed = _auto_executed_today(db, user_id)
        try:
            with db.begin_nested():
                db.add(AutonomyDailyCounter(user_id=user_id, day=day, count=seed))
                db.flush()
        except IntegrityError:
            pass  # 并发已建 → 走下面的条件自增

    affected = (
        db.query(AutonomyDailyCounter)
        .filter(
            AutonomyDailyCounter.user_id == user_id,
            AutonomyDailyCounter.day == day,
            AutonomyDailyCounter.count < AUTONOMY_DAILY_CAP,
        )
        .update(
            {"count": AutonomyDailyCounter.count + 1}, synchronize_session=False
        )
    )
    db.commit()  # 立即提交,使预留对并发请求可见且持久(confirm 随后另起事务)
    return bool(affected)


def _release_autonomy_slot(db: Session, user_id: int, day) -> None:
    """归还一个已预留但**未真正执行**(confirm 抛错 / 幂等未执行)的额度。原子条件自减。"""
    from app.models.autonomy_daily_counter import AutonomyDailyCounter

    try:
        db.query(AutonomyDailyCounter).filter(
            AutonomyDailyCounter.user_id == user_id,
            AutonomyDailyCounter.day == day,
            AutonomyDailyCounter.count > 0,
        ).update(
            {"count": AutonomyDailyCounter.count - 1}, synchronize_session=False
        )
        db.commit()
    except Exception as e:  # noqa: BLE001 — 归还失败只会让额度偏保守(少执行),安全方向,不抛
        logger.warning("[write_autonomy] 归还自治额度失败(偏保守,忽略): %s", e)
        try:
            db.rollback()
        except Exception:
            pass


def _safety_blocks_autonomy(db: Session, user_id: int, *, tier: str = "CRITICAL") -> bool:
    """安全规则评估有任何条目失败,**或**有 alert ≥ 给定门档(tier)→ 抑制自治。

    关键(评审 BLOCKING):用 evaluate_rules_with_status 拿 failed_rule_count —— 普通 evaluate_safety
    会吞掉单条规则异常(critical_count 仍 0),若某 CRITICAL 规则在脏 twin 上崩了,门会假绿放行自治。
    部分筛查失败 = 可能漏了 CRITICAL → fail-safe 抑制。安全门用最新 twin(use_cache=False),不吃缓存。
    任何异常 → 抑制(绝不默许自治)。

    tier(per-kind 门档,见 _GATE_TIER_BY_KIND):
    - 'CRITICAL'(measurement_prompt,首切片唯一 kind)—— 仅急症抑制,行为与首切片一致。
    - 'HIGH'(默认,未来更高 stakes kind)—— 连 HIGH(高但非急)告警也抑制,宁可多让人确认。
    默认 'CRITICAL' 使存量调用方(及 monkeypatch `lambda db, uid: ...` 的测试)行为零变化。
    fail-safe:只有显式 'CRITICAL' 走 CRITICAL 门;其余任何值(含拼写错/未知 tier)→ 更严的
    HIGH 门(HIGH < CRITICAL,门更紧,会抑制更多)—— 绝不因 tier 字符串异常而**放松**自治门。
    """
    try:
        from app.agents.safety_guardian.engine import evaluate_rules_with_status
        from app.agents.safety_guardian.schema import Severity
        from app.twin.builder import build_twin

        alerts, failed_rule_count = evaluate_rules_with_status(build_twin(db, user_id, use_cache=False))
        if failed_rule_count > 0:
            logger.warning(
                "[write_autonomy] %s 条安全规则评估失败 → fail-safe 抑制自治(可能漏 CRITICAL)",
                failed_rule_count,
            )
            return True
        # fail-safe:只有显式 'CRITICAL' 用 CRITICAL 门;未知/异常 tier → 更严的 HIGH 门(绝不放松)。
        threshold = Severity.CRITICAL if tier == "CRITICAL" else Severity.HIGH
        return any(a.severity >= threshold for a in alerts)
    except Exception as e:  # noqa: BLE001 — 安全检查失败必须 fail-safe 抑制,不能默许自治
        logger.warning("[write_autonomy] safety gate check failed → 抑制自治: %s", e)
        return True


def _is_auto_eligible(kind: str, allowlist: frozenset) -> bool:
    """belt-and-suspenders 自治准入:kind ∈ 有效 allowlist **且** kind ∉ NEVER_AUTONOMY_KINDS。

    两道正交的门同时成立才放行 —— 即便有人误把某 NEVER kind(如 adherence_nudge)加进 allowlist,
    或 C 的挣权接入误升级了某临床/财务 kind,NEVER 这道硬底线仍单独把它拦死(PRD #11)。
    """
    return kind in allowlist and kind not in NEVER_AUTONOMY_KINDS


def auto_execute_pending(db: Session, user_id: int) -> Dict[str, Any]:
    """对该用户 allowlisted 的 pending WriteIntent,gate 全过则无需人确认自动执行(走既有 confirm)。

    返回 {auto_executed, reason}。供 generate_measurement_prompts 之后(或后台任务/Celery worker)调用。
    gate 任一不过 → auto_executed=0 + reason,WriteIntent 维持 pending 留人确认。

    自治准入两道正交硬门(belt-and-suspenders,PRD #11):
      ① kind ∈ runtime_autonomy_allowlist(C 的挣权接入点;B v1 = 静态 {measurement_prompt})
      ② kind ∉ NEVER_AUTONOMY_KINDS(临床/剂量/处方/依从/财务永久人确认,只增不减)
    """
    if not autonomy_enabled():
        return {"auto_executed": 0, "reason": "disabled"}

    # 有效 allowlist 减去 NEVER 硬底线 = 真正可自治的 kind 集合(B v1 恒 {measurement_prompt})。
    eligible_kinds = {
        k for k in runtime_autonomy_allowlist(db, user_id) if k not in NEVER_AUTONOMY_KINDS
    }
    if not eligible_kinds:
        return {"auto_executed": 0, "reason": "no_eligible_kinds"}

    # 安全门按本批 eligible kind 里**最严**的档位评一次(任一 kind 要 HIGH → 整批用 HIGH)。
    # B v1 仅 measurement_prompt(CRITICAL),故仍是 CRITICAL 门,首切片行为零变化。
    # fail-safe(Codex capstone BLOCKING #2):仅当本批**所有** eligible kind 都显式 'CRITICAL'
    # 才用更松的 CRITICAL 门;任一 HIGH **或未知/拼写错**的档 → collapse 到更严的 HIGH。
    # 旧写法 `any(==HIGH) else CRITICAL` 会把 _GATE_TIER_BY_KIND 里的拼写错值(非 HIGH 非 CRITICAL)
    # 误落到 CRITICAL(更松)分支,且因显式传 'CRITICAL' 绕过 _safety_blocks_autonomy 内部
    # "未知 tier→HIGH" 的兜底 —— 等于 tier 配错就放松了门。改成"全显式 CRITICAL 才 CRITICAL,否则 HIGH"。
    gate_tier = "CRITICAL" if all(_gate_tier_for(k) == "CRITICAL" for k in eligible_kinds) else "HIGH"
    # CRITICAL(默认)时按旧 2-参签名调用 —— 兼容存量调用方与既有 monkeypatch(`lambda db, uid: ...`);
    # 仅 HIGH 才显式传 tier(此分支今日无 kind 触发,框架就位待 C)。
    blocked = (
        _safety_blocks_autonomy(db, user_id, tier="HIGH")
        if gate_tier == "HIGH"
        else _safety_blocks_autonomy(db, user_id)
    )
    if blocked:
        return {"auto_executed": 0, "reason": "safety_gate_blocked"}
    # 软预筛(限查询行数 + 早退):用今日真实已执行数算剩余预算。硬保证在 _reserve_autonomy_slot。
    budget = AUTONOMY_DAILY_CAP - _auto_executed_today(db, user_id)
    if budget <= 0:
        return {"auto_executed": 0, "reason": "daily_cap"}

    pendings = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.status == "pending",
            WriteIntent.kind.in_(tuple(eligible_kinds)),
        )
        .order_by(WriteIntent.created_at.asc())
        .limit(budget)
        .all()
    )
    if not pendings:
        return {"auto_executed": 0, "reason": "no_eligible_pending"}

    runtime_allow = runtime_autonomy_allowlist(db, user_id)
    from app.agents import audit  # 自治写取证审计(旁路)
    from app.services import write_intent_service  # 懒导入断循环(write_intent_service 反向引用本模块)

    today = get_china_today()
    executed = 0
    for wi in pendings:
        # belt-and-suspenders 最后一道(纵深防御):逐条复核两道硬门 —— 即便上面的 SQL 过滤被
        # 误改、或 NEVER kind 误进了 allowlist,这里仍硬拦,绝不自治执行 NEVER kind。
        if not _is_auto_eligible(wi.kind, runtime_allow):
            logger.warning(
                "[write_autonomy] wi=%s kind=%s 不满足自治准入(allowlist∩¬NEVER)→ 硬拦,留人确认",
                wi.id, wi.kind,
            )
            continue
        # 硬上限:每条执行前原子预留一个额度;预留不到(今日已满,含并发)→ 停。
        if not _reserve_autonomy_slot(db, user_id, today):
            break
        # trust_tier=auto 由 confirm 在赢得原子认领时随 status 一起翻档(不旁路改,防并发误标)。
        try:
            res = write_intent_service.confirm(db, user_id, wi.id, trust_tier="auto")
        except Exception as e:  # noqa: BLE001 — 单条失败不拖累其余
            # cap fail-safe(Codex capstone BLOCKING #1):confirm 在 db.commit() **之后**才 refresh,
            # 若 refresh/旁路在 commit 之后抛 → 写已落库(status=executed + SmartReminder 已建)却异常逃逸。
            # 无条件归还额度会把**已消费**的槽错误释放 → 并发 sweep 复用 → 越过 CAP(破"硬保证")。
            # 故归还前用新读核实:仅在确证该 intent **未** executed 时才归还;已执行 / 状态读不到 →
            # 当已消费,不归还(宁可少执行,绝不超 CAP)。
            logger.warning("[write_autonomy] auto-confirm wi=%s 失败: %s", wi.id, e)
            committed = True  # 默认保守:除非新读确证未执行,否则当已消费
            try:
                db.rollback()  # 清理可能的脏 session(confirm 的 commit 已持久,rollback 只开新事务)
                row = (
                    db.query(WriteIntent.status)
                    .filter(WriteIntent.id == wi.id, WriteIntent.user_id == user_id)
                    .first()
                )
                committed = bool(row and row[0] == "executed")
            except Exception:  # noqa: BLE001 — 核实读失败 → 保守当已消费(不归还),不超 CAP
                committed = True
            if not committed:
                _release_autonomy_slot(db, user_id, today)  # 确证未执行 → 归还额度
            continue
        if res.get("status") == "executed" and not res.get("idempotent"):
            executed += 1
            # 治理(NIT-3):系统"无人确认即写"一等审计记录。旁路,失败不反噬已执行的写。
            audit.log_autonomous_write(
                db, user_id, intent_id=wi.id, kind=wi.kind,
                executed_ref=res.get("executed_ref"), trust_tier="auto",
            )
        else:
            _release_autonomy_slot(db, user_id, today)  # 幂等/未执行 → 归还额度
    return {"auto_executed": executed, "reason": "ok"}
