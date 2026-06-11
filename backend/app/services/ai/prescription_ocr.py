"""处方图片 OCR —— 从医生处方照片提取药品列表。

复用 vision model 基础设施(同 medical_report_ocr)。vision 同时承担"把乱名规整成
标准通用名"的职责(混合方案的 LLM 规整部分);原研药事实由 originator_drugs 精选表
判定,不在此处。返回供用户确认,**不直接入库**(OCR 可能出错)。
"""
import json
import logging
from typing import Any, Dict

from app.services.ai.food_recognition import extract_json_from_text
from app.services.llm import get_vision_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是处方识别助手。用户上传医生处方的照片。
请识别其中开具的**药品**,提取为结构化 JSON。

返回格式:
{
  "items": [
    {
      "raw_name": "处方上的原始药名(含商品名/规格,原样)",
      "generic_name": "该药的标准**通用名**(中文,只要活性成分名,去掉商品名/规格/剂型;不确定填 null)",
      "dosage": "规格/单次剂量 如 20mg 或 null",
      "frequency": "用法 如 每日1次/每日3次 或 null"
    }
  ]
}

注意:
- generic_name 只填活性成分通用名(如"泮托拉唑""伏诺拉生""阿托伐他汀"),不要带商品名/钠/钙/规格。
- 只识别药品,忽略煎服法、医院抬头、医生签名等。
- 不确定的字段填 null,不要编造。
- 若照片模糊或不是处方,返回 {"error": "无法识别"}
"""


async def recognize_prescription(image_base64: str, image_type: str = "jpeg") -> Dict[str, Any]:
    """从处方图片提取药品列表(含规整后的通用名)。"""
    try:
        from app.services.llm.usage_tracker import set_caller
        set_caller("prescription_ocr.recognize")
        provider = get_vision_provider()
        if not provider:
            return {"error": "Vision model not configured"}

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别这张处方上开具的所有药品。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_type};base64,{image_base64}"}},
                ],
            },
        ]
        response = await provider.chat(messages=messages, temperature=0.1, max_tokens=2000)
        content = response if isinstance(response, str) else response.get("content", "")
        result = json.loads(extract_json_from_text(content or ""))
        if "error" in result:
            return result
        items = result.get("items", []) or []
        logger.info(f"[处方OCR] 识别成功: 共 {len(items)} 种药")
        return {"items": items}
    except json.JSONDecodeError:
        logger.warning("[处方OCR] JSON 解析失败")
        return {"error": "OCR 结果解析失败"}
    except Exception as e:
        logger.error(f"[处方OCR] 识别失败: {e}")
        return {"error": str(e)}
