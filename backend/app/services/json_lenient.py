"""宽松 JSON 解析 —— 救 LLM 吐的非法 JSON(弯引号/全角引号/裸 key/尾逗号/控制字符)。

为什么:体检报告等"PDF→LLM→JSON"路径,弱模型/中文语境常吐 `{"x"："y"}`(全角冒号引号)、
`{summary: "…"}`(裸 key)、尾随逗号或内嵌控制字符 → 标准 `json.loads` 抛
`Expecting property name enclosed in double quotes`,用户拿到 HTTP 400(实测 pdf_parser 上传体检
报告烧过)。`agent_executor` 早有同款修复(`_normalize_json_quotes` + 裸 key 补引号),本模块把
它集中成一个可复用、可单测的 `lenient_loads`,供 pdf_parser / lab_photo_parse 等出口共用。

设计铁律:
- **只在严格 `json.loads` 失败后兜底**;合法 JSON 走快路径,零行为变化。
- **修不动时原样抛出"严格解析的原始异常"**(不是修复后的),这样调用方的"截断检测"
  (按原始 pos 判断)仍准确 —— 截断 ≠ 格式错误,要给不同的用户指引(分次导入 vs 重试)。
- 只补 **key 位置** 的引号(`{`/`,` 之后、`:` 之前的裸标识符),绝不动 value(避免把中文值误加引号)。
- 加层不减层:只放宽解析,不丢字段、不静默吞。
"""
from __future__ import annotations

import json
import re
from typing import Any

# 弯引号 / 全角引号 → 直引号(与 agent_executor._normalize_json_quotes 同表,单一语义)
_SMART_DOUBLE_QUOTES = "“”„‟″＂"
_SMART_SINGLE_QUOTES = "‘’‚‛′＇"
_QUOTE_NORMALIZE_TABLE = str.maketrans(
    {ord(c): '"' for c in _SMART_DOUBLE_QUOTES} | {ord(c): "'" for c in _SMART_SINGLE_QUOTES}
)
# 全角冒号 / 逗号(LLM 中文语境常混入分隔符位)
_FULLWIDTH_SEP_TABLE = str.maketrans({"：": ":", "，": ",", "｛": "{", "｝": "}", "［": "[", "］": "]"})

# 非法的裸控制字符(JSON 字符串里 U+0000–U+001F 必须转义);保留 \t \n \r 以免破坏合法转义后的内容
_ILLEGAL_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# 裸 key:`{` 或 `,` 之后、`:` 之前的未加引号 ASCII 标识符 → 补双引号(不碰 value)
_BARE_KEY_RE = re.compile(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)')
# 尾随逗号:`,}` / `,]`
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # 去掉首尾 ``` 围栏(含可选的 ```json)
        t = _FENCE_RE.sub("", t).strip()
        # 末尾可能仍残留 ```
        if t.endswith("```"):
            t = t[:-3].strip()
    return t


def lenient_loads(raw: Any) -> Any:
    """尽力把 LLM 输出解析成 dict/list。

    严格解析优先;失败后跑修复阶梯(去围栏→去控制字符→引号/分隔符归一→裸 key 补引号→去尾逗号)。
    全部失败时**抛出严格解析的原始 json.JSONDecodeError**(供调用方做截断/格式判别)。
    """
    if raw is None:
        raise json.JSONDecodeError("empty input", "", 0)
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        raw = str(raw)

    text = _strip_code_fence(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_err:
        repaired = _ILLEGAL_CTRL_RE.sub("", text)
        repaired = repaired.translate(_QUOTE_NORMALIZE_TABLE)
        repaired = repaired.translate(_FULLWIDTH_SEP_TABLE)
        repaired = _BARE_KEY_RE.sub(r'\1"\2"\3', repaired)
        repaired = _TRAILING_COMMA_RE.sub(r"\1", repaired)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            # 修不动 → 抛原始严格异常(pos 对应原始 text,截断检测仍准),不假装成功
            raise first_err
