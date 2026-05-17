"""医疗文本标准化管道 — 将自然语言转为结构化健康数据

支持输入：
- "血压150/95" → {type: "blood_pressure", systolic: 150, diastolic: 95}
- "今天吃药了" → {type: "medication_taken"}
- "体重72.5公斤" → {type: "weight", value: 72.5}
- "血糖6.2" → {type: "blood_glucose", value: 6.2}
- "喝了一杯水" → {type: "water", amount: 250}
- "头疼发烧38.5" → {type: "symptom", description: "头疼发烧", temperature: 38.5}
"""
import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── 正则模式匹配（快速路径，不需要 LLM） ──────────────────

PATTERNS = [
    # 血压
    (r"血压\s*(\d{2,3})\s*[/，,]\s*(\d{2,3})", lambda m: {
        "type": "blood_pressure", "systolic": int(m.group(1)), "diastolic": int(m.group(2)),
        "display": f"血压 {m.group(1)}/{m.group(2)} mmHg"
    }),
    # 体重
    (r"体重\s*(\d{2,3}\.?\d?)\s*(公斤|kg|斤)?", lambda m: {
        "type": "weight",
        "value": float(m.group(1)) * 0.5 if m.group(2) == "斤" else float(m.group(1)),
        "unit": "kg",
        "display": f"体重 {float(m.group(1))}{'斤' if m.group(2) == '斤' else 'kg'}"
    }),
    # 血糖
    (r"血糖\s*(\d{1,2}\.?\d?)", lambda m: {
        "type": "blood_glucose", "value": float(m.group(1)), "unit": "mmol/L",
        "display": f"血糖 {m.group(1)} mmol/L"
    }),
    # 体温
    (r"(?:体温|发烧)\s*(\d{2}\.?\d?)\s*度?", lambda m: {
        "type": "temperature", "value": float(m.group(1)),
        "display": f"体温 {m.group(1)}°C"
    }),
    # 心率
    (r"心率\s*(\d{2,3})", lambda m: {
        "type": "heart_rate", "value": int(m.group(1)),
        "display": f"心率 {m.group(1)} bpm"
    }),
    # 饮水
    (r"(?:喝了?|饮水?)\s*(?:一杯|一瓶|半杯|两杯)?.*?(\d+)\s*(?:ml|毫升)?", lambda m: {
        "type": "water", "amount": int(m.group(1)),
        "display": f"饮水 {m.group(1)}ml"
    }),
    (r"(?:喝了?|饮水?)一杯水", lambda m: {
        "type": "water", "amount": 250,
        "display": "饮水 250ml"
    }),
    # 服药
    (r"(?:吃了?|服了?).*?药", lambda m: {
        "type": "medication_taken",
        "display": "已服药"
    }),
]


LAB_INDICATORS = [
    {
        "code": "ALT",
        "name": "谷丙转氨酶",
        "category": "liver_function",
        "unit": "U/L",
        "aliases": ["ALT", "谷丙转氨酶", "丙氨酸氨基转移酶", "丙氨酸转氨酶"],
    },
    {
        "code": "AST",
        "name": "谷草转氨酶",
        "category": "liver_function",
        "unit": "U/L",
        "aliases": ["AST", "谷草转氨酶", "天门冬氨酸氨基转移酶", "天冬氨酸氨基转移酶"],
    },
    {
        "code": "GGT",
        "name": "谷氨酰转肽酶",
        "category": "liver_function",
        "unit": "U/L",
        "aliases": ["GGT", "γ-谷氨酰转肽酶", "γ谷氨酰转肽酶", "谷氨酰转肽酶", "谷氨酰转移酶"],
    },
    {
        "code": "CHE",
        "name": "胆碱酯酶",
        "category": "liver_function",
        "unit": "U/L",
        "aliases": ["CHE", "胆碱酯酶"],
    },
    {
        "code": "TBIL",
        "name": "总胆红素",
        "category": "liver_function",
        "unit": "μmol/L",
        "aliases": ["TBIL", "总胆红素"],
    },
    {
        "code": "DBIL",
        "name": "直接胆红素",
        "category": "liver_function",
        "unit": "μmol/L",
        "aliases": ["DBIL", "直接胆红素", "结合胆红素"],
    },
    {
        "code": "CREA",
        "name": "肌酐",
        "category": "kidney_function",
        "unit": "μmol/L",
        "aliases": ["CREA", "Cr", "CRE", "肌酐", "血肌酐"],
    },
    {
        "code": "BUN",
        "name": "尿素氮",
        "category": "kidney_function",
        "unit": "mmol/L",
        "aliases": ["BUN", "尿素氮", "尿素"],
    },
    {
        "code": "UA",
        "name": "尿酸",
        "category": "kidney_function",
        "unit": "μmol/L",
        "aliases": ["UA", "尿酸", "血尿酸"],
    },
    {
        "code": "FBG",
        "name": "空腹血糖",
        "category": "glucose",
        "unit": "mmol/L",
        "aliases": ["FBG", "FPG", "空腹血糖", "葡萄糖"],
    },
    {
        "code": "HCY",
        "name": "同型半胱氨酸",
        "category": "cardiovascular",
        "unit": "μmol/L",
        "aliases": ["HCY", "Hcy", "同型半胱氨酸", "同型半胱酸"],
    },
]

