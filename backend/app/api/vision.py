"""
视觉分析 API - 颜值测试、图片识别
使用统一 LLM Provider
每用户每天最多 10 次
"""
import json
import logging
import re
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.vision_usage import VisionUsageLog
from app.api.auth import get_current_user_required
from app.services.llm import get_vision_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vision", tags=["vision"])

DAILY_LIMIT = 10  # 每用户每天最多次数


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        return match.group(1).strip()
    first = text.find('{')
    last = text.rfind('}')
    if first != -1 and last > first:
        return text[first:last + 1]
    return text


def _get_today_usage(db: Session, user_id: int) -> int:
    """获取用户今日已使用次数"""
    today = date.today()
    return db.query(VisionUsageLog).filter(
        VisionUsageLog.user_id == user_id,
        VisionUsageLog.usage_date == today,
    ).count()


def _record_usage(db: Session, user_id: int, usage_type: str):
    """记录一次使用"""
    log = VisionUsageLog(
        user_id=user_id,
        usage_date=date.today(),
        usage_type=usage_type,
    )
    db.add(log)
    db.commit()


class ImageAnalysisRequest(BaseModel):
    image_base64: str
    image_type: str = "jpeg"


class BeautyResponse(BaseModel):
    success: bool
    score: int = 0
    title: str = ""
    description: str = ""
    features: list[str] = []
    tips: str = ""
    error: str = ""
    remaining: int = DAILY_LIMIT  # 剩余次数


class RecognitionResponse(BaseModel):
    success: bool
    description: str = ""
    items: list[str] = []
    error: str = ""
    remaining: int = DAILY_LIMIT  # 剩余次数


class UsageResponse(BaseModel):
    used: int
    remaining: int
    daily_limit: int


@router.get("/usage", response_model=UsageResponse, summary="查询今日使用次数")
async def get_usage(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户今日视觉API使用情况"""
    used = _get_today_usage(db, current_user.id)
    return UsageResponse(
        used=used,
        remaining=max(0, DAILY_LIMIT - used),
        daily_limit=DAILY_LIMIT,
    )


@router.post("/beauty", response_model=BeautyResponse, summary="颜值测试")
async def analyze_beauty(
    req: ImageAnalysisRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """拍照测颜值 - 给出趣味评分和夸奖"""
    from app.services.llm.usage_tracker import set_caller
    set_caller("vision.beauty", user_id=current_user.id)
    used = _get_today_usage(db, current_user.id)
    remaining = max(0, DAILY_LIMIT - used)
    if remaining <= 0:
        return BeautyResponse(
            success=False,
            error=f"今天已用完 {DAILY_LIMIT} 次，明天再来玩吧~",
            remaining=0,
        )

    try:
        provider = get_vision_provider()
    except Exception:
        raise HTTPException(status_code=503, detail="AI 服务不可用")

    try:
        data_url = f"data:image/{req.image_type};base64,{req.image_base64}"

        system_prompt = """You are a fun photography critique assistant for a children's game.
Your task: analyze the PHOTOGRAPHY QUALITIES of the image — colors, lighting, composition, mood, energy.

IMPORTANT RULES:
- DO NOT identify, name, or analyze any individuals in the photo
- DO NOT comment on anyone's appearance, age, gender, or ethnicity
- ONLY discuss: color palette, lighting quality, composition, overall mood/energy, background elements
- This is a fun photography game for kids, always be positive and encouraging
- Score range: 85-99

Return ONLY this JSON, no other text:
{
    "score": number between 85-99,
    "title": "a fun Chinese title like 阳光活力派 or 甜蜜梦幻风 or 元气满满星人",
    "description": "2-3 fun sentences IN CHINESE describing the photo's mood and energy",
    "features": ["photography highlight 1 IN CHINESE", "highlight 2", "highlight 3"],
    "tips": "one warm encouraging message IN CHINESE"
}"""

        raw = await provider.chat_with_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Please analyze the photography qualities of this image for our fun kids game!"},
            ],
            image_url=data_url,
            temperature=0.7,
            max_tokens=500,
        ) or ""
        json_str = _extract_json(raw)
        result = json.loads(json_str)

        # 成功后记录使用
        _record_usage(db, current_user.id, "beauty")
        new_remaining = remaining - 1

        return BeautyResponse(
            success=True,
            score=result.get("score", 90),
            title=result.get("title", ""),
            description=result.get("description", ""),
            features=result.get("features", []),
            tips=result.get("tips", ""),
            remaining=new_remaining,
        )
    except json.JSONDecodeError:
        logger.error("颜值分析 JSON 解析失败 response_len=%s", len(raw))
        return BeautyResponse(success=False, error="分析结果解析失败，请重试", remaining=remaining)
    except Exception as e:
        logger.error(f"颜值分析失败: {e}")
        return BeautyResponse(success=False, error="分析失败，请重试", remaining=remaining)


@router.post("/recognize", response_model=RecognitionResponse, summary="图片识别")
async def recognize_image(
    req: ImageAnalysisRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """通用图片识别 - 识别图片中的物体、场景等"""
    from app.services.llm.usage_tracker import set_caller
    set_caller("vision.recognize", user_id=current_user.id)
    used = _get_today_usage(db, current_user.id)
    remaining = max(0, DAILY_LIMIT - used)
    if remaining <= 0:
        return RecognitionResponse(
            success=False,
            error=f"今天已用完 {DAILY_LIMIT} 次，明天再来玩吧~",
            remaining=0,
        )

    try:
        provider = get_vision_provider()
    except Exception:
        raise HTTPException(status_code=503, detail="AI 服务不可用")

    try:
        data_url = f"data:image/{req.image_type};base64,{req.image_base64}"

        system_prompt = """You are an image description assistant for a children's app.
Describe the scene, objects, colors, and environment in the image using fun, child-friendly Chinese language.
DO NOT identify, name, or describe any specific individuals.
Only describe objects, scenes, animals, plants, colors, and environment.

Return ONLY this JSON:
{
    "description": "detailed description in Chinese (2-4 sentences)",
    "items": ["object/element 1 in Chinese", "element 2", ...]
}"""

        raw = await provider.chat_with_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Please describe the objects and scene in this image"},
            ],
            image_url=data_url,
            temperature=0.3,
            max_tokens=500,
        ) or ""
        json_str = _extract_json(raw)
        result = json.loads(json_str)

        # 成功后记录使用
        _record_usage(db, current_user.id, "recognize")
        new_remaining = remaining - 1

        return RecognitionResponse(
            success=True,
            description=result.get("description", ""),
            items=result.get("items", []),
            remaining=new_remaining,
        )
    except json.JSONDecodeError:
        logger.error(f"图片识别 JSON 解析失败")
        return RecognitionResponse(success=False, error="识别结果解析失败，请重试", remaining=remaining)
    except Exception as e:
        logger.error(f"图片识别失败: {e}")
        return RecognitionResponse(success=False, error="识别失败，请重试", remaining=remaining)
