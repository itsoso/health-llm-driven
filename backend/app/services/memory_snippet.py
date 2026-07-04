"""memory_snippet — 把可能带脏数据的记忆文本整形成能直接给 UI 的短句。

WHY (2026-07-04 修复, founder 首页截图):
chat opener 的"我记得你 X"直接把 `ConversationMemory.content` /
`MemoryFact.object_value` 塞给前端。历史上上游抽取器过度提取, 有些行存的是
整段 JSON blob (`…按说明书需要时服用。", "注意事项": "有肝病时慎用…`), 直接
serve 给用户就是一坨 JSON key 碎片。

修复选型 — 服务端整形, 不做数据迁移:
- 脏数据已经落库 (over-extraction 是已知历史问题家族), 迁移是另一条工单;
  这里在 serving 边界做纯函数整形, 让坏数据不再泄漏到 UI。
- 整形不出合理内容 (剥离后 < 6 字) → 返回 None, 调用方 SKIP 这条 opener。
  "没有线索"比"一坨垃圾"好。
- 遇到 blob 形态时打一条 (限流) WARNING, 用于量化上游问题规模。

纯函数, 无 DB / 无 LLM。
"""
from __future__ import annotations

import json
import logging
import re
import time

logger = logging.getLogger(__name__)

# 整形后仍 < 该长度视为"没剩下有意义的内容" → 返回 None。
_MIN_SENSIBLE_LEN = 6

# 句末边界 (在 max_len 内优先截到这些标点之后, 保持句子完整)。
_SENTENCE_ENDINGS = "。！？；!?;"

# JSON blob 特征: 出现 `", "键": "` 这类 key/value 分隔片段。
_JSON_KV_SEP = re.compile(r'["“”]\s*[,，]\s*["“”][^"“”]{1,20}["“”]\s*[:：]\s*["“”]')
# 单个 `"键": "` 起手 (blob 开头没有前置逗号那种)。
_JSON_KEY_LEAD = re.compile(r'["“”][^"“”]{1,20}["“”]\s*[:：]\s*["“”]')
# 花括号 / 中括号 结构字符。
_JSON_BRACES = re.compile(r"[{}\[\]]")


def looks_like_json_blob(text: str) -> bool:
    """启发式判断一段文本是不是 JSON blob 泄漏 (供限流告警 + 判定用)。"""
    if not text:
        return False
    if _JSON_KV_SEP.search(text):
        return True
    # 同时出现结构括号 + 引号包裹的键值冒号 → 高度疑似
    if _JSON_BRACES.search(text) and _JSON_KEY_LEAD.search(text):
        return True
    return False


# ── 限流告警 (避免 opener 高频调用刷爆日志) ──
_last_blob_warn_at = 0.0
_BLOB_WARN_INTERVAL_S = 60.0


def _warn_blob_rate_limited(sample: str) -> None:
    global _last_blob_warn_at
    now = time.monotonic()
    if now - _last_blob_warn_at < _BLOB_WARN_INTERVAL_S:
        return
    _last_blob_warn_at = now
    logger.warning(
        "[memory_snippet] object_value looks like a raw JSON blob "
        "(upstream over-extraction); sanitizing at serve time. sample=%r",
        sample[:80],
    )


def _extract_first_json_value(text: str) -> str | None:
    """若整段文本是良构 JSON object/array, 抽第一个有意义的字符串值。

    e.g. '{"建议":"鼻炎发作时优先冲洗。", "注意事项":"…"}' → "鼻炎发作时优先冲洗。"
    抽不出 (非良构 JSON / 无字符串值) 返回 None, 回退到正则剥离路径。
    """
    s = text.strip()
    if not (s.startswith("{") or s.startswith("[")):
        return None
    try:
        parsed = json.loads(s)
    except (ValueError, TypeError):
        return None

    def _first_str(node: object) -> str | None:
        if isinstance(node, str):
            v = node.strip()
            return v or None
        if isinstance(node, dict):
            for val in node.values():
                got = _first_str(val)
                if got:
                    return got
            return None
        if isinstance(node, list):
            for item in node:
                got = _first_str(item)
                if got:
                    return got
            return None
        return None

    return _first_str(parsed)


