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
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

from sqlalchemy.orm import Session

from app.orchestrator.intent import classify_intent
from app.orchestrator.schema import (
    Intent,
    OrchestratorRequest,
    OrchestratorResponse,
    SpecialistFinding,
)
from app.orchestrator.specialists import all_specialists, get_specialist
from app.twin.builder import build_twin
from app.twin.formatter import twin_to_prompt_blob
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# ───────────────────── 专家调度 ────────────────────────


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

    return [s for s in all_specialists() if s.applies_to(intent, twin)]


def _run_specialists(
    twin: HealthTwin, specialists: List, context: Dict
) -> List[SpecialistFinding]:
    """
    并行调用 specialist，收集结构化 finding。

    依赖关系: Recovery Coach 把 readiness_zone 写入 context，Movement Coach 读取。
    策略: Recovery Coach 先同步执行 → 其余 specialist 并发执行。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ctx = dict(context)  # 不污染调用方
    findings: List[SpecialistFinding] = []

    # ---- Phase 1: 先跑 recovery_coach（如果在列表中）----
    recovery_sp = None
    rest_specialists = []
    for sp in specialists:
        if sp.name == "recovery_coach":
            recovery_sp = sp
        else:
            rest_specialists.append(sp)

    if recovery_sp:
        try:
            finding = recovery_sp.run(twin, ctx)
            findings.append(finding)
            zone = (finding.raw or {}).get("zone")
            if zone:
                ctx["readiness_zone"] = zone
                ctx["readiness_score"] = (finding.raw or {}).get("score")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[orchestrator] specialist {recovery_sp.name} 失败: {e}")

    # ---- Phase 2: 其余 specialist 并发执行 ----
    if not rest_specialists:
        return findings

    def _run_one(sp):
        try:
            return sp, sp.run(twin, ctx)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[orchestrator] specialist {sp.name} 失败: {e}")
            return sp, None

    # 最多开 4 个线程（specialist 都是 CPU-bound 计算 + 少量 IO）
    max_workers = min(len(rest_specialists), 4)
    ordered_findings = [None] * len(rest_specialists)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_run_one, sp): idx
            for idx, sp in enumerate(rest_specialists)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            sp, finding = future.result()
            if finding:
                ordered_findings[idx] = finding

    # 保持原始注册顺序
    findings.extend(f for f in ordered_findings if f is not None)
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
        from sqlalchemy import func, Integer
        from datetime import datetime, timezone, timedelta as _td
        from app.models.action_card import ActionCard

        since = datetime.now(timezone.utc) - _td(days=days)
        rows = db.query(
            ActionCard.creator_specialist,
            func.count(ActionCard.id).label("total"),
            func.avg(ActionCard.accuracy_score).label("avg_score"),
            func.sum((ActionCard.accuracy_score >= 70).cast(Integer)).label("hits"),
        ).filter(
            ActionCard.user_id == user_id,
            ActionCard.graded_at.isnot(None),
            ActionCard.graded_at >= since,
            ActionCard.creator_specialist.isnot(None),
        ).group_by(ActionCard.creator_specialist).all()

        if not rows:
            return ""
        parts = []
        for r in rows:
            total = int(r.total)
            hits = int(r.hits or 0)
            rate = (hits / total * 100) if total else 0
            parts.append(f"{r.creator_specialist}={rate:.0f}% ({hits}/{total}, avg {float(r.avg_score or 0):.0f})")
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
            highs = base_q.filter(ActionCard.accuracy_score >= 70)\
                .order_by(ActionCard.accuracy_score.desc()).limit(top_n).all()
            lows = base_q.filter(ActionCard.accuracy_score <= 30)\
                .order_by(ActionCard.accuracy_score.asc()).limit(top_n).all()
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


def _build_synthesis_prompt(
    query: str, twin: HealthTwin, findings: List[SpecialistFinding],
    db: Optional[Session] = None, user_id: Optional[int] = None,
    conflict_arb_block: str = "",
) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt).

    conflict_arb_block: 由调用方预先渲染的 cross_review + LLM 仲裁 markdown.
    如果为空, 保留向下兼容: 内部跑一次 cross_review (无 LLM 仲裁).
    """

    twin_blob = twin_to_prompt_blob(twin)

    findings_text_parts: List[str] = []
    for f in findings:
        findings_text_parts.append(f"【{f.specialist_name}】{f.summary}")
        for idx, item in enumerate(f.findings, 1):
            if isinstance(item, dict):
                sev = item.get("severity_label", "")
                title = item.get("title", "")
                action = item.get("action") or ""
                line = f"  {idx}. [{sev}] {title}"
                if action:
                    line += f" → {action}"
                findings_text_parts.append(line)
    findings_text = "\n".join(findings_text_parts) or "(无 specialist 输出)"

    # 信任循环反馈: 把过去 30 天的 specialist 命中率注入 prompt
    credit_text = ""
    track_text = ""
    if db is not None and user_id is not None:
        credit_text = _build_specialist_credit_block(db, user_id, days=30)
        # 本次 run 的 specialist 名单, 只拉它们的历史 — 避免 prompt 膨胀
        active_sp_names = [f.specialist_name for f in findings if f.specialist_name]
        track_text = _build_per_specialist_track_block(
            db, user_id, active_sp_names, days=90, top_n=2,
        )

    # Trust Loop v2: 用户对过去判断的显式反馈 (not_helpful / irrelevant)
    # 让 LLM 看到"用户否定过的判断", 避免重复类似错误
    user_feedback_text = ""
    if db is not None and user_id is not None:
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
    conflicts_text = conflict_arb_block
    if not conflicts_text:
        try:
            from app.orchestrator.cross_review import detect_conflicts, render_conflicts_for_prompt
            conflicts = detect_conflicts(findings, twin, db=db)
            if conflicts:
                conflicts_text = render_conflicts_for_prompt(conflicts)
                logger.info(f"[orchestrator] cross_review 检测到 {len(conflicts)} 个 specialist 冲突 (fallback)")
                try:
                    from app.agents.audit import log_cross_review_conflicts
                    log_cross_review_conflicts(
                        db, user_id=user_id or twin.meta.user_id,
                        conflicts=[{
                            "specialist_a": c.specialist_a,
                            "specialist_b": c.specialist_b,
                            "severity": c.severity,
                            "description": c.description,
                            "resolution_hint": c.resolution_hint,
                        } for c in conflicts],
                        used_specialists=[f.specialist_name for f in findings],
                    )
                except Exception as e_audit:  # noqa: BLE001
                    logger.debug(f"[orchestrator] cross_review audit 失败: {e_audit}")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[orchestrator] cross_review 跳过: {e}")

    system_prompt = (
        "你是健康助理的首席分析师。下游 specialist agent 已经对用户的 Digital Health Twin 做了结构化裁决，"
        "你的任务是：\n"
        "1. 理解用户的原始问题\n"
        "2. 把各个 specialist 的发现合成一个中文自然语言回答\n"
        "3. 严重度高的优先说，轻的收尾\n"
        "4. 数字和规则名不要凭空捏造，只用 specialist 给你的事实\n"
        "5. 给出 2-4 个具体的下一步行动（时间/频率/剂量要具体）\n"
        "6. 涉及药物/剂量调整时，明确说需要和医生确认\n"
        "7. 不超过 500 字，简洁有力，避免废话\n"
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
    )

    user_prompt_parts = [
        f"【用户原始问题】\n{query}",
        f"【用户当前健康快照】\n{twin_blob or '(数据暂缺)'}",
    ]
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


