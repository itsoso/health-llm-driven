"""
AI 食物识别服务
使用 LLM Provider 识别食物图片并估算营养信息
"""
import base64
import json
import logging
import re
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.llm import get_vision_provider

logger = logging.getLogger(__name__)


def _as_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return round(number, 1)


def _looks_like_food_ui_text(value: Any) -> bool:
    normalized = re.sub(r"\s+", "", str(value or "")).lower()
    if not normalized:
        return False
    if re.fullmatch(r"(?:和)?(?:早餐|午餐|晚餐|加餐|餐食)?(?:食品?)?营养卡", normalized):
        return True
    return any(marker in normalized for marker in (
        "营养卡",
        "保存并确认",
        "确认记录",
        "今日饮食",
        "待确认",
        "完成修正",
        "去饮食页修正",
        "看下一餐建议",
    ))


def sanitize_food_recognition_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Drop OCR/UI copy that a vision model mis-labeled as food."""
    if not isinstance(result, dict):
        return {
            "success": False,
            "error": "AI响应格式错误，请重试",
            "foods": [],
        }

    foods = result.get("foods")
    if not isinstance(foods, list):
        foods = []

    cleaned: List[Dict[str, Any]] = []
    for raw in foods:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name or _looks_like_food_ui_text(name):
            continue
        item = dict(raw)
        item["name"] = name[:80]
        cleaned.append(item)

    result["foods"] = cleaned
    if not cleaned:
        result["success"] = False
        result["error"] = "图片中未识别到可记录的食物，请重新拍摄餐食本身。"
        result["meal_description"] = "未识别到可记录的食物"
        result["total_calories"] = None
        result["total_protein"] = None
        result["total_carbs"] = None
        result["total_fat"] = None
        result["total_fiber"] = None
        return result

    mapping = {
        "calories": "total_calories",
        "protein": "total_protein",
        "carbs": "total_carbs",
        "fat": "total_fat",
        "fiber": "total_fiber",
    }
    for source_key, total_key in mapping.items():
        values = [_as_number(food.get(source_key)) for food in cleaned]
        if any(value is None for value in values):
            result[total_key] = None
            continue
        total = sum(value for value in values if value is not None)
        result[total_key] = int(round(total)) if total_key == "total_calories" else round(total, 1)

    descriptions = []
    for food in cleaned:
        quantity = str(food.get("quantity") or "").strip()
        descriptions.append(f"{food['name']} {quantity}".strip())
    result["meal_description"] = "、".join(descriptions)[:300]
    result["success"] = True
    return result


def extract_json_from_text(text: str) -> str:
    """
    从文本中提取JSON内容，处理各种可能的格式

    支持的格式：
    - 纯JSON: {"key": "value"}
    - Markdown代码块: ```json\n{...}\n```
    - 带前缀的JSON: Some text {"key": "value"}
    """
    if not text:
        return text

    text = text.strip()

    # 1. 首先尝试提取markdown代码块中的JSON
    # 匹配 ```json ... ``` 或 ``` ... ```
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, text)
    if match:
        extracted = match.group(1).strip()
        logger.info(f"从markdown代码块中提取JSON, 长度: {len(extracted)}")
        return extracted

    # 2. 如果没有代码块，尝试找到JSON对象的开始和结束
    # 找第一个 { 和最后一个 }
    first_brace = text.find('{')
    last_brace = text.rfind('}')

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        extracted = text[first_brace:last_brace + 1]
        logger.info(f"从文本中提取JSON对象, 长度: {len(extracted)}")
        return extracted

    # 3. 如果都找不到，返回原文
    logger.warning(f"无法提取JSON，返回原文, 长度: {len(text)}")
    return text

class FoodRecognitionService:
    """AI食物识别服务"""

    def __init__(self):
        self._provider = None
        logger.info("AI食物识别服务初始化成功（使用统一 LLM Provider）")

    def _get_provider(self):
        """懒加载获取 LLM Provider"""
        if self._provider is None:
            try:
                self._provider = get_vision_provider()
            except Exception as e:
                logger.error(f"获取 LLM Provider 失败: {e}")
        return self._provider

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._get_provider() is not None

    async def recognize_food_from_base64(
        self,
        image_base64: str,
        image_type: str = "jpeg"
    ) -> Dict[str, Any]:
        """
        从Base64编码的图片识别食物

        Args:
            image_base64: Base64编码的图片数据
            image_type: 图片类型 (jpeg, png, gif, webp)

        Returns:
            包含识别结果的字典
        """
        logger.info(f"开始食物图片识别, 图片类型: {image_type}, base64长度: {len(image_base64) if image_base64 else 0}")

        if not self.is_available():
            logger.error("AI服务不可用")
            return {
                "success": False,
                "error": "智能识别服务不可用",
                "foods": []
            }

        try:
            # 构建图片URL
            data_url = f"data:image/{image_type};base64,{image_base64}"
            logger.info(f"调用 LLM Vision API 识别食物")

            system_prompt = """你是一个专业的营养师和食物识别专家。请分析用户上传的食物图片，识别出所有食物并估算营养信息。