def _strip_json_artifacts(text: str) -> str:
    """剥掉 JSON 结构碎片, 只留下值文本 (良构 JSON 走 _extract_first_json_value)。"""
    s = text
    # `", "键": "` / `","键":"` → 断开成句界 (用句号占位, 后面截断会处理)
    s = _JSON_KV_SEP.sub("。", s)
    # 行首 `"键": "` 起手
    s = _JSON_KEY_LEAD.sub("", s)
    # 花括号 / 中括号
    s = _JSON_BRACES.sub("", s)
    # 剩余的孤立引号 (中英文)
    s = re.sub(r'["“”]', "", s)
    # 反斜杠转义残留
    s = s.replace("\\n", " ").replace("\\t", " ").replace("\\", "")
    return s


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate_at_sentence(text: str, max_len: int) -> str:
    """在 max_len 内优先截到句末标点; 只能截在句中时才加省略号。"""
    if len(text) <= max_len:
        return text
    window = text[:max_len]
    # 找窗口内最后一个句末标点
    last_end = -1
    for i, ch in enumerate(window):
        if ch in _SENTENCE_ENDINGS:
            last_end = i
    if last_end >= _MIN_SENSIBLE_LEN - 1:
        # 截到句末标点之后 (含标点), 不加省略号
        return window[: last_end + 1]
    # 句中硬截 → 去掉尾部悬挂标点/分隔符再加省略号
    cut = window.rstrip("，,、;；:： ")
    if not cut:
        cut = window
    return cut + "…"


# "实义字符" = 去掉标点/结构符/空白后剩下的字 (中英文数字)。
_NON_SUBSTANTIVE = re.compile(r'[\s。！？；;:：,，、.、·…"“”\'`{}\[\]()（）<>《》/\\|~^*#%$&+=_-]+')


def _substantive_len(text: str) -> int:
    return len(_NON_SUBSTANTIVE.sub("", text))


def _has_sensible_content(text: str, was_blob: bool) -> bool:
    """判断整形后是否还剩下"有意义内容"。

    - blob 剥离后: 实义字符必须 ≥ 6 (剥完只剩零星碎片 → 无意义)。
    - 干净短句 (未判定为 blob): 只要有 ≥1 个实义字符就通过 (别误杀
      "对花粉过敏" 这类合法 5 字记忆)。
    """
    subs = _substantive_len(text)
    if was_blob:
        return subs >= _MIN_SENSIBLE_LEN
    return subs >= 1


def sanitize_memory_snippet(text: str | None, max_len: int = 50) -> str | None:
    """把记忆文本整形成可直接展示的短句。

    步骤: 剥 JSON 碎片 → 折叠空白 → 句界截断 (超 max_len 才截)。
    整形后 < 6 字 (没剩下有意义内容) → 返回 None, 调用方应 SKIP 这条线索。

    遇到 blob 形态会打一条限流 WARNING 以便量化上游问题。
    """
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None

    is_blob = looks_like_json_blob(raw)
    if is_blob:
        _warn_blob_rate_limited(raw)
        # 良构 JSON → 抽第一个有意义的值; 否则回退正则剥离碎片。
        cleaned = _extract_first_json_value(raw) or _strip_json_artifacts(raw)
    else:
        cleaned = raw

    cleaned = _collapse_ws(cleaned)
    # 去掉整形产生的悬挂句界标点 (开头/连续)
    cleaned = re.sub(r"^[。！？；!?;\s]+", "", cleaned)
    cleaned = re.sub(r"[。！？；!?;]{2,}", "。", cleaned).strip()

    if not _has_sensible_content(cleaned, is_blob):
        return None

    result = _truncate_at_sentence(cleaned, max_len).strip()
    if not _has_sensible_content(result, is_blob):
        return None
    return result
