"""Unified Health Agent API — 统一健康助理端点

所有对话（记录、查询、分析、图片识别）统一走此入口。
OpenClaw 降级为 fallback 渠道。
"""
import asyncio
import json
import logging
from typing import Optional, List


from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required

logger = logging.getLogger(__name__)

# 2026-05-14 FIX-5 (G-W9 同模式): 客户端断开后 bg task 继续跑完 LLM/tool/写库.
# set 持 task 引用防 GC; done_callback 自动清理.
_BACKGROUND_AGENT_TASKS: set = set()
router = APIRouter()


# 防双发短期缓存: (user_id, msg_hash) → expiry_ts
# 用于检测客户端 silence_timer + onSpeechEnd 偶发同一 message 短时间内发 2 次的情况.
# 不持久化, 进程内即可; 多 worker 各自一份没关系 (同一连接通常落同一 worker).
_RECENT_DUP_CACHE: dict[tuple[int, str], float] = {}
_DUP_WINDOW_SECONDS = 3.0


def _merge_card_descriptors(*groups: list | None) -> list:
    """Merge SSE card descriptors without duplicating identical payloads."""

    out: list = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for card in group:
            if not isinstance(card, dict) or not isinstance(card.get("type"), str):
                continue
            try:
                key = json.dumps(card, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                key = f"{card.get('type')}:{len(out)}"
            if key in seen:
                continue
            seen.add(key)
            out.append(card)
    return out


def _persist_done_cards(db: Session, message_id: int | None, cards: list) -> None:
    """Persist cards appended by the API wrapper into OpenClawMessage.meta.

    AgentExecutor already writes its own metadata before yielding `done`. The
    route wrapper may append inline/query cards afterwards, so it must patch the
    same assistant message or history reload will lose cards that were visible
    during the live stream.
    """

    if not message_id or not cards:
        return
    try:
        from app.models.openclaw import OpenClawMessage

        msg = db.query(OpenClawMessage).filter(OpenClawMessage.id == message_id).first()
        if not msg:
            return
        meta = dict(msg.meta or {})
        meta["cards"] = _merge_card_descriptors(meta.get("cards"), cards)
        msg.meta = meta
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("[agent.stream] persist done cards skipped: %s", e)


def _check_recent_dup(user_id: int, message: str) -> bool:
    """同一 user 同一 message 在 3s 内重复 → 返回 True (拒绝).

    幅匹配: 取 message strip + 前 200 字 (语音转写常见). 不区分 conversation_id —
    用户多 tab 同一句话可能 fire 2 次, 同样应该拒.
    """
    import time
    now = time.time()
    key = (user_id, (message or "").strip()[:200])

    # 清理过期
    if len(_RECENT_DUP_CACHE) > 256:
        for k, exp in list(_RECENT_DUP_CACHE.items()):
            if exp < now:
                _RECENT_DUP_CACHE.pop(k, None)

    expiry = _RECENT_DUP_CACHE.get(key)
    if expiry and expiry > now:
        logger.warning(
            f"[agent.stream] dup msg rejected user={user_id} msg={key[1][:40]!r}"
        )
        return True

    _RECENT_DUP_CACHE[key] = now + _DUP_WINDOW_SECONDS
    return False


# ---------------------------------------------------------------------------
# GenUI 短路 (reva-ui line_chart) — 与 orchestrator 同一确定性 builder。
#
# 背景: Mac/mobile 统一聊天走本文件的 `agent_stream`, 但历史上只有
# orchestrator 端点接了 GenUI 协商。charting query ("绘制我最近半年的HRV曲线")
# 带 genui-v1 cap 落到这里会走 LLM 吐 ASCII/文本, 不出图。
#
# 铁律 (R4): 图表数值全部来自 chart_builder 的 DB 查询, 本路径绝不调用 LLM。
# 数据不足 / 异常 → 返回 None, 调用方 FALL THROUGH 到普通 AgentExecutor 路径
# (永不因 genui 失败而断聊天)。
# ---------------------------------------------------------------------------

GENUI_CAP = "genui-v1"

_GENUI_METRIC_LABEL = {
    "hrv": "HRV",
    "resting_hr": "静息心率",
    "stress": "压力",
    "sleep": "睡眠时长",
    "weight": "体重",
}
_GENUI_RANGE_LABEL = {"1m": "近一个月", "3m": "近三个月", "6m": "近半年"}


def _maybe_genui_chart_events(
    db: Session, user_id: int, message: str, conversation_id: int | None, caps: list[str]
) -> Optional[tuple[list[dict], int, int]]:
    """确定性构建 reva-ui line_chart, 持久化 assistant 消息, 返回要 emit 的 SSE 事件。

    返回 (events, conversation_id, message_id) 命中时; 否则 None (调用方走普通路径)。
    - caps 缺 genui-v1 / 非图表意图 / 数据不足 → None。
    - events 复用 `agent_stream` 现有 shape: token (data.content 含 ```reva-ui block)
      + done ({conversation_id, message_id, elapsed_ms, mode})。
    - assistant 消息写入与普通路径同一 durable store (OpenClawService), 含 reva-ui
      文本 → 历史/恢复可见, message_id 真实。
    """
    if GENUI_CAP not in (caps or []):
        return None

    from app.services.genui import (
        build_line_chart,
        detect_chart_request,
        render_reva_ui_block,
    )

    detected = detect_chart_request(message)
    if detected is None:
        return None

    metric, rng = detected
    block = build_line_chart(db, user_id, metric, range=rng)
    if block is None:
        # 数据不足: 与 orchestrator 路径一致 — 不补点, 回退普通路径 (让 LLM 解释/引导)。
        return None

    metric_label = _GENUI_METRIC_LABEL.get(metric, metric)
    range_label = _GENUI_RANGE_LABEL.get(rng, rng)
    note = block.get("data_note", "")
    # 确定性模板叙事 (无 LLM); 图表数值只来自 block。
    intro = (
        f"{range_label}{metric_label}趋势（数据来自你的设备，{note}）："
        if note
        else f"{range_label}{metric_label}趋势（数据来自你的设备）："
    )
    full_reply = f"{intro}\n\n{render_reva_ui_block(block)}"

    # 持久化: 与 AgentExecutor.run_stream 相同的 OpenClawService 会话/消息存储。
    from app.services.openclaw_service import OpenClawService

    svc = OpenClawService(db)
    conv = svc.get_or_create_conversation(user_id, conversation_id, title=message)
    svc.save_message(conv.id, "user", message)
    ai_msg = svc.save_message(conv.id, "assistant", full_reply)
    try:
        ai_msg.meta = {"mode": "agent", "genui": True, "sources_used": ["设备数据"]}
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("[agent.stream] genui meta write skipped: %s", e)

    events = [
        {"event": "agent_start", "data": {"message": "正在绘制图表…", "conversation_id": conv.id}},
        {"event": "token", "data": {"content": full_reply}},
        {
            "event": "done",
            "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
                "elapsed_ms": 0,
                "mode": "agent",
                "genui": True,
            },
        },
    ]
    return events, conv.id, ai_msg.id


