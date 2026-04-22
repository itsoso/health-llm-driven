"""OpenClaw Channel API — 独立于健康助理的 OpenClaw 对话通道"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.openclaw import OpenClawMessage, OpenClawConversation
from app.models.user import User
from app.services.openclaw_service import OpenClawService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openclaw", tags=["openclaw"])


# ── Schemas ───────────────────────────────────────────────

class OpenClawSendRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    image_base64: str | None = None
    image_type: str | None = "jpeg"
    file_base64: str | None = None
    file_name: str | None = None


class OpenClawConversationResponse(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class OpenClawMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    rating: int | None = None
    created_at: str

    class Config:
        from_attributes = True


class OpenClawConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: List[OpenClawMessageResponse]

    class Config:
        from_attributes = True


class RateMessageRequest(BaseModel):
    rating: int

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("rating must be 1 (thumbs up) or -1 (thumbs down)")
        return v


# ── Endpoints ─────────────────────────────────────────────

@router.post("/stream", summary="OpenClaw 流式对话")
async def stream_message(
    request: Request,
    req: OpenClawSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """流式发送消息到 OpenClaw Gateway，SSE 实时返回"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 文件附件：提取文本并注入消息
    message = req.message.strip()
    if req.file_base64 and req.file_name:
        try:
            from app.services.file_extract_service import extract_text_from_base64
            file_text = extract_text_from_base64(req.file_base64, req.file_name)
            if file_text:
                message = f"{message}\n\n[附件: {req.file_name}]\n{file_text}"
        except Exception as e:
            logger.warning(f"文件提取失败: {e}")

    service = OpenClawService(db)

    # 提取当前用户的 auth token（多租户：Skill 调用时使用用户自己的凭证）
    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    async def generate():
        full_reply = ""
        try:
            async for event in service.send_message_stream(
                user_id=current_user.id,
                message=message,
                conversation_id=req.conversation_id,
                is_admin=current_user.is_admin,
                image_base64=req.image_base64,
                image_type=req.image_type or "jpeg",
                user_auth_token=user_token,
            ):
                if event.get("event") == "token":
                    full_reply += event.get("data", {}).get("content", "")
                elif event.get("event") == "done":
                    # 饮食自动补录
                    if _is_diet_record_intent(message, full_reply):
                        diet_data = _auto_save_diet_if_missing(db, current_user.id, message, full_reply)
                        if diet_data:
                            event["data"]["diet_saved"] = True
                            event["data"]["diet_data"] = diet_data
                            logger.info(f"[OpenClaw 流式补录] 用户 {current_user.id} 饮食: {diet_data.get('food_items', '')[:50]}")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"OpenClaw 流式异常: {e}", exc_info=True)
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


