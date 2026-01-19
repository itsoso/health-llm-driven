"""
AI 食物识别服务
使用 GPT-4 Vision 识别食物图片并估算营养信息
"""
import base64
import json
import logging
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# 尝试导入 OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI库未安装，AI食物识别功能将不可用")


class FoodRecognitionService:
    """AI食物识别服务"""
    
    def __init__(self):
        self.client = None
        self.model = "gpt-4o"  # 使用支持视觉的模型
        
        if OPENAI_AVAILABLE and settings.openai_api_key:
            try:
                client_kwargs = {"api_key": settings.openai_api_key}
                if settings.openai_base_url:
                    client_kwargs["base_url"] = settings.openai_base_url
                self.client = OpenAI(**client_kwargs)
                logger.info("AI食物识别服务初始化成功")
            except Exception as e:
                logger.error(f"AI食物识别服务初始化失败: {e}")
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.client is not None
    
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
            logger.info(f"调用GPT-4 Vision API, 模型: {self.model}")
            
            # 调用GPT-4 Vision
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业的营养师和食物识别专家。请分析用户上传的食物图片，识别出所有食物并估算营养信息。

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
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请识别这张图片中的食物，并估算营养信息。"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_url,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1500,
                temperature=0.3
            )
            
            # 解析响应
            content = response.choices[0].message.content.strip()
            
            # 尝试清理可能的markdown标记
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            result["success"] = True
            
            logger.info(f"食物识别成功: {len(result.get('foods', []))} 种食物")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"解析AI响应失败: {e}, 原始内容: {content[:500] if 'content' in locals() else 'N/A'}")
            return {
                "success": False,
                "error": f"解析AI响应失败: {str(e)}",
                "foods": [],
                "raw_response": content[:500] if 'content' in locals() else None
            }
        except Exception as e:
            import traceback
            logger.error(f"食物识别失败: {e}")
            logger.error(f"详细错误: {traceback.format_exc()}")
            return {
                "success": False,
                "error": f"识别失败: {str(e)}",
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业的营养师和食物识别专家。请分析用户上传的食物图片，识别出所有食物并估算营养信息。

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
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请识别这张图片中的食物，并估算营养信息。"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1500,
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            result["success"] = True
            return result
            
        except Exception as e:
            logger.error(f"从URL识别食物失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "foods": []
            }
    
    def estimate_nutrition_from_text(self, food_description: str) -> Dict[str, Any]:
        """
        根据文字描述估算营养信息（不使用图片）
        
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
        
        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model or "gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业营养师。根据用户描述的食物，估算营养信息。

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
                    },
                    {
                        "role": "user",
                        "content": f"请估算以下食物的营养信息：{food_description}"
                    }
                ],
                max_tokens=1000,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content.strip()
            result = json.loads(content)
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
