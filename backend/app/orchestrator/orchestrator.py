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


def _build_synthesis_prompt(
    query: str, twin: HealthTwin, findings: List[SpecialistFinding],
    db: Optional[Session] = None, user_id: Optional[int] = None,
) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt)。"""

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
    if db is not None and user_id is not None:
        credit_text = _build_specialist_credit_block(db, user_id, days=30)

    # Cross-Review: specialist 之间矛盾检测 + audit log
    conflicts_text = ""
    try:
        from app.orchestrator.cross_review import detect_conflicts, render_conflicts_for_prompt
        conflicts = detect_conflicts(findings, twin, db=db)
        if conflicts:
            conflicts_text = render_conflicts_for_prompt(conflicts)
            logger.info(f"[orchestrator] cross_review 检测到 {len(conflicts)} 个 specialist 冲突")
            # Audit log (旁路, 失败不影响主流程)
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
        " 没有命中率数据的 specialist 视为中等可信.\n"
        "9. **冲突仲裁**: 如果下方'Specialist 矛盾'区域有内容, 你必须在回答里明示如何裁决,"
        " 不能两个矛盾建议并列输出. hard 矛盾按 resolution_hint 走, soft 矛盾说明权衡."
    )

    user_prompt_parts = [
        f"【用户原始问题】\n{query}",
        f"【用户当前健康快照】\n{twin_blob or '(数据暂缺)'}",
    ]
    if credit_text:
        user_prompt_parts.append(f"【Specialist 历史命中率 (近 30 天)】\n{credit_text}")
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

    # 4) Memory Facts (LLM Wiki v2): 个人知识库 — 高 confidence + 相关 tag 的事实
    try:
        from app.services.memory_service import get_active_facts, render_facts_for_prompt
        # 优先抓 semantic / procedural tier (跨 session 已固化的)
        # 用 metric_key 做 tag 过滤 (case_thread.theme = tag)
        from app.services.clinical_journal_service import _theme_from_metric
        tag = _theme_from_metric(metric_key) if metric_key else None
        facts = []
        for tier in ("procedural", "semantic"):
            facts.extend(get_active_facts(
                db, user_id, tier=tier, tag=tag,
                min_confidence=0.4, limit=8,
            ))
        # 去重 (按 id)
        seen = set()
        unique = []
        for f in facts:
            if f.id not in seen:
                seen.add(f.id)
                unique.append(f)
        if unique:
            out += f"\n\n{render_facts_for_prompt(unique, max_lines=10)}\n"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] memory facts 注入失败 (跳过): {e}")

    # 5) Knowledge Graph 2-hop: 把 query 提到的 entity 周围连接的关系拼进 prompt
    # (LLM Wiki v2 graph traversal — 让 specialist 看到 medication ↔ condition ↔ lab 的链条)
    try:
        from app.services.kg_service import render_neighborhood_for_prompt
        # 从原 user_prompt (不含已注入的 memory) 取 query 文本
        # 简化: 用 user_prompt 前 200 字作 mention 检测
        query_seed = (user_prompt or "")[:300]
        kg_md = render_neighborhood_for_prompt(
            db, user_id, query_seed, max_seeds=3, hops=2, max_per_hop=5,
        )
        if kg_md:
            out += f"\n\n{kg_md}\n"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[orchestrator] KG neighborhood 注入失败 (跳过): {e}")

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
    findings = _run_specialists(twin, specialists, {"query": req.query, "db": db})

    system_prompt, user_prompt = _build_synthesis_prompt(req.query, twin, findings, db=db, user_id=user_id)

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

        yield _sse(
            "intent",
            {
                "categories": intent.categories,
                "keywords": intent.keywords,
                "used_specialists": [s.name for s in specialists],
                "twin_build_ms": twin.meta.build_ms,
            },
        )

        findings = _run_specialists(twin, specialists, {"query": req.query, "db": db})
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

        system_prompt, user_prompt = _build_synthesis_prompt(req.query, twin, findings, db=db, user_id=user_id)
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
