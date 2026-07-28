"""
体检报告图片 OCR 服务
复用 vision model 基础设施，从拍照的体检报告中提取结构化指标。
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.services.ai.food_recognition import extract_json_from_text
from app.services.llm import get_vision_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个医学报告识别助手。用户会上传医学报告的照片。
请仔细识别报告内容，提取为结构化JSON。报告分两大类：
1. 数值化验单(血常规/生化/血脂等)：每项有数值+单位+参考范围。
2. 叙述性报告(病理/影像/超声/内镜/心电等)：核心是文字诊断结论，往往没有数值。

返回格式：
{
  "report_category": "numeric_lab | narrative_report",
  "report_type": "血常规|生化|肝功能|肾功能|血脂|甲状腺|尿常规|pathology|imaging|ultrasound|endoscopy|ecg|其他",
  "report_date": "2026-01-15 或 null",
  "institution": "医院名称 或 null",
  "items": [
    {
      "name": "指标中文名 或 诊断条目名(如'病理诊断')",
      "name_en": "英文缩写（如ALT、LDL-C、HbA1c）或 null",
      "value": 数值 或 null,
      "value_text": "非数值结果时逐字照抄的原文，数值项则为 null",
      "unit": "单位 或 null",
      "reference_low": 参考下限或null,
      "reference_high": 参考上限或null,
      "is_abnormal": true/false,
      "abnormal_direction": "high|low|null"
    }
  ],
  "conclusion": "报告结论/诊断全文（逐字照抄，如有）"
}

数值化验单(numeric_lab)注意：
- 数值尽量转为数字，而非字符串；此时 value_text 置 null
- 参考范围如 "3.5-5.5" 拆为 reference_low=3.5, reference_high=5.5
- 箭头↑↓或H/L标记表示异常

叙述性报告(narrative_report，含病理/影像/超声/内镜)注意：
- 完整诊断文字必须放进顶层 "conclusion"，且**逐字照抄**报告原文
- 每一条诊断/结论落一个 item：{"name": 条目名(如"病理诊断"/"影像所见"), "value": null, "value_text": 该条诊断的逐字原文}
- 这类诊断项 value 必须为 null，绝不能把文字硬塞进 value 字段

**严格约束（违反=错误输出）：**
- value_text 与 conclusion 必须是报告原文的**逐字子串**，禁止总结、改写、推断、补全、删减
- 不得新造病名、严重程度、治疗建议；报告没写的绝不添加；报告写了的绝不省略(如"HP-"、"建议短期治疗后复查"必须原样保留)
- 只输出你在图片中确实看到的文字

- 如果照片模糊或不是医学报告，返回 {"error": "无法识别"}
"""


async def recognize_medical_report(
    image_base64: str,
    image_type: str = "jpeg",
) -> Dict[str, Any]:
    """从体检报告图片中提取结构化指标。"""
    try:
        from app.services.llm.usage_tracker import set_caller
        set_caller("medical_report_ocr.recognize")
        provider = get_vision_provider()
        if not provider:
            return {"error": "Vision model not configured"}

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别这张体检报告中的所有检查指标。"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_type};base64,{image_base64}",
                        },
                    },
                ],
            },
        ]

        # provider.chat() 接受 multi-part content (text + image_url),
        # 返回纯文本 str 或 tool_calls dict. 这里不用 tool, 结果就是 str.
        response = await provider.chat(
            messages=messages,
            temperature=0.1,
            # 体检报告指标多,结构化 JSON 输出常 >3000 token → 截断 → json.loads 失败。
            # active 模型实测接受 ≥32000,放开到 16000 覆盖整份报告(同 pdf_parser)。
            max_tokens=16000,
        )
        content = response if isinstance(response, str) else response.get("content", "")
        json_str = extract_json_from_text(content or "")
        result = json.loads(json_str)

        if "error" in result:
            return result

        items_count = len(result.get("items", []))
        abnormal_count = sum(1 for i in result.get("items", []) if i.get("is_abnormal"))
        logger.info(
            f"[体检OCR] 识别成功: {result.get('report_type', '未知')} "
            f"共{items_count}项, 异常{abnormal_count}项"
        )
        return result

    except json.JSONDecodeError:
        logger.warning("[体检OCR] JSON解析失败")
        return {"error": "OCR结果解析失败"}
    except Exception as exc:
        logger.error("[体检OCR] 识别失败 error_type=%s", type(exc).__name__)
        return {"error": "医疗报告识别服务暂时不可用"}
