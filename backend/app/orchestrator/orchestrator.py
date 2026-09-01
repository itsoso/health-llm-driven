"""
Orchestrator 主执行循环。

run_orchestrator    同步/非流式调用 —— 返回完整 OrchestratorResponse
stream_orchestrator 流式调用       —— yield SSE event 字符串序列
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.config import settings
from app.orchestrator import parallel_synthesis
from app.orchestrator.intent import classify_intent
from app.orchestrator.schema import (
    Intent,
    OrchestratorRequest,
    OrchestratorResponse,
    SpecialistFinding,
)
from app.orchestrator.specialists import all_specialists, get_specialist
from app.services.episode.validator import validate_text, TextValidationResult
from app.services.llm.error_messages import safe_llm_error_message
from app.twin.builder import build_twin
from app.twin.formatter import twin_to_prompt_blob
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TurnKBResolution:
    """One immutable system-KB snapshot shared by a single Orchestrator turn."""

    lookup_result: Dict[str, Any]
    prompt_text: str
    lookup_ms: int
    lookup_count: int
    lookup_ok: bool
    claim_count: int

# 2026-05-13: 用户级 LLM 偏好 — run_orchestrator / stream_orchestrator 入口 set,
# _call_llm / _stream_llm 读取后调 create_provider_for_user. 避免 _call_llm 签名扩散.
_user_pref_ctx: ContextVar[Optional[Tuple[int, Session]]] = ContextVar(
    "orch_user_pref", default=None
)
# 成本/延迟分级路由(Tier 4):按 intent 设任务档,_call_llm 读取传给 factory。
# flag(settings.task_tiered_routing)默认关 → task_tier 被忽略 = 零行为变更。
_task_tier_ctx: ContextVar[Optional[str]] = ContextVar("orch_task_tier", default=None)
# rank11 分段合成:仅在**段落**调用期间(run_parallel_sectioned 的 gather 子任务)置位,
# _call_llm 读到即按本次真实 model 加思考/缓存控制(build_section_llm_kwargs 门控)。
# MEGA synthesis 调用不在此 ctx 内 → 永不带控制。default None = 存量行为逐字节不变。
_section_synthesis_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "orch_section_synthesis", default=None
)


def _section_synthesis_controls() -> Dict[str, Any]:
    """从 settings 算出段落调用的思考/缓存控制意图(不含 model 门控 —— 那在 _call_llm 里按
    本次真实 model 决定)。thinking 档见 parallel_synthesis.resolve_section_thinking;cache 复用
    rank3 的 llm_explicit_prompt_cache flag(默认关),让思考与缓存两个变量可独立开关。"""
    return {
        "thinking": parallel_synthesis.resolve_section_thinking(
            getattr(settings, "parallel_synthesis_section_thinking", "off")
        ),
        "cache": bool(getattr(settings, "llm_explicit_prompt_cache", False)),
    }

# 高风险类别 → reasoning 强模型;其余 → balanced。
# 安全不变量(fail-closed):orchestrator 合成永远产出面向用户的医疗内容(即便 intent
# 落到 general 也跑完 specialist + LLM 叙事),所以**任何 intent 都不许降到 casual/fast**。
# 地板是 balanced;高风险类别提到 reasoning。见 task_routing._FAST_ELIGIBLE_TIERS 的第二道闸。
_HIGH_STAKES_CATEGORIES = {"safety", "chronic", "mental", "labs", "longevity"}

# GenUI 能力协商: 客户端在 X-Reva-Client-Caps 头声明 'genui-v1' 才返回 reva-ui block。
# 新客户端再声明 'genui-components-v1' 时, 返回通用动态组件 schema。
GENUI_CAP = "genui-v1"
GENUI_COMPONENTS_CAP = "genui-components-v1"

_METRIC_LABEL = {
    "hrv": "HRV",
    "resting_hr": "静息心率",
    "stress": "压力",
    "sleep": "睡眠时长",
    "sleep_score": "睡眠评分",
    "steps": "步数",
    "body_battery": "身体电量",
    "weight": "体重",
}
_RANGE_LABEL = {"1m": "近一个月", "3m": "近三个月", "6m": "近半年"}


def _maybe_build_genui_chart(
    db: Session, user_id: int, req: OrchestratorRequest
) -> Optional[OrchestratorResponse]:
    """GenUI 图表组件短路。

    仅当 (a) 客户端 caps 含 genui-v1 且 (b) 检测到图表意图时介入。
    - 数据足够 → 返回带 ```reva-ui block + 确定性叙事的 OrchestratorResponse。
    - 数据不足 → 返回"数据不足"文本 (绝不补点)。
    - 不命中 (caps 缺 / 非图表意图) → 返回 None, 调用方走现状全流程 (零回归)。

    铁律: block 的数值全部来自 build_line_chart 的 DB 查询, 本路径不调用任何 LLM。
    """
    if GENUI_CAP not in (req.client_caps or []):
        return None

    from app.services.genui import (
        build_intra_curve,
        build_line_chart,
        build_multi_metric_chart,
        detect_chart_requests,
        detect_intra_curve_request,
        render_reva_ui_block,
    )

    # 单窗(昼/夜)intra 曲线优先 (血氧/HRV/心率/呼吸/压力/血糖/睡眠)。bug 修: 「昨晚/今天X」
    # 曾被误判成近半年月度趋势。命中即走逐点分支; 该窗无数据则诚实兜底走全流程, 绝不回退月度趋势。
    intra = detect_intra_curve_request(req.query)
    if intra is not None:
        _intra_metric, _intra_window = intra
        block = build_intra_curve(db, user_id, _intra_metric, _intra_window)
        if block is None:
            return None
        note = block.get("data_note", "")
        synthesis = (
            f"已根据你的设备逐点采样绘制{block.get('title', '曲线')}（{note}）。"
            f"图中为各时段实测值，未做任何推断填充。"
            f"\n\n{render_reva_ui_block(block)}"
        )
        return OrchestratorResponse(
            query=req.query,
            intent=classify_intent(req.query),
            findings=[],
            synthesis=synthesis,
            used_specialists=[],
            twin_build_ms=0,
            total_ms=0,
        )

    detected = detect_chart_requests(req.query)
    if not detected:
        return None

    rng = detected[0][1]
    intent = classify_intent(req.query)
    range_label = _RANGE_LABEL.get(rng, rng)

    component = (
        "metric_line_chart"
        if GENUI_COMPONENTS_CAP in (req.client_caps or [])
        else "line_chart"
    )

    if len(detected) >= 2:
        # 多指标叠加: 一张 line_chart 叠多条 metric 7 日滚动均值对比线 (无 LLM)。
        metrics = [m for m, _ in detected]
        block = build_multi_metric_chart(db, user_id, metrics, range=rng, component=component)
        if block is None:
            synthesis = (
                f"暂时无法绘制{range_label}的多指标趋势对比图：可用的真实数据点不足。"
                f"等设备同步更多数据后再试。"
            )
        else:
            note = block.get("data_note", "")
            synthesis = (
                f"已根据你的真实数据绘制{range_label}的多指标趋势对比（{note}）。"
                f"图中每条线均为对应指标的 7 日滚动均值，未做任何推断填充。"
                f"\n\n{render_reva_ui_block(block)}"
            )
    else:
        metric, _rng = detected[0]
        block = build_line_chart(db, user_id, metric, range=rng, component=component)
        metric_label = _METRIC_LABEL.get(metric, metric)

        if block is None:
            synthesis = (
                f"暂时无法绘制{range_label}的{metric_label}趋势图：可用的真实数据点不足。"
                f"等设备同步更多数据后再试。"
            )
        else:
            note = block.get("data_note", "")
            synthesis = (
                f"已根据你的真实数据绘制{range_label}的{metric_label}趋势（{note}）。"
                f"图中数值均为按月/周聚合的实测均值，未做任何推断填充。"
                f"\n\n{render_reva_ui_block(block)}"
            )

    return OrchestratorResponse(
        query=req.query,
        intent=intent,
        findings=[],
        synthesis=synthesis,
        used_specialists=[],
        twin_build_ms=0,
        total_ms=0,
    )


def _tier_for_intent(intent) -> str:
    cats = set(getattr(intent, "categories", []) or [])
    if cats & _HIGH_STAKES_CATEGORIES:
        return "high_stakes"
    # general / 空 / recovery / fuel / movement 等一律 balanced —— 合成是医疗内容,
    # 绝不降到 casual(=fast)。这是 fail-closed 地板,不是成本优化的可调项。
    return "balanced"


# G-W9: 客户端断开后 bg task 继续跑完 audit / memory / journal.
# set 持 task 引用防 GC; done_callback 自动清理.
_BACKGROUND_STREAM_TASKS: set = set()


def _safety_wrap(text: str, *, source: str = "orchestrator") -> TextValidationResult:
    """v3 cross-cutting: 所有 LLM 终态文本输出统一过 validator.

    异常时降级 (返回 ok=True / pass / 原文), 不能因为 validator 自身 bug
    把整个 orchestrator 弄挂.
    """
    try:
        return validate_text(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("[safety_wrap %s] validator 异常, 降级原文: %s", source, e)
        return TextValidationResult(ok=True, action="pass", safe_text=text or "")


# ───────────────────── 专家调度 ────────────────────────


# perf (2026-05-28): trivial query 短路阈值. categories=['general'] 且 query 字符数
# ≤ 这个值时跳过 specialist 全员 (hi/你好/在吗/thanks 等问候), 直接走 LLM + Twin.
# 选 6 是因为 6 个中文字 ≈ "今天我累了" 这类已包含 keyword 触发 (不会到 general).
_TRIVIAL_QUERY_MAX_LEN = 6


def _is_trivial_query(intent: Intent) -> bool:
    """问候/单词级 query: 无关键字命中 + 文本极短. 不需要 specialist 团队判断."""
    if intent.categories != ["general"]:
        return False
    q = (intent.raw_query or "").strip()
    return 0 < len(q) <= _TRIVIAL_QUERY_MAX_LEN


def _select_specialists(
    intent: Intent, twin: HealthTwin, forced: Optional[List[str]]
) -> List:
    """决定调度哪些 specialist。"""
    if forced:
        selected = []
        for name in forced:
            s = get_specialist(name)
            if s:
                selected.append(s)
        return selected

    if _is_trivial_query(intent):
        logger.info(
            f"[orchestrator] 跳过 specialist 全员: trivial query "
            f"(len={len(intent.raw_query or '')}, categories=general)"
        )
        return []

    return [s for s in all_specialists() if s.applies_to(intent, twin)]


_SPECIALIST_PARALLEL_TIMEOUT_S = 12.0  # 总墙钟上限, 防单个 stuck specialist 拖全链


def _run_specialists(
    twin: HealthTwin, specialists: List, context: Dict,
    *, timings: Optional[Dict[str, Any]] = None,
) -> List[SpecialistFinding]:
    """
    并行调用 specialist，收集结构化 finding。

    依赖关系: Recovery Coach 把 readiness_zone 写入 context, Movement Coach 读取。
    策略 (2026-05-28 优化):
      - 如果 movement_coach 在列表 → recovery 同步先跑 (传 readiness_zone)
      - 否则 → recovery 进并行池 (省 2-5s 串行等待)
      - 并行池整体超时 12s, 超时的 specialist 进 failed[] 不阻塞其余 finding

    Python 线程无法强杀, 超时只是停止等待; specialist 本身的 LLM 调用应有自己的
    HTTP 超时 (provider 层 30s 默认).

    perf (2026-05-28): 传 `timings={}` 时会原地填入:
        - recovery_ms:        recovery_coach 同步阶段耗时 (并入池时为 0)
        - parallel_wall_ms:   并行池墙钟时间 (含 recovery 如果并入)
        - per_specialist_ms:  {name: ms} 每个 specialist 的独立耗时
        - total_ms:           Phase 1 + Phase 2 之和
        - failed:             [name, ...] 异常或超时的 specialist 名
        - timed_out:          [name, ...] 因 12s 超时被丢的 specialist (subset of failed)
        - recovery_inlined:   bool — recovery 是否被并入池 (无 movement 时 True)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError

    ctx = dict(context)  # 不污染调用方
    findings: List[SpecialistFinding] = []
    per_sp_ms: Dict[str, int] = {}
    failed: List[str] = []
    timed_out: List[str] = []
    t_run_start = time.monotonic()
    recovery_ms = 0
    parallel_wall_ms = 0

    # ---- 分类: recovery / movement / rest ----
    recovery_sp = None
    movement_present = False
    rest_specialists = []
    for sp in specialists:
        if sp.name == "recovery_coach":
            recovery_sp = sp
        else:
            if sp.name == "movement_coach":
                movement_present = True
            rest_specialists.append(sp)

    recovery_inlined = bool(recovery_sp) and not movement_present

    # ---- Phase 1: movement_coach 在列表时才同步跑 recovery (才能传 readiness_zone) ----
    if recovery_sp and movement_present:
        t_sp = time.monotonic()
        try:
            finding = recovery_sp.run(twin, ctx)
            recovery_ms = int((time.monotonic() - t_sp) * 1000)
            per_sp_ms[recovery_sp.name] = recovery_ms
            findings.append(finding)
            zone = (finding.raw or {}).get("zone")
            if zone:
                ctx["readiness_zone"] = zone
                ctx["readiness_score"] = (finding.raw or {}).get("score")
        except Exception as e:  # noqa: BLE001
            recovery_ms = int((time.monotonic() - t_sp) * 1000)
            per_sp_ms[recovery_sp.name] = recovery_ms
            failed.append(recovery_sp.name)
            logger.warning(f"[orchestrator] specialist {recovery_sp.name} 失败: {e}")

    # ---- Phase 2: 其余 specialist 并发执行 (无 movement 时 recovery 也并入) ----
    pool_specialists: List = list(rest_specialists)
    if recovery_inlined:
        pool_specialists.insert(0, recovery_sp)  # type: ignore[arg-type]

    if pool_specialists:
        def _run_one(sp):
            t_sp = time.monotonic()
            try:
                result = sp.run(twin, ctx)
                return sp, result, int((time.monotonic() - t_sp) * 1000), None
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[orchestrator] specialist {sp.name} 失败: {e}")
                return sp, None, int((time.monotonic() - t_sp) * 1000), str(e)

        # 最多开 4 个线程（specialist 都是 CPU-bound 计算 + 少量 IO）
        max_workers = min(len(pool_specialists), 4)
        ordered_findings: List[Optional[SpecialistFinding]] = [None] * len(pool_specialists)

        t_parallel_start = time.monotonic()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_run_one, sp): idx
                for idx, sp in enumerate(pool_specialists)
            }
            try:
                for future in as_completed(
                    future_to_idx, timeout=_SPECIALIST_PARALLEL_TIMEOUT_S
                ):
                    idx = future_to_idx[future]
                    sp, finding, sp_ms, err = future.result()
                    per_sp_ms[sp.name] = sp_ms
                    if err:
                        failed.append(sp.name)
                    if finding:
                        ordered_findings[idx] = finding
            except FutureTimeoutError:
                elapsed = int((time.monotonic() - t_parallel_start) * 1000)
                for future, idx in future_to_idx.items():
                    if not future.done():
                        sp = pool_specialists[idx]
                        per_sp_ms[sp.name] = elapsed
                        failed.append(sp.name)
                        timed_out.append(sp.name)
                        logger.warning(
                            f"[orchestrator] specialist {sp.name} 超时 "
                            f"({_SPECIALIST_PARALLEL_TIMEOUT_S}s wall) — 已丢弃"
                        )
                        future.cancel()  # best-effort, 线程无法强杀
        parallel_wall_ms = int((time.monotonic() - t_parallel_start) * 1000)

        # 保持原始注册顺序: 如果 recovery 并入, 它在 pool[0], findings 顺序仍然 recovery 在前
        findings.extend(f for f in ordered_findings if f is not None)

    if timings is not None:
        timings["recovery_ms"] = recovery_ms
        timings["parallel_wall_ms"] = parallel_wall_ms
        timings["per_specialist_ms"] = per_sp_ms
        timings["total_ms"] = int((time.monotonic() - t_run_start) * 1000)
        timings["failed"] = failed
        timings["timed_out"] = timed_out
        timings["recovery_inlined"] = recovery_inlined

    return findings


def _persist_proposed_cards(
    db: Session, user_id: int, findings: List[SpecialistFinding]
) -> List[int]:
    """
    把每个 specialist 的 proposed_cards 落地为 ActionCard, 进入信任循环.

    去重: 如果该用户当前 active 状态已存在同 (creator_specialist, metric_key) 的卡片,
    跳过新建 (避免每次 orchestrator 跑都重复创建).
    """
    from datetime import datetime, timedelta, timezone
    from app.models.action_card import ActionCard

    persisted_ids: List[int] = []
    now = datetime.now(timezone.utc)

    for finding in findings:
        for proposed in finding.proposed_cards:
            # 去重: active + 同 specialist + 同 metric_key
            existing = db.query(ActionCard.id).filter(
                ActionCard.user_id == user_id,
                ActionCard.creator_specialist == finding.specialist_name,
                ActionCard.metric_key == proposed.metric_key,
                ActionCard.status == "active",
            ).first()
            if existing:
                logger.info(
                    f"[orchestrator] 跳过重复 proposed_card: "
                    f"specialist={finding.specialist_name} metric={proposed.metric_key} "
                    f"existing_id={existing[0]}"
                )
                continue

            check_back = now + timedelta(days=proposed.verification_days)
            card = ActionCard(
                user_id=user_id,
                title=proposed.title,
                content=proposed.content,
                card_type=proposed.card_type,
                source_type="orchestrator",
                priority=proposed.priority,
                metric_key=proposed.metric_key,
                baseline_value=proposed.baseline_value,
                target_value=proposed.target_value,
                verification_days=proposed.verification_days,
                evidence_level=getattr(proposed, "evidence_level", None) or "medium",
                evidence_refs=list(finding.evidence_refs or []),
                creator_specialist=finding.specialist_name,
                check_back_date=check_back,
            )
            try:
                db.add(card)
                db.commit()
                db.refresh(card)
                persisted_ids.append(card.id)
                logger.info(
                    f"[orchestrator] 落地 proposed_card #{card.id} "
                    f"({finding.specialist_name} → {proposed.metric_key} {proposed.target_value}, "
                    f"复查 {proposed.verification_days}d)"
                )
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.warning(f"[orchestrator] 落地 proposed_card 失败: {e}")

    return persisted_ids


# ───────────────────── LLM 合并 prompt ────────────────────


def _build_specialist_credit_block(db: Session, user_id: int, days: int = 30) -> str:
    """生成 specialist 命中率简短文本, 供 LLM 决策时参考 (信任循环反馈)."""
    try:
        from collections import defaultdict
        from datetime import datetime, timezone, timedelta as _td
        from app.models.action_card import ActionCard
        from app.services.outcome_safety import is_efficacy_score_eligible_card

        since = datetime.now(timezone.utc) - _td(days=days)
        cards = db.query(ActionCard).filter(
            ActionCard.user_id == user_id,
            ActionCard.graded_at.isnot(None),
            ActionCard.graded_at >= since,
            ActionCard.creator_specialist.isnot(None),
            ActionCard.accuracy_score.isnot(None),
        ).all()
        eligible = [card for card in cards if is_efficacy_score_eligible_card(card)]

        if not eligible:
            return ""
        by_specialist = defaultdict(list)
        for card in eligible:
            by_specialist[card.creator_specialist].append(int(card.accuracy_score))
        parts = []
        for specialist, scores in by_specialist.items():
            total = len(scores)
            hits = sum(score >= 70 for score in scores)
            rate = (hits / total * 100) if total else 0
            parts.append(f"{specialist}={rate:.0f}% ({hits}/{total}, avg {sum(scores) / total:.0f})")
        return " | ".join(parts)
    except Exception as e:
        logger.warning(f"[orchestrator] credit block 失败 (旁路): {e}")
        return ""


def _build_per_specialist_track_block(
    db: Session,
    user_id: int,
    active_specialists: List[str],
    days: int = 90,
    top_n: int = 2,
) -> str:
    """每个 active specialist 近 90 天的 top 高分 / 低分 ActionCard 摘要.

    与 credit_block 的聚合命中率互补:
      - credit_block 告诉 LLM "这个 specialist 整体可信度如何" (信任权重)
      - 本块告诉 LLM "具体哪条建议命中/没命中" (避免重复烂建议, 参考已验证有效建议)

    空结果 (冷启动/无评分) 返回 "", 不浪费 token.
    """
    if not active_specialists:
        return ""
    try:
        from datetime import datetime, timezone, timedelta as _td
        from app.models.action_card import ActionCard
        from app.services.outcome_safety import is_efficacy_score_eligible_card

        since = datetime.now(timezone.utc) - _td(days=days)
        now = datetime.now(timezone.utc)

        def _weeks_ago(dt) -> int:
            if dt is None:
                return 0
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, int((now - dt).total_seconds() / 86400 / 7))

        def _fmt(card: "ActionCard") -> str:
            title = (card.title or "")[:40]
            metric = card.metric_key or "?"
            score = int(card.accuracy_score or 0)
            w = _weeks_ago(card.graded_at)
            return f'"{title} → {metric}" ({score}分, {w}周前)'

        sections: List[str] = []
        for sp in active_specialists:
            base_q = db.query(ActionCard).filter(
                ActionCard.user_id == user_id,
                ActionCard.creator_specialist == sp,
                ActionCard.graded_at.isnot(None),
                ActionCard.graded_at >= since,
                ActionCard.accuracy_score.isnot(None),
            )
            cards = [card for card in base_q.all() if is_efficacy_score_eligible_card(card)]
            highs = sorted(
                (card for card in cards if card.accuracy_score >= 70),
                key=lambda card: card.accuracy_score,
                reverse=True,
            )[:top_n]
            lows = sorted(
                (card for card in cards if card.accuracy_score <= 30),
                key=lambda card: card.accuracy_score,
            )[:top_n]
            if not highs and not lows:
                continue
            lines = [f"- {sp}:"]
            for c in highs:
                lines.append(f"  ✅ 高命中: {_fmt(c)}")
            for c in lows:
                lines.append(f"  ❌ 低命中: {_fmt(c)}")
            sections.append("\n".join(lines))

        if not sections:
            return ""
        return "\n".join(sections)
    except Exception as e:
        logger.warning(f"[orchestrator] per-specialist track block 失败 (旁路): {e}")
        return ""


# ─── Coach Persona (P3-1, 2026-05-11) ──────────────────────────────────────
#
# 三档语气, 只加在主 system prompt 末尾, 不改 specialist / Twin / safety 输入.
# 不影响 source='siri' 路径 (Siri 已有自己的口语化规则).

PERSONA_ADDENDUM = {
    "strict_coach": (
        "12. **风格 (严厉教练)**: 直接命令式. 用户问题先给结论, 再给"
        "**1 个**最关键的行动. 不要软化, 不要'可以考虑/建议尝试', "
        "用'立刻'/'必须'/'今天就'. 用户找借口时, 引用具体数据反驳. "
        "目标: 让用户行动, 不让用户舒服."
    ),
    "gentle_advisor": (
        "12. **风格 (温和顾问)**: 共情开场, 解释为什么这条数据重要, "
        "再给 2-3 个可选行动让用户选. 用'看起来/好像/可以考虑/或许'等"
        "缓冲词. 高严重度内容仍然要明示, 不要过度温和到掩盖紧急性. "
        "目标: 让用户感到被理解, 在理解中接受改变."
    ),
    "data_driven": (
        "12. **风格 (数据派)**: 每条建议**必须**带具体数字阈值或参考范围. "
        "例: '减到 5g/天'/'保持在 60-100bpm'/'>140 立刻测'. "
        "不允许'适量/规律/坚持'等模糊词. 不解释生理机制, 直接给 "
        "metric → action → expected change 三段式. 目标: 让爱看数据的"
        "用户能验证每一条建议."
    ),
}


def _build_persona_addendum(db: Session, user_id: int) -> str:
    """查 user.coach_persona, 返回对应风格指令. 失败返回空 (不影响主 prompt)."""
    try:
        from app.models.user import User
        u = db.query(User).filter(User.id == user_id).first()
        if u is None:
            return ""
        persona = (u.coach_persona or "gentle_advisor").lower()
        return PERSONA_ADDENDUM.get(persona, "")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] persona addendum 失败 (旁路): {e}")
        return ""


def _fallback_cross_review_block(
    findings: List[SpecialistFinding],
    twin: HealthTwin,
    db: Optional[Session],
    user_id: Optional[int],
) -> str:
    """Run the deterministic rule layer when no precomputed result exists."""

    try:
        from app.orchestrator.cross_review import detect_conflicts, render_conflicts_for_prompt

        conflicts = detect_conflicts(findings, twin, db=db)
        if not conflicts:
            return ""
        conflicts_text = render_conflicts_for_prompt(conflicts)
        logger.info(
            f"[orchestrator] cross_review 检测到 {len(conflicts)} 个 specialist 冲突 (fallback)"
        )
        try:
            from app.agents.audit import log_cross_review_conflicts

            log_cross_review_conflicts(
                db,
                user_id=user_id or twin.meta.user_id,
                conflicts=[{
                    "specialist_a": conflict.specialist_a,
                    "specialist_b": conflict.specialist_b,
                    "severity": conflict.severity,
                    "description": conflict.description,
                    "resolution_hint": conflict.resolution_hint,
                } for conflict in conflicts],
                used_specialists=[finding.specialist_name for finding in findings],
            )
        except Exception as audit_error:  # noqa: BLE001
            logger.debug(f"[orchestrator] cross_review audit 失败: {audit_error}")
        return conflicts_text
    except Exception as error:  # noqa: BLE001
        logger.debug(f"[orchestrator] cross_review 跳过: {error}")
        return ""


def _build_synthesis_prompt(
    query: str, twin: HealthTwin, findings: List[SpecialistFinding],
    db: Optional[Session] = None, user_id: Optional[int] = None,
    conflict_arb_block: Optional[str] = None,
    realtime_evidence_block: str = "",
    system_kb_text: Optional[str] = None,
    source: Optional[str] = None,
    lite_mode: bool = False,
) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt).

    conflict_arb_block: 由调用方预先渲染的 cross_review + LLM 仲裁 markdown.
    None 表示未计算/检测失败, 保留向下兼容: 内部跑一次规则层 fallback.
    空串表示已成功计算且无冲突, 不得重复检测.

    source: 'siri' → 走语音播报口语化 prompt (短句/无 markdown/数字口语化/250 字上限),
           其它值 (chat/widget/None) → 走常规详细 prompt.

    lite_mode (2026-05-28): trivial/short query 走快路径时设为 True. 跳过:
        - system_kb_text (DB + vector lookup)
        - credit_text + track_text (30/90 天 audit_log 聚合)
        - user_feedback_text (negative feedback 查询)
        - persona_addendum (User 表查询)
      保留: twin_blob + personal_matrix (内存计算) + cross_review (findings 空时无开销).
      用在: _is_trivial_query 命中, 或 specialists 空 (无 finding 时这些块无意义).

    P3-1 (2026-05-11): 末尾按 user.coach_persona 切语气 (strict_coach /
    gentle_advisor / data_driven). 不改 specialist 输入也不改主 system 规则,
    只追加一条 12. 风格指令.
    """

    twin_blob = twin_to_prompt_blob(twin)
    personal_matrix_text = _format_personal_evidence_matrix_for_prompt(twin)
    if lite_mode:
        system_kb_text = ""
    elif system_kb_text is None and db is not None:
        try:
            from app.services.system_knowledge_service import format_system_knowledge_for_prompt

            system_kb_text = format_system_knowledge_for_prompt(
                db,
                _system_kb_twin_payload(twin),
                max_claims=6,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[orchestrator] system KB prompt injection skipped: {e}")
            system_kb_text = ""
    elif system_kb_text is None:
        system_kb_text = ""

    findings_text_parts: List[str] = []
    for f in findings:
        findings_text_parts.append(f"【{f.specialist_name}】{f.summary}")
        refs = list(f.evidence_refs or [])
        support_status = "supported" if refs else "model_inference"
        evidence_ref_text = ",".join(refs) if refs else "none"
        findings_text_parts.append(
            f"  证据契约: support_status={support_status}; evidence_refs={evidence_ref_text}"
        )
        for idx, item in enumerate(f.findings, 1):
            if isinstance(item, dict):
                sev = item.get("severity_label", "")
                title = item.get("title", "")
                action = item.get("action") or ""
                line = f"  {idx}. [{sev}] {title}"
                if action:
                    line += f" → {action}"
                item_refs = item.get("evidence_refs")
                if isinstance(item_refs, list) and item_refs:
                    line += f" (evidence_refs={','.join(str(ref) for ref in item_refs)})"
                findings_text_parts.append(line)
    findings_text = "\n".join(findings_text_parts) or "(无 specialist 输出)"

    # 信任循环反馈: 把过去 30 天的 specialist 命中率注入 prompt
    # lite_mode 跳过 — 没 specialist 的 trivial query 无需历史命中率上下文
    credit_text = ""
    track_text = ""
    if not lite_mode and db is not None and user_id is not None:
        credit_text = _build_specialist_credit_block(db, user_id, days=30)
        # 本次 run 的 specialist 名单, 只拉它们的历史 — 避免 prompt 膨胀
        active_sp_names = [f.specialist_name for f in findings if f.specialist_name]
        track_text = _build_per_specialist_track_block(
            db, user_id, active_sp_names, days=90, top_n=2,
        )

    # Trust Loop v2: 用户对过去判断的显式反馈 (not_helpful / irrelevant)
    # 让 LLM 看到"用户否定过的判断", 避免重复类似错误
    user_feedback_text = ""
    if not lite_mode and db is not None and user_id is not None:
        try:
            from app.api.judgment_feedback import get_recent_negative_feedback
            neg = get_recent_negative_feedback(db, user_id, days=30, limit=5)
            if neg:
                lines = ["## ⚠️ 用户最近否定过的 AI 判断 (避免重复)"]
                for n in neg:
                    snap = (n.get("snapshot") or "(无摘要)")[:150]
                    lines.append(
                        f"- {n.get('target_type')}#{n.get('target_id')} "
                        f"[{n.get('feedback')}]: {snap}"
                    )
                user_feedback_text = "\n".join(lines)
        except Exception:  # noqa: BLE001
            user_feedback_text = ""

    # Cross-Review: specialist 之间矛盾检测 + audit log
    # 如果 caller 已经预渲染了 (含 LLM 仲裁), 直接用; 否则 fallback 跑规则层
    conflicts_text = conflict_arb_block or ""
    if conflict_arb_block is None:
        conflicts_text = _fallback_cross_review_block(findings, twin, db, user_id)

    if source == "siri":
        system_prompt = (
            "你是健康助理的 Siri 语音播报员. 用户通过 Siri 问了你一个健康问题,"
            "你的回答会被 iOS 直接念出来给用户听, 必须是**说话的口吻**, 不是写作的口吻.\n\n"
            "硬性规则:\n"
            "1. **不要用任何 markdown** — 没有星号/井号/竖线/破折号列表/表格. 纯文本.\n"
            "2. **数字口语化** — 58 毫秒说'五十八毫秒', 92% 说'百分之九十二', 8.2 小时说'八小时十二分钟'. 保留 HRV/BP 等缩写字母发音.\n"
            "3. **短句短段** — 每句不超过 20 字, 全文不超过 200 字 (Siri 念完 1 分钟以内).\n"
            "4. **结论先行** — 第一句给答案, 后面最多两个支撑点.\n"
            "5. **最多一个行动** — 只说一条具体行动, 说清做什么、多少、什么时候.\n"
            "6. **不用术语** — 'ACWR'、'readiness zone'、'specialist'、'cross-review' 统统不说, 翻成人话.\n"
            "7. **不编数字** — 只用下方 specialist 给你的事实. 没数据就直说'暂时没有相关数据'.\n"
            "8. **不要'首先、其次、第三'结构词** — 说话人不这么说话.\n"
            "9. **严重度高优先说** — 红色告警放第一句; 常规建议在后.\n\n"
            "好的例子: '你最近睡得不错, 八小时多, 恢复度九十二分. 但心率变异偏低, 五十五毫秒, 比平均低一成. 今天训练量减半, 早点休息.'\n\n"
            "不好的例子: '**睡眠**: 8.2h | HRV: 55.0ms ↓10%. 建议: ACWR 调整.'"
        )
    else:
        system_prompt = (
            "你是健康助理的首席分析师。下游 specialist agent 已经对用户的 Digital Health Twin 做了结构化裁决，"
            "你的任务是：\n"
            "1. 理解用户的原始问题\n"
            "2. 把各个 specialist 的发现合成一个中文自然语言回答\n"
            "3. 严重度高的优先说，轻的收尾\n"
            "4. 数字和规则名不要凭空捏造，只用 specialist 给你的事实\n"
            "5. 给出 2-4 个具体的下一步行动（时间/频率要具体）\n"
            "6. **补剂/药物一律不写具体剂量数字 (2026-07-15 R4 硬化, 对齐确定性剂量护栏)**: "
            "任何补剂或药物只给种类/形式 (如 活性叶酸、维生素D3) 与随餐时机, **绝不输出剂量数字** "
            "(mg/μg/IU/g/毫克/单位/'每日X'/'X~Y'), 具体剂量交由临床医生; 涉及药物调整明确说需和医生确认。"
            "禁止引入 specialist findings 中未提及的补剂。\n"
            "7. 按问题完整回答，简洁有力，避免无关重复；不要因为回答较长而省略必要的证据、风险边界或下一步\n"
            "7.1 **医疗来源边界**: 涉及药物、补剂、溃疡、检查或复查时，必须明确区分"
            "用户陈述、已检索证据、模型推断和医生确认指示；不得把模型推断写成医嘱，"
            "不得在没有已验证写入回执时声称已安排、已预约或已记录。\n"
            "8. **信任校准**: 你下方会看到过去 30 天各 specialist 的预测命中率."
            " 命中率 ≥ 70% 的 specialist 建议优先采纳;"
            " 命中率 < 40% 的 specialist 建议表达时加 '仅供参考' 或要求用户复测;"
            " 没有命中率数据的 specialist 视为中等可信."
            " 如果有'具体建议追踪'块, 参考高命中建议的风格/剂量,"
            " 避免重复低命中的同质建议 (换角度/换剂量/换时段).\n"
            "9. **冲突仲裁**: 如果下方'Specialist 矛盾'区域有内容, 你必须在回答里明示如何裁决,"
            " 不能两个矛盾建议并列输出. hard 矛盾按 resolution_hint 走, soft 矛盾说明权衡."
            "\n10. **Trust Loop 避重**: 如果下方出现'用户最近否定过的 AI 判断', 不要重复同类判断,"
            " 或在给出时明示 '上次你反馈过不对, 这次我给出更谨慎的表述'."
            "\n10.5 **禁止软化硬约束 (2026-05-13 修)**: Specialist 的结构化裁决里, 含"
            " 'rest/停跑/禁 X/避免/不宜/暂停/过载/超载/hard_block' 等**禁止类**关键词时,"
            " 你**不得**在同一回答里提出'可以轻度进行 / Z1 30min / 少量 / 替代'等软化版建议."
            " 同一问题必须给**一致结论**: 若 MovementCoach 说 rest, 你回答'能跑步吗'时**只能**说"
            " 不能 + 原因 + 何时重评; 不能并列给出'但你可以轻度跑'. 类似规则适用: "
            " SafetyGuardian 急性告警 / SupplementAdvisor HFE 铁阻断 / 药物互动警告. "
            " 违反此条视为回答错误."
            "\n10.6 **数据缺口不编造 (2026-05-13 加)**: 任何 specialist finding 出现"
            " type='data_gap' 或 raw.data_gap=True 时, 你**不能**对该 specialist 涉及的指标"
            " 做任何具体数值/状态描述 (例如不能说 '您的血压可能正常' / '代谢看起来平稳'). "
            " 唯一允许的输出: 直接告诉用户'这部分缺 X 数据, 请上传/记录后我再分析'. "
            " 列出 data_gap.missing 的字段清单. 不允许用通用知识填空."
            "\n11. **显式归因 (P4 强制规则)**: 当你的建议**用到了用户的差异化数据**, "
            "**必须**在该建议后用括号明确标注来源, 让用户感受到 AI 在用他自己的数据 "
            "(而不是套用通用模板). 必填 marker 格式:\n"
            "    - 基因变体:   '(基于你的 MTHFR C677T 杂合)' / '(基于你的 ALDH2 杂合)'\n"
            "    - 化验结果:   '(参照你 6 月 LDL 4.1)' / '(参照你近期 HbA1c 5.8)'\n"
            "    - 在服药物:   '(因你在服异丙托溴铵)' / '(因你在服 GLP-1)'\n"
            "    - 历史症状:   '(基于你之前提到的鼻塞)' / '(基于你 6 月反馈的失眠)'\n"
            "    - 长期趋势:   '(参照你近 90 天 HRV 下降趋势)'\n"
            "    - 可穿戴日读数(HRV/睡眠/血氧/心率等): 引用具体数值时**尽量附数据日期或来源**"
            "(如 '你 6/21 夜间记录的 HRV 42ms' / '昨晚睡眠 3.3h'), 让每个个人数值可被核对到某一天.\n"
            "  没用到差异化数据的通用建议**不要**加 marker (避免噪声). "
            "  用了就**必须**加, 不加视为输出不合格."
            "\n12. **系统知识库证据优先**: 专家裁决中会出现 `support_status` 和 `evidence_refs`。"
            " `support_status=supported` 的建议有系统知识库 claim 支撑，优先采用；"
            " `support_status=model_inference` 或 `evidence_refs=none` 的建议只能作为模型推断，"
            "不得压过有证据的相反建议。若回答采用模型推断，必须用'目前证据不足，先作为尝试'等字样降级表达。"
        )

        # 健康世界观注入(四定律 + 四层 + 症状级红线)—— 统一所有 specialist 的哲学底座
        try:
            from app.services.health_worldview import worldview_prompt_blob
            system_prompt = system_prompt + "\n\n" + worldview_prompt_blob(include_triage=True)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[orchestrator] worldview 注入跳过: {e}")

        # P3-1 Coach Persona: 末尾追加风格指令 (不改前面规则, 只加语气)
        # lite_mode 跳过 User 表查询 — trivial query 用默认温和风格即可
        if not lite_mode and db is not None and user_id is not None:
            persona_addendum = _build_persona_addendum(db, user_id)
            if persona_addendum:
                system_prompt = system_prompt + "\n\n" + persona_addendum

    user_prompt_parts = [
        f"【用户原始问题】\n{query}",
        f"【用户当前健康快照】\n{twin_blob or '(数据暂缺)'}",
    ]
    if personal_matrix_text:
        user_prompt_parts.append(f"【个人证据矩阵】\n{personal_matrix_text}")
    if system_kb_text:
        user_prompt_parts.append(f"【系统知识库命中】\n{system_kb_text}")
    if realtime_evidence_block:
        # IQS 实时检索证据 — 补时效性/外部事实降幻觉; 放系统知识库后、专家裁决前。
        # 块内已含"不得覆盖个人数据与专家裁决"指令 (见 services/iqs_search._format_block)。
        user_prompt_parts.append(realtime_evidence_block)
    if credit_text:
        user_prompt_parts.append(f"【Specialist 历史命中率 (近 30 天)】\n{credit_text}")
    if track_text:
        user_prompt_parts.append(f"【各 Specialist 具体建议追踪 (近 90 天)】\n{track_text}")
    if user_feedback_text:
        user_prompt_parts.append(user_feedback_text)
    user_prompt_parts.append(f"【专家裁决】\n{findings_text}")
    if conflicts_text:
        # 冲突放在 specialist 输出之后, 醒目位置
        user_prompt_parts.append(conflicts_text)
    user_prompt_parts.append("请基于以上信息写回答。")

    return system_prompt, "\n\n".join(user_prompt_parts)


def _format_personal_evidence_matrix_for_prompt(twin: HealthTwin) -> str:
    try:
        from app.services.personal_evidence_matrix import (
            build_personal_evidence_matrix,
            compact_personal_evidence_matrix,
        )

        compact = compact_personal_evidence_matrix(build_personal_evidence_matrix(twin), max_signals=10)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[orchestrator] personal evidence matrix prompt skipped: %s", exc)
        return ""

    summary = compact.get("summary") or {}
    flags = list(compact.get("planner_flags") or [])
    lines = [
        f"summary: signals={summary.get('signal_count', 0)}; data_gaps={summary.get('data_gap_count', 0)}",
        f"planner_flags={','.join(flags) if flags else 'none'}",
    ]
    if "genetic_only_policy" in flags:
        lines.append("genetic_only_policy=low_until_validated")
    if "poor_recovery_matrix" in flags:
        lines.append("recovery_policy=avoid_high_intensity")
    epigenetic_ids = [
        str(signal.get("signal_id"))
        for signal in compact.get("key_signals", [])
        if str(signal.get("signal_type") or "") == "epigenetic"
    ]
    if epigenetic_ids:
        lines.append("epigenetic_policy=long_term_proxy_only")
        lines.append("epigenetic_boundary=甲基化/表观遗传时钟只能作为长期代理指标，不能证明短期抗衰疗效或真实衰老速度改变")
        lines.append(f"epigenetic_signals={','.join(epigenetic_ids)}")
    gap_ids = [
        str(signal.get("signal_id"))
        for signal in compact.get("key_signals", [])
        if str(signal.get("signal_id") or "").startswith("gap.")
    ]
    if gap_ids:
        lines.append(f"data_gaps={','.join(gap_ids)}")
    return "\n".join(lines)


def _system_kb_twin_payload(twin: HealthTwin) -> Dict[str, Any]:
    """Map HealthTwin fields into the compact KB condition namespace."""

    from app.services.system_knowledge_service import system_kb_twin_payload_from_health_twin

    return system_kb_twin_payload_from_health_twin(twin)


def _new_kb_lookup_session(
    db: Session,
    *,
    fallback_user_id: int,
) -> Session:
    """Create a caller-bind-compatible Session with an independent transaction."""

    bind = db.get_bind()
    if isinstance(bind, Connection):
        bind = bind.engine
    lookup_db = Session(bind=bind, autoflush=False)
    caller_info = getattr(db, "info", None)
    tenant_id = (
        caller_info.get("app_user_id")
        if isinstance(caller_info, dict)
        else None
    )
    lookup_db.info["app_user_id"] = (
        int(tenant_id) if tenant_id is not None else int(fallback_user_id)
    )
    return lookup_db


def _resolve_turn_system_knowledge(
    db: Session,
    twin: HealthTwin,
    *,
    enabled: bool,
) -> _TurnKBResolution:
    """Resolve one bounded KB snapshot, with one exceptional-path retry."""

    empty_result: Dict[str, Any] = {
        "entities": [],
        "contextual_entities": [],
        "claims": [],
        "claim_boundary": "",
    }
    if not enabled:
        return _TurnKBResolution(
            lookup_result=empty_result,
            prompt_text="",
            lookup_ms=0,
            lookup_count=0,
            lookup_ok=True,
            claim_count=0,
        )

    started = time.monotonic()
    try:
        from app.services.system_knowledge_service import (
            format_system_knowledge_result_for_prompt,
            lookup_for_twin,
        )

        payload = _system_kb_twin_payload(twin)
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "[orchestrator] system KB setup failed error_type=%s",
            type(error).__name__,
        )
        return _TurnKBResolution(
            lookup_result=empty_result,
            prompt_text="",
            lookup_ms=int((time.monotonic() - started) * 1000),
            lookup_count=0,
            lookup_ok=False,
            claim_count=0,
        )

    lookup_count = 0
    result: Optional[Dict[str, Any]] = None
    for attempt in range(2):
        lookup_db: Optional[Session] = None
        try:
            # KB resolution owns its transaction. This preserves the caller's
            # pending unit of work and prevents a failed read from poisoning the
            # Session used by later safety/context stages.
            lookup_db = _new_kb_lookup_session(
                db,
                fallback_user_id=twin.meta.user_id,
            )
            lookup_count += 1
            candidate = lookup_for_twin(lookup_db, payload)
            if not isinstance(candidate, dict):
                raise TypeError("lookup_for_twin returned a non-dict result")
            result = candidate
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "[orchestrator] system KB lookup failed attempt=%s error_type=%s",
                attempt + 1,
                type(error).__name__,
            )
            if lookup_db is not None:
                try:
                    lookup_db.rollback()
                except Exception as rollback_error:  # noqa: BLE001
                    logger.warning(
                        "[orchestrator] system KB lookup rollback failed "
                        "attempt=%s error_type=%s",
                        attempt + 1,
                        type(rollback_error).__name__,
                    )
        finally:
            if lookup_db is not None:
                try:
                    lookup_db.close()
                except Exception as close_error:  # noqa: BLE001
                    logger.warning(
                        "[orchestrator] system KB lookup session close failed "
                        "attempt=%s error_type=%s",
                        attempt + 1,
                        type(close_error).__name__,
                    )
        if result is not None:
            break

    if result is None:
        return _TurnKBResolution(
            lookup_result=empty_result,
            prompt_text="",
            lookup_ms=int((time.monotonic() - started) * 1000),
            lookup_count=lookup_count,
            lookup_ok=False,
            claim_count=0,
        )

    claims = result.get("claims") or []
    try:
        prompt_text = format_system_knowledge_result_for_prompt(
            result,
            max_claims=6,
        )
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "[orchestrator] system KB prompt formatting failed error_type=%s",
            type(error).__name__,
        )
        prompt_text = ""
    return _TurnKBResolution(
        lookup_result=result,
        prompt_text=prompt_text,
        lookup_ms=int((time.monotonic() - started) * 1000),
        lookup_count=lookup_count,
        lookup_ok=True,
        claim_count=len(claims),
    )


def _attach_kb_evidence_to_findings(
    db: Session,
    twin: HealthTwin,
    findings: List[SpecialistFinding],
    *,
    lookup_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    try:
        from app.services.system_knowledge_service import attach_system_knowledge_evidence

        return attach_system_knowledge_evidence(
            db,
            _system_kb_twin_payload(twin),
            findings,
            lookup_result=lookup_result,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] system KB evidence attach skipped: {e}")
        return {"findings_updated": 0, "claim_refs": 0}


def _count_avoided_kb_lookups(
    findings: List[SpecialistFinding],
    resolution: _TurnKBResolution,
) -> int:
    """Return legacy lookup attempts avoided by the shared turn snapshot."""

    if not resolution.lookup_ok or resolution.lookup_count == 0:
        return 0
    applicable_findings = sum(
        1
        for finding in findings
        if isinstance(finding.raw, dict)
        and isinstance(finding.raw.get("evidence_resolution"), dict)
        and finding.raw["evidence_resolution"].get("support_status")
        != "not_applicable"
    )
    legacy_lookup_count = applicable_findings + 1  # per finding + prompt rendering
    return max(0, legacy_lookup_count - resolution.lookup_count)


def _apply_planner_evidence_policy(
    findings: List[SpecialistFinding],
) -> tuple[List[SpecialistFinding], Dict[str, Any]]:
    """Deterministically keep unsupported advice out of planner synthesis.

    The final LLM is still useful for wording, but it should not decide whether
    unsupported actionable advice can overrule KB-backed advice. Safety alerts
    and data gaps are exempt because absence of a KB claim must not hide risk or
    missing-data instructions.
    """

    supported_categories = {
        (finding.category or "").lower()
        for finding in findings
        if getattr(finding, "evidence_refs", None)
    }
    supported_domains = {
        _planner_evidence_domain(finding)
        for finding in findings
        if getattr(finding, "evidence_refs", None)
    }
    kept: List[SpecialistFinding] = []
    blocked: List[Dict[str, Any]] = []

    for finding in findings:
        refs = list(finding.evidence_refs or [])
        category = (finding.category or "").lower()
        if refs:
            _mark_planner_policy(finding, blocked=False, kept_reason="supported")
            kept.append(finding)
            continue

        if _finding_is_safety_or_data_gap(finding):
            _mark_planner_policy(finding, blocked=False, kept_reason="safety_or_data_gap")
            kept.append(finding)
            continue

        evidence_domain = _planner_evidence_domain(finding)
        has_supported_peer = (
            category in supported_categories
            or (evidence_domain != "general" and evidence_domain in supported_domains)
        )
        if has_supported_peer and _finding_is_actionable(finding):
            reason = "unsupported_actionable_same_category_has_supported_kb"
            _mark_planner_policy(finding, blocked=True, reason=reason)
            blocked.append(
                {
                    "specialist": finding.specialist_name,
                    "category": finding.category,
                    "evidence_domain": evidence_domain,
                    "summary": finding.summary,
                    "reason": reason,
                }
            )
            continue

        _mark_planner_policy(finding, blocked=False, kept_reason="no_supported_same_category")
        kept.append(finding)

    return kept, {
        "input_count": len(findings),
        "kept_count": len(kept),
        "blocked_count": len(blocked),
        "blocked": blocked,
    }


def _mark_planner_policy(
    finding: SpecialistFinding,
    *,
    blocked: bool,
    reason: str | None = None,
    kept_reason: str | None = None,
) -> None:
    raw = getattr(finding, "raw", None)
    if not isinstance(raw, dict):
        try:
            finding.raw = {}
        except Exception:  # noqa: BLE001
            return
    payload: Dict[str, Any] = {"blocked": blocked}
    if reason:
        payload["reason"] = reason
    if kept_reason:
        payload["kept_reason"] = kept_reason
    finding.raw["planner_evidence_policy"] = payload


def _planner_evidence_domain(finding: SpecialistFinding) -> str:
    text = f"{getattr(finding, 'specialist_name', '')} {getattr(finding, 'category', '')}".lower()
    if any(token in text for token in ("movement", "recovery", "training", "exercise")):
        return "training_recovery"
    if any(token in text for token in ("fuel", "nutrition", "diet", "metabolic")):
        return "metabolic_nutrition"
    if any(token in text for token in ("supplement", "medication", "drug", "safety")):
        return "medication_supplement_safety"
    if "sleep" in text:
        return "sleep_recovery"
    return (getattr(finding, "category", None) or "general").lower() or "general"


def _finding_is_actionable(finding: SpecialistFinding) -> bool:
    for item in getattr(finding, "findings", None) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() == "data_gap":
            continue
        if item.get("action") or item.get("recommendation") or item.get("title"):
            return True
    return bool((getattr(finding, "summary", "") or "").strip())


def _finding_is_safety_or_data_gap(finding: SpecialistFinding) -> bool:
    name = (getattr(finding, "specialist_name", "") or "").lower()
    category = (getattr(finding, "category", "") or "").lower()
    if "safety" in name or category == "safety":
        return True
    raw = getattr(finding, "raw", None) or {}
    if isinstance(raw, dict) and raw.get("data_gap"):
        return True
    for item in getattr(finding, "findings", None) or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        severity = str(item.get("severity_label") or item.get("severity") or "").lower()
        if item_type == "data_gap":
            return True
        if severity in {"red", "critical", "emergency", "high", "severe"}:
            return True
    return False


def _collect_evidence_claim_ids(findings: List[SpecialistFinding]) -> List[str]:
    """Distinct KB claim doc_ids handed to the LLM as evidence across all findings.

    Union of each finding's top-level ``evidence_refs`` and any per-item
    ``evidence_refs`` nested in ``finding.findings``. Order-preserving, deduped.
    """
    seen: set[str] = set()
    ordered: List[str] = []

    def _add(ref: Any) -> None:
        if isinstance(ref, str) and ref and ref not in seen:
            seen.add(ref)
            ordered.append(ref)

    for finding in findings:
        for ref in getattr(finding, "evidence_refs", None) or []:
            _add(ref)
        for item in getattr(finding, "findings", None) or []:
            if isinstance(item, dict):
                for ref in item.get("evidence_refs") or []:
                    _add(ref)
    return ordered


def _specialist_audit_snapshot(findings: List[SpecialistFinding]) -> List[Dict[str, Any]]:
    """Build specialist audit payload with system-KB evidence coverage.

    Missing `evidence_refs` is intentionally marked as unsupported for KB
    coverage metrics. This does not block or downgrade the user-facing answer.
    """

    snapshot: List[Dict[str, Any]] = []
    for f in findings:
        data = f.model_dump(mode="json").get("raw") or {}
        if not isinstance(data, dict):
            data = {"raw": data}
        data = dict(data)
        resolution = data.get("evidence_resolution")
        if not isinstance(resolution, dict):
            resolution = {}
        refs = list(f.evidence_refs or resolution.get("evidence_refs") or [])
        evidence_ref_count = len(refs)
        if resolution:
            support_status = str(
                resolution.get("support_status")
                or ("supported" if refs else "model_inference")
            )
            unsupported = bool(
                resolution.get("unsupported", support_status == "model_inference" and not refs)
            )
            unsupported_reason = resolution.get("unsupported_reason")
        else:
            unsupported = len(refs) == 0
            support_status = "model_inference" if unsupported else "supported"
            unsupported_reason = "missing_system_kb_evidence_refs" if unsupported else None
        data["evidence_refs"] = refs
        data["evidence_ref_count"] = evidence_ref_count
        data["support_status"] = support_status
        data["unsupported"] = unsupported
        if unsupported:
            data["unsupported_reason"] = unsupported_reason
        else:
            data.pop("unsupported_reason", None)
        snapshot.append(
            {
                "specialist": f.specialist_name,
                "kind": f.category,
                "summary": f.summary,
                "data": data,
                "evidence_refs": refs,
                "evidence_ref_count": evidence_ref_count,
                "support_status": support_status,
                "unsupported": unsupported,
                "unsupported_reason": unsupported_reason,
                "proposed_cards": [c.model_dump(mode="json") for c in (f.proposed_cards or [])],
            }
        )
    return snapshot


def _inject_memory(db: Session, user_id: int, user_prompt: str,
                    findings: Optional[List[SpecialistFinding]] = None,
                    lite_mode: bool = False,
                    ) -> tuple[str, Dict[str, Any]]:
    """注入用户对话记忆 + Clinical Journal 相关 case timeline.

    每个 stage 显式跟踪 ok / chars / count / error, 最后写到 audit_log
    (agent_type='memory_injection') 给 observability dashboard 聚合.
    这是 T1.1 Memory 注入诊断 — 让"AI 真的记得我吗"可量化.

    lite_mode (2026-05-28): trivial query 快路径设为 True. 跳过 hybrid retrieval
        (BM25 + Graph + RRF over 个人 facts, 几百 ms+, 对 'hi' 无意义).
        保留 conversation memory / directives — 这俩对任何 query 都重要 (过敏/医嘱).

    Returns:
        (prompt_with_memory, trace_dict). trace 已经写入 memory_injection audit,
        但调用方也需要它以传给 log_orchestrator_run, 让 orchestrator 主 audit 也
        带上 memory 数据 (Phase 0.3: 之前 result_detail 没记录, audit 看不到).
    """
    out = user_prompt
    base_len = len(user_prompt)
    trace = {
        "stages": {},
        "total_chars_added": 0,
    }

    def _record(name: str, ok: bool, chars: int, count: int, error: Optional[str] = None) -> None:
        trace["stages"][name] = {
            "ok": ok,
            "chars": chars,
            "count": count,
            "error": (error[:200] if error else None),
        }

    # 1) 通用对话记忆 (过敏/医嘱/偏好)
    try:
        from app.services.conversation_memory_service import get_relevant_memories
        memories = get_relevant_memories(db, user_id, limit=5)
        if memories:
            block = f"\n\n【用户历史偏好/记忆】\n{memories}\n"
            out += block
            _record("conversation", ok=True, chars=len(block),
                    count=memories.count("\n") + 1)
        else:
            _record("conversation", ok=False, chars=0, count=0)
    except Exception as e:  # noqa: BLE001
        _record("conversation", ok=False, chars=0, count=0, error=str(e))

    # 2) Clinical Journal case timeline (本次 finding 相关的 metric 历史)
    metric_key: Optional[str] = None
    try:
        from app.services.clinical_journal_service import (
            get_recent_case_summary,
            _pick_primary_metric,
        )
        if findings:
            metric_key = _pick_primary_metric(findings)
            if metric_key:
                history = get_recent_case_summary(db, user_id, metric_key, max_entries=3)
                if history:
                    block = (f"\n\n【相关 case 历史 — agent 应基于此连贯回应】\n"
                            f"{history}\n")
                    out += block
                    _record("case_timeline", ok=True, chars=len(block),
                            count=history.count("\n") + 1)
                else:
                    _record("case_timeline", ok=False, chars=0, count=0)
            else:
                _record("case_timeline", ok=False, chars=0, count=0,
                        error="no_metric_key_picked")
        else:
            _record("case_timeline", ok=False, chars=0, count=0,
                    error="no_findings")
    except Exception as e:  # noqa: BLE001
        _record("case_timeline", ok=False, chars=0, count=0, error=str(e))
        logger.debug(f"[orchestrator] case timeline 注入失败 (跳过): {e}")

    # 3) User Directives — 医生 / 用户硬性指令 (specialist 必须遵循)
    try:
        from app.services.directive_parser import get_active_directives_for_prompt
        directives_md = get_active_directives_for_prompt(db, user_id, metric_key=metric_key)
        if directives_md:
            block = f"\n\n{directives_md}\n"
            out += block
            _record("directives", ok=True, chars=len(block),
                    count=directives_md.count("\n") + 1)
        else:
            _record("directives", ok=False, chars=0, count=0)
    except Exception as e:  # noqa: BLE001
        _record("directives", ok=False, chars=0, count=0, error=str(e))
        logger.debug(f"[orchestrator] directive 注入失败 (跳过): {e}")

    # 4) Hybrid Retrieval (BM25 + Graph + RRF) — LLM Wiki v2 阶段 C
    # 一路替换原来的 facts + KG 双路注入. 检索结果按 RRF 融合排序.
    # lite_mode 跳过 — BM25 + Graph 对 trivial query 'hi' 没有信号.
    if lite_mode:
        _record("hybrid", ok=False, chars=0, count=0, error="lite_mode_skip")
    else:
        try:
            from app.services.hybrid_search import hybrid_retrieve, render_hits_for_prompt
            query_seed = (user_prompt or "")[:300]
            hits = hybrid_retrieve(db, user_id, query_seed, top_k=10)
            if hits:
                rendered = render_hits_for_prompt(hits, max_lines=10)
                block = f"\n\n{rendered}\n"
                out += block
                _record("hybrid", ok=True, chars=len(block), count=len(hits))
            else:
                _record("hybrid", ok=False, chars=0, count=0)
        except Exception as e:  # noqa: BLE001
            _record("hybrid", ok=False, chars=0, count=0, error=str(e))
            logger.debug(f"[orchestrator] hybrid retrieval 注入失败 (跳过): {e}")

    trace["total_chars_added"] = len(out) - base_len

    # 旁路写 audit (失败不影响主流程)
    try:
        from app.agents.audit import log_memory_injection
        log_memory_injection(db, user_id, trace)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] memory_injection audit 写入失败 (跳过): {e}")

    return out, trace


# ───────────────────── LLM 调用（带回退） ─────────────────


# perf (2026-05-28): lite_mode 的 max_tokens 上限. trivial query 通常 30-100 token 够,
# 降到 300 给一些余量, 比默认 900 省 50%+ 生成时间 (尤其慢模型 reasoning tier).
_LITE_MAX_TOKENS = 300
# full 模式上限。max_tokens 是天花板不是目标:正常 finish_reason=stop 会提前停,
# 抬高不拖慢会自然结束的回答,只让长分析(体检/抗衰多 section、Opus 详尽输出)写完。
# 900 太低,深度分析会被 finish_reason=length 从中间截断(web Opus-4.7 实测)。
_FULL_MAX_TOKENS = 2000


def _strip_llm_reva_ui(text: str) -> str:
    """确定性护栏 (R4, 防御纵深): 剥掉 LLM synthesis 里伪造的 ```reva-ui``` 图表 block。

    图表 block 只能由 `_maybe_build_genui_chart` 确定性短路产出 —— 它更早返回, 从不
    经过任何 LLM synthesis 路径, 因此本函数只作用于 LLM 生成文本, 绝不会吃掉短路的 block。
    单一真源在 `app.services.genui.strip_reva_ui_blocks`。"""
    from app.services.genui import strip_reva_ui_blocks

    return strip_reva_ui_blocks(text)


async def _call_llm(
    system_prompt: str, user_prompt: str, *, lite_mode: bool = False,
    allow_synthesis_override: bool = False,
) -> str:
    """调用 LLM，失败时尝试 openai fallback。返回空字符串表示失败。

    主路径走 settings.llm_provider (默认 tokenplan / 阿里云 MiniMax),
    失败回退到 openai (DashScope vision key 也可作 OpenAI-兼容).
    外部旧 provider 已退役, 不再作为兜底.

    lite_mode (2026-05-28): trivial query 走 lite path 时降 max_tokens 到 300
        (默认 900). 不换模型 → 不影响 voice, 只省生成时长.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    max_toks = _LITE_MAX_TOKENS if lite_mode else _FULL_MAX_TOKENS

    async def _try(provider_type: Optional[str]) -> Optional[str]:
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.factory import create_llm_provider, create_provider_for_user

            if provider_type:
                provider = create_llm_provider(provider_type)
            else:
                # 深报告 mega 合成模型覆盖(2026-07-15, D 组换快):仅当调用方显式
                # allow_synthesis_override=True(= run_orchestrator 的报告 mega 合成)且 settings
                # 非空时,用指定 model_id 建 provider(绕过 per-user/task_tier),走更快的
                # deepseek-v4-flash。**不作用于 Siri 语音 / 冲突仲裁 / 段落合成**(它们不传此开关)——
                # 安全评审要求:覆盖范围必须与"深报告"注释一致,不静默扩到未验证的产品面。
                # 默认空/未开 → 存量行为;失败仍走下方 openai fallback(provider_type)。
                _synth_model = (
                    (getattr(settings, "orchestrator_synthesis_model_id", "") or "").strip()
                    if allow_synthesis_override else ""
                )
                if _synth_model:
                    from app.services.llm.factory import create_provider_for_model_id
                    provider = create_provider_for_model_id(_synth_model)
                else:
                    pref = _user_pref_ctx.get()
                    if pref is not None:
                        uid, _db = pref
                        provider = create_provider_for_user(uid, _db, task_tier=_task_tier_ctx.get())
                    else:
                        provider = get_llm_provider()
            # rank11 段落调用:在 ctx 内则按本次真实 model 加思考/缓存控制(门控 fail-closed;
            # MEGA 调用不在 ctx 内 → extra 恒空,payload 逐字节不变)。failover 到不同 model 时
            # 按该 provider 的 model 再各自门控,不会把控制误带给不支持的兜底端点。
            _section_ctrl = _section_synthesis_ctx.get()
            extra_kwargs: Dict[str, Any] = (
                parallel_synthesis.build_section_llm_kwargs(
                    getattr(provider, "model", None), _section_ctrl
                )
                if _section_ctrl
                else {}
            )
            result = await provider.chat(
                messages=messages, temperature=0.3, max_tokens=max_toks, **extra_kwargs
            )
            if isinstance(result, dict):
                return (result.get("content") or "").strip() or None
            return str(result or "").strip() or None
        except Exception as e:
            logger.warning(
                f"[orchestrator] LLM provider={provider_type or 'default'} 失败: {str(e)[:200]}"
            )
            return None

    text = await _try(None)
    if not text:
        text = await _try("openai")
    return text or ""


async def _run_cross_review_and_arbitration(
    findings: List[SpecialistFinding],
    twin: HealthTwin,
    db: Optional[Session],
    user_id: Optional[int],
) -> Optional[str]:
    """检测 cross_review 冲突 → 达到门槛就 LLM 仲裁. 返回要注入 synthesis prompt 的渲染文本.

    - 有冲突 + 达到 LLM 触发门槛 (hard 或 >=2): await arbitrate_conflicts; 写 audit
    - 有冲突但未到门槛: 仅渲染 cross_review (规则层), 写 cross_review audit
    - 无冲突: 返回空串
    - 检测失败: 返回 None, 由调用方执行一次规则层 fallback
    """
    try:
        from app.orchestrator.cross_review import detect_conflicts, render_conflicts_for_prompt
        conflicts = detect_conflicts(findings, twin, db=db)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] cross_review 跳过: {e}")
        return None

    if not conflicts:
        return ""

    # 1) 规则层 audit (无论是否触发 LLM 都记)
    uid = user_id or twin.meta.user_id
    conflict_snapshot = [{
        "specialist_a": c.specialist_a, "specialist_b": c.specialist_b,
        "severity": c.severity, "description": c.description,
        "resolution_hint": c.resolution_hint,
    } for c in conflicts]
    try:
        from app.agents.audit import log_cross_review_conflicts
        log_cross_review_conflicts(
            db, user_id=uid,
            conflicts=conflict_snapshot,
            used_specialists=[f.specialist_name for f in findings],
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] cross_review audit 失败: {e}")
    logger.info(f"[orchestrator] cross_review 检测到 {len(conflicts)} 个 specialist 冲突")

    # 2) LLM 仲裁 (仅 hard 或 >=2 conflicts)
    try:
        from app.orchestrator.arbitration import (
            arbitrate_conflicts, render_arbitration_for_prompt, _should_arbitrate,
        )
        if _should_arbitrate(conflicts):
            arb = await arbitrate_conflicts(conflicts, findings, twin, _call_llm)
            if arb is not None:
                # Audit arbitration (旁路)
                try:
                    from app.agents.audit import log_llm_arbitration
                    log_llm_arbitration(
                        db, user_id=uid,
                        arbitration=arb.to_dict(),
                        conflicts_snapshot=conflict_snapshot,
                    )
                except Exception as e_audit:  # noqa: BLE001
                    logger.debug(f"[orchestrator] arbitration audit 失败: {e_audit}")
                logger.info(f"[orchestrator] LLM 仲裁: winning={arb.winning_side} conf={arb.confidence:.2f}")
                return render_arbitration_for_prompt(arb)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] arbitration 跳过: {e}")

    # 3) 回退: 仅规则层渲染
    return render_conflicts_for_prompt(conflicts)


async def _resolve_cross_review_block(
    findings: List[SpecialistFinding],
    twin: HealthTwin,
    db: Optional[Session],
    user_id: Optional[int],
) -> str:
    """Resolve cross-review to one final string shared by every synthesis path."""

    block = await _run_cross_review_and_arbitration(findings, twin, db, user_id)
    if block is not None:
        return block
    return _fallback_cross_review_block(findings, twin, db, user_id)


async def _stream_llm(
    system_prompt: str, user_prompt: str, *, lite_mode: bool = False,
) -> AsyncIterator[str]:
    """流式调用 LLM。失败时一次性返回错误 fallback。

    lite_mode (2026-05-28): trivial query 走 lite path 时降 max_tokens 到 300.
        不换模型 → 不影响 voice, 只省尾部生成时长 (慢模型省 1-3s).
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    max_toks = _LITE_MAX_TOKENS if lite_mode else _FULL_MAX_TOKENS

    async def _try_stream(provider_type: Optional[str]):
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.factory import create_llm_provider, create_provider_for_user

            # 合成模型覆盖**不作用于 _stream_llm**(stream_orchestrator/web + Siri 流式共用
            # 此函数):安全评审指出全局覆盖会静默把 Siri 语音换到未在该面验证的模型。覆盖只
            # 限定在 _call_llm 的**深报告 mega 合成**(allow_synthesis_override=True 显式开)。
            if provider_type:
                provider = create_llm_provider(provider_type)
            else:
                pref = _user_pref_ctx.get()
                if pref is not None:
                    uid, _db = pref
                    provider = create_provider_for_user(uid, _db, task_tier=_task_tier_ctx.get())
                else:
                    provider = get_llm_provider()
            result = await provider.chat(
                messages=messages, temperature=0.3, max_tokens=max_toks, stream=True
            )
            if hasattr(result, "__aiter__"):
                async for chunk in result:
                    text = chunk if isinstance(chunk, str) else str(chunk)
                    if text:
                        yield text
                return
            # Provider 不支持流：一次性 yield
            if isinstance(result, dict):
                text = result.get("content") or ""
            else:
                text = str(result or "")
            if text:
                yield text
        except Exception as e:
            logger.warning(
                f"[orchestrator.stream] LLM provider={provider_type or 'default'} 失败: {str(e)[:200]}"
            )

    got_any = False
    async for chunk in _try_stream(None):
        got_any = True
        yield chunk

    if not got_any:
        async for chunk in _try_stream("openai"):
            got_any = True
            yield chunk

    if not got_any:
        yield "[AI 综合分析暂不可用（所有 LLM provider 都失败），请稍后重试。]"


# ───────────────────── 公开 API ────────────────────────


def _launch_shadow_parallel_synthesis(
    user_id: int,
    query: str,
    twin: HealthTwin,
    findings: List[SpecialistFinding],
    arb_block: str,
    *,
    task_tier: Optional[str] = None,
    mega_ms: Optional[int] = None,
) -> None:
    """rank11 shadow: 把并行分段合成丢后台跑, 落 audit。绝不阻塞/影响服务回合。

    mega-synthesis 已服务用户(调用方在 launch 前 await 完毕)。本 bg task 是纯旁路影子样本,
    供离线 pairwise judge。持 task 引用防 GC(与 G-W9 stream bg task 共用集合), 完成即清理。
    `mega_ms` = 本回合 mega synthesis 墙钟, 落进 shadow meta 让 pairwise 数据自洽(段落 wall
    vs mega wall 同一回合可比)。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("[orchestrator.shadow] 无运行中的事件循环, 跳过 shadow parallel synthesis")
        return
    task = loop.create_task(
        _shadow_parallel_synthesis_worker(
            user_id, query, twin, findings, arb_block, task_tier, mega_ms
        )
    )
    _BACKGROUND_STREAM_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_STREAM_TASKS.discard)


async def _shadow_parallel_synthesis_worker(
    user_id: int,
    query: str,
    twin: HealthTwin,
    findings: List[SpecialistFinding],
    arb_block: str,
    task_tier: Optional[str],
    mega_ms: Optional[int] = None,
) -> None:
    """rank11 shadow worker: fresh SessionLocal + 独立 provider 作用域, 落 audit。fail-soft。

    DB 会话纪律(镜像 rank8 in-process 模式): 用**独立 fresh SessionLocal**, 不复用请求 db
    (请求可能已在 shadow 完成前 close)。provider 作用域也切到 fresh db(override _user_pref_ctx),
    与请求生命周期完全解耦。任何异常/超时只落日志, 绝不影响已返回的服务回合。

    shadow meta 富化(供 pairwise judge 自洽读数):section_thinking(段落思考档)、
    cached_tokens_total(段落调用显式缓存命中真值,经隔离 usage capture 桶汇总)、
    mega_ms(同回合 mega 墙钟)。段落调用经 _section_synthesis_ctx 携带思考/缓存控制。
    """
    from app.database import SessionLocal
    from app.services.llm.usage_tracker import (
        begin_usage_capture,
        end_usage_capture,
        sum_captured_cached_tokens,
    )

    t_start = time.monotonic()
    shadow_db = SessionLocal()
    tok_pref = _user_pref_ctx.set((user_id, shadow_db))
    tok_tier = _task_tier_ctx.set(task_tier)
    _section_ctrl = _section_synthesis_controls()
    tok_section = _section_synthesis_ctx.set(_section_ctrl)
    # 隔离 usage capture 桶: gather 子任务按引用共享该 list 就地 append, gather 后本任务汇总。
    tok_cap = begin_usage_capture()
    try:
        text, meta = await parallel_synthesis.run_parallel_sectioned(
            call_llm=_call_llm, query=query, twin=twin,
            findings=findings, arb_block=arb_block,
        )
        # 与 mega 同一条出站护栏(加层不减层), 使影子样本与服务文本可比。
        text = _strip_llm_reva_ui(text)
        text = _safety_wrap(text, source="orchestrator.shadow_parallel").safe_text
        # GenUI-first (deep-report milestone-1): 确定性数据卡承载精确数值(零 LLM, R4), 段落只写
        # 定性结论。**必须在 _strip_llm_reva_ui 之后 prepend** —— 否则卡的 reva-ui fence 会被 R4
        # 剥除; 卡是结构化确定性数据, 不过 LLM free-text safety_wrap(与 table_builder 已服务的
        # 确定性卡片同纪律)。卡在前、段落在后 = 切 'on' 后服务的完整形态, 供 pairwise judge 看到
        # 卡里的数字。卡片纯增益, 生成失败 fail-soft(不拖垮 shadow 样本)。
        try:
            from app.orchestrator import report_cards
            _card_blocks = report_cards.build_report_cards(findings)
        except Exception as _card_err:  # noqa: BLE001 — 旁路增益, 失败绝不影响 shadow 落库
            _card_blocks = []
            logger.warning("[orchestrator.shadow] report_cards 生成失败 (旁路): %s", _card_err)
        if _card_blocks:
            cards_text = "\n\n".join(
                report_cards.render_metric_table_block(b) for b in _card_blocks
            )
            text = cards_text + "\n\n" + text
            meta["report_cards"] = len(_card_blocks)
            meta["report_card_labels"] = [b.get("title", "") for b in _card_blocks]
        meta["wall_ms"] = int((time.monotonic() - t_start) * 1000)
        meta["section_thinking"] = _section_ctrl.get("thinking")
        meta["cached_tokens_total"] = sum_captured_cached_tokens()
        meta["mega_ms"] = mega_ms
        from app.agents.audit import log_shadow_synthesis
        log_shadow_synthesis(shadow_db, user_id=user_id, query=query, text=text, meta=meta)
    except Exception as e:  # noqa: BLE001 — shadow 是旁路, 绝不影响服务回合
        logger.warning("[orchestrator.shadow] 并行分段 shadow 失败 (旁路, 不影响回合): %s", e)
        try:
            shadow_db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        end_usage_capture(tok_cap)
        _section_synthesis_ctx.reset(tok_section)
        _user_pref_ctx.reset(tok_pref)
        _task_tier_ctx.reset(tok_tier)
        shadow_db.close()


async def run_orchestrator(
    db: Session, user_id: int, req: OrchestratorRequest
) -> OrchestratorResponse:
    """非流式主入口。

    source=siri 走 fast 路径: 只跑 Twin + 口语化 LLM, 跳过所有 specialist /
    cross-review / arbitration / journal / card 持久化, 目标 3-5 秒内返回,
    避免 Siri extension 60 秒硬超时。"""
    if req.source == "siri":
        return await _run_orchestrator_fast(db, user_id, req)

    # GenUI 短路: caps=genui-v1 + 图表意图 → 确定性出 reva-ui block, 跳过 LLM 数据路径。
    genui = _maybe_build_genui_chart(db, user_id, req)
    if genui is not None:
        return genui

    from app.services.llm.usage_tracker import set_caller
    set_caller("orchestrator.synthesis", user_id=user_id)
    # 2026-05-13: set 用户偏好 ctx, _call_llm 内部读取.
    _user_pref_ctx.set((user_id, db))
    t_start = time.monotonic()
    perf: Dict[str, Any] = {
        "twin_wall_ms": 0,
        "kb_lookup_ms": 0,
        "kb_lookup_count": 0,
        "kb_lookup_reuse_count": 0,
        "kb_lookup_ok": True,
        "kb_claim_count": 0,
        "cross_review_ms": 0,
        "iqs_ms": 0,
    }

    t_twin = time.monotonic()
    twin = build_twin(db, user_id)
    perf["twin_wall_ms"] = int((time.monotonic() - t_twin) * 1000)
    t_intent = time.monotonic()
    intent = classify_intent(req.query)
    _task_tier_ctx.set(_tier_for_intent(intent))  # 成本路由(flag 默认关时无效)
    perf["intent_ms"] = int((time.monotonic() - t_intent) * 1000)
    specialists = _select_specialists(intent, twin, req.specialists)
    # lite_mode 仍以是否选中 specialist 为准,不能改成 findings 是否为空:
    # specialist 全失败时仍需保留存量 non-lite prompt/检索语义。
    lite_mode = not specialists
    perf["lite_mode"] = lite_mode
    # 注入 active case threads (STRATEGY 阶段 3): specialist 可读 context['recent_cases']
    # 了解用户有哪些"进行中的问题线"来决定是否开新 card / 避免重复.
    try:
        from app.services.clinical_journal_service import get_active_case_briefs
        recent_cases = get_active_case_briefs(db, user_id, limit=5)
    except Exception:
        recent_cases = []
    sp_timings: Dict[str, Any] = {}
    findings = _run_specialists(
        twin, specialists, {"query": req.query, "db": db, "recent_cases": recent_cases},
        timings=sp_timings,
    )
    perf["specialists"] = sp_timings
    kb_resolution = _resolve_turn_system_knowledge(
        db,
        twin,
        enabled=not lite_mode,
    )
    perf["kb_lookup_ms"] = kb_resolution.lookup_ms
    perf["kb_lookup_count"] = kb_resolution.lookup_count
    perf["kb_lookup_ok"] = kb_resolution.lookup_ok
    perf["kb_claim_count"] = kb_resolution.claim_count
    _attach_kb_evidence_to_findings(
        db,
        twin,
        findings,
        lookup_result=kb_resolution.lookup_result,
    )
    perf["kb_lookup_reuse_count"] = _count_avoided_kb_lookups(
        findings,
        kb_resolution,
    )
    findings, evidence_policy_trace = _apply_planner_evidence_policy(findings)

    # Cross-review + (可选) LLM 仲裁, 结果注入 synthesis prompt
    t_cross_review = time.monotonic()
    conflict_arb_block = await _resolve_cross_review_block(findings, twin, db, user_id)
    perf["cross_review_ms"] = int((time.monotonic() - t_cross_review) * 1000)

    # IQS 实时检索 grounding — 非 lite / 非 siri 才取 (flag 关或失败则空, 不阻断)
    realtime_evidence_block = ""
    if not lite_mode and req.source != "siri":
        from app.services.iqs_search import fetch_realtime_evidence
        t_iqs = time.monotonic()
        realtime_evidence_block = await fetch_realtime_evidence(req.query)
        perf["iqs_ms"] = int((time.monotonic() - t_iqs) * 1000)

    system_prompt, user_prompt = _build_synthesis_prompt(
        req.query, twin, findings, db=db, user_id=user_id,
        conflict_arb_block=conflict_arb_block,
        realtime_evidence_block=realtime_evidence_block,
        system_kb_text=kb_resolution.prompt_text,
        source=req.source,
        lite_mode=lite_mode,
    )

    # 注入对话记忆（用户历史偏好/医嘱/过敏等）
    user_prompt, memory_trace = _inject_memory(
        db, user_id, user_prompt, findings=findings, lite_mode=lite_mode,
    )

    # rank11 分段合成: flag 归一 + 报告形 gate。off / 非报告形 → mega-synthesis 逐字节不变。
    _synth_mode = parallel_synthesis.resolve_mode(
        getattr(settings, "orchestrator_parallel_synthesis", "off")
    )
    _sectioned_ok = _synth_mode != "off" and parallel_synthesis.report_shaped(
        lite_mode, findings, req.source
    )

    t_llm = time.monotonic()
    if _synth_mode == "on" and _sectioned_ok:
        # 'on': 并行分段结果直接服务用户。全段失败(空产出)→ fail-closed 回落 mega。
        # ctx 只包住段落 gather —— 回落 mega(下方)在 finally 复位之后,恒不带段落控制。
        _sec_tok = _section_synthesis_ctx.set(_section_synthesis_controls())
        try:
            synthesis, _sec_meta = await parallel_synthesis.run_parallel_sectioned(
                call_llm=_call_llm, query=req.query, twin=twin,
                findings=findings, arb_block=conflict_arb_block,
            )
        finally:
            _section_synthesis_ctx.reset(_sec_tok)
        perf["parallel_synthesis"] = _sec_meta
        if not (synthesis or "").strip():
            logger.warning("[orchestrator] parallel synthesis 空产出, 回落 mega-synthesis")
            synthesis = await _call_llm(
                system_prompt, user_prompt, lite_mode=lite_mode,
                allow_synthesis_override=True,
            )
            perf["parallel_synthesis_fallback"] = "empty_sections"
    else:
        synthesis = await _call_llm(
            system_prompt, user_prompt, lite_mode=lite_mode,
            allow_synthesis_override=True,
        )
    perf["llm_full_ms"] = int((time.monotonic() - t_llm) * 1000)
    synthesis = _strip_llm_reva_ui(synthesis)  # R4 护栏: 剥 LLM 伪造图表 block

    # v3 cross-cutting safety: 所有 LLM 终态自由文本统一过 validator。
    # 分段('on')与 mega 走**同一条** _safety_wrap, 套在拼接整体上(加层不减层):
    # 任一段落越界 → 整篇同样被句级遮蔽 + disclaimer。
    safety = _safety_wrap(synthesis, source="orchestrator.run")
    synthesis = safety.safe_text

    # 'shadow': mega 已服务用户(上方)。并行分段丢后台 bg task 跑, 落 audit 供离线 pairwise
    # judge; fresh SessionLocal, 失败/超时 fail-soft 绝不影响本回合。
    if _synth_mode == "shadow" and _sectioned_ok:
        _launch_shadow_parallel_synthesis(
            user_id, req.query, twin, list(findings), conflict_arb_block,
            task_tier=_task_tier_ctx.get(),
            mega_ms=perf.get("llm_full_ms"),
        )

    # 旁路观测: KB 证据引用率 —— 提供给 LLM 的 claim 里有多少在终稿里显现 (cheap substring).
    # 失败绝不影响主流程。
    try:
        from app.services.system_knowledge_service import record_kb_citation_usage
        record_kb_citation_usage(
            db,
            _collect_evidence_claim_ids(findings),
            synthesis,
            source="orchestrator.run",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] kb_citation_usage audit bypass 失败: {e}")

    # 信任循环: 把 specialist 的 proposed_cards 落地为 ActionCard
    persisted_card_ids = _persist_proposed_cards(db, user_id, findings)

    # Clinical Journal: 旁路写一条 SOAP entry (失败不阻塞主流程)
    try:
        from app.services.clinical_journal_service import write_soap_entry
        write_soap_entry(
            db, user_id=user_id, query=req.query, twin=twin,
            findings=findings, persisted_card_ids=persisted_card_ids,
            created_by="orchestrator",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] write_soap_entry 失败 (旁路): {e}")

    # Memory Extractor: specialist findings → 个人知识库 facts (旁路)
    try:
        from app.services.memory_extractor import extract_from_specialist_finding
        for f in findings:
            extract_from_specialist_finding(db, user_id, f, f.specialist_name)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] memory extract 失败 (旁路): {e}")

    # 旁路审计: 支持 /reasoning-trace/specialist/{audit_id} 反查单 finding
    try:
        from app.agents.audit import log_specialist_findings
        log_specialist_findings(
            db,
            user_id=user_id,
            findings=_specialist_audit_snapshot(findings),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] specialist_findings audit bypass 失败: {e}")

    total_ms = int((time.monotonic() - t_start) * 1000)
    perf["twin_build_ms"] = twin.meta.build_ms
    perf["total_ms"] = total_ms
    logger.info(
        f"[perf.orchestrator] user={user_id} mode=nonstream total={total_ms}ms "
        f"twin={twin.meta.build_ms}ms twin_wall={perf['twin_wall_ms']}ms "
        f"intent={perf['intent_ms']}ms "
        f"sp_wall={sp_timings.get('parallel_wall_ms', 0)}ms "
        f"recovery={sp_timings.get('recovery_ms', 0)}ms "
        f"kb={perf['kb_lookup_ms']}ms kb_calls={perf['kb_lookup_count']} "
        f"kb_reuse={perf['kb_lookup_reuse_count']} "
        f"cross_review={perf['cross_review_ms']}ms iqs={perf['iqs_ms']}ms "
        f"llm_full={perf['llm_full_ms']}ms "
        f"sp_count={len(specialists)} sp_failed={len(sp_timings.get('failed', []))} "
        f"lite={lite_mode}"
    )

    # Phase 0.3 (2026-05-04): non-stream 路径之前完全没写 orchestrator audit,
    # 历史 silent gap. 现在补齐, 与 stream / siri 路径对齐, 同时带 memory_trace
    # + output_text 给 memory 引用率看板.
    try:
        from app.agents.audit import log_orchestrator_run
        log_orchestrator_run(
            db=db, user_id=user_id,
            query=req.query,
            intent_categories=intent.categories,
            used_specialists=[s.name for s in specialists],
            findings_count=sum(len(f.findings) for f in findings),
            twin_build_ms=twin.meta.build_ms,
            total_ms=total_ms,
            result_summary=(synthesis or "")[:200],
            source=req.source,
            memory_trace=memory_trace,
            output_text=synthesis,
            perf_breakdown=perf,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] orchestrator_run audit bypass 失败: {e}")

    if evidence_policy_trace.get("blocked_count"):
        logger.info(
            "[orchestrator] planner evidence policy blocked %s unsupported findings",
            evidence_policy_trace["blocked_count"],
        )

    return OrchestratorResponse(
        query=req.query,
        intent=intent,
        findings=findings,
        synthesis=synthesis,
        used_specialists=[s.name for s in specialists],
        twin_build_ms=twin.meta.build_ms,
        total_ms=int((time.monotonic() - t_start) * 1000),
        persisted_card_ids=persisted_card_ids,
        safety_disclaimer=safety.disclaimer or None,
        safety_action=safety.action,
    )


async def _run_orchestrator_fast(
    db: Session, user_id: int, req: OrchestratorRequest
) -> OrchestratorResponse:
    """Siri 专用极简路径: Twin + 口语化 LLM, 跳过 specialist/arbitration/journal.

    设计取舍:
    - Twin 构建 (Redis 缓存 5min, 命中时毫秒级; miss 1-3 秒) → 保留, 因为 LLM
      需要基本数据快照, 否则回答是空话.
    - Specialists 单次 30-60 秒 (10 个专家串并行) → 跳过. Siri 场景承担不起.
    - Cross-review + LLM 仲裁 → 跳过. 没有 specialist 输出, 无事可做.
    - ClinicalJournal SOAP 写入 → 跳过. 语音场景不生成长期记录.
    - ActionCard 持久化 → 跳过. 语音不产出 card.
    - Intent 分类保留 (几乎免费, 后端审计要用).

    审计仍然写, source='siri' 能在分析看板看到这条入口数据.
    """
    from app.services.llm.usage_tracker import set_caller
    set_caller("orchestrator.synthesis.siri_fast", user_id=user_id)
    t_start = time.monotonic()

    twin = build_twin(db, user_id)
    intent = classify_intent(req.query)

    # 直接走口语化 synthesis, findings 传空 list —— prompt builder 会退化为
    # "基于 twin 快照 + 用户原始问题" 的极简回答. lite_mode=True 跳过所有 DB-heavy block.
    system_prompt, user_prompt = _build_synthesis_prompt(
        req.query, twin, findings=[], db=db, user_id=user_id,
        conflict_arb_block="", source="siri",
        lite_mode=True,
    )

    # 注入 conversation memory (用户历史偏好/医嘱/过敏), 保留连续对话感.
    user_prompt, memory_trace = _inject_memory(
        db, user_id, user_prompt, findings=[], lite_mode=True,
    )

    synthesis = await _call_llm(system_prompt, user_prompt, lite_mode=True)
    synthesis = _strip_llm_reva_ui(synthesis)  # R4 护栏: 剥 LLM 伪造图表 block

    # v3 cross-cutting safety: Siri 路径同样过 validator
    safety = _safety_wrap(synthesis, source="orchestrator.siri_fast")
    synthesis = safety.safe_text

    # 审计 (旁路, 失败不阻塞返回)
    try:
        from app.agents.audit import log_orchestrator_run
        log_orchestrator_run(
            db=db, user_id=user_id,
            query=req.query,
            intent_categories=intent.categories,
            used_specialists=[],
            findings_count=0,
            twin_build_ms=twin.meta.build_ms,
            total_ms=int((time.monotonic() - t_start) * 1000),
            result_summary=synthesis[:200],
            source=req.source,
            memory_trace=memory_trace,
            output_text=synthesis,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator.siri_fast] audit 失败: {e}")

    return OrchestratorResponse(
        query=req.query,
        intent=intent,
        findings=[],
        synthesis=synthesis,
        used_specialists=[],
        twin_build_ms=twin.meta.build_ms,
        total_ms=int((time.monotonic() - t_start) * 1000),
        safety_disclaimer=safety.disclaimer or None,
        safety_action=safety.action,
    )


async def _stream_orchestrator_fast(
    db: Session, user_id: int, req: OrchestratorRequest
):
    """Siri 专用流式快版本: yield SSE chunk 让 voice-chat 边收边念。

    跳过和 _run_orchestrator_fast 相同的所有重负载, 只额外把 LLM 调用从
    一次性 _call_llm 换成 _stream_llm, 让 client 第一个字 1-2s 内就能听到。

    G-W9: bg task + queue 模式 — 客户端断开不影响 audit 落库.
    """
    from app.services.llm.usage_tracker import set_caller
    set_caller("orchestrator.stream.siri_fast", user_id=user_id)

    t_start = time.monotonic()

    def _sse(event: str, data) -> str:
        payload = data if isinstance(data, str) else json.dumps(data, default=str, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n"

    chunk_queue: asyncio.Queue = asyncio.Queue()

    async def _background_task():
        from app.database import SessionLocal as _SessionLocal
        bg_db = _SessionLocal()
        try:
            twin = build_twin(bg_db, user_id)
            intent = classify_intent(req.query)

            system_prompt, user_prompt = _build_synthesis_prompt(
                req.query, twin, findings=[], db=bg_db, user_id=user_id,
                conflict_arb_block="", source="siri",
                lite_mode=True,
            )
            user_prompt, memory_trace = _inject_memory(
                bg_db, user_id, user_prompt, findings=[], lite_mode=True,
            )

            full = ""
            try:
                async for chunk in _stream_llm(system_prompt, user_prompt, lite_mode=True):
                    full += chunk
                    await chunk_queue.put(_sse("chunk", chunk))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[orchestrator.stream.siri_fast] LLM stream 失败: {e}")

            full = _strip_llm_reva_ui(full)  # R4 护栏: 剥 LLM 伪造图表 block (audit 前)

            safety = _safety_wrap(full, source="orchestrator.siri_fast.stream")
            total_ms = int((time.monotonic() - t_start) * 1000)

            await chunk_queue.put(_sse("done", {
                "total_ms": total_ms,
                "synthesis_len": len(full),
                "safety_action": safety.action,
            }))
            if safety.action == "replace":
                await chunk_queue.put(_sse("safety_override", {"safe_text": safety.safe_text}))
            elif safety.action == "append_disclaimer":
                await chunk_queue.put(_sse("safety_disclaimer", {"disclaimer": safety.disclaimer}))

            try:
                from app.agents.audit import log_orchestrator_run
                log_orchestrator_run(
                    db=bg_db, user_id=user_id,
                    query=req.query,
                    intent_categories=intent.categories,
                    used_specialists=[],
                    findings_count=0,
                    twin_build_ms=twin.meta.build_ms,
                    total_ms=total_ms,
                    result_summary=full[:200],
                    source="siri",
                    memory_trace=memory_trace,
                    output_text=full,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[orchestrator.stream.siri_fast] audit 失败: {e}")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[orchestrator.stream.siri_fast] bg 失败: {e}")
            try:
                await chunk_queue.put(_sse("error", {"message": "分析服务暂时不可用，请稍后再试"}))
            except Exception:
                pass
        finally:
            await chunk_queue.put(None)
            try:
                bg_db.close()
            except Exception:
                pass

    bg_task = asyncio.create_task(_background_task())
    _BACKGROUND_STREAM_TASKS.add(bg_task)
    bg_task.add_done_callback(_BACKGROUND_STREAM_TASKS.discard)

    try:
        while True:
            event = await chunk_queue.get()
            if event is None:
                break
            yield event
    except (asyncio.CancelledError, GeneratorExit):
        logger.info(
            "[orchestrator.stream.siri_fast] client disconnected, "
            "bg task continues to finish audit"
        )
        raise


async def stream_orchestrator(
    db: Session, user_id: int, req: OrchestratorRequest
) -> AsyncIterator[str]:
    """
    流式主入口。按 SSE 协议 yield 字符串。

    事件类型：
    - intent:      路由决定
    - specialist:  每个专家的结构化输出
    - chunk:       LLM 合并结果的流式文本片段
    - done:        结束信号，带 total_ms

    source=siri: 走 fast 流式路径 (Twin + 直接 LLM stream chunk),
    跳过 specialist/cross-review/arbitration/journal/cards, 目标 1-2s 内
    第一个 chunk 出来, 让 voice-chat 流式 TTS 立刻有内容念。

    G-W9: bg task + asyncio.Queue 模式. 客户端断开后 specialist /
    persist_cards / SOAP / memory_extract / LLM synthesis / audit 继续
    跑完, 不丢数据. 外层 generator 只从 queue 转发 SSE event.
    """
    if req.source == "siri":
        async for chunk in _stream_orchestrator_fast(db, user_id, req):
            yield chunk
        return

    def _sse(event: str, data) -> str:
        payload = data if isinstance(data, str) else json.dumps(data, default=str, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n"

    # GenUI 短路: caps=genui-v1 + 图表意图 → 确定性出 reva-ui block, 跳过 specialist/LLM。
    # 整段 synthesis (含 ```reva-ui block) 作为单个 chunk 推出, 客户端按现状渲染。
    genui = _maybe_build_genui_chart(db, user_id, req)
    if genui is not None:
        yield _sse("intent", {
            "categories": genui.intent.categories,
            "keywords": genui.intent.keywords,
            "used_specialists": [],
            "twin_build_ms": 0,
        })
        yield _sse("chunk", genui.synthesis)
        yield _sse("done", {"total_ms": 0, "genui": True})
        return

    from app.services.llm.usage_tracker import set_caller
    set_caller("orchestrator.stream", user_id=user_id)
    # 2026-05-13: 用户偏好 ctx
    _user_pref_ctx.set((user_id, db))

    t_start = time.monotonic()

    chunk_queue: asyncio.Queue = asyncio.Queue()

    async def _background_task():
        from app.database import SessionLocal as _SessionLocal
        bg_db = _SessionLocal()
        try:
            try:
                # perf 2026-05-28: 分阶段计时, 用于 done SSE + audit + 单行 grep 日志
                perf: Dict[str, Any] = {
                    "twin_wall_ms": 0,
                    "kb_lookup_ms": 0,
                    "kb_lookup_count": 0,
                    "kb_lookup_reuse_count": 0,
                    "kb_lookup_ok": True,
                    "kb_claim_count": 0,
                    "cross_review_ms": 0,
                    "iqs_ms": 0,
                }
                t_twin = time.monotonic()
                twin = build_twin(bg_db, user_id)
                perf["twin_wall_ms"] = int((time.monotonic() - t_twin) * 1000)
                t_intent = time.monotonic()
                intent = classify_intent(req.query)
                _task_tier_ctx.set(_tier_for_intent(intent))  # 成本路由(flag 默认关时无效)
                perf["intent_ms"] = int((time.monotonic() - t_intent) * 1000)
                specialists = _select_specialists(intent, twin, req.specialists)
                lite_mode = not specialists
                perf["lite_mode"] = lite_mode
                try:
                    from app.services.clinical_journal_service import get_active_case_briefs
                    recent_cases = get_active_case_briefs(bg_db, user_id, limit=5)
                except Exception:
                    recent_cases = []

                await chunk_queue.put(_sse(
                    "intent",
                    {
                        "categories": intent.categories,
                        "keywords": intent.keywords,
                        "used_specialists": [s.name for s in specialists],
                        "twin_build_ms": twin.meta.build_ms,
                    },
                ))

                sp_timings: Dict[str, Any] = {}
                findings = _run_specialists(
                    twin, specialists,
                    {"query": req.query, "db": bg_db, "recent_cases": recent_cases},
                    timings=sp_timings,
                )
                perf["specialists"] = sp_timings
                kb_resolution = _resolve_turn_system_knowledge(
                    bg_db,
                    twin,
                    enabled=not lite_mode,
                )
                perf["kb_lookup_ms"] = kb_resolution.lookup_ms
                perf["kb_lookup_count"] = kb_resolution.lookup_count
                perf["kb_lookup_ok"] = kb_resolution.lookup_ok
                perf["kb_claim_count"] = kb_resolution.claim_count
                _attach_kb_evidence_to_findings(
                    bg_db,
                    twin,
                    findings,
                    lookup_result=kb_resolution.lookup_result,
                )
                perf["kb_lookup_reuse_count"] = _count_avoided_kb_lookups(
                    findings,
                    kb_resolution,
                )
                findings, evidence_policy_trace = _apply_planner_evidence_policy(findings)
                if evidence_policy_trace.get("blocked_count"):
                    await chunk_queue.put(_sse(
                        "planner_evidence_policy",
                        evidence_policy_trace,
                    ))
                for f in findings:
                    await chunk_queue.put(_sse("specialist", f.model_dump(mode="json")))

                persisted_ids = _persist_proposed_cards(bg_db, user_id, findings)
                if persisted_ids:
                    await chunk_queue.put(_sse("action_cards_created", {"ids": persisted_ids}))

                try:
                    from app.services.clinical_journal_service import write_soap_entry
                    write_soap_entry(
                        bg_db, user_id=user_id, query=req.query, twin=twin,
                        findings=findings, persisted_card_ids=persisted_ids,
                        created_by="orchestrator",
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[orchestrator.stream] write_soap_entry 失败: {e}")

                try:
                    from app.services.memory_extractor import extract_from_specialist_finding
                    for f in findings:
                        extract_from_specialist_finding(bg_db, user_id, f, f.specialist_name)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[orchestrator.stream] memory extract 失败: {e}")

                t_cross_review = time.monotonic()
                conflict_arb_block = await _resolve_cross_review_block(
                    findings, twin, bg_db, user_id
                )
                perf["cross_review_ms"] = int(
                    (time.monotonic() - t_cross_review) * 1000
                )

                try:
                    from app.agents.audit import log_specialist_findings
                    log_specialist_findings(
                        bg_db,
                        user_id=user_id,
                        findings=_specialist_audit_snapshot(findings),
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[orchestrator.stream] specialist_findings audit bypass 失败: {e}")

                # IQS 实时检索 grounding (与 run_orchestrator 对齐, flag 关/失败则空, 不阻断流)
                realtime_evidence_block = ""
                if not lite_mode and req.source != "siri":
                    from app.services.iqs_search import fetch_realtime_evidence
                    t_iqs = time.monotonic()
                    realtime_evidence_block = await fetch_realtime_evidence(req.query)
                    perf["iqs_ms"] = int((time.monotonic() - t_iqs) * 1000)

                system_prompt, user_prompt = _build_synthesis_prompt(
                    req.query, twin, findings, db=bg_db, user_id=user_id,
                    conflict_arb_block=conflict_arb_block,
                    realtime_evidence_block=realtime_evidence_block,
                    system_kb_text=kb_resolution.prompt_text,
                    source=req.source,
                    lite_mode=lite_mode,
                )
                user_prompt, memory_trace = _inject_memory(
                    bg_db, user_id, user_prompt, findings=findings, lite_mode=lite_mode,
                )

                full = ""
                t_llm = time.monotonic()
                llm_ttft_ms: Optional[int] = None
                try:
                    async for chunk in _stream_llm(
                        system_prompt, user_prompt, lite_mode=lite_mode,
                    ):
                        if llm_ttft_ms is None and chunk:
                            llm_ttft_ms = int((time.monotonic() - t_llm) * 1000)
                        full += chunk
                        await chunk_queue.put(_sse("chunk", chunk))
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[orchestrator.stream] LLM stream 失败: {e}")
                perf["llm_ttft_ms"] = llm_ttft_ms
                perf["llm_full_ms"] = int((time.monotonic() - t_llm) * 1000)

                full = _strip_llm_reva_ui(full)  # R4 护栏: 剥 LLM 伪造图表 block (audit 前)

                safety = _safety_wrap(full, source="orchestrator.stream")
                total_ms = int((time.monotonic() - t_start) * 1000)
                perf["twin_build_ms"] = twin.meta.build_ms
                perf["total_ms"] = total_ms

                # 单行 grep 日志, 在生产 journalctl 上方便 `grep '\[perf\.orchestrator\]'`
                logger.info(
                    f"[perf.orchestrator] user={user_id} total={total_ms}ms "
                    f"twin={twin.meta.build_ms}ms twin_wall={perf['twin_wall_ms']}ms "
                    f"intent={perf['intent_ms']}ms "
                    f"sp_wall={sp_timings.get('parallel_wall_ms', 0)}ms "
                    f"recovery={sp_timings.get('recovery_ms', 0)}ms "
                    f"kb={perf['kb_lookup_ms']}ms kb_calls={perf['kb_lookup_count']} "
                    f"kb_reuse={perf['kb_lookup_reuse_count']} "
                    f"cross_review={perf['cross_review_ms']}ms iqs={perf['iqs_ms']}ms "
                    f"llm_ttft={llm_ttft_ms}ms llm_full={perf['llm_full_ms']}ms "
                    f"sp_count={len(specialists)} sp_failed={len(sp_timings.get('failed', []))} "
                    f"lite={lite_mode}"
                )

                try:
                    from app.agents.audit import log_orchestrator_run
                    log_orchestrator_run(
                        db=bg_db,
                        user_id=user_id,
                        query=req.query,
                        intent_categories=intent.categories,
                        used_specialists=[s.name for s in specialists],
                        findings_count=sum(len(f.findings) for f in findings),
                        twin_build_ms=twin.meta.build_ms,
                        total_ms=total_ms,
                        result_summary=full[:200],
                        source=req.source,
                        memory_trace=memory_trace,
                        output_text=full,
                        perf_breakdown=perf,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[orchestrator.stream] orchestrator_run audit bypass 失败: {e}")

                try:
                    from app.services.system_knowledge_service import record_kb_citation_usage
                    record_kb_citation_usage(
                        bg_db,
                        _collect_evidence_claim_ids(findings),
                        full,
                        source="orchestrator.stream",
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[orchestrator.stream] kb_citation_usage audit bypass 失败: {e}")

                await chunk_queue.put(_sse("done", {
                    "total_ms": total_ms,
                    "persisted_card_ids": persisted_ids,
                    "safety_action": safety.action,
                    "perf": perf,
                }))
                if safety.action == "replace":
                    await chunk_queue.put(_sse("safety_override", {"safe_text": safety.safe_text}))
                elif safety.action == "append_disclaimer":
                    await chunk_queue.put(_sse("safety_disclaimer", {"disclaimer": safety.disclaimer}))
            except Exception as e:  # noqa: BLE001
                logger.exception("[orchestrator.stream] 未捕获异常")
                try:
                    await chunk_queue.put(_sse("error", {"message": safe_llm_error_message(e)}))
                except Exception:
                    pass
        finally:
            await chunk_queue.put(None)
            try:
                bg_db.close()
            except Exception:
                pass

    bg_task = asyncio.create_task(_background_task())
    _BACKGROUND_STREAM_TASKS.add(bg_task)
    bg_task.add_done_callback(_BACKGROUND_STREAM_TASKS.discard)

    try:
        while True:
            event = await chunk_queue.get()
            if event is None:
                break
            yield event
    except (asyncio.CancelledError, GeneratorExit):
        logger.info(
            "[orchestrator.stream] client disconnected, "
            "bg task continues to finish audit / journal / memory"
        )
        raise