def _inject_memory(db: Session, user_id: int, user_prompt: str,
                    findings: Optional[List[SpecialistFinding]] = None) -> str:
    """注入用户对话记忆 + Clinical Journal 相关 case timeline."""
    out = user_prompt

    # 1) 通用对话记忆 (过敏/医嘱/偏好)
    try:
        from app.services.conversation_memory_service import get_relevant_memories
        memories = get_relevant_memories(db, user_id, limit=5)
        if memories:
            out += f"\n\n【用户历史偏好/记忆】\n{memories}\n"
    except Exception:
        pass

    # 2) Clinical Journal case timeline (本次 finding 相关的 metric 历史)
    metric_key = None
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
                    out += (f"\n\n【相关 case 历史 — agent 应基于此连贯回应】\n"
                           f"{history}\n")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] case timeline 注入失败 (跳过): {e}")

    # 3) User Directives — 医生 / 用户硬性指令 (specialist 必须遵循)
    try:
        from app.services.directive_parser import get_active_directives_for_prompt
        directives_md = get_active_directives_for_prompt(db, user_id, metric_key=metric_key)
        if directives_md:
            out += f"\n\n{directives_md}\n"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] directive 注入失败 (跳过): {e}")

    # 4) Hybrid Retrieval (BM25 + Graph + RRF) — LLM Wiki v2 阶段 C
    # 一路替换原来的 facts + KG 双路注入. 检索结果按 RRF 融合排序.
    try:
        from app.services.hybrid_search import hybrid_retrieve, render_hits_for_prompt
        # query seed: 取 user_prompt 前 300 字 (含 query + twin_blob 开头)
        query_seed = (user_prompt or "")[:300]
        hits = hybrid_retrieve(db, user_id, query_seed, top_k=10)
        if hits:
            out += f"\n\n{render_hits_for_prompt(hits, max_lines=10)}\n"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] hybrid retrieval 注入失败 (跳过): {e}")

    return out