class ImageItem(BaseModel):
    base64: str
    type: str = "jpeg"


class AgentRequest(BaseModel):
    message: str = Field(max_length=10000)
    conversation_id: Optional[int] = None
    image_base64: Optional[str] = None
    image_type: Optional[str] = None
    images: Optional[List[ImageItem]] = None
    file_base64: Optional[str] = None
    file_name: Optional[str] = None
    # 入口 deeplink 携带的结构化上下文 (JSON string), 注入到 LLM prompt 不展示给用户.
    # 例: SNP 详情页点"详细聊饮食方案" → context 带当前页正展示的食材条目.
    extra_context: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("image_base64")
    @classmethod
    def check_image_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 10_000_000:
            raise ValueError("图片太大，最大支持约 7.5MB")
        return v

    @field_validator("images")
    @classmethod
    def check_images(cls, v: Optional[List]) -> Optional[List]:
        if v and len(v) > 9:
            raise ValueError("最多支持 9 张图片")
        if v:
            for img in v:
                if len(img.base64) > 10_000_000:
                    raise ValueError("单张图片太大，最大支持约 7.5MB")
        return v

    @field_validator("file_base64")
    @classmethod
    def check_file_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 15_000_000:  # ~11MB file
            raise ValueError("文件太大，最大支持约 11MB")
        return v


class ConversationTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        normalized = v.strip()
        if not normalized:
            raise ValueError("标题不能为空")
        return normalized


@router.post("/stream", summary="统一健康助理流式对话")
async def agent_stream(
    request: Request,
    req: AgentRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    x_reva_client_caps: str | None = Header(default=None),
):
    """统一健康 Agent — 记录 + 查询 + 分析 + 图片识别

    SSE 事件类型：
    - agent_start: Agent 开始
    - tool_call: 正在调用工具 {tool, args, round}
    - tool_result: 工具返回 {tool, success, preview}
    - token: 文本内容（思考过程或最终回答）
    - done: 完成 {conversation_id, message_id, elapsed_ms, mode}
    - error: 错误
    """
    has_images = bool(req.image_base64 or req.images)
    if not req.message.strip() and not has_images and not req.file_base64:
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 防双发 (用户反馈批 4): 客户端 silence_timer + onSpeechEnd 偶发同一 message 发 2 次
    # 后端用 in-memory 短期缓存 (3s 窗) 拒同一用户重复 message, 避免 LLM 重试浪费 + 撞 OpenAI proxy 限流.
    # 不持久化也 OK — 短期防护即可.
    _reject = _check_recent_dup(current_user.id, req.message)
    if _reject:
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍候。（同一消息 3 秒内已发送）",
        )

    # Normalize: merge single image_base64 and images array into one list
    all_images: List[dict] = []
    if req.images:
        all_images = [{"base64": img.base64, "type": img.type} for img in req.images]
    elif req.image_base64:
        all_images = [{"base64": req.image_base64, "type": req.image_type or "jpeg"}]

    from app.services.agent_executor import AgentExecutor

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
    user_id = current_user.id
    msg_text = req.message.strip()
    conv_id = req.conversation_id
    images_local = all_images or None
    file_b64 = req.file_base64
    file_nm = req.file_name
    extra_ctx = req.extra_context

    # GenUI 短路: caps=genui-v1 + 图表意图 + 无图片/附件 → 确定性出 reva-ui block,
    # 跳过 AgentExecutor/LLM (R4: 数值只来自 DB)。命中即持久化消息并直接 SSE 回放。
    # 数据不足 / 任何异常 → genui_events=None, FALL THROUGH 到普通路径 (永不断聊天)。
    from app.api._client_caps import parse_client_caps

    caps = parse_client_caps(x_reva_client_caps)
    genui_events: Optional[list[dict]] = None
    if not has_images and not file_b64:
        try:
            hit = _maybe_genui_chart_events(db, user_id, msg_text, conv_id, caps)
            if hit is not None:
                genui_events, _conv, _mid = hit
                logger.info(
                    "[agent.stream] GenUI short-circuit hit user=%s conv=%s msg_id=%s",
                    user_id, _conv, _mid,
                )
        except Exception as e:  # noqa: BLE001
            # 失败软着陆: 不破坏聊天, 回退普通路径。
            logger.warning("[agent.stream] GenUI short-circuit failed, fall through: %s", e)
            try:
                db.rollback()
            except Exception:
                pass
            genui_events = None

    if genui_events is not None:
        async def genui_generate():
            for event in genui_events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            genui_generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def generate():
        """G-W9 同模式 (FIX-5, 2026-05-14): bg task + asyncio.Queue.

        客户端断开 (App 后台 30s+ / 切走页面) → 这个 generator 抛 CancelledError /
        GeneratorExit 退出, 但 bg_task 继续跑到 LLM 完成 + 把 message 写库 + audit.
        用户回到 App 后, useFocusEffect/AppState 重新拉 conversation, 看到完整回复.
        """
        chunk_queue: asyncio.Queue = asyncio.Queue()

        async def _bg():
            # 独立 db session — 主 request 的 db 在客户端断开时会被 close
            from app.database import SessionLocal as _SessionLocal
            bg_db = _SessionLocal()
            try:
                executor_bg = AgentExecutor(bg_db)
                # 累积 LLM 流式输出, done 时扫描 fenced ```menu_share 块 (L1 分享菜单)
                full_text_buf: list = []
                async for event in executor_bg.run_stream(
                    user_id=user_id,
                    message=msg_text,
                    conversation_id=conv_id,
                    user_auth_token=user_token,
                    images=images_local,
                    file_base64=file_b64,
                    file_name=file_nm,
                    extra_context=extra_ctx,
                ):
                    if event.get("event") == "token":
                        tc = event.get("data", {}).get("content")
                        if isinstance(tc, str):
                            full_text_buf.append(tc)
                    # 在 done 事件里附加动态卡片, 失败静默
                    if event.get("event") == "done":
                        try:
                            from app.services.inline_cards import build_cards, extract_inline_card_blocks
                            existing = event.get("data", {}).get("cards")
                            cards = build_cards(bg_db, user_id, msg_text)
                            inline = extract_inline_card_blocks("".join(full_text_buf))
                            # LLM 主动输出的卡片优先，其次保留 AgentExecutor 已写入的
                            # system-KB evidence，再追加 query 派生卡片。历史恢复依赖
                            # message.meta.cards，所以合并后回写同一 assistant message。
                            merged = _merge_card_descriptors(inline, existing, cards)
                            if merged:
                                event.setdefault("data", {})["cards"] = merged
                                _persist_done_cards(
                                    bg_db,
                                    event.get("data", {}).get("message_id"),
                                    merged,
                                )
                        except Exception as e:
                            logger.debug(f"inline_cards 失败: {e}")
                    await chunk_queue.put(f"data: {json.dumps(event, ensure_ascii=False)}\n\n")
            except Exception as e:
                logger.error(f"Agent bg 流式异常: {e}", exc_info=True)
                err = {"event": "error", "data": {"message": str(e)}}
                try:
                    await chunk_queue.put(f"data: {json.dumps(err, ensure_ascii=False)}\n\n")
                except Exception:
                    pass
            finally:
                # sentinel: 通知 generator 结束
                try:
                    await chunk_queue.put(None)
                except Exception:
                    pass
                try:
                    bg_db.close()
                except Exception:
                    pass

        bg_task = asyncio.create_task(_bg())
        _BACKGROUND_AGENT_TASKS.add(bg_task)
        bg_task.add_done_callback(_BACKGROUND_AGENT_TASKS.discard)

        try:
            while True:
                item = await chunk_queue.get()
                if item is None:
                    break
                yield item
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开 — bg_task 不取消, 让它跑完写完消息.
            logger.info(
                f"[agent.stream] client disconnected user={user_id}, "
                f"bg task continues to finish LLM + write message"
            )
            raise

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", summary="统一健康助理对话列表")
async def list_conversations(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, description="分页偏移(翻页用)"),
    title_like: Optional[str] = Query(None, description="按标题模糊过滤"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """List current user's Agent conversations (paginated).

    返回 {items, total, limit, offset} —— 前端历史记录用 offset 做上一页/下一页翻页。
    AgentExecutor persists conversations through OpenClawService so mobile/web
    can resume interrupted streams from the same durable message store.
    """
    from sqlalchemy import func
    from app.models.openclaw import OpenClawMessage
    from app.services.openclaw_service import OpenClawService

    service = OpenClawService(db)
    total = service.count_conversations(current_user.id, title_like=title_like)
    convs = service.get_conversations(current_user.id, limit, title_like=title_like, offset=offset)
    conv_ids = [c.id for c in convs]
    last_msgs = {}
    if conv_ids:
        subq = (
            db.query(
                OpenClawMessage.conversation_id,
                func.max(OpenClawMessage.id).label("max_id"),
            )
            .filter(
                OpenClawMessage.conversation_id.in_(conv_ids),
                OpenClawMessage.role == "user",
            )
            .group_by(OpenClawMessage.conversation_id)
            .subquery()
        )
        rows = (
            db.query(OpenClawMessage.conversation_id, OpenClawMessage.content)
            .join(subq, OpenClawMessage.id == subq.c.max_id)
            .all()
        )
        last_msgs = {r[0]: (r[1] or "")[:80] for r in rows}

    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "last_message": last_msgs.get(c.id),
                "created_at": str(c.created_at),
                "updated_at": str(c.updated_at),
                "mode": "agent",
            }
            for c in convs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/conversations/{conversation_id}", summary="统一健康助理对话详情")
