"""Unified Health Agent API — 统一健康助理端点

所有对话（记录、查询、分析、图片识别）统一走此入口。
OpenClaw 降级为 fallback 渠道。
"""
import asyncio
import json
import logging
from typing import Optional, List


from fastapi import APIRouter, Depends, HTTPException, Request
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


@router.post("/stream", summary="统一健康助理流式对话")
async def agent_stream(
    request: Request,
    req: AgentRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
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
                async for event in executor_bg.run_stream(
                    user_id=user_id,
                    message=msg_text,
                    conversation_id=conv_id,
                    user_auth_token=user_token,
                    images=images_local,
                    file_base64=file_b64,
                    file_name=file_nm,
                ):
                    # 在 done 事件里附加动态卡片, 失败静默
                    if event.get("event") == "done":
                        try:
                            from app.services.inline_cards import build_cards
                            cards = build_cards(bg_db, user_id, msg_text)
                            if cards:
                                event.setdefault("data", {})["cards"] = cards
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
