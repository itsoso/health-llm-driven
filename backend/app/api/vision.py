"""
视觉分析 API - 颜值测试、图片识别
使用 GPT-4 Vision
"""
import base64
import json
import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.api.auth import get_current_user_required

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vision", tags=["vision"])

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def _get_client():
    if not OPENAI_AVAILABLE or not settings.openai_api_key:
        return None
    kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)


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


class RecognitionResponse(BaseModel):
    success: bool
    description: str = ""
    items: list[str] = []
    error: str = ""


@router.post("/beauty", response_model=BeautyResponse, summary="颜值测试")
async def analyze_beauty(
    req: ImageAnalysisRequest,
    current_user: User = Depends(get_current_user_required),
):
    """拍照测颜值 - 给出趣味评分和夸奖"""
    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="AI 服务不可用")

    try:
        data_url = f"data:image/{req.image_type};base64,{req.image_base64}"
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a fun photography critique assistant for a children's game.
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
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please analyze the photography qualities of this image for our fun kids game!"},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "low"}
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.7,
        )

        raw = response.choices[0].message.content or ""
        json_str = _extract_json(raw)
        result = json.loads(json_str)
        return BeautyResponse(
            success=True,
            score=result.get("score", 90),
            title=result.get("title", ""),
            description=result.get("description", ""),
            features=result.get("features", []),
            tips=result.get("tips", ""),
        )
    except json.JSONDecodeError:
        logger.error(f"颜值分析 JSON 解析失败: {raw[:300]}")
        return BeautyResponse(success=False, error="分析结果解析失败，请重试")
    except Exception as e:
        logger.error(f"颜值分析失败: {e}")
        return BeautyResponse(success=False, error="分析失败，请重试")


@router.post("/recognize", response_model=RecognitionResponse, summary="图片识别")
async def recognize_image(
    req: ImageAnalysisRequest,
    current_user: User = Depends(get_current_user_required),
):
    """通用图片识别 - 识别图片中的物体、场景等"""
    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="AI 服务不可用")

    try:
        data_url = f"data:image/{req.image_type};base64,{req.image_base64}"
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an image description assistant for a children's app.
Describe the scene, objects, colors, and environment in the image using fun, child-friendly Chinese language.
DO NOT identify, name, or describe any specific individuals.
Only describe objects, scenes, animals, plants, colors, and environment.

Return ONLY this JSON:
{
    "description": "detailed description in Chinese (2-4 sentences)",
    "items": ["object/element 1 in Chinese", "element 2", ...]
}"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please describe the objects and scene in this image"},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "low"}
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.3,
        )

        raw = response.choices[0].message.content or ""
        json_str = _extract_json(raw)
        result = json.loads(json_str)
        return RecognitionResponse(
            success=True,
            description=result.get("description", ""),
            items=result.get("items", []),
        )
    except json.JSONDecodeError:
        logger.error(f"图片识别 JSON 解析失败")
        return RecognitionResponse(success=False, error="识别结果解析失败，请重试")
    except Exception as e:
        logger.error(f"图片识别失败: {e}")
        return RecognitionResponse(success=False, error="识别失败，请重试")