async def get_conversation(
    conversation_id: int,
    days: Optional[int] = Query(None, ge=1, le=365, description="只返回最近 N 天的消息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.openclaw_service import OpenClawService

    service = OpenClawService(db)
    conv = service.get_conversation_detail(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    msgs = conv.messages
    total_messages = len(msgs)
    if days is not None:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        msgs = [m for m in msgs if m.created_at and _msg_dt(m.created_at) >= cutoff]

    return {
        "id": conv.id,
        "title": conv.title,
        "total_messages": total_messages,
        "mode": "agent",
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "image_url": m.image_url,
                "rating": m.rating,
                "created_at": str(m.created_at),
                "meta": getattr(m, "meta", None),
            }
            for m in msgs
        ],
    }


def _msg_dt(value):
    """Normalize SQLite naive / PostgreSQL aware timestamps to aware UTC."""
    from datetime import datetime, timezone

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc) if value else datetime.now(timezone.utc)


@router.delete("/conversations/{conversation_id}", summary="删除统一健康助理对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.openclaw_service import OpenClawService

    service = OpenClawService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@router.patch("/conversations/{conversation_id}", summary="重命名统一健康助理对话")
async def update_conversation_title(
    conversation_id: int,
    body: ConversationTitleUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.openclaw_service import OpenClawService

    service = OpenClawService(db)
    try:
        conv = service.update_conversation_title(current_user.id, conversation_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "updated_at": str(conv.updated_at),
        "mode": "agent",
    }


@router.get("/conversation-opener", summary="Chat 起手未读续接 — AI 主动开场白")
def conversation_opener(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    返回 AI 主动续接上次话题的开场白. 前端 chat tab mount 时拉这个,
    用来替代/前置 SUGGESTIONS chip.

    Returns:
        - 200 OK: 有 opener 信号 — { opener: { text, source, source_id?, quick_replies, deep_link?, priority } }
        - 200 OK: 无信号 — { opener: null }  (前端退化到默认 SUGGESTIONS)

    Never raises — 错误时返回 { opener: null }, 静默退化, 不影响 chat 启动.
    """
    from dataclasses import asdict
    from app.services.conversation_opener import compute_conversation_opener

    try:
        opener = compute_conversation_opener(db, current_user.id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[conversation_opener] endpoint bypass: {e}")
        opener = None

    return {"opener": asdict(opener) if opener else None}


@router.get("/conversation-starters", summary="新对话页 prompts — 动态建议 chip")
def conversation_starters(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return dynamic prompt chips for the new-chat empty state.

    This endpoint is fail-soft: it never raises (except auth) and falls back to
    stable defaults on any internal error.
    """
    from dataclasses import asdict
    from app.services.conversation_opener import compute_conversation_opener
    from app.services.conversation_starters import compute_conversation_suggestion_cards

    opener = None
    try:
        opener = compute_conversation_opener(db, current_user.id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[conversation_starters] opener bypass: {e}")

    # Structured cards carry the generator `key` so the client can attribute
    # impressions/clicks per generator (CTR). Clients tolerate the legacy
    # plain-string shape too (see conversationOpener.ts / ai-assistant page).
    cards = compute_conversation_suggestion_cards(db, current_user.id, limit=4)

    return {
        "opener": asdict(opener) if opener else None,
        "suggestions": [
            {"text": c.text, "key": c.key, "priority": c.priority} for c in cards
        ],
    }


@router.get("/tools", summary="列出可用工具")
def list_agent_tools(
    current_user: User = Depends(get_current_user_required),
):
    """列出 Agent 可调用的所有工具"""
    from app.services.tool_schema_registry import get_health_tools
    tools = get_health_tools()
    return {
        "tools": tools,
        "count": len(tools),
        "model": "Hermes-3 (OpenAI-compatible)",
    }
