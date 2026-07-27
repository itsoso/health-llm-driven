"""
AI 食物识别服务
使用 LLM Provider 识别食物图片并估算营养信息
"""
import json
import logging
import math
import re
from typing import Dict, Any, List, Optional
from app.services.intake_intent_classifier import (
    classify_intake_intent,
    looks_like_food_ui_text,
)
from app.services.llm import get_vision_provider

logger = logging.getLogger(__name__)

MAX_RECOGNIZED_FOODS = 12
_NON_FOOD_INTENT_KINDS = {"diet_management", "medication", "supplement"}
_FOOD_CONTEXT_SUFFIX_RE = re.compile(
    r"(?:酸奶|饮料|果汁|茶|咖啡|牛奶|豆奶|沙拉|水果|坚果|面包|麦片|粥|饭|面|菜|汤|蛋|肉)$",
    re.I,
)
_SAFE_OPERATIONAL_ERRORS = {
    "智能识别服务不可用",
    "AI返回空内容，请重试",
    "图片中未识别到食物，请确保图片清晰且包含食物内容",
    "图片中未识别到食物，请重新拍照或选择包含食物的图片",
    "AI响应格式错误，请重试",
    "服务繁忙，请稍后重试",
    "AI服务配置错误，请联系管理员",
    "识别超时，请重试",
    "识别失败，请重试",
}
_NUTRIENT_LIMITS = {
    "calories": 5000.0,
    "protein": 1000.0,
    "carbs": 1000.0,
    "fat": 500.0,
    "fiber": 200.0,
}
_NUTRITION_LABEL_UNSCALED_BASES = {
    "nutrition_label_per_100g",
    "nutrition_label_per_serving",
}
_EXPLICIT_FOOD_MASS_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kilograms?|kg|公斤|千克|grams?|g|克|斤)(?![a-z])",
    re.I,
)

FOOD_RECOGNITION_SYSTEM_PROMPT = """你是专业的食物识别与营养估算助手。分析照片中清晰可见的餐食，或清晰可读的食品营养成分表；不把界面文字、按钮、药物或补剂识别成食物，也不要猜测被遮挡的配料。

请严格只返回以下 JSON，不要附加说明：
{
  "foods": [
    {
      "name": "中文食物名称",
      "quantity": "约1碗",
      "quantity_grams": null,
      "label_basis_grams": null,
      "calories": 320,
      "protein": 18.0,
      "carbs": 42.0,
      "fat": 9.0,
      "fiber": 4.0,
      "confidence": 0.86,
      "portion_confidence": 0.68,
      "source": "vision_estimate",
      "nutrition_basis": "vision_estimate"
    }
  ],
  "meal_description": "餐食简述",
  "health_tips": "简短营养提示"
}

规则：
1. 只列出照片中确实可见的食物，最多 12 项；没有食物时 foods 返回空数组。
2. 份量永远是视觉估算，不是测量值。没有清晰参照物时宁可返回 null，不编造精确克数。
3. 无法确认食物身份或营养值时使用 null，不用 0 代替未知。
4. 不输出药品、补剂、餐食卡片文字、按钮文字或其他界面元素。
5. 同一种食物合并为一个条目，quantity 写用户这一餐可见的总份量。
6. 如果图片主体是食品包装上的营养成分表，可将商品作为一个 food 返回，但只抄录标签基准值，不推断用户实际吃了多少：
   - 标签按每 100g 标示时，quantity 写“每100g”，quantity_grams 和 label_basis_grams 都写 100，source 写 nutrition_label，nutrition_basis 写 nutrition_label_per_100g。
   - 标签按每份标示且份量克数清晰时，quantity 写标签份量，quantity_grams 和 label_basis_grams 写该份克数，source 写 nutrition_label，nutrition_basis 写 nutrition_label_per_serving。
   - 标签只有千焦时，除以 4.184 换算为千卡。标签基准、单位或商品身份不清楚时返回 null，不猜测。
7. 只返回合法 JSON。"""


def _as_number(value: Any, maximum: Optional[float] = None) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if maximum is not None and number > maximum:
        return None
    return round(number, 1)


