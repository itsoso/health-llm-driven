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


# ───────────────────── LLM 合并 prompt ────────────────────


def _build_synthesis_prompt(
    query: str, twin: HealthTwin, findings: List[SpecialistFinding]
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
    )

    user_prompt = (
        f"【用户原始问题】\n{query}\n\n"
        f"【用户当前健康快照】\n{twin_blob or '(数据暂缺)'}\n\n"
        f"【专家裁决】\n{findings_text}\n\n"
        "请基于以上信息写回答。"
    )

    return system_prompt, user_prompt


def _inject_memory(db: Session, user_id: int, user_prompt: str) -> str:
    """注入用户对话记忆（过敏/医嘱/偏好等）。失败降级。"""
    try:
        from app.services.conversation_memory_service import get_relevant_memories

        memories = get_relevant_memories(db, user_id, limit=5)
        if memories:
            return user_prompt + f"\n\n【用户历史偏好/记忆】\n{memories}\n"
    except Exception:
        pass
    return user_prompt


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
    t_start = time.monotonic()

    twin = build_twin(db, user_id)
    intent = classify_intent(req.query)
    specialists = _select_specialists(intent, twin, req.specialists)
    findings = _run_specialists(twin, specialists, {"query": req.query, "db": db})

    system_prompt, user_prompt = _build_synthesis_prompt(req.query, twin, findings)

    # 注入对话记忆（用户历史偏好/医嘱/过敏等）
    user_prompt = _inject_memory(db, user_id, user_prompt)

    synthesis = await _call_llm(system_prompt, user_prompt)

    return OrchestratorResponse(
        query=req.query,
        intent=intent,
        findings=findings,
        synthesis=synthesis,
        used_specialists=[s.name for s in specialists],
        twin_build_ms=twin.meta.build_ms,
        total_ms=int((time.monotonic() - t_start) * 1000),
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

        system_prompt, user_prompt = _build_synthesis_prompt(req.query, twin, findings)
        user_prompt = _inject_memory(db, user_id, user_prompt)

        # 流式 LLM
        async for chunk in _stream_llm(system_prompt, user_prompt):
            yield _sse("chunk", chunk)

        yield _sse("done", {"total_ms": int((time.monotonic() - t_start) * 1000)})
    except Exception as e:  # noqa: BLE001
        logger.exception("[orchestrator.stream] 未捕获异常")
        yield _sse("error", {"detail": str(e)})