@router.post("/send", summary="OpenClaw 非流式对话")
async def send_message(
    request: Request,
    req: OpenClawSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """非流式发送消息到 OpenClaw Gateway，收集完整回复后一次性返回（适用于不支持 SSE 的客户端）"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    # 文件附件：提取文本并注入消息
    message = req.message.strip()
    if req.file_base64 and req.file_name:
        try:
            from app.services.file_extract_service import extract_text_from_base64
            file_text = extract_text_from_base64(req.file_base64, req.file_name)
            if file_text:
                message = f"{message}\n\n[附件: {req.file_name}]\n{file_text}"
        except Exception as e:
            logger.warning(f"文件提取失败: {e}")

    service = OpenClawService(db)

    # 提取当前用户的 auth token
    auth_header = request.headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    full_reply = ""
    conversation_id = None
    message_id = None

    try:
        async for event in service.send_message_stream(
            user_id=current_user.id,
            message=message,
            conversation_id=req.conversation_id,
            is_admin=current_user.is_admin,
            image_base64=req.image_base64,
            image_type=req.image_type or "jpeg",
            user_auth_token=user_token,
        ):
            evt_type = event.get("event")
            if evt_type == "token":
                content = event.get("data", {}).get("content", "")
                full_reply += content
            elif evt_type == "done":
                conversation_id = event.get("data", {}).get("conversation_id")
                message_id = event.get("data", {}).get("message_id")
    except Exception as e:
        logger.error(f"OpenClaw 非流式调用异常: {e}", exc_info=True)
        if not full_reply:
            full_reply = "抱歉，OpenClaw 暂时无法响应，请稍后再试。"

    # 饮食记录自动补录：AI 可能声称"已记录"但实际未调用 API
    diet_saved = False
    diet_data = None
    if full_reply and _is_diet_record_intent(req.message, full_reply):
        diet_data = _auto_save_diet_if_missing(db, current_user.id, req.message, full_reply)
        if diet_data:
            diet_saved = True
            logger.info(f"[OpenClaw 补录] 用户 {current_user.id} 饮食自动补录成功: {diet_data.get('food_items', '')[:50]}")

    return {
        "reply": full_reply,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "diet_saved": diet_saved,
        "diet_data": diet_data,
    }


@router.get("/conversations", summary="OpenClaw 对话列表")
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    convs = service.get_conversations(current_user.id, limit)
    from app.models.openclaw import OpenClawMessage
    # 批量获取每个对话的最后一条用户消息作为预览
    conv_ids = [c.id for c in convs]
    last_msgs = {}
    if conv_ids:
        from sqlalchemy import func
        subq = (
            db.query(
                OpenClawMessage.conversation_id,
                func.max(OpenClawMessage.id).label("max_id")
            )
            .filter(
                OpenClawMessage.conversation_id.in_(conv_ids),
                OpenClawMessage.role == "user"
            )
            .group_by(OpenClawMessage.conversation_id)
            .subquery()
        )
        rows = (
            db.query(OpenClawMessage.conversation_id, OpenClawMessage.content)
            .join(subq, OpenClawMessage.id == subq.c.max_id)
            .all()
        )
        last_msgs = {r[0]: r[1][:50] for r in rows}
    return [
        {
            "id": c.id,
            "title": c.title,
            "last_message": last_msgs.get(c.id),
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}", summary="OpenClaw 对话详情")
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    conv = service.get_conversation_detail(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "image_url": m.image_url,
                "rating": m.rating,
                "created_at": str(m.created_at),
            }
            for m in conv.messages
        ],
    }


@router.delete("/conversations/{conversation_id}", summary="删除 OpenClaw 对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@router.post("/messages/{message_id}/rate", summary="评价 OpenClaw 消息质量")
async def rate_message(
    message_id: int,
    req: RateMessageRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """对 OpenClaw 助手消息进行 thumbs up/down 评价"""
    message = (
        db.query(OpenClawMessage)
        .join(OpenClawConversation, OpenClawMessage.conversation_id == OpenClawConversation.id)
        .filter(
            OpenClawMessage.id == message_id,
            OpenClawConversation.user_id == current_user.id,
        )
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    message.rating = req.rating
    db.commit()
    return {"ok": True, "message_id": message_id, "rating": req.rating}


@router.get("/rating-stats", summary="OpenClaw 消息评价统计")
async def get_rating_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的 OpenClaw 消息评价统计"""
    base_query = (
        db.query(OpenClawMessage)
        .join(OpenClawConversation, OpenClawMessage.conversation_id == OpenClawConversation.id)
        .filter(
            OpenClawConversation.user_id == current_user.id,
            OpenClawMessage.rating.isnot(None),
        )
    )

    total_rated = base_query.count()
    thumbs_up = base_query.filter(OpenClawMessage.rating == 1).count()
    thumbs_down = base_query.filter(OpenClawMessage.rating == -1).count()
    satisfaction_rate = round(thumbs_up / total_rated, 2) if total_rated > 0 else 0.0

    return {
        "total_rated": total_rated,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "satisfaction_rate": satisfaction_rate,
    }


# ── 饮食记录自动补录工具函数 ────────────────────────────

import re
from datetime import date, datetime

_MEAL_MAP = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner", "加餐": "snack", "宵夜": "snack"}

# 用户必须明确表达"记录某餐 + 食物内容"，排除投诉/询问
_DIET_RECORD_PATTERN = re.compile(
    r"记录\s*(早餐|午餐|晚餐|加餐|宵夜)\s*[：:．]?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
_ATE_PATTERN = re.compile(
    r"(?:刚)?吃了\s*[：:．]?\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
# 排除词：如果消息包含这些词，不是记录意图
_EXCLUDE_KEYWORDS = ["问题", "没有", "为什么", "怎么", "错误", "bug", "失败", "查询", "查看", "分析"]


def _is_diet_record_intent(user_msg: str, ai_reply: str) -> bool:
    """检测用户意图是记录饮食（严格匹配）"""
    msg = user_msg.strip()
    # 排除投诉/询问
    if any(kw in msg for kw in _EXCLUDE_KEYWORDS):
        return False
    # 必须匹配"记录午餐：xxx"或"吃了xxx"格式
    has_record = bool(_DIET_RECORD_PATTERN.search(msg) or _ATE_PATTERN.search(msg))
    # AI 必须声称已记录
    ai_confirmed = bool(re.search(r"(已.{0,4}记录|记录.*✅|补记为)", ai_reply))
    return has_record and ai_confirmed


def _detect_meal_type(user_msg: str) -> str:
    """从用户消息推断餐次"""
    for cn, en in _MEAL_MAP.items():
        if cn in user_msg:
            return en
    hour = datetime.now().hour
    if 5 <= hour < 10:
        return "breakfast"
    elif 10 <= hour < 14:
        return "lunch"
    elif 14 <= hour < 17:
        return "snack"
    elif 17 <= hour < 21:
        return "dinner"
    return "snack"


def _extract_food_and_calories(user_msg: str, ai_reply: str) -> tuple[str, float | None]:
    """从用户消息提取食物描述，从 AI 回复中提取热量"""
    # 食物：从"记录午餐：xxx"或"吃了xxx"中提取
    m = _DIET_RECORD_PATTERN.search(user_msg)
    if m:
        food = m.group(2).strip()
    else:
        m2 = _ATE_PATTERN.search(user_msg)
        food = m2.group(1).strip() if m2 else user_msg
    # 清理多余的标点
    food = re.sub(r"[，。！？]$", "", food).strip()

    # 热量：从 AI 回复中提取 "= 653 kcal" 或 "约550kcal" 或 "热量：400"
    calories = None
    cal_match = re.search(r"[=≈约]\s*([\d,.]+)\s*(?:kcal|千卡|大卡|cal)", ai_reply, re.IGNORECASE)
    if cal_match:
        try:
            calories = float(cal_match.group(1).replace(",", ""))
        except ValueError:
            pass
    if not calories:
        cal_match2 = re.search(r"([\d,.]+)\s*(?:kcal|千卡)", ai_reply, re.IGNORECASE)
        if cal_match2:
            try:
                calories = float(cal_match2.group(1).replace(",", ""))
                # 排除太大的数字（可能是总热量统计而非单餐）
                if calories > 3000:
                    calories = None
            except ValueError:
                pass

    return food, calories


def _auto_save_diet_if_missing(db, user_id: int, user_msg: str, ai_reply: str) -> dict | None:
    """检查今天是否已有对应餐次记录，没有则自动补录（含热量）"""
    from app.models.daily_health import DietRecord
    from datetime import timedelta

    meal_type = _detect_meal_type(user_msg)
    today = date.today()

    # 检查最近 90 秒内是否已有记录（Skill 可能已调用 API）
    existing = db.query(DietRecord).filter(
        DietRecord.user_id == user_id,
        DietRecord.record_date == today,
        DietRecord.meal_type == meal_type,
        DietRecord.created_at >= datetime.now() - timedelta(seconds=90),
    ).first()

    if existing:
        return None  # Skill 已经正确记录了

    food_items, calories = _extract_food_and_calories(user_msg, ai_reply)

    record = DietRecord(
        user_id=user_id,
        record_date=today,
        meal_type=meal_type,
        food_items=food_items,
        calories=calories,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "meal_type": meal_type,
        "food_items": food_items,
        "calories": calories,
        "record_date": str(today),
    }
