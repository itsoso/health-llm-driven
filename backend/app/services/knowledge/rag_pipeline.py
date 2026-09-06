"""
RAG (Retrieval-Augmented Generation) 管道

将知识库检索与大模型生成结合，提供更专业、更准确的健康建议
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.config import settings

from .vectorstore import vector_store
from .document_loader import document_loader

logger = logging.getLogger(__name__)

# 尝试导入 OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class RAGPipeline:
    """
    RAG 管道

    实现检索增强生成流程：
    1. 接收用户查询/健康数据
    2. 从知识库检索相关内容
    3. 将检索结果与用户数据结合
    4. 调用大模型生成个性化建议
    """

    def __init__(self):
        self.openai_client = None
        self.model = "gpt-4o-mini"

        self._initialize()

    def _initialize(self):
        """初始化 RAG 管道"""
        if OPENAI_AVAILABLE and settings.openai_api_key:
            client_kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                client_kwargs["base_url"] = settings.openai_base_url
            from app.services.ai_consent import guard_openai_client
            self.openai_client = guard_openai_client(OpenAI(**client_kwargs))
            self.model = settings.openai_model or "gpt-4o-mini"
            logger.info("RAG Pipeline 初始化成功")
        else:
            logger.warning("OpenAI 未配置，RAG 生成功能将不可用")

    def is_available(self) -> bool:
        """检查 RAG 管道是否可用"""
        if not settings.legacy_knowledge_runtime_enabled:
            return False
        return self.openai_client is not None and vector_store.is_available()

    def retrieve_relevant_knowledge(
        self,
        query: str,
        category: Optional[str] = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        检索相关知识

        Args:
            query: 查询内容
            category: 知识分类过滤
            n_results: 返回结果数量

        Returns:
            相关知识列表
        """
        if not settings.legacy_knowledge_runtime_enabled:
            logger.info("legacy Chroma RAG 运行时检索已关闭")
            return []

        if not vector_store.is_available():
            logger.warning("向量存储不可用，无法检索知识")
            return []

        results = vector_store.search(
            query=query,
            n_results=n_results,
            category=category
        )

        # 过滤低相关度结果（降低阈值以提高召回率）
        filtered_results = [
            r for r in results
            if r.get("relevance_score", 0) > 0.15  # 相关度阈值从 0.3 降低到 0.15
        ]

        logger.info(f"检索到 {len(filtered_results)} 条相关知识（原始 {len(results)} 条，阈值 0.15）")
        return filtered_results

    def generate_with_knowledge(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        health_data: Optional[Dict[str, Any]] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        基于知识库生成回答

        Args:
            user_query: 用户问题
            user_context: 用户上下文（画像信息）
            health_data: 健康数据（可选）
            category: 知识分类过滤

        Returns:
            生成的回答和来源
        """
        if not settings.legacy_knowledge_runtime_enabled:
            return {
                "success": False,
                "error": "legacy_knowledge_runtime_disabled",
                "answer": None,
            }

        if not self.openai_client:
            return {
                "success": False,
                "error": "LLM 服务不可用",
                "answer": None
            }

        # 1. 检索相关知识
        relevant_knowledge = self.retrieve_relevant_knowledge(
            query=user_query,
            category=category,
            n_results=5
        )

        # 2. 构建上下文
        knowledge_context = self._build_knowledge_context(relevant_knowledge)
        user_info = self._build_user_info(user_context)
        health_info = self._build_health_info(health_data) if health_data else ""

        # 3. 构建提示词
        system_prompt = """你是一位专业的智能助理，具有丰富的医学和营养学知识。

你的任务是根据用户的问题，结合以下信息给出专业、个性化的健康建议：
1. 知识库中的专业健康知识
2. 用户的个人画像信息
3. 用户的健康数据（如果有）

回答原则：
1. 优先使用知识库中的专业内容作为依据
2. 结合用户的个人情况（年龄、健康状况、目标等）给出针对性建议
3. 如果知识库中没有相关内容，可以基于专业知识回答，但要说明这是一般性建议
4. 对于医疗问题，提醒用户咨询专业医生
5. 建议要具体、可执行
6. 使用友好、鼓励的语气

请用以下 JSON 格式返回：
{
    "answer": "详细的回答内容",
    "key_points": ["要点1", "要点2", "要点3"],
    "action_items": ["具体行动建议1", "行动建议2"],
    "knowledge_used": true/false,  // 是否使用了知识库内容
    "confidence": "high/medium/low",  // 回答的置信度
    "disclaimer": "必要的免责声明（如涉及医疗建议）"
}
"""

        user_prompt = f"""用户问题：{user_query}

{user_info}

{health_info}

参考知识库内容：
{knowledge_context if knowledge_context else "（知识库中暂无直接相关内容）"}

请基于以上信息给出专业回答。"""

        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import set_caller
            from app.utils.async_helpers import run_async
            set_caller("rag_pipeline.generate_with_knowledge")
            provider = get_llm_provider()
            content = run_async(provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1500,
            ))
            content = (content or "").strip()

            # 解析 JSON 响应
            import json
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)
            result["success"] = True
            result["sources"] = [
                {
                    "title": k.get("metadata", {}).get("title", ""),
                    "category": k.get("metadata", {}).get("category", ""),
                    "relevance": k.get("relevance_score", 0)
                }
                for k in relevant_knowledge[:3]  # 返回前3个来源
            ]

            return result

        except json.JSONDecodeError:
            # 如果 JSON 解析失败，返回原始文本
            return {
                "success": True,
                "answer": content if 'content' in locals() else "生成回答时出错",
                "key_points": [],
                "action_items": [],
                "knowledge_used": len(relevant_knowledge) > 0,
                "confidence": "medium",
                "sources": []
            }
        except Exception as e:
            logger.error(f"RAG 生成失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "answer": None
            }

    def enhance_daily_advice(
        self,
        rule_analysis: Dict[str, Any],
        user_context: Dict[str, Any],
        health_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        增强每日健康建议

        将知识库内容融入到每日 AI 建议生成中

        Args:
            rule_analysis: 规则分析结果
            user_context: 用户上下文
            health_data: 健康数据

        Returns:
            增强后的建议
        """
        if not self.is_available():
            return {"enhanced": False, "reason": "RAG 服务不可用"}

        # 根据分析结果确定需要检索的知识类别
        queries = []

        # 睡眠相关
        sleep_status = rule_analysis.get("sleep_analysis", {}).get("status")
        if sleep_status in ["poor", "fair"]:
            queries.append(("如何改善睡眠质量", "sleep"))

        # 活动相关
        activity_status = rule_analysis.get("activity_analysis", {}).get("status")
        if activity_status in ["poor", "fair"]:
            queries.append(("如何增加日常活动量", "exercise"))

        # 压力/恢复相关
        recovery_status = rule_analysis.get("stress_analysis", {}).get("recovery_status")
        if recovery_status == "needs_rest":
            queries.append(("如何有效恢复身体疲劳", "mental_health"))

        # 慢性病相关（从用户画像获取）
        chronic_conditions = user_context.get("health_conditions", {}).get("chronic_conditions", [])
        for condition in chronic_conditions[:2]:  # 最多处理2个
            queries.append((f"如何管理{condition}", "chronic_disease"))

        # 检索相关知识
        all_knowledge = []
        for query, category in queries:
            knowledge = self.retrieve_relevant_knowledge(query, category, n_results=2)
            all_knowledge.extend(knowledge)

        if not all_knowledge:
            return {"enhanced": False, "reason": "未找到相关知识"}

        # 构建增强提示
        knowledge_context = self._build_knowledge_context(all_knowledge)

        system_prompt = """你是一位专业的智能助理。请基于知识库中的专业内容，为用户的每日健康建议提供补充。

要求：
1. 从知识库内容中提取与用户当前状况最相关的建议
2. 建议要具体、可执行
3. 结合用户的健康目标和慢性病情况
4. 返回 3-5 条高质量的补充建议

请用 JSON 格式返回：
{
    "enhanced_tips": ["具体建议1", "具体建议2", "具体建议3"],
    "knowledge_highlights": ["来自知识库的重要信息1", "重要信息2"],
    "personalized_focus": "今天最应该关注的一点（基于用户画像）"
}
"""

        user_prompt = f"""用户健康数据分析结果：
{self._build_analysis_summary(rule_analysis)}

用户信息：
{self._build_user_info(user_context)}

相关知识库内容：
{knowledge_context}

请提供增强的健康建议。"""

        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import set_caller
            from app.utils.async_helpers import run_async
            set_caller("rag_pipeline.enhance_daily_advice")
            provider = get_llm_provider()
            content = run_async(provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=800,
            ))
            content = (content or "").strip()

            import json
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)
            result["enhanced"] = True
            result["knowledge_sources"] = len(all_knowledge)

            return result

        except Exception as e:
            logger.error(f"增强建议生成失败: {e}")
            return {"enhanced": False, "error": str(e)}

    def _build_knowledge_context(self, knowledge_list: List[Dict[str, Any]]) -> str:
        """构建知识上下文"""
        if not knowledge_list:
            return ""

        context_parts = []
        for i, k in enumerate(knowledge_list, 1):
            title = k.get("metadata", {}).get("title", f"知识点{i}")
            content = k.get("content", "")[:500]  # 限制长度
            category = k.get("metadata", {}).get("category", "")

            context_parts.append(f"""
【{title}】({category})
{content}
""")

        return "\n---\n".join(context_parts)

    def _build_user_info(self, user_context: Dict[str, Any]) -> str:
        """构建用户信息描述"""
        parts = ["用户画像："]

        if user_context.get("name"):
            parts.append(f"- 姓名: {user_context['name']}")
        if user_context.get("age"):
            parts.append(f"- 年龄: {user_context['age']}岁")
        if user_context.get("gender"):
            parts.append(f"- 性别: {user_context['gender']}")

        # 健康目标
        goals = user_context.get("health_goals", {})
        if goals:
            parts.append("- 健康目标:")
            if goals.get("target_weight"):
                parts.append(f"  - 目标体重: {goals['target_weight']}kg")
            if goals.get("target_steps"):
                parts.append(f"  - 目标步数: {goals['target_steps']}步")
            if goals.get("target_sleep_hours"):
                parts.append(f"  - 目标睡眠: {goals['target_sleep_hours']}小时")

        # 健康状况
        conditions = user_context.get("health_conditions", {})
        chronic = conditions.get("chronic_conditions", [])
        if chronic:
            parts.append(f"- 慢性病: {', '.join(chronic)}")

        allergies = conditions.get("allergies", [])
        if allergies:
            parts.append(f"- 过敏: {', '.join(allergies)}")

        return "\n".join(parts)

    def _build_health_info(self, health_data: Dict[str, Any]) -> str:
        """构建健康数据描述"""
        if not health_data:
            return ""

        parts = ["近期健康数据："]

        if health_data.get("sleep_score"):
            parts.append(f"- 睡眠分数: {health_data['sleep_score']}")
        if health_data.get("steps"):
            parts.append(f"- 今日步数: {health_data['steps']}")
        if health_data.get("resting_heart_rate"):
            parts.append(f"- 静息心率: {health_data['resting_heart_rate']} bpm")
        if health_data.get("stress_level"):
            parts.append(f"- 压力水平: {health_data['stress_level']}")
        if health_data.get("body_battery"):
            parts.append(f"- 身体电量: {health_data['body_battery']}")

        return "\n".join(parts)

    def _build_analysis_summary(self, rule_analysis: Dict[str, Any]) -> str:
        """构建分析结果摘要"""
        parts = []

        overall = rule_analysis.get("overall_status", "unknown")
        parts.append(f"整体状态: {overall}")

        sleep = rule_analysis.get("sleep_analysis", {})
        parts.append(f"睡眠: {sleep.get('status', 'unknown')} - {sleep.get('quality_assessment', '')}")

        activity = rule_analysis.get("activity_analysis", {})
        parts.append(f"活动: {activity.get('status', 'unknown')}")

        heart = rule_analysis.get("heart_rate_analysis", {})
        parts.append(f"心率: {heart.get('status', 'unknown')}")

        stress = rule_analysis.get("stress_analysis", {})
        parts.append(f"恢复: {stress.get('recovery_status', 'unknown')}")

        return "\n".join(parts)


# 单例实例
rag_pipeline = RAGPipeline()
