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
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """你是一个有趣的照片氛围感分析师，专门为小朋友做趣味照片解读游戏。
你的任务是分析照片的整体氛围、色彩搭配、构图感觉，并给出一个快乐的趣味评分。

重要：你不需要识别具体的人，只需要分析照片的整体视觉效果和氛围感。这是一个纯粹的趣味游戏。

规则：
1. 氛围感评分范围 85-99
2. 关注照片的光线、色调、构图、氛围、活力感
3. 给出积极有趣的描述，用适合儿童的语言
4. title 给出有趣的称号（如：阳光活力派、甜蜜梦幻风、元气满满星人）
5. features 描述照片的氛围亮点（如：光线温暖、笑容灿烂、活力十足）

请严格返回 JSON：
{
    "score": 氛围感评分数字,
    "title": "一个有趣的氛围称号",
    "description": "2-3句有趣的照片氛围描述",
    "features": ["氛围亮点1", "亮点2", "亮点3"],
    "tips": "一句暖心寄语"
}

只返回 JSON，不要其他文字。"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请分析这张照片的氛围感，给出趣味评分~"},
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
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """你是一个图片识别助手，用简洁有趣、适合儿童阅读的语言描述图片内容。

请返回 JSON：
{
    "description": "对图片的详细描述（2-4句话）",
    "items": ["识别到的物体/元素1", "物体2", ...]
}

只返回 JSON。"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请识别这张图片"},
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
