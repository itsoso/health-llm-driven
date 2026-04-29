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

SYSTEM_PROMPT = """你是一个医学报告识别助手。用户会上传体检报告的照片。
请仔细识别报告中的所有检查指标，提取为结构化JSON。

返回格式：
{
  "report_type": "血常规|生化|肝功能|肾功能|血脂|甲状腺|尿常规|其他",
  "report_date": "2026-01-15 或 null",
  "institution": "医院名称 或 null",
  "items": [
    {
      "name": "指标中文名",
      "name_en": "英文缩写（如ALT、LDL-C、HbA1c）",
      "value": 数值,
      "unit": "单位",
      "reference_low": 参考下限或null,
      "reference_high": 参考上限或null,
      "is_abnormal": true/false,
      "abnormal_direction": "high|low|null"
    }
  ],
  "conclusion": "报告结论文字（如有）"
}

注意：
- 数值尽量转为数字，而非字符串
- 参考范围如 "3.5-5.5" 拆为 reference_low=3.5, reference_high=5.5
- 箭头↑↓或H/L标记表示异常
- 如果照片模糊或不是体检报告，返回 {"error": "无法识别"}
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

        response = await provider.chat_completion(messages=messages, temperature=0.1)
        content = response.get("content", "")
        json_str = extract_json_from_text(content)
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
    except Exception as e:
        logger.error(f"[体检OCR] 识别失败: {e}")
        return {"error": str(e)}