请严格按照以下JSON格式返回结果，不要有任何其他文字：
{
    "foods": [
        {
            "name": "食物名称（中文）",
            "quantity": "估算的份量，如: 1碗、200g、1个",
            "calories": 估算的热量（整数，单位kcal）,
            "protein": 估算的蛋白质（浮点数，单位g）,
            "carbs": 估算的碳水化合物（浮点数，单位g）,
            "fat": 估算的脂肪（浮点数，单位g）,
            "fiber": 估算的膳食纤维（浮点数，单位g，可选）,
            "confidence": 识别置信度（0-1之间的浮点数）
        }
    ],
    "meal_description": "对这顿餐食的简短描述",
    "health_tips": "营养建议或健康提示",
    "total_calories": 总热量估算（整数）,
    "total_protein": 总蛋白质（浮点数）,
    "total_carbs": 总碳水（浮点数）,
    "total_fat": 总脂肪（浮点数）
}

注意：
1. 如果图片中没有食物，返回空的foods数组并在meal_description中说明
2. 营养估算基于中国常见食物的营养成分表
3. 份量估算要尽可能准确，参考常见餐具大小
4. 只返回JSON，不要有任何额外说明文字"""

            provider = self._get_provider()
            from app.services.llm.usage_tracker import set_caller
            set_caller("food_recognition.from_base64")
            raw_content = await provider.chat_with_vision(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "请识别这张图片中的食物，并估算营养信息。"},
                ],
                image_url=data_url,
                temperature=0.3,
                max_tokens=1500,
            )
            if not raw_content:
                logger.error("AI返回空内容")
                return {
                    "success": False,
                    "error": "AI返回空内容，请重试",
                    "foods": []
                }

            content = raw_content.strip()
            logger.info(f"AI原始响应长度: {len(content)}, 前100字符: {content[:100]}")

            # 检查是否是拒绝识别的回复
            refuse_keywords = ["无法识别", "抱歉", "不是食物", "cannot identify", "sorry", "not food", "看不清", "无法分析"]
            if any(keyword in content.lower() for keyword in refuse_keywords):
                logger.warning(f"AI无法识别图片内容: {content[:200]}")
                return {
                    "success": False,
                    "error": "图片中未识别到食物，请确保图片清晰且包含食物内容",
                    "foods": [],
                    "ai_message": content[:200]
                }

            # 使用改进的JSON提取函数
            json_content = extract_json_from_text(content)
            logger.info(f"提取的JSON内容长度: {len(json_content)}, 前100字符: {json_content[:100]}")

            try:
                result = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}")
                logger.error(f"尝试解析的内容: {json_content[:500]}")
                logger.error(f"原始AI响应: {content[:500]}")

                # 检查是否是拒绝识别的情况
                if any(keyword in content.lower() for keyword in refuse_keywords):
                    return {
                        "success": False,
                        "error": "图片中未识别到食物，请重新拍照或选择包含食物的图片",
                        "foods": [],
                        "ai_message": content[:200]
                    }
                return {
                    "success": False,
                    "error": "AI响应格式错误，请重试",
                    "foods": [],
                    "raw_response": content[:500]
                }

            result["success"] = True

            # 验证返回的数据结构
            if "foods" not in result:
                result["foods"] = []
            result = sanitize_food_recognition_result(result)

            foods_count = len(result.get('foods', []))
            logger.info(f"食物识别完成: success={result.get('success')} foods={foods_count}")

            if foods_count > 0:
                food_names = [f.get('name', '未知') for f in result['foods']]
                logger.info(f"识别到的食物: {', '.join(food_names)}")

            return result

        except Exception as e:
            import traceback
            error_msg = str(e)
            logger.error(f"食物识别失败: {error_msg}")
            logger.error(f"详细错误: {traceback.format_exc()}")

            # 检查是否是OpenAI API相关错误
            if "rate limit" in error_msg.lower():
                return {
                    "success": False,
                    "error": "服务繁忙，请稍后重试",
                    "foods": []
                }
            elif "invalid_api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                return {
                    "success": False,
                    "error": "AI服务配置错误，请联系管理员",
                    "foods": []
                }
            elif "timeout" in error_msg.lower():
                return {
                    "success": False,
                    "error": "识别超时，请重试",
                    "foods": []
                }

            return {
                "success": False,
                "error": f"识别失败: {error_msg[:100]}",
                "foods": []
            }

    async def recognize_food_from_url(self, image_url: str) -> Dict[str, Any]:
        """
        从图片URL识别食物

        Args:
            image_url: 图片的URL地址

        Returns:
            包含识别结果的字典
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "智能识别服务不可用",
                "foods": []
            }

        try:
            system_prompt = """你是一个专业的营养师和食物识别专家。请分析用户上传的食物图片，识别出所有食物并估算营养信息。

请严格按照以下JSON格式返回结果：
{
    "foods": [
        {
            "name": "食物名称（中文）",
            "quantity": "估算的份量",
            "calories": 热量（整数，kcal）,
            "protein": 蛋白质（浮点数，g）,
            "carbs": 碳水化合物（浮点数，g）,
            "fat": 脂肪（浮点数，g）,
            "fiber": 膳食纤维（浮点数，g，可选）,
            "confidence": 识别置信度（0-1）
        }
    ],
    "meal_description": "餐食描述",
    "health_tips": "健康提示",
    "total_calories": 总热量,
    "total_protein": 总蛋白质,
    "total_carbs": 总碳水,
    "total_fat": 总脂肪
}"""

            provider = self._get_provider()
            from app.services.llm.usage_tracker import set_caller
            set_caller("food_recognition.from_url")
            raw_content = await provider.chat_with_vision(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "请识别这张图片中的食物，并估算营养信息。"},
                ],
                image_url=image_url,
                temperature=0.3,
                max_tokens=1500,
            )

            if not raw_content:
                logger.error("AI返回空内容")
                return {
                    "success": False,
                    "error": "AI返回空内容，请重试",
                    "foods": []
                }

            content = raw_content.strip()
            logger.info(f"从URL识别 - AI响应长度: {len(content)}")

            # 使用改进的JSON提取函数
            json_content = extract_json_from_text(content)

            try:
                result = json.loads(json_content)
                result["success"] = True
                return sanitize_food_recognition_result(result)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}, 内容: {json_content[:500]}")
                return {
                    "success": False,
                    "error": "AI响应格式错误，请重试",
                    "foods": [],
                    "raw_response": content[:500]
                }

        except Exception as e:
            logger.error(f"从URL识别食物失败: {e}")
            return {
                "success": False,
                "error": str(e)[:100],
                "foods": []
            }

    def estimate_nutrition_from_text(self, food_description: str) -> Dict[str, Any]:
        """
        根据文字描述估算营养信息（不使用图片）
        注意：此方法内部使用同步调用，兼容旧接口。

        Args:
            food_description: 食物描述文字

        Returns:
            包含营养估算的字典
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "智能识别服务不可用",
                "foods": []
            }

        import asyncio

        async def _do_estimate():
            system_prompt = """你是一个专业营养师。根据用户描述的食物，估算营养信息。

请严格按照JSON格式返回：
{
    "foods": [
        {
            "name": "食物名称",
            "quantity": "份量",
            "calories": 热量(kcal),
            "protein": 蛋白质(g),
            "carbs": 碳水(g),
            "fat": 脂肪(g),
            "fiber": 膳食纤维(g)
        }
    ],
    "total_calories": 总热量,
    "total_protein": 总蛋白质,
    "total_carbs": 总碳水,
    "total_fat": 总脂肪,
    "health_tips": "营养建议"
}

只返回JSON，无其他文字。"""

            provider = self._get_provider()
            from app.services.llm.usage_tracker import set_caller
            set_caller("food_recognition.estimate_nutrition")
            content = await provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请估算以下食物的营养信息：{food_description}"},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            return content

        try:
            # 尝试获取运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 在已有事件循环中，创建新线程执行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    content = pool.submit(asyncio.run, _do_estimate()).result()
            else:
                content = asyncio.run(_do_estimate())

            content = content.strip()
            # 提取 JSON
            json_content = extract_json_from_text(content)
            result = json.loads(json_content)
            result["success"] = True
            return result

        except Exception as e:
            logger.error(f"文字营养估算失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "foods": []
            }


# 创建单例
food_recognition_service = FoodRecognitionService()
