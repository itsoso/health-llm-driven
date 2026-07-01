# -*- coding: utf-8 -*-
"""多模态录入 —— 化验报告拍照 → 结构化化验项(Next Horizon Tier 5)。

冷启动/数据稀疏最大摩擦是手动录入。用 vision LLM 把化验单照片解析成 {项目,值,单位},
用户确认后即可导入 → 喂 Twin/PhenoAge。复用既有 vision provider(chat_with_vision)。

诚实:JSON 解析是确定性、可测;但**真实 OCR 准确率需现场验证**(vision 非确定性),
故解析结果须用户确认后再入库,不直接落库。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services.json_lenient import lenient_loads

_VISION_PROMPT = """你是化验单 OCR 解析器。从这张化验报告图片里提取所有检验项目。
只返回 JSON,不要解释:
{"items": [{"item_name": "项目中文名", "value": "数值(纯数字字符串)", "unit": "单位或null"}]}
规则:
- 只提取有明确数值的检验项;无数值的(如"阴性"文字结论)跳过
- value 用纯数字字符串(去掉 ↑↓ 箭头和参考区间)
- 看不清/没有化验项 → {"items": []}"""


def _extract_json(text: str) -> str:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        return text[first:last + 1]
    return text


def parse_lab_items(raw_text: str) -> list[dict[str, Any]]:
    """从 vision 返回文本解析出化验项(纯函数,可测)。

    只保留有 item_name + 可转 float 的 value 的项;value 去箭头;脏数据丢弃不猜。
    """
    try:
        # 先做 brace 抽取(从含散文的 vision 输出里割出 JSON 对象,lenient_loads 不做这步),
        # 再走宽松解析(弯引号/全角分隔符/裸 key/尾逗号);仍不可修复时 lenient_loads 抛
        # json.JSONDecodeError(ValueError 子类)→ 被下方 except 接住,fail-soft 返回 []。
        data = lenient_loads(_extract_json(raw_text))
    except (ValueError, TypeError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (it.get("item_name") or "").strip()
        raw_val = str(it.get("value") if it.get("value") is not None else "").strip()
        cleaned = re.sub(r"[↑↓⬆⬇\s]", "", raw_val)
        if not name or not cleaned:
            continue
        try:
            val = float(cleaned)
        except ValueError:
            continue  # 非数值 → 丢弃,不猜
        unit = it.get("unit")
        out.append({"item_name": name, "value": val,
                    "unit": (str(unit).strip() if unit else None)})
    return out


async def parse_lab_photo(image_base64: str, image_type: str = "jpeg") -> list[dict[str, Any]]:
    """化验单照片 → 结构化化验项(vision LLM)。解析结果供用户确认,不直接入库。"""
    from app.services.llm import get_vision_provider

    provider = get_vision_provider()
    data_url = f"data:image/{image_type};base64,{image_base64}"
    raw: Optional[str] = await provider.chat_with_vision(
        messages=[
            {"role": "system", "content": _VISION_PROMPT},
            {"role": "user", "content": "请解析这张化验单的所有检验项目"},
        ],
        image_url=data_url,
        temperature=0.0,
        # 化验单项目多时 1500 token 会截断结构化输出。active 模型实测接受 ≥32000,
        # 放开到 16000 覆盖整张化验单(同 pdf_parser / medical_report_ocr)。
        max_tokens=16000,
    )
    return parse_lab_items(raw or "")
