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
import re
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.ai_consent import require_ai_consent

logger = logging.getLogger(__name__)

# CosyVoice 默认会把 "3.6千米" 里的 "." 吞掉读成 "3 6千米". 把数字间的小数点
# 替换成 "点" 让模型按中文习惯读. IP / 版本号 (1.0.2) / 比分 (3:1) 也能正确处理.
_DECIMAL_RE = re.compile(r"(?<=\d)\.(?=\d)")


def _normalize_for_tts(text: str) -> str:
    """把阿拉伯数字之间的英文 '.' 替换成中文 '点', 让 CosyVoice 念得出来."""
    return _DECIMAL_RE.sub("点", text)

VOICE_MAP = {
    # cosyvoice-v2 真人级音质. voice id 带 _v2 后缀.
    # 当前账号未开 longyuetw (台腔), 用 longjiayi (港普) 作最接近"林志玲感"的合法选项.
    "soft_hk_female": "longjiayi_v2",     # 港普女声, 柔软温暖, 默认推荐
    "warm_female": "longwan_v2",           # 温暖女声
    "gentle_cs_female": "longyue_v2",      # 温柔女声, 标普
    "knowing_female": "longxiaochun_v2",   # 知性女声
    "casual_female": "longxiaobai_v2",     # 休闲女声, 自然
    "calm_male": "longcheng_v2",           # 沉稳男声
}
DEFAULT_VOICE_KEY = "cloned_private_female"  # 优先用户复刻音色; 未配置则降级到 soft_hk_female


def _cloned_voice_id() -> Optional[str]:
    """用户自有的声音复刻 voice_id (target_model=cosyvoice-v3.5-plus)."""
    return getattr(settings, "tts_cloned_voice_id", None)


def _resolve_voice_id(voice_style: str) -> str:
    """voice_style → 实际 voice_id. cloned_* 走用户复刻, 其它走 VOICE_MAP."""
    if voice_style.startswith("cloned_"):
        cid = _cloned_voice_id()
        if cid:
            return cid
        # 未配置复刻音色 → 降级到默认 v2 港普
        return VOICE_MAP["soft_hk_female"]
    return VOICE_MAP.get(voice_style, VOICE_MAP["soft_hk_female"])


def _resolve_model(voice_id: str) -> str:
    """根据 voice_id 自动选模型. 复刻音色 id 是 cosyvoice-v3.5-plus-bailian-... 前缀."""
    if voice_id.startswith("cosyvoice-v3.5-plus"):
        return "cosyvoice-v3.5-plus"
    if voice_id.startswith("cosyvoice-v3"):
        return "cosyvoice-v3"
    # 默认 v2 (官方音色 _v2 后缀)
    return settings.tts_model or "cosyvoice-v2"


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

    require_ai_consent(destination=dashscope.base_websocket_api_url)

    key = _resolve_api_key()
    if not key:
        raise RuntimeError("TTS API key 未配置")
    dashscope.api_key = key

    model = _resolve_model(voice_id)
    # SDK 参数: speech_rate 在 v2 不是每个 voice 都支持, 先不传, 避免 400.
    # 需要变速可以走客户端播放速率.
    synth = SpeechSynthesizer(model=model, voice=voice_id)
    audio = synth.call(text)
    if not audio:
        raise RuntimeError(f"TTS 返回空 (model={model}, voice={voice_id})")
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

    require_ai_consent()

    # 进模型前做一次文本规范化 (数字小数点等). 缓存 key 用规范化后的文本,
    # 不然旧 cache 命中会绕过新逻辑.
    normalized = _normalize_for_tts(text)
    voice_id = _resolve_voice_id(voice_style)

    if settings.tts_cache_enabled:
        cache = _cache_path(normalized, voice_id, speed)
        if cache.exists():
            return cache.read_bytes()

    # dashscope SDK 是同步阻塞 I/O → to_thread 放线程池避免卡 event loop
    audio_bytes = await asyncio.to_thread(_synth_blocking, normalized, voice_id, speed)

    if settings.tts_cache_enabled:
        try:
            cache = _cache_path(normalized, voice_id, speed)
            cache.write_bytes(audio_bytes)
        except Exception as e:
            logger.warning("TTS 缓存写入失败: %s", e)

    return audio_bytes


def list_voices() -> list[dict]:
    voices = []
    if _cloned_voice_id():
        voices.append({
            "key": "cloned_private_female",
            "label": "私享女声",
            "description": "专属声音复刻, 真人级 (推荐)",
        })
    voices.extend([
        {"key": "soft_hk_female", "label": "柔软女声", "description": "带港普口音, 温柔有亲和力"},
        {"key": "warm_female", "label": "温暖女声", "description": "温暖自然, 日常播报"},
        {"key": "gentle_cs_female", "label": "温柔女声", "description": "标准普通话, 柔和"},
        {"key": "knowing_female", "label": "知性女声", "description": "清晰知性, 沉稳"},
        {"key": "casual_female", "label": "休闲女声", "description": "自然轻松, 真人感"},
        {"key": "calm_male", "label": "沉稳男声", "description": "低频稳重, 专业感"},
    ])
    return voices
