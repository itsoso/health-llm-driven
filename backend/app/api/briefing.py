"""
GET /api/v1/briefing/voice-script        — 今日晨间简报 (60-90 字, A 改进)
GET /api/v1/briefing/weekly-voice-script — 本周回顾 (80-150 字, E 改进)
GET /api/v1/briefing/preworkout-voice-script — 跑前 readiness 建议 (60-100 字, F 改进)

为什么共用 briefing prefix:
  都是 "时间窗口语音稿" 同语义 — daily / weekly / preworkout 只是触发场景不同.
  同一份缓存机制, 同一份 voice-chat ?intent=* 入口, 减少分裂.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, get_db
from app.models.user import User
from app.services.briefing_voice_script import build_voice_script
from app.services.weekly_review_voice_script import build_weekly_review_voice_script
from app.services.preworkout_voice_script import build_preworkout_voice_script
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefing", tags=["briefing"])


class VoiceScriptResponse(BaseModel):
    script: str
    char_count: int
    generated_at: str
    target_date: str  # YYYY-MM-DD


# 简易内存缓存 (单进程; 多 worker 各自缓存, 没必要走 Redis 增加依赖).
# key: (user_id, "daily"|"weekly", date_str) → (script, ts)
_CACHE: dict[tuple[int, str, str], tuple[str, datetime]] = {}
_CACHE_TTL_SECONDS = 600  # 10min — 简报内容半天内变化小, 避免聚合重复跑


@router.get("/voice-script", response_model=VoiceScriptResponse)
def get_voice_script(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    now = get_china_now()
    today_str = now.date().isoformat()
    cache_key = (current_user.id, "daily", today_str)

    cached = _CACHE.get(cache_key)
    if cached:
        script, ts = cached
        if (now - ts).total_seconds() < _CACHE_TTL_SECONDS:
            return VoiceScriptResponse(
                script=script,
                char_count=len(script),
                generated_at=ts.isoformat(),
                target_date=today_str,
            )

    script = build_voice_script(db, current_user.id, target_date=now.date())
    _CACHE[cache_key] = (script, now)

    return VoiceScriptResponse(
        script=script,
        char_count=len(script),
        generated_at=now.isoformat(),
        target_date=today_str,
    )


@router.get("/weekly-voice-script", response_model=VoiceScriptResponse)
def get_weekly_voice_script(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """本周回顾语音稿 (E 产品改进 - 周聊).

    voice-chat ?intent=weekly 进入时拉, 私享女声播完进 listening 接话.
    建议周日 20:00 推送时调用; 也支持用户主动从设置/分析页"听听本周"按钮触发.
    """
    now = get_china_now()
    today_str = now.date().isoformat()
    cache_key = (current_user.id, "weekly", today_str)

    cached = _CACHE.get(cache_key)
    if cached:
        script, ts = cached
        if (now - ts).total_seconds() < _CACHE_TTL_SECONDS:
            return VoiceScriptResponse(
                script=script,
                char_count=len(script),
                generated_at=ts.isoformat(),
                target_date=today_str,
            )

    script = build_weekly_review_voice_script(db, current_user.id, today=now.date())
    _CACHE[cache_key] = (script, now)

    return VoiceScriptResponse(
        script=script,
        char_count=len(script),
        generated_at=now.isoformat(),
        target_date=today_str,
    )


@router.get("/preworkout-voice-script", response_model=VoiceScriptResponse)
def get_preworkout_voice_script(
    workout_type: Optional[str] = Query(default=None, description="预期运动类型: running/cycling/strength/yoga/..."),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """跑前/练前 readiness 建议短稿 (F 产品改进).

    用法:
      mobile 首页 '马上要运动' 按钮 → 跳 /voice-chat?intent=preworkout&workout_type=running
      → 拉本端点 → 私享女声播 → 接话.

    不缓存 (readiness 数据会随当日心率/压力实时更新; 用户重复点也只是再算一次, 便宜).
    """
    now = get_china_now()
    script = build_preworkout_voice_script(db, current_user.id, workout_type=workout_type)
    return VoiceScriptResponse(
        script=script,
        char_count=len(script),
        generated_at=now.isoformat(),
        target_date=now.date().isoformat(),
    )