# ───────────────────── LLM 调用（带回退） ─────────────────


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用 LLM，失败时尝试 openclaw fallback。返回空字符串表示失败。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async def _try(provider_type: Optional[str]) -> Optional[str]:
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.factory import create_llm_provider

            provider = create_llm_provider(provider_type) if provider_type else get_llm_provider()
            result = await provider.chat(
                messages=messages, temperature=0.3, max_tokens=900
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
        text = await _try("openclaw")
    return text or ""


async def _run_cross_review_and_arbitration(
    findings: List[SpecialistFinding],
    twin: HealthTwin,
    db: Optional[Session],
    user_id: Optional[int],
) -> str:
    """检测 cross_review 冲突 → 达到门槛就 LLM 仲裁. 返回要注入 synthesis prompt 的渲染文本.

    - 有冲突 + 达到 LLM 触发门槛 (hard 或 >=2): await arbitrate_conflicts; 写 audit
    - 有冲突但未到门槛: 仅渲染 cross_review (规则层), 写 cross_review audit
    - 无冲突: 返回空串
    """
    try:
        from app.orchestrator.cross_review import detect_conflicts, render_conflicts_for_prompt
        conflicts = detect_conflicts(findings, twin, db=db)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] cross_review 跳过: {e}")
        return ""

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