_LAB_UNITS_RE = r"(?:U/L|IU/L|μmol/L|umol/L|µmol/L|mmol/L|mg/dL|g/L|%)"


def parse_lab_indicators_from_text(text: str) -> list[dict[str, Any]]:
    """Extract multi-indicator lab panels from pasted/chat OCR text.

    This parser is deliberately deterministic. LLM output may mention values in
    prose, but persistence needs stable item codes so Twin and KB conditions can
    read the newest liver/kidney labs immediately.
    """

    if not text:
        return []

    normalized = (
        text.replace("μ", "µ")
        .replace("（", "(")
        .replace("）", ")")
        .replace("：", ":")
        .replace("，", ",")
        .replace("；", ";")
    )
    items_by_code: dict[str, dict[str, Any]] = {}
    for indicator in LAB_INDICATORS:
        code = indicator["code"]
        aliases = sorted(indicator["aliases"], key=len, reverse=True)
        alias_re = "|".join(re.escape(alias) for alias in aliases)
        pattern = re.compile(
            rf"(?P<alias>{alias_re})[^\d\-+]{{0,32}}"
            rf"(?P<value>\d{{1,4}}(?:\.\d+)?)\s*"
            rf"(?P<unit>{_LAB_UNITS_RE})?"
            rf"\s*(?P<flag>[↑↓HhLl高低偏高偏低]*)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(normalized):
            try:
                value = float(match.group("value"))
            except (TypeError, ValueError):
                continue
            flag = (match.group("flag") or "").strip()
            is_abnormal = "normal"
            if any(token in flag for token in ("↑", "H", "h", "高", "偏高")):
                is_abnormal = "high"
            elif any(token in flag for token in ("↓", "L", "l", "低", "偏低")):
                is_abnormal = "low"

            unit = (match.group("unit") or indicator["unit"]).replace("µ", "μ")
            current = items_by_code.get(code)
            if current is not None and current.get("is_abnormal") != "normal":
                continue
            items_by_code[code] = {
                "item_name": indicator["name"],
                "item_code": code,
                "name_en": code,
                "category": indicator["category"],
                "value": value,
                "unit": unit,
                "is_abnormal": is_abnormal,
                "result": {"high": "偏高", "low": "偏低"}.get(is_abnormal, "正常"),
                "notes": "由聊天/文本自动解析",
            }

    return list(items_by_code.values())


def parse_medical_text(text: str) -> Optional[Dict[str, Any]]:
    """
    尝试用正则快速解析医疗文本。

    Returns:
        解析结果 dict，或 None（需要 LLM 兜底）
    """
    text = text.strip()
    lab_items = parse_lab_indicators_from_text(text)
    if len(lab_items) >= 2:
        return {
            "type": "medical_exam",
            "items": lab_items,
            "display": f"识别到 {len(lab_items)} 项化验指标",
        }

    for pattern, handler in PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                result = handler(match)
                result["raw_text"] = text
                result["parse_method"] = "regex"
                return result
            except Exception as e:
                logger.warning(f"正则解析失败 pattern={pattern}: {e}")
                continue
    return None


async def parse_medical_text_with_llm(text: str) -> Optional[Dict[str, Any]]:
    """
    用 LLM 解析无法正则匹配的医疗文本。

    用于：复杂描述、症状记录、模糊表达。
    """
    try:
        from app.services.llm import get_llm_provider
        from app.services.llm.usage_tracker import set_caller
        set_caller("medical_text_parser.parse_with_llm")
        llm = get_llm_provider()

        messages = [
            {"role": "system", "content": (
                "你是医疗数据解析助手。将用户的自然语言转为结构化 JSON。\n"
                "支持的类型：\n"
                '- 血压: {"type":"blood_pressure","systolic":数值,"diastolic":数值}\n'
                '- 体重: {"type":"weight","value":数值,"unit":"kg"}\n'
                '- 血糖: {"type":"blood_glucose","value":数值,"unit":"mmol/L"}\n'
                '- 体温: {"type":"temperature","value":数值}\n'
                '- 心率: {"type":"heart_rate","value":数值}\n'
                '- 饮水: {"type":"water","amount":毫升数}\n'
                '- 服药: {"type":"medication_taken","drug_name":"药名(如果提到)"}\n'
                '- 症状: {"type":"symptom","description":"症状描述"}\n'
                '- 无法识别: {"type":"unknown","description":"原文"}\n'
                "只返回 JSON，不要其他文字。"
            )},
            {"role": "user", "content": text},
        ]
        resp = await llm.chat(messages, temperature=0.1)

        resp_text = resp.strip()
        if resp_text.startswith("```"):
            resp_text = resp_text.split("```")[1].strip()
            if resp_text.startswith("json"):
                resp_text = resp_text[4:].strip()

        result = json.loads(resp_text)
        result["raw_text"] = text
        result["parse_method"] = "llm"
        return result

    except Exception as e:
        logger.warning(f"LLM 医疗文本解析失败: {e}")
        return {"type": "unknown", "description": text, "raw_text": text, "parse_method": "failed"}


async def parse_and_route(text: str) -> Dict[str, Any]:
    """
    统一入口：先正则快速匹配，失败则 LLM 兜底。

    Returns:
        {type, ..., raw_text, parse_method, api_action}
    """
    # 快速路径
    result = parse_medical_text(text)

    # LLM 兜底
    if result is None:
        result = await parse_medical_text_with_llm(text)

    # 映射到 API action
    if result:
        result["api_action"] = _map_to_api_action(result)

    return result


def _map_to_api_action(parsed: Dict) -> Optional[Dict[str, str]]:
    """将解析结果映射到具体的后端 API 调用"""
    t = parsed.get("type")

    if t == "blood_pressure":
        return {
            "method": "POST",
            "endpoint": "/blood-pressure/records",
            "body": {"systolic": parsed["systolic"], "diastolic": parsed["diastolic"]},
        }
    elif t == "weight":
        return {
            "method": "POST",
            "endpoint": "/weight/records",
            "body": {"weight": parsed["value"]},
        }
    elif t == "blood_glucose":
        return {
            "method": "POST",
            "endpoint": "/blood-pressure/records",  # 暂无独立血糖端点，记录为备注
            "body": {"notes": f"血糖 {parsed['value']} {parsed.get('unit', '')}"},
        }
    elif t == "water":
        return {
            "method": "POST",
            "endpoint": f"/water/records/quick?amount={parsed.get('amount', 250)}",
            "body": None,
        }
    elif t == "medication_taken":
        return {
            "method": "POST",
            "endpoint": "/family-health/medications/FIRST_ACTIVE/take",  # 需要运行时替换
            "body": None,
            "note": "需要先查询用户的活跃药物列表",
        }
    elif t == "temperature":
        return {
            "method": "NOTE",
            "endpoint": None,
            "body": {"temperature": parsed["value"]},
            "note": "体温记录暂存为健康事件",
        }
    elif t == "symptom":
        return {
            "method": "NOTE",
            "endpoint": None,
            "body": {"description": parsed.get("description", "")},
            "note": "症状记录暂存为健康事件",
        }

    return None
