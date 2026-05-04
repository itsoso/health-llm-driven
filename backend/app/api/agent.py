"""Unified Health Agent API — 统一健康助理端点

所有对话（记录、查询、分析、图片识别）统一走此入口。
OpenClaw 降级为 fallback 渠道。
"""
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
router = APIRouter()


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

    # Normalize: merge single image_base64 and images array into one list
    all_images: List[dict] = []
    if req.images:
        all_images = [{"base64": img.base64, "type": img.type} for img in req.images]
    elif req.image_base64:
        all_images = [{"base64": req.image_base64, "type": req.image_type or "jpeg"}]

    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)

    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    async def generate():
        try:
            async for event in executor.run_stream(
                user_id=current_user.id,
                message=req.message.strip(),
                conversation_id=req.conversation_id,
                user_auth_token=user_token,
                images=all_images or None,
                file_base64=req.file_base64,
                file_name=req.file_name,
            ):
                # 在 done 事件里附加动态卡片, 失败静默
                if event.get("event") == "done":
                    try:
                        from app.services.inline_cards import build_cards
                        cards = build_cards(db, current_user.id, req.message.strip())
                        if cards:
                            event.setdefault("data", {})["cards"] = cards
                    except Exception as e:
                        logger.debug(f"inline_cards 失败: {e}")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Agent 流式异常: {e}", exc_info=True)
            error_event = {"event": "error", "data": {"message": str(e)}}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

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