async def _stream_llm(
    system_prompt: str, user_prompt: str
) -> AsyncIterator[str]:
    """流式调用 LLM。失败时一次性返回错误 fallback。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async def _try_stream(provider_type: Optional[str]):
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.factory import create_llm_provider

            provider = create_llm_provider(provider_type) if provider_type else get_llm_provider()
            result = await provider.chat(
                messages=messages, temperature=0.3, max_tokens=900, stream=True
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
        async for chunk in _try_stream("openclaw"):
            got_any = True
            yield chunk

    if not got_any:
        yield "[AI 综合分析暂不可用（所有 LLM provider 都失败），请稍后重试。]"


# ───────────────────── 公开 API ────────────────────────


async def run_orchestrator(
    db: Session, user_id: int, req: OrchestratorRequest
) -> OrchestratorResponse:
    """非流式主入口。"""
    from app.services.llm.usage_tracker import set_caller
    set_caller("orchestrator.synthesis", user_id=user_id)
    t_start = time.monotonic()

    twin = build_twin(db, user_id)
    intent = classify_intent(req.query)
    specialists = _select_specialists(intent, twin, req.specialists)
    # 注入 active case threads (STRATEGY 阶段 3): specialist 可读 context['recent_cases']
    # 了解用户有哪些"进行中的问题线"来决定是否开新 card / 避免重复.
    try:
        from app.services.clinical_journal_service import get_active_case_briefs
        recent_cases = get_active_case_briefs(db, user_id, limit=5)
    except Exception:
        recent_cases = []
    findings = _run_specialists(
        twin, specialists, {"query": req.query, "db": db, "recent_cases": recent_cases}
    )

    # Cross-review + (可选) LLM 仲裁, 结果注入 synthesis prompt
    conflict_arb_block = await _run_cross_review_and_arbitration(findings, twin, db, user_id)

    system_prompt, user_prompt = _build_synthesis_prompt(
        req.query, twin, findings, db=db, user_id=user_id,
        conflict_arb_block=conflict_arb_block,
    )

    # 注入对话记忆（用户历史偏好/医嘱/过敏等）
    user_prompt = _inject_memory(db, user_id, user_prompt, findings=findings)

    synthesis = await _call_llm(system_prompt, user_prompt)

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
        findings_snapshot = [
            {
                "specialist": f.specialist_name,
                "kind": f.category,
                "summary": f.summary,
                # f.model_dump(mode="json") coerces datetime/Decimal/UUID/Path to str, PG JSONB safe.
                # 只存 'raw' 作为结构化 data; 不重复存 'findings' (和 raw 重叠 80%).
                "data": f.model_dump(mode="json").get("raw"),
                "proposed_cards": [c.model_dump(mode="json") for c in (f.proposed_cards or [])],
            }
            for f in findings
        ]
        log_specialist_findings(db, user_id=user_id, findings=findings_snapshot)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[orchestrator] specialist_findings audit bypass 失败: {e}")

    return OrchestratorResponse(
        query=req.query,
        intent=intent,
        findings=findings,
        synthesis=synthesis,
        used_specialists=[s.name for s in specialists],
        twin_build_ms=twin.meta.build_ms,
        total_ms=int((time.monotonic() - t_start) * 1000),
        persisted_card_ids=persisted_card_ids,
    )


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
    """
    from app.services.llm.usage_tracker import set_caller
    set_caller("orchestrator.stream", user_id=user_id)

    t_start = time.monotonic()

    def _sse(event: str, data) -> str:
        payload = data if isinstance(data, str) else json.dumps(data, default=str, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n"

    try:
        twin = build_twin(db, user_id)
        intent = classify_intent(req.query)
        specialists = _select_specialists(intent, twin, req.specialists)
        try:
            from app.services.clinical_journal_service import get_active_case_briefs
            recent_cases = get_active_case_briefs(db, user_id, limit=5)
        except Exception:
            recent_cases = []

        yield _sse(
            "intent",
            {
                "categories": intent.categories,
                "keywords": intent.keywords,
                "used_specialists": [s.name for s in specialists],
                "twin_build_ms": twin.meta.build_ms,
            },
        )

        findings = _run_specialists(
            twin, specialists,
            {"query": req.query, "db": db, "recent_cases": recent_cases},
        )
        for f in findings:
            yield _sse("specialist", f.model_dump(mode="json"))

        # 信任循环: 落地 proposed_cards
        persisted_ids = _persist_proposed_cards(db, user_id, findings)
        if persisted_ids:
            yield _sse("action_cards_created", {"ids": persisted_ids})

        # Clinical Journal: 异步写 SOAP (旁路, 失败只 log)
        try:
            from app.services.clinical_journal_service import write_soap_entry
            write_soap_entry(
                db, user_id=user_id, query=req.query, twin=twin,
                findings=findings, persisted_card_ids=persisted_ids,
                created_by="orchestrator",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[orchestrator.stream] write_soap_entry 失败: {e}")

        # Memory Extractor: specialist findings → 个人知识库 facts (旁路)
        try:
            from app.services.memory_extractor import extract_from_specialist_finding
            for f in findings:
                extract_from_specialist_finding(db, user_id, f, f.specialist_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[orchestrator.stream] memory extract 失败: {e}")

        # Cross-review + (可选) LLM 仲裁 (流式路径也走同样逻辑)
        conflict_arb_block = await _run_cross_review_and_arbitration(findings, twin, db, user_id)

        # 旁路审计: 与 run_orchestrator 对齐, 在 cross-review 后, 保证两条路径存同样状态的 findings
        try:
            from app.agents.audit import log_specialist_findings
            findings_snapshot = [
                {
                    "specialist": f.specialist_name,
                    "kind": f.category,
                    "summary": f.summary,
                    # f.model_dump(mode="json") coerces datetime/Decimal/UUID/Path to str, PG JSONB safe.
                    # 只存 'raw' 作为结构化 data; 不重复存 'findings' (和 raw 重叠 80%).
                    "data": f.model_dump(mode="json").get("raw"),
                    "proposed_cards": [c.model_dump(mode="json") for c in (f.proposed_cards or [])],
                }
                for f in findings
            ]
            log_specialist_findings(db, user_id=user_id, findings=findings_snapshot)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[orchestrator.stream] specialist_findings audit bypass 失败: {e}")

        system_prompt, user_prompt = _build_synthesis_prompt(
            req.query, twin, findings, db=db, user_id=user_id,
            conflict_arb_block=conflict_arb_block,
        )
        user_prompt = _inject_memory(db, user_id, user_prompt, findings=findings)

        # 流式 LLM
        async for chunk in _stream_llm(system_prompt, user_prompt):
            yield _sse("chunk", chunk)

        yield _sse("done", {
            "total_ms": int((time.monotonic() - t_start) * 1000),
            "persisted_card_ids": persisted_ids,
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("[orchestrator.stream] 未捕获异常")
        yield _sse("error", {"detail": str(e)})