def _as_probability(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or number > 1:
        return None
    return round(number, 3)


def _clean_text(value: Any, maximum_length: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:maximum_length]


def _looks_like_non_food_intake(name: str) -> bool:
    intent = classify_intake_intent(name)
    if intent.kind == "supplement" and _FOOD_CONTEXT_SUFFIX_RE.search(name):
        return False
    return intent.kind in _NON_FOOD_INTENT_KINDS


def _sanitize_food_item(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = _clean_text(raw.get("name"), 80)
    if not name or looks_like_food_ui_text(name):
        return None
    if _looks_like_non_food_intake(name):
        return None

    quantity = _clean_text(raw.get("quantity"), 40) or None
    item: Dict[str, Any] = {
        "name": name,
        "quantity": quantity,
        "confidence": _as_probability(raw.get("confidence")),
        "portion_basis": "vision_estimate" if quantity else "unknown",
        "portion_confidence": _as_probability(raw.get("portion_confidence")) if quantity else None,
    }
    for field, maximum in _NUTRIENT_LIMITS.items():
        item[field] = _as_number(raw.get(field), maximum=maximum)

    quantity_grams = _as_number(raw.get("quantity_grams"), maximum=10000.0)
    if quantity_grams is not None:
        item["quantity_grams"] = quantity_grams
    label_basis_grams = _as_number(
        raw.get("label_basis_grams"),
        maximum=10000.0,
    )
    if label_basis_grams is not None:
        item["label_basis_grams"] = label_basis_grams
    for field, maximum_length in (
        ("food_id", 120),
        ("source", 80),
        ("nutrition_basis", 40),
        ("unit", 20),
    ):
        value = _clean_text(raw.get(field), maximum_length)
        if value:
            item[field] = value
    return item


def apply_user_stated_amount_to_nutrition_label(
    result: Dict[str, Any],
    user_message: str,
) -> Dict[str, Any]:
    """Scale one product label locally without sending free-form text upstream."""
    transformed = dict(result)
    foods = [
        dict(food)
        for food in result.get("foods") or []
        if isinstance(food, dict)
    ]
    label_indexes = [
        index
        for index, food in enumerate(foods)
        if _is_unscaled_nutrition_label(food)
    ]
    if not label_indexes:
        return transformed

    consumed_grams = _single_explicit_food_mass_grams(user_message)
    if len(label_indexes) != 1 or consumed_grams is None:
        transformed["nutrition_label_requires_amount"] = True
        transformed["foods"] = foods
        return transformed

    food = foods[label_indexes[0]]
    basis = str(food.get("nutrition_basis") or "").strip().lower()
    basis_grams = _as_number(food.get("label_basis_grams"), maximum=10000.0)
    if basis_grams is None and basis == "nutrition_label_per_100g":
        basis_grams = 100.0
    if basis_grams is None:
        basis_grams = _as_number(food.get("quantity_grams"), maximum=10000.0)
    if basis_grams is None or basis_grams <= 0:
        transformed["nutrition_label_requires_amount"] = True
        transformed["foods"] = foods
        return transformed

    factor = consumed_grams / basis_grams
    for field in _NUTRIENT_LIMITS:
        value = _as_number(food.get(field), maximum=_NUTRIENT_LIMITS[field])
        if value is not None:
            food[field] = round(value * factor, 1)
    food["quantity"] = f"{_display_grams(consumed_grams)}g"
    food["quantity_grams"] = round(consumed_grams, 1)
    food["source"] = "nutrition_label"
    food["nutrition_basis"] = "nutrition_label_scaled"
    foods[label_indexes[0]] = food
    transformed["foods"] = foods
    transformed["nutrition_label_amount_applied"] = True
    return transformed


def _is_unscaled_nutrition_label(food: Dict[str, Any]) -> bool:
    basis = str(food.get("nutrition_basis") or "").strip().lower()
    if basis in _NUTRITION_LABEL_UNSCALED_BASES:
        return True
    if basis != "nutrition_label":
        return False
    quantity = re.sub(r"\s+", "", str(food.get("quantity") or "")).lower()
    return bool(
        re.search(r"每(?:100)?(?:g|克)", quantity)
        or _as_number(food.get("label_basis_grams"), maximum=10000.0)
        is not None
    )


def _single_explicit_food_mass_grams(text: str) -> Optional[float]:
    matches: List[float] = []
    for match in _EXPLICIT_FOOD_MASS_RE.finditer(str(text or "")):
        prefix = str(text or "")[max(0, match.start() - 1):match.start()]
        if prefix == "每":
            continue
        amount = float(match.group("amount"))
        unit = match.group("unit").lower()
        if unit in {"kg", "kilogram", "kilograms", "公斤", "千克"}:
            amount *= 1000
        elif unit == "斤":
            amount *= 500
        if 0 < amount <= 10000:
            matches.append(round(amount, 3))
    unique = sorted(set(matches))
    return unique[0] if len(unique) == 1 else None


def _display_grams(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


def sanitize_food_recognition_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize untrusted vision output into the public recognition contract."""
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
    seen: set[tuple[str, str]] = set()
    for raw in foods:
        if not isinstance(raw, dict):
            continue
        item = _sanitize_food_item(raw)
        if item is None:
            continue
        dedupe_key = (
            re.sub(r"\s+", "", item["name"]).lower(),
            re.sub(r"\s+", "", item.get("quantity") or "").lower(),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned.append(item)
        if len(cleaned) >= MAX_RECOGNIZED_FOODS:
            break

    sanitized: Dict[str, Any] = {
        "foods": cleaned,
        "health_tips": _clean_text(result.get("health_tips"), 300) or None,
    }
    if not cleaned:
        operational_error = _clean_text(result.get("error"), 120)
        if result.get("success") is False:
            error = operational_error if operational_error in _SAFE_OPERATIONAL_ERRORS else "识别失败，请重试"
        else:
            error = "图片中未识别到可记录的食物，请重新拍摄餐食本身。"
        sanitized.update({
            "success": False,
            "error": error,
            "meal_description": "未识别到可记录的食物",
            "total_calories": None,
            "total_protein": None,
            "total_carbs": None,
            "total_fat": None,
            "total_fiber": None,
        })
        return sanitized

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
            sanitized[total_key] = None
            continue
        total = sum(value for value in values if value is not None)
        sanitized[total_key] = int(round(total)) if total_key == "total_calories" else round(total, 1)

    descriptions = []
    for food in cleaned:
        quantity = str(food.get("quantity") or "").strip()
        descriptions.append(f"{food['name']} {quantity}".strip())
    sanitized["meal_description"] = "、".join(descriptions)[:300]
    sanitized["success"] = True
    return sanitized


def merge_food_recognition_results(
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge independent views of one meal without double-counting dishes.

    The existing privacy boundary remains unchanged: each photo is recognized
    through the current single-image provider call, then only sanitized JSON is
    merged locally. Same dish + same portion is an alternate view. Conflicting
    portions are retained once and force manual confirmation upstream.
    """
    merged_foods: List[Dict[str, Any]] = []
    food_positions: Dict[str, int] = {}
    conflict = False
    ambiguous_duplicate = False
    health_tips: Optional[str] = None
    safe_errors: List[str] = []
    consumed_fractions: List[float] = []
    consumed_fraction_labels: List[str] = []

    for raw_result in results:
        result = sanitize_food_recognition_result(raw_result)
        if not result.get("success"):
            error = str(result.get("error") or "").strip()
            if error:
                safe_errors.append(error)
            continue
        if health_tips is None and result.get("health_tips"):
            health_tips = str(result["health_tips"])
        raw_fraction = raw_result.get("consumed_fraction")
        fraction = (
            float(raw_fraction)
            if isinstance(raw_fraction, (int, float))
            and not isinstance(raw_fraction, bool)
            and math.isfinite(float(raw_fraction))
            else None
        )
        label = str(raw_result.get("consumed_fraction_label") or "").strip()
        if fraction is not None and 0 < fraction < 1:
            consumed_fractions.append(fraction)
            if label:
                consumed_fraction_labels.append(label)
        for food in result.get("foods") or []:
            if not isinstance(food, dict):
                continue
            name_key = re.sub(r"\s+", "", str(food.get("name") or "")).lower()
            if not name_key:
                continue
            existing_position = food_positions.get(name_key)
            if existing_position is None:
                food_positions[name_key] = len(merged_foods)
                merged_foods.append(dict(food))
                continue

            existing = merged_foods[existing_position]
            # Independent photos do not prove whether this is another view of
            # one serving or a second identical serving. Keep one conservative
            # estimate but force confirmation instead of silently undercounting.
            ambiguous_duplicate = True
            conflict = True
            existing_quantity = re.sub(
                r"\s+",
                "",
                str(existing.get("quantity") or ""),
            ).lower()
            incoming_quantity = re.sub(
                r"\s+",
                "",
                str(food.get("quantity") or ""),
            ).lower()
            if (
                existing_quantity
                and incoming_quantity
                and existing_quantity != incoming_quantity
            ):
                conflict = True
                continue
            if not existing_quantity and incoming_quantity:
                merged_foods[existing_position] = dict(food)
                continue
            existing_confidence = _as_probability(existing.get("confidence")) or 0
            incoming_confidence = _as_probability(food.get("confidence")) or 0
            if incoming_confidence > existing_confidence:
                merged_foods[existing_position] = dict(food)

    if not merged_foods:
        return {
            "success": False,
            "error": safe_errors[0] if safe_errors else "图片中未识别到可记录的食物，请重新拍摄餐食本身。",
            "foods": [],
            "multi_photo_conflict": False,
        }

    merged = sanitize_food_recognition_result({
        "success": True,
        "foods": merged_foods,
        "health_tips": health_tips,
    })
    merged["multi_photo_conflict"] = conflict
    merged["multi_photo_ambiguous_duplicate"] = ambiguous_duplicate
    merged["source_image_count"] = len(results)
    if consumed_fractions:
        first_fraction = consumed_fractions[0]
        if all(abs(value - first_fraction) < 1e-6 for value in consumed_fractions):
            merged["consumed_fraction"] = first_fraction
            if consumed_fraction_labels:
                merged["consumed_fraction_label"] = consumed_fraction_labels[0]
        else:
            merged["multi_photo_conflict"] = True
    confidences = [
        confidence
        for food in merged.get("foods") or []
        if (confidence := _as_probability(food.get("confidence"))) is not None
    ]
    merged["multi_photo_min_confidence"] = min(confidences) if confidences else None
    return merged


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


def _vision_chat_options(provider: Any) -> Dict[str, Any]:
    """Keep Qwen3 visual extraction on its low-latency deterministic path."""
    model = str(getattr(provider, "model", "") or "").strip().lower()
    if model.startswith("qwen3"):
        return {"extra_body": {"enable_thinking": False}}
    return {}


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
                logger.error("获取 LLM Provider 失败 error_type=%s", type(e).__name__)
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
            logger.info("调用 LLM Vision API 识别食物")

            provider = self._get_provider()
            from app.services.llm.usage_tracker import set_caller
            set_caller("food_recognition.from_base64")
            raw_content = await provider.chat_with_vision(
                messages=[
                    {"role": "system", "content": FOOD_RECOGNITION_SYSTEM_PROMPT},
                    {"role": "user", "content": "请识别这张图片中的食物，并估算营养信息。"},
                ],
                image_url=data_url,
                temperature=0.1,
                max_tokens=2000,
                **_vision_chat_options(provider),
            )
            if not raw_content:
                logger.error("AI返回空内容")
                return {
                    "success": False,
                    "error": "AI返回空内容，请重试",
                    "foods": []
                }

            content = raw_content.strip()
            logger.info("AI原始响应已接收 response_length=%s", len(content))

            # 检查是否是拒绝识别的回复
            refuse_keywords = ["无法识别", "抱歉", "不是食物", "cannot identify", "sorry", "not food", "看不清", "无法分析"]
            if any(keyword in content.lower() for keyword in refuse_keywords):
                logger.warning("AI无法识别图片内容 response_length=%s", len(content))
                return {
                    "success": False,
                    "error": "图片中未识别到食物，请确保图片清晰且包含食物内容",
                    "foods": [],
                }

            # 使用改进的JSON提取函数
            json_content = extract_json_from_text(content)
            logger.info("已提取识别JSON json_length=%s", len(json_content))

            try:
                result = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(
                    "食物识别JSON解析失败 line=%s column=%s response_length=%s",
                    e.lineno,
                    e.colno,
                    len(content),
                )

                # 检查是否是拒绝识别的情况
                if any(keyword in content.lower() for keyword in refuse_keywords):
                    return {
                        "success": False,
                        "error": "图片中未识别到食物，请重新拍照或选择包含食物的图片",
                        "foods": [],
                    }
                return {
                    "success": False,
                    "error": "AI响应格式错误，请重试",
                    "foods": [],
                }

            result["success"] = True

            # 验证返回的数据结构
            if "foods" not in result:
                result["foods"] = []
            result = sanitize_food_recognition_result(result)

            foods_count = len(result.get('foods', []))
            logger.info(f"食物识别完成: success={result.get('success')} foods={foods_count}")

            return result

        except Exception as e:
            error_msg = str(e)
            logger.error("食物识别失败 error_type=%s", type(e).__name__)

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
                "error": "识别失败，请重试",
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
            provider = self._get_provider()
            from app.services.llm.usage_tracker import set_caller
            set_caller("food_recognition.from_url")
            raw_content = await provider.chat_with_vision(
                messages=[
                    {"role": "system", "content": FOOD_RECOGNITION_SYSTEM_PROMPT},
                    {"role": "user", "content": "请识别这张图片中的食物，并估算营养信息。"},
                ],
                image_url=image_url,
                temperature=0.1,
                max_tokens=2000,
                **_vision_chat_options(provider),
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
                logger.error(
                    "URL食物识别JSON解析失败 line=%s column=%s response_length=%s",
                    e.lineno,
                    e.colno,
                    len(content),
                )
                return {
                    "success": False,
                    "error": "AI响应格式错误，请重试",
                    "foods": [],
                }

        except Exception as e:
            logger.error("从URL识别食物失败 error_type=%s", type(e).__name__)
            return {
                "success": False,
                "error": "识别失败，请重试",
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
            logger.error("文字营养估算失败 error_type=%s", type(e).__name__)
            return {
                "success": False,
                "error": "营养估算失败，请重试",
                "foods": []
            }


# 创建单例
food_recognition_service = FoodRecognitionService()
