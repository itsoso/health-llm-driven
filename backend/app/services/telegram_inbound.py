"""
Telegram inbound 处理器 — 把用户在 Telegram 发的语音/文字解析为健康行为.

流程:
  用户 → Telegram → bot 转发到 webhook
  → 如果是 voice 消息: getFile + 下载 ogg → Whisper STT → 文字
  → 意图分类 (共享 Agent Kernel 语义帧):
      directive → user_directives (走 directive_parser, 老路径)
      record    → 调 health_record 工具 (LLM tool calling, 单次)
      query/chat → LLM 直接回复 (≤80 字, 适合 IM)
  → 回执 markdown 摘要 (你做了什么, 写库结果)

Karpathy verification 思想: 写库前预览 + 用户在 Telegram 直接看到结果.

最小依赖:
  - openai SDK (已有, Whisper + chat)
  - httpx (已有)
  - LLM provider (现成 services.llm.factory)
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Optional

import httpx

from app.config import settings
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext

logger = logging.getLogger(__name__)


# 意图标签 — directive 暂留老规则; record/query 使用共享 Agent Kernel.
_DIRECTIVE_HINTS = (
    "控制在", "目标", "戒酒", "戒烟", "限制",
    "不要再推", "不要给我", "禁止",
    "之前我说过", "再次强调", "记住",
)


def classify_intent(text: str) -> str:
    """粗分类: directive / record / query / chat.

    Health record routing must use the shared semantic frame. A keyword such as
    "记录" is not enough to grant the record path, because it is often a noun in
    read-only requests.
    """
    t = text.strip()
    if not t:
        return "chat"
    if any(h in t for h in _DIRECTIVE_HINTS):
        return "directive"

    envelope = AgentEnvelope(user_id=None, channel="telegram", text=t)
    context = ExecutionContext.now(user_id=None, channel="telegram")
    frame = build_intent_frame(envelope, context)

    if frame.primary == "write" and frame.operation == "create":
        return "record"
    if frame.primary in {"read", "advice", "mutate"}:
        return "query"
    return "chat"


# ─── Telegram 文件下载 ───────────────────────────────────────────────

async def download_telegram_file(file_id: str) -> Optional[bytes]:
    """从 Telegram 下载文件 → bytes."""
    token = settings.telegram_bot_token
    if not token:
        return None

    api_base = (
        getattr(settings, "telegram_api_base", None)
        or "https://api.telegram.org"
    ).rstrip("/")
    proxy_url = getattr(settings, "telegram_proxy_url", None) or None

    client_kwargs: dict = {"timeout": 30}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.get(
                f"{api_base}/bot{token}/getFile", params={"file_id": file_id}
            )
            j = r.json()
            if not j.get("ok"):
                logger.warning(f"[telegram-inbound] getFile failed: {j}")
                return None
            file_path = j["result"]["file_path"]

            url = f"{api_base}/file/bot{token}/{file_path}"
            r2 = await client.get(url)
            if r2.status_code != 200:
                logger.warning(f"[telegram-inbound] download failed: {r2.status_code}")
                return None
            return r2.content
    except Exception as e:
        logger.warning(f"[telegram-inbound] file download error: {e}")
        return None


# ─── Whisper STT ─────────────────────────────────────────────────────

async def transcribe_voice_bytes(
    audio_bytes: bytes, ext: str = "ogg"
) -> Optional[str]:
    """走 OpenAI Whisper. ext 通常 ogg (Telegram voice 默认 opus in ogg container)."""
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        client = OpenAI(**kwargs)
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            with open(path, "rb") as af:
                t = client.audio.transcriptions.create(
                    model="whisper-1", file=af, language="zh"
                )
            return (t.text or "").strip()
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[telegram-inbound] whisper failed: {e}")
        return None


# ─── 健康数据写入: LLM tool calling (单轮) ─────────────────────────────

async def llm_extract_record(text: str) -> Optional[dict]:
    """
    让 LLM 把用户文字解析为 health_record tool call 参数.
    单次 chat completions + tools 强制 function call.
    返回: {"record_type": "weight", "data": {...}} 或 None (无法解析)
    """
    try:
        from app.services.llm.factory import get_llm_provider
        from app.services.llm.usage_tracker import set_caller
        from app.services.tool_schema_registry import HEALTH_TOOLS
        set_caller("telegram.inbound.extract_record")
        provider = get_llm_provider()

        # 只暴露 health_record 工具, 强制走它
        record_tool = next(
            (t for t in HEALTH_TOOLS if t["function"]["name"] == "health_record"),
            None,
        )
        if not record_tool:
            return None

        result = await provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "用户通过 Telegram 录入健康数据. 调 health_record 工具写库. "
                        "不确定的字段就别填. 不要给医疗建议. 不要复述用户的话."
                    ),
                },
                {"role": "user", "content": text},
            ],
            tools=[record_tool],
            tool_choice="auto",
            max_tokens=400,
            temperature=0.1,
        )

        # provider.chat 在工具调用时返回 dict {"tool_calls": [...]}
        if not isinstance(result, dict):
            return None
        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            return None
        first = tool_calls[0]
        fn = first.get("function") or {}
        if fn.get("name") != "health_record":
            return None
        args_raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            return None
        return args
    except Exception as e:
        logger.warning(f"[telegram-inbound] llm_extract_record failed: {e}")
        return None


async def execute_health_record(db, user_id: int, args: dict) -> str:
    """
    调 agent_executor 内部的 _exec_health_record (复用 schema/校验/确认逻辑).

    base_url 取 settings.health_api_base_url, 没配则默认 localhost.
    """
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = user_id
    try:
        base = (settings.health_api_base_url or "http://localhost:8000/api/v1").rstrip("/")
        from app.api.wechat import create_access_token
        token = create_access_token(user_id)
        headers = {"Authorization": f"Bearer {token}"}
        result = await executor._exec_health_record(base, headers, args)
        return result or "✅ 已记录"
    except Exception as e:
        logger.warning(
            f"[telegram-inbound] _exec_health_record failed: {e}", exc_info=True
        )
        return f"⚠️ 写入失败: {str(e)[:120]}"


async def llm_chat_reply(text: str) -> str:
    """普通对话 / 查询: LLM 简短回复 (Telegram 场景, ≤80 字)."""
    try:
        from app.services.llm.factory import get_llm_provider
        from app.services.llm.usage_tracker import set_caller
        set_caller("telegram.inbound.chat")
        provider = get_llm_provider()
        raw = await provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是健康助理. 用户通过 Telegram 简短交流. "
                        "回复 ≤ 80 字, 直接给结论, 不要客套不要 markdown 标题."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=200,
            temperature=0.4,
        )
        if isinstance(raw, dict):
            raw = raw.get("content", "") or ""
        return (raw or "").strip() or "✅ 收到"
    except Exception as e:
        logger.warning(f"[telegram-inbound] chat reply failed: {e}")
        return "✅ 收到 (LLM 暂时不可用)"


# ─── 主入口 ──────────────────────────────────────────────────────────

async def handle_inbound_text(
    db,
    user_id: int,
    text: str,
    *,
    source_message_id: Optional[str] = None,
) -> str:
    """
    根据 text 自动分流, 返回给用户的 Telegram 回执.
    """
    intent = classify_intent(text)
    logger.info(f"[telegram-inbound] user={user_id} intent={intent} text={text[:80]!r}")

    if intent == "directive":
        # 老路径
        from app.services.directive_parser import parse_and_store
        try:
            ids = parse_and_store(
                db,
                user_id=user_id,
                text=text,
                source="external_telegram",
                source_message_id=source_message_id,
            )
            if not ids:
                return "ℹ️ 没识别出指令. 试试 'LDL 控制在 2.6 以下' 或 '严格戒酒 30 天'"
            from app.models.user_directive import UserDirective
            rows = db.query(UserDirective).filter(UserDirective.id.in_(ids)).all()
            summary = "\n".join(
                f"  • [{r.kind}] {r.instruction[:60]}"
                + (f" ({r.metric_key}={r.target_value})" if r.metric_key and r.target_value else "")
                for r in rows
            )
            return f"✅ 已录入 {len(ids)} 条指令:\n{summary}"
        except Exception as e:
            logger.warning(f"[telegram-inbound] directive parse failed: {e}")
            return f"⚠️ 指令解析失败: {str(e)[:100]}"

    if intent == "record":
        # LLM 抽 → 调 health_record
        args = await llm_extract_record(text)
        if not args or "record_type" not in args:
            return "ℹ️ 没识别出可记录的健康数据. 用更具体的话, 例: '体重 71.2', '吃了 2 个鸡蛋'"
        result = await execute_health_record(db, user_id, args)
        # 处理 NEEDS_CONFIRMATION (L8 weight 确认) 这种半结构化返回
        if "[NEEDS_CONFIRMATION]" in result:
            return f"🤔 {result.replace('[NEEDS_CONFIRMATION]', '').strip()}\n\n回复 '确认' 完成记录."
        if result.startswith("Error"):
            return f"⚠️ {result[:200]}"
        # 简化结果展示 (返回的是 JSON 一坨, 取关键字段)
        try:
            d = json.loads(result) if isinstance(result, str) else result
            rt = args.get("record_type", "")
            if rt == "weight":
                return f"✅ 已记体重 {d.get('weight')} kg ({d.get('record_date', '今天')})"
            if rt == "diet":
                return f"✅ 已记饮食: {d.get('food_items', '')[:50]}"
            if rt == "water":
                return f"✅ 已记饮水 {d.get('amount', 250)}ml"
            return f"✅ 已记录 {rt}"
        except Exception:
            return f"✅ {result[:120]}"

    # query / chat → LLM 简短回复
    return await llm_chat_reply(text)
