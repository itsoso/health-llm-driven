"""
阿里云 DashScope CosyVoice TTS — 通过官方 dashscope SDK 调用.

为什么不用 REST:
  REST endpoint 是异步 task 模型 (需要 X-DashScope-Async: enable + 轮询 task_id),
  直接同步调会报 "task can not be null". SDK 的 SpeechSynthesizer 封装了这些细节,
  直接返回 audio bytes, 用起来简单.

为什么要后端代理:
  1. DashScope API key 不能泄露到客户端
  2. 句级缓存 — 同一段文本多用户共享 mp3, 省钱
  3. Provider 切换 (未来上 VoxCPM 自部署) 不用发 mobile 新版本

Voice IP 合规:
  - longxiaochun / longwan / longxiaoxia / longcheng 都是阿里云官方授权声库
  - 不使用"林志玲"等真人明星本名 (民法典 1023 条声音权)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

VOICE_MAP = {
    # 注: 当前账号未开通 cosyvoice-v2, 只能用 v1 音色.
    # v1 不支持 longyuetw (台腔); longjiayi (港普女声) 是目前最接近"林志玲柔声"的合法选项.
    "soft_hk_female": "longjiayi",     # 港普女声, 带轻微港腔, 柔软
    "warm_female": "longyuan",          # 温暖女声
    "gentle_cs_female": "longyue",      # 温柔女声, 标普
    "knowing_female": "longxiaochun",   # 知性女声
    "calm_male": "longcheng",           # 沉稳男声
}
DEFAULT_VOICE_KEY = "soft_hk_female"


def _resolve_api_key() -> Optional[str]:
    return settings.tts_api_key or settings.llm_vision_api_key


def _cache_path(text: str, voice_id: str, speed: float) -> Path:
    base = Path(settings.tts_cache_dir)
    base.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{voice_id}|{speed:.2f}|{text}".encode("utf-8")).hexdigest()
    return base / f"{key}.mp3"


def _synth_blocking(text: str, voice_id: str, speed: float) -> bytes:
    """阻塞调 DashScope SDK. dashscope 没原生 async 接口, 外层用 to_thread 包."""
    import dashscope
    from dashscope.audio.tts_v2 import SpeechSynthesizer

    key = _resolve_api_key()
    if not key:
        raise RuntimeError("TTS API key 未配置")
    dashscope.api_key = key

    # SDK 参数: speech_rate 在 v2 不是每个 voice 都支持, 先不传, 避免 400.
    # 需要变速可以走客户端播放速率.
    synth = SpeechSynthesizer(model=settings.tts_model, voice=voice_id)
    audio = synth.call(text)
    if not audio:
        raise RuntimeError("TTS 返回空")
    return audio


async def synthesize(
    text: str,
    voice_style: str = DEFAULT_VOICE_KEY,
    speed: float = 1.0,
) -> bytes:
    """
    合成 text 为 mp3 字节流. 句级缓存命中时秒返.
    """
    if not text or not text.strip():
        raise ValueError("text 不能为空")

    voice_id = VOICE_MAP.get(voice_style, VOICE_MAP[DEFAULT_VOICE_KEY])

    if settings.tts_cache_enabled:
        cache = _cache_path(text, voice_id, speed)
        if cache.exists():
            return cache.read_bytes()

    # dashscope SDK 是同步阻塞 I/O → to_thread 放线程池避免卡 event loop
    audio_bytes = await asyncio.to_thread(_synth_blocking, text, voice_id, speed)

    if settings.tts_cache_enabled:
        try:
            cache = _cache_path(text, voice_id, speed)
            cache.write_bytes(audio_bytes)
        except Exception as e:
            logger.warning("TTS 缓存写入失败: %s", e)

    return audio_bytes


def list_voices() -> list[dict]:
    return [
        {"key": "soft_hk_female", "label": "柔软女声", "description": "带轻微港腔, 温柔有亲和力 (推荐)"},
        {"key": "warm_female", "label": "温暖女声", "description": "温暖自然, 日常播报"},
        {"key": "gentle_cs_female", "label": "温柔女声", "description": "标准普通话, 柔和"},
        {"key": "knowing_female", "label": "知性女声", "description": "清晰知性, 沉稳"},
        {"key": "calm_male", "label": "沉稳男声", "description": "低频稳重, 专业感"},
    ]
