"""Weather condition tag — 把计划 title 里的天气前缀抽成结构化 tag.

#67 follow-up of #66: 当时短期方案是推送时再剥前缀, 现在把抽取做到入库时:
  - title="雨天力量维护日" → tag="rain"
  - 推送时拿 tag 去比对实际天气, 而不是再用前缀 string 重新猜
"""
from __future__ import annotations

from typing import Optional

# 规范 tag → 这些 title 前缀都映射到它
_TAG_PREFIXES = {
    "rain": ["雷雨日", "阴雨日", "下雨日", "雨天"],
    "snow": ["下雪日", "雪天"],
    "sun": ["大晴天", "晴天"],
    "fog": ["雾霾日", "雾天"],
    "wind": ["大风日"],
    "thunder": ["雷暴日"],
}

# 反查: title 真实天气文本里出现这些字 → 可以认为今天是该 tag
_TAG_KEYWORDS = {
    "rain": ["雨"],
    "snow": ["雪"],
    "sun": ["晴"],
    "fog": ["雾", "霾"],
    "wind": ["风"],
    "thunder": ["雷"],
}


def extract_weather_tag(title: str) -> Optional[str]:
    """从 plan item title 抽出 canonical tag, 没有就返回 None.

    LLM 生成 title 时常自带"雨天/晴天/雾霾日"前缀, 这是隐式约束 — 把它扶正.
    """
    if not title:
        return None
    for tag, prefixes in _TAG_PREFIXES.items():
        for prefix in prefixes:
            if title.startswith(prefix):
                return tag
    return None


def weather_text_matches_tag(actual_weather: str, tag: Optional[str]) -> bool:
    """实际天气文本(从 weather API 来) 是否仍然匹配该 tag.

    actual_weather 空 / tag 空 → 视为不匹配 (推送时不剥前缀).
    """
    if not tag or not actual_weather:
        return False
    keywords = _TAG_KEYWORDS.get(tag, [])
    return any(k in actual_weather for k in keywords)


def strip_tag_prefix(title: str, tag: Optional[str]) -> str:
    """剥掉 title 里属于该 tag 的前缀 (含分隔符), 用于天气不符时清理推送文案."""
    if not title or not tag:
        return title
    for prefix in _TAG_PREFIXES.get(tag, []):
        if title.startswith(prefix):
            stripped = title[len(prefix):].lstrip(" -—_:,，·")
            return stripped or title
    return title
