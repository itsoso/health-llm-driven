"""
GET /api/v1/briefing/voice-script — 取今日晨间语音简报短稿 (60-90 字).

为什么要单独 endpoint:
  1. mobile voice-chat ?intent=briefing 进来时拉取 → TTS 播
  2. push notification body 也用同一份内容 (锁屏可读 + 听到的一致, 不分裂)
  3. 1 小时 Redis 缓存 — 同一用户 1h 内多次请求 (锁屏点开 + voice-chat 拉) 共享一次 build_twin
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, get_db
from app.models.user import User
from app.services.briefing_voice_script import build_voice_script
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefing", tags=["briefing"])


class VoiceScriptResponse(BaseModel):
    script: str
    char_count: int
    generated_at: str
    target_date: str  # YYYY-MM-DD


# 简易内存缓存 (单进程; 多 worker 各自缓存, 没必要走 Redis 增加依赖).
# key: (user_id, date_str) → (script, ts)
_CACHE: dict[tuple[int, str], tuple[str, datetime]] = {}
_CACHE_TTL_SECONDS = 600  # 10min — 简报内容半天内变化小, 避免 build_twin 重复跑


@router.get("/voice-script", response_model=VoiceScriptResponse)
def get_voice_script(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    now = get_china_now()
    today_str = now.date().isoformat()
    cache_key = (current_user.id, today_str)

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
