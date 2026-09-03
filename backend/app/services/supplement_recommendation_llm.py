"""
补剂科学推荐服务 - 基于 LLM 和知识库

益家知研 AI + 皮皮妈妈知识库
"""
import os
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData, DietRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.utils.timezone import get_china_now
from app.services.llm_health_analyzer import LLMHealthAnalyzer
from app.services.knowledge.rag_pipeline import RAGPipeline
from app.services.supplement_evidence import (
    enrich_supplement_recommendations,
    evidence_warnings_to_precautions,
)
from app.services.supplement_safety_context import build_supplement_safety_context

logger = logging.getLogger(__name__)


class SupplementRecommendationServiceLLM:
    """
    补剂科学推荐服务 - LLM 版本

    基于益家知研 AI 和皮皮妈妈知识库的智能推荐系统
    """

    def __init__(self):
        self.llm_analyzer = LLMHealthAnalyzer()
        self.rag_pipeline = RAGPipeline()
        self.knowledge_base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'knowledge',
            'supplement_knowledge.md'
        )

    async def generate_supplement_recommendation(
        self,
        db: Session,
        user_id: int,
        target_date: Optional[date] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        生成补剂科学推荐

        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期（默认今天）
            debug: 是否返回调试信息

        Returns:
            推荐结果（包含健康分析、推荐补剂、服用建议等）
        """
        start_time = time.time()

        if target_date is None:
            target_date = get_china_now().date()

        logger.info(f"[补剂推荐LLM] 开始为用户 {user_id} 生成推荐 (debug={debug})")

        # Debug 信息
        debug_info = {
            "steps": [],
            "data_sources": {},
            "reasoning": [],
            "knowledge_retrieved": [],
            "performance": {},
            "timeline": []
        } if debug else None

        try:
            # 1. 获取用户资料
            step_start = time.time()
            profile = db.query(UserProfile).filter_by(user_id=user_id).first()
            if debug:
                self._add_debug_step(debug_info, "获取用户资料", time.time() - step_start)
                self._add_debug_data(debug_info, "用户资料", {
                    "年龄": profile.age if profile else None,
                    "性别": profile.gender if profile else None,
                    "体重": f"{profile.current_weight_kg}kg" if profile and profile.current_weight_kg else None,
                    "身高": f"{profile.height_cm}cm" if profile and profile.height_cm else None,
                    "过敏": profile.allergies if profile and profile.allergies else [],
                    "慢性病": profile.chronic_conditions if profile and profile.chronic_conditions else []
                })

            # 2. 获取最近健康数据
            step_start = time.time()
            health_data = self._get_recent_health_data(db, user_id, target_date)
            if debug:
                self._add_debug_step(debug_info, "获取健康数据", time.time() - step_start)
                self._add_debug_data(debug_info, "健康数据", {
                    "睡眠时长": f"{health_data.get('avg_sleep_hours', 0):.1f}小时" if health_data else None,
                    "睡眠评分": health_data.get('latest_sleep_score') if health_data else None,
                    "压力水平": health_data.get('avg_stress_level') if health_data else None,
                    "静息心率": health_data.get('avg_resting_hr') if health_data else None
                })

            # 3. 获取运动数据
            step_start = time.time()
            workout_data = self._get_recent_workout_data(db, user_id, target_date)
            if debug:
                self._add_debug_step(debug_info, "获取运动数据", time.time() - step_start)
                self._add_debug_data(debug_info, "运动数据", {
                    "运动次数": workout_data.get('workout_count', 0) if workout_data else 0,
                    "总时长": f"{workout_data.get('total_duration_minutes', 0)}分钟" if workout_data else None,
                    "高强度": workout_data.get('has_high_intensity', False) if workout_data else False
                })

            # 4. 获取饮食数据
            step_start = time.time()
            diet_data = self._get_recent_diet_data(db, user_id, target_date)
            if debug:
                self._add_debug_step(debug_info, "获取饮食数据", time.time() - step_start)
                self._add_debug_data(debug_info, "饮食数据", {
                    "蛋白质": f"{diet_data.get('avg_daily_protein', 0):.1f}g" if diet_data else None,
                    "记录天数": diet_data.get('record_count', 0) if diet_data else 0
                })

            # 4.5 获取基因数据
            step_start = time.time()
            genetic_data = self._get_genetic_data(db, user_id)
            if debug:
                self._add_debug_step(debug_info, "获取基因数据", time.time() - step_start)
                self._add_debug_data(debug_info, "基因数据", {
                    "变异数量": len(genetic_data),
                    "高风险": [g['gene'] for g in genetic_data if g.get('risk') == 'high'],
                    "分类": list(set(g.get('category', '') for g in genetic_data)),
                })

            # 5. 获取当前补剂状态
            step_start = time.time()
            supplement_status = self._get_supplement_status(db, user_id, target_date)
            if debug:
                self._add_debug_step(debug_info, "获取补剂状态", time.time() - step_start)
                self._add_debug_data(debug_info, "补剂状态", {
                    "已添加补剂": supplement_status.get('total_count', 0),
                    "今日完成": supplement_status.get('taken_count', 0),
                    "完成率": f"{supplement_status.get('completion_rate_today', 0):.1f}%"
                })

            # 6. 从知识库检索相关信息
            step_start = time.time()
            knowledge_results = await self._retrieve_supplement_knowledge(
                profile, health_data, workout_data, diet_data, debug_info
            )
            if debug:
                self._add_debug_step(debug_info, "检索知识库", time.time() - step_start)
                self._add_debug_reasoning(debug_info, "info",
                    f"📚 从知识库检索到 {len(knowledge_results)} 条相关知识")

            # 7. 使用 LLM 生成推荐
            step_start = time.time()
            llm_result = await self._generate_llm_recommendation(
                profile, health_data, workout_data, diet_data,
                supplement_status, knowledge_results, debug_info,
                genetic_data=genetic_data
            )
            evidence_summary = enrich_supplement_recommendations(
                llm_result.get("recommendations", []),
                build_supplement_safety_context(db, user_id, profile, target_date),
            )
            llm_result["evidence_summary"] = evidence_summary
            llm_result["precautions"] = self._merge_precautions(
                llm_result.get("precautions", []),
                evidence_warnings_to_precautions(evidence_summary),
            )
            if debug:
                self._add_debug_step(debug_info, "LLM 生成推荐", time.time() - step_start)
                self._add_debug_reasoning(
                    debug_info,
                    "info",
                    f"🧾 结构化证据匹配 {evidence_summary.get('matched', 0)}/{evidence_summary.get('total', 0)} 条",
                )

            # 8. 计算总耗时
            total_time = time.time() - start_time
            if debug:
                debug_info["performance"]["total_time"] = f"{total_time:.2f}s"

            logger.info(f"[补剂推荐LLM] 推荐生成完成 - 耗时 {total_time:.2f}s")

            result = {
                "success": True,
                "generated_at": get_china_now().isoformat(),
                "target_date": target_date.isoformat(),
                **llm_result
            }

            if debug:
                result["debug"] = debug_info

            return result

        except Exception as e:
            logger.error(f"[补剂推荐LLM] 生成失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "生成补剂推荐失败，请稍后重试",
                "debug": debug_info if debug else None
            }

    async def _retrieve_supplement_knowledge(
        self,
        profile: Optional[UserProfile],
        health_data: Optional[Dict[str, Any]],
        workout_data: Optional[Dict[str, Any]],
        diet_data: Optional[Dict[str, Any]],
        debug_info: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """从知识库检索相关补剂知识"""

        # 构建查询策略
        queries = []

        # 基础查询
        queries.append({
            "query": "基础补剂推荐 维生素D 复合维生素",
            "category": None,
            "n_results": 3
        })

        # 基于健康数据的查询
        if health_data:
            sleep_hours = health_data.get('avg_sleep_hours', 0)
            if sleep_hours < 7:
                queries.append({
                    "query": "改善睡眠的补剂 镁 褪黑素",
                    "category": None,
                    "n_results": 3
                })
                if debug_info:
                    self._add_debug_reasoning(debug_info, "warning",
                        f"⚠️ 睡眠不足（{sleep_hours:.1f}小时），查询睡眠改善补剂")

            stress = health_data.get('avg_stress_level', 0)
            if stress > 50:
                queries.append({
                    "query": "压力管理补剂 维生素B族 Omega-3",
                    "category": None,
                    "n_results": 3
                })
                if debug_info:
                    self._add_debug_reasoning(debug_info, "warning",
                        f"⚠️ 压力水平较高（{stress}），查询压力管理补剂")

        # 基于运动数据的查询
        if workout_data and workout_data.get('workout_count', 0) > 3:
            queries.append({
                "query": "运动恢复补剂 蛋白粉 肌酸 BCAA",
                "category": None,
                "n_results": 3
            })
            if debug_info:
                self._add_debug_reasoning(debug_info, "success",
                    f"✅ 运动频繁（{workout_data.get('workout_count')}次/周），查询运动恢复补剂")

        # 基于过敏和疾病的查询
        if profile:
            if profile.chronic_conditions and '鼻炎' in str(profile.chronic_conditions):
                queries.append({
                    "query": "呼吸道健康补剂 NAC 维生素C",
                    "category": None,
                    "n_results": 2
                })
                if debug_info:
                    self._add_debug_reasoning(debug_info, "info",
                        "📋 检测到鼻炎，查询呼吸道健康补剂")

        # 执行检索
        all_results = []
        for query_config in queries:
            try:
                results = self.rag_pipeline.retrieve_relevant_knowledge(
                    query=query_config["query"],
                    category=query_config.get("category"),
                    n_results=query_config["n_results"]
                )
                all_results.extend(results)

                if debug_info:
                    debug_info["knowledge_retrieved"].append({
                        "query": query_config["query"],
                        "results_count": len(results),
                        "results": [r.get("content", "")[:100] + "..." for r in results]
                    })
            except Exception as e:
                logger.warning(f"[补剂推荐LLM] 知识库检索失败: {e}")

        # 去重和排序
        unique_results = []
        seen_content = set()
        for result in all_results:
            content = result.get("content", "")
            if content and content not in seen_content:
                seen_content.add(content)
                unique_results.append(result)

        # 返回前 10 条最相关的
        return unique_results[:10]

    async def _generate_llm_recommendation(
        self,
        profile: Optional[UserProfile],
        health_data: Optional[Dict[str, Any]],
        workout_data: Optional[Dict[str, Any]],
        diet_data: Optional[Dict[str, Any]],
        supplement_status: Dict[str, Any],
        knowledge_results: List[Dict[str, Any]],
        debug_info: Optional[Dict[str, Any]],
        genetic_data: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """使用 LLM 生成补剂推荐"""

        # 构建知识库上下文
        knowledge_context = "\n\n".join([
            f"【知识点 {i+1}】\n{r.get('content', '')}"
            for i, r in enumerate(knowledge_results[:5])
        ])

        # 构建用户上下文
        user_context = self._build_user_context(
            profile, health_data, workout_data, diet_data, supplement_status,
            genetic_data=genetic_data
        )

        # 构建 Prompt
        system_prompt = """你是益家知研 AI 的补剂推荐专家，结合皮皮妈妈营养知识库，为用户提供个性化的补剂建议。

你的任务：
1. 分析用户的健康状况和需求
2. 基于知识库推荐合适的补剂
3. 提供详细的理由和使用建议
4. 给出注意事项

输出格式（JSON）：
{
  "health_analysis": {
    "sleep_quality": "良好/偏少/不足",
    "stress_level": "低/中等/偏高/高",
    "exercise_intensity": "缺乏/偏少/适中/高",
    "nutrition_status": "充足/基本充足/不足",
    "positive_factors": ["积极因素1", "积极因素2"],
    "risk_factors": ["风险因素1", "风险因素2"]
  },
  "recommendations": [
    {
      "category": "basic/sleep/stress/exercise/nutrition/special",
      "name": "补剂名称",
      "reason": "推荐理由（基于用户数据和知识库）",
      "dosage": "推荐剂量",
      "timing": "服用时间",
      "priority": "高/中/低",
      "icon": "emoji图标",
      "knowledge_source": "来自知识库的哪个部分"
    }
  ],
  "timing_suggestions": {
    "morning": ["早晨服用的补剂"],
    "noon": ["中午服用的补剂"],
    "evening": ["晚上服用的补剂"],
    "bedtime": ["睡前服用的补剂"],
    "workout": ["运动相关的补剂"]
  },
  "precautions": ["注意事项1", "注意事项2"],
  "overall_rating": {
    "score": 0-10,
    "rating": "优秀/良好/一般/需改进",
    "emoji": "😊/😐/😰",
    "message": "总体评价"
  }
}

注意：
- 推荐要基于用户的实际数据和需求
- 如有基因检测数据, 只能作为风险分层和追问线索, 不能直接替代化验、医生判断或形成确定性剂量指令：
  - MTHFR C677T TT/CT: 提示叶酸代谢可能受影响；是否使用 5-MTHF 或甲基化 B 族, 需要结合同型半胱氨酸、B12、叶酸化验、饮食和医生或营养师意见
  - ALDH2 缺陷: 避免主动推荐含酒精补剂；NAD+ 前体等建议需结合耐受性和用药情况
  - CYP1A2 慢代谢: 对咖啡因和绿茶提取物等含咖啡因补剂保持保守
  - FADS1/FADS2: 可提示 omega-3 转化效率差异, EPA/DHA 剂量仍需结合饮食摄入、血脂和出血风险
  - VDR 变异: 可提示关注维生素 D 状态, 剂量应结合 25(OH)D 化验
  - COMT Met/Met: 对高剂量甲基供体保持谨慎, 结合症状和专业意见
- 优先推荐最需要的补剂（3-5个即可）
- 考虑用户的过敏史和疾病史
- 给出具体的剂量和服用时间
- 提供清晰的理由，引用知识库内容和基因数据
"""

        user_prompt = f"""请为以下用户生成补剂推荐：

## 用户信息
{user_context}

## 知识库参考
{knowledge_context}

## 当前补剂状态
- 已添加补剂数：{supplement_status.get('total_count', 0)}
- 今日完成率：{supplement_status.get('completion_rate_today', 0):.1f}%
- 7天完成率：{supplement_status.get('completion_rate_7days', 0):.1f}%

请基于以上信息，生成个性化的补剂推荐方案。"""

        if debug_info:
            self._add_debug_reasoning(debug_info, "info", "🤖 开始调用 LLM 生成推荐")
            self._add_debug_reasoning(debug_info, "info", f"📝 Prompt 长度: {len(system_prompt + user_prompt)} 字符")

        # 调用 LLM
        try:
            step_start = time.time()
            response = await self.llm_analyzer.analyze_with_prompt(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            llm_time = time.time() - step_start

            if debug_info:
                self._add_debug_step(debug_info, "LLM 推理", llm_time)
                self._add_debug_reasoning(debug_info, "success",
                    f"✅ LLM 响应完成，耗时 {llm_time:.2f}s")

            # 解析 LLM 响应
            import json
            result = json.loads(response)

            # 确保字段完整性
            result = self._validate_and_fill_result(result)

            if debug_info:
                self._add_debug_reasoning(debug_info, "success",
                    f"✅ 生成 {len(result.get('recommendations', []))} 个推荐")

            return result

        except Exception as e:
            logger.error(f"[补剂推荐LLM] LLM 调用失败: {e}", exc_info=True)

            if debug_info:
                self._add_debug_reasoning(debug_info, "error",
                    f"❌ LLM 调用失败: {str(e)}")

            # 降级到规则推荐
            return self._fallback_rule_based_recommendation(
                profile, health_data, workout_data, diet_data,
                supplement_status, debug_info
            )

    def _build_user_context(
        self,
        profile: Optional[UserProfile],
        health_data: Optional[Dict[str, Any]],
        workout_data: Optional[Dict[str, Any]],
        diet_data: Optional[Dict[str, Any]],
        supplement_status: Dict[str, Any],
        genetic_data: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """构建用户上下文"""
        context_parts = []

        # 基本信息
        if profile:
            context_parts.append("### 基本信息")
            context_parts.append(f"- 年龄：{profile.age}岁")
            context_parts.append(f"- 性别：{profile.gender}")
            if profile.current_weight_kg:
                context_parts.append(f"- 体重：{profile.current_weight_kg}kg")
            if profile.height_cm:
                context_parts.append(f"- 身高：{profile.height_cm}cm")
                if profile.current_weight_kg:
                    bmi = profile.current_weight_kg / ((profile.height_cm / 100) ** 2)
                    context_parts.append(f"- BMI：{bmi:.1f}")

            if profile.chronic_conditions:
                context_parts.append(f"- 慢性病：{', '.join(profile.chronic_conditions)}")
            if profile.allergies:
                context_parts.append(f"- 过敏：{', '.join(profile.allergies)}")

        # 基因数据 — 关键个性化信息
        if genetic_data:
            context_parts.append(f"\n### 基因检测数据（{len(genetic_data)}项变异）")
            # 按分类分组
            by_cat: Dict[str, list] = {}
            for g in genetic_data:
                cat = g.get('category', 'other')
                by_cat.setdefault(cat, []).append(g)
            cat_labels = {'nutrition': '营养代谢', 'exercise': '运动基因', 'drug_sensitivity': '药物敏感性', 'disease_risk': '疾病风险', 'sleep': '睡眠基因'}
            for cat, items in by_cat.items():
                context_parts.append(f"\n**{cat_labels.get(cat, cat)}:**")
                for g in items:
                    risk_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(g.get('risk', ''), 'ℹ️')
                    line = f"- {risk_emoji} {g['gene']}"
                    if g.get('variant'):
                        line += f" {g['variant']}"
                    if g.get('genotype'):
                        line += f" ({g['genotype']})"
                    if g.get('result'):
                        line += f": {g['result']}"
                    if g.get('description'):
                        line += f" — {g['description'][:100]}"
                    context_parts.append(line)

        # 健康数据
        if health_data:
            context_parts.append("\n### 最近健康数据（7天平均）")
            context_parts.append(f"- 睡眠时长：{health_data.get('avg_sleep_hours', 0):.1f}小时/天")
            if health_data.get('latest_sleep_score'):
                context_parts.append(f"- 睡眠评分：{health_data.get('latest_sleep_score')}/100")
            context_parts.append(f"- 压力水平：{health_data.get('avg_stress_level', 0):.0f}/100")
            context_parts.append(f"- 静息心率：{health_data.get('avg_resting_hr', 0):.0f} bpm")

        # 运动数据
        if workout_data:
            context_parts.append("\n### 运动情况（最近7天）")
            context_parts.append(f"- 运动次数：{workout_data.get('workout_count', 0)}次")
            context_parts.append(f"- 总时长：{workout_data.get('total_duration_minutes', 0)}分钟")
            if workout_data.get('has_high_intensity'):
                context_parts.append("- 包含高强度训练")

        # 饮食数据
        if diet_data:
            context_parts.append("\n### 饮食情况（最近7天）")
            context_parts.append(f"- 平均蛋白质：{diet_data.get('avg_daily_protein', 0):.1f}g/天")
            if profile and profile.current_weight_kg:
                protein_per_kg = diet_data.get('avg_daily_protein', 0) / profile.current_weight_kg
                context_parts.append(f"- 蛋白质/体重：{protein_per_kg:.2f}g/kg")

        return "\n".join(context_parts)

    def _get_genetic_data(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """获取用户基因数据"""
        try:
            from app.models.genetic_data import GeneticVariant
            variants = db.query(GeneticVariant).filter(
                GeneticVariant.user_id == user_id
            ).order_by(
                # 高风险优先
                GeneticVariant.risk_level.desc(),
                GeneticVariant.category
            ).all()
            return [
                {
                    "gene": v.gene_name,
                    "variant": v.variant_name,
                    "genotype": v.genotype,
                    "result": v.result_label,
                    "risk": v.risk_level,
                    "category": v.category,
                    "description": v.description,
                    "implications": v.health_implications,
                }
                for v in variants
            ]
        except Exception as e:
            logger.warning(f"[补剂推荐LLM] 获取基因数据失败: {e}")
            return []

    def _validate_and_fill_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """验证并填充结果字段"""
        return {
            "health_analysis": result.get("health_analysis", {
                "sleep_quality": "未知",
                "stress_level": "未知",
                "exercise_intensity": "未知",
                "nutrition_status": "未知",
                "positive_factors": [],
                "risk_factors": []
            }),
            "recommendations": result.get("recommendations", []),
            "timing_suggestions": result.get("timing_suggestions", {
                "morning": [],
                "noon": [],
                "evening": [],
                "bedtime": [],
                "workout": []
            }),
            "precautions": result.get("precautions", []),
            "overall_rating": result.get("overall_rating", {
                "score": 7,
                "rating": "良好",
                "emoji": "😊",
                "message": "补剂方案合理"
            })
        }

    @staticmethod
    def _merge_precautions(existing: List[str], extra: List[str], limit: int = 7) -> List[str]:
        merged: List[str] = []
        seen = set()
        for item in [*existing, *extra]:
            if not item or item in seen:
                continue
            seen.add(item)
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    def _fallback_rule_based_recommendation(
        self,
        profile: Optional[UserProfile],
        health_data: Optional[Dict[str, Any]],
        workout_data: Optional[Dict[str, Any]],
        diet_data: Optional[Dict[str, Any]],
        supplement_status: Dict[str, Any],
        debug_info: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """降级到规则推荐（当 LLM 失败时）"""

        if debug_info:
            self._add_debug_reasoning(debug_info, "warning",
                "⚠️ LLM 不可用，使用规则推荐")

        recommendations = []

        # 基础推荐
        recommendations.append({
            "category": "basic",
            "name": "维生素D3",
            "reason": "基础营养补充，现代人普遍缺乏维生素D",
            "dosage": "1000-2000 IU",
            "timing": "早餐后",
            "priority": "高",
            "icon": "☀️",
            "knowledge_source": "基础补剂知识库"
        })

        recommendations.append({
            "category": "basic",
            "name": "复合维生素",
            "reason": "确保每日所需维生素和矿物质的全面摄入",
            "dosage": "1片",
            "timing": "早餐后",
            "priority": "中",
            "icon": "💊",
            "knowledge_source": "基础补剂知识库"
        })

        recommendations.append({
            "category": "basic",
            "name": "Omega-3 鱼油",
            "reason": "减轻炎症，支持心血管和大脑健康",
            "dosage": "1000mg EPA+DHA",
            "timing": "随餐",
            "priority": "中",
            "icon": "🐟",
            "knowledge_source": "基础补剂知识库"
        })

        return {
            "health_analysis": {
                "sleep_quality": "未知",
                "stress_level": "未知",
                "exercise_intensity": "未知",
                "nutrition_status": "未知",
                "positive_factors": [],
                "risk_factors": ["LLM 服务暂时不可用"]
            },
            "recommendations": recommendations,
            "timing_suggestions": {
                "morning": ["维生素D3", "复合维生素"],
                "noon": [],
                "evening": ["Omega-3"],
                "bedtime": [],
                "workout": []
            },
            "precautions": [
                "以上为基础推荐，建议咨询医生或营养师",
                "如有疾病或正在服药，请先咨询医生",
                "补剂不能替代均衡饮食"
            ],
            "overall_rating": {
                "score": 7,
                "rating": "良好",
                "emoji": "😊",
                "message": "基础补剂方案，建议根据个人情况调整"
            }
        }

    # ===== 数据获取方法（与原服务相同）=====

    def _get_recent_health_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """获取最近健康数据"""
        try:
            records = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= target_date - timedelta(days=7),
                GarminData.record_date <= target_date
            ).order_by(GarminData.record_date.desc()).all()

            if not records:
                return None

            # 计算平均值
            sleep_hours = [r.total_sleep_duration / 60 for r in records if r.total_sleep_duration]
            stress_levels = [r.stress_level for r in records if r.stress_level]
            resting_hrs = [r.resting_heart_rate for r in records if r.resting_heart_rate]

            return {
                "avg_sleep_hours": sum(sleep_hours) / len(sleep_hours) if sleep_hours else 0,
                "avg_stress_level": sum(stress_levels) / len(stress_levels) if stress_levels else 0,
                "avg_resting_hr": sum(resting_hrs) / len(resting_hrs) if resting_hrs else 0,
                "latest_sleep_score": records[0].sleep_score if records[0].sleep_score else None,
                "latest_body_battery": records[0].body_battery_current if records[0].body_battery_current else None,
                "data_count": len(records)
            }
        except Exception as e:
            logger.error(f"[补剂推荐LLM] 获取健康数据失败: {e}")
            return None

    def _get_recent_workout_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """获取最近运动数据"""
        try:
            from app.models.daily_health import WorkoutRecord

            records = db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.start_time >= target_date - timedelta(days=7),
                WorkoutRecord.start_time <= target_date
            ).all()

            if not records:
                return None

            total_duration = sum([r.duration_seconds / 60 for r in records if r.duration_seconds])
            has_high_intensity = any([
                r.avg_heart_rate and r.avg_heart_rate > 150
                for r in records
            ])

            return {
                "workout_count": len(records),
                "total_duration_minutes": total_duration,
                "avg_duration_minutes": total_duration / len(records) if records else 0,
                "has_high_intensity": has_high_intensity
            }
        except Exception as e:
            logger.error(f"[补剂推荐LLM] 获取运动数据失败: {e}")
            return None

    def _get_recent_diet_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """获取最近饮食数据"""
        try:
            records = db.query(DietRecord).filter(
                DietRecord.user_id == user_id,
                DietRecord.record_date >= target_date - timedelta(days=7),
                DietRecord.record_date <= target_date
            ).all()

            if not records:
                return None

            total_protein = sum([r.protein for r in records if r.protein])

            return {
                "record_count": len(records),
                "avg_daily_protein": total_protein / 7 if total_protein else 0
            }
        except Exception as e:
            logger.error(f"[补剂推荐LLM] 获取饮食数据失败: {e}")
            return None

    def _get_supplement_status(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """获取当前补剂服用情况"""
        try:
            # 获取用户的所有补剂定义
            definitions = db.query(SupplementDefinition).filter_by(
                user_id=user_id,
                is_active=True
            ).all()

            # 获取今日记录
            today_records = db.query(SupplementRecord).filter_by(
                user_id=user_id,
                record_date=target_date
            ).all()

            # 获取最近7天记录
            week_records = db.query(SupplementRecord).filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.record_date >= target_date - timedelta(days=6),
                SupplementRecord.record_date <= target_date
            ).all()

            taken_today = len([r for r in today_records if r.taken])
            taken_week = len([r for r in week_records if r.taken])

            return {
                "total_count": len(definitions),
                "taken_count": taken_today,
                "completion_rate_today": (taken_today / len(definitions) * 100) if definitions else 0,
                "completion_rate_7days": (taken_week / (len(definitions) * 7) * 100) if definitions else 0,
                "categories": {},
                "has_supplements": len(definitions) > 0
            }
        except Exception as e:
            logger.error(f"[补剂推荐LLM] 获取补剂状态失败: {e}")
            return {
                "total_count": 0,
                "taken_count": 0,
                "completion_rate_today": 0,
                "completion_rate_7days": 0,
                "categories": {},
                "has_supplements": False
            }

    # ===== Debug 辅助方法 =====

    def _add_debug_step(
        self,
        debug_info: Dict[str, Any],
        step_name: str,
        duration: float
    ):
        """添加调试步骤"""
        debug_info["steps"].append({
            "name": step_name,
            "duration": f"{duration:.3f}s",
            "timestamp": datetime.now().isoformat()
        })
        debug_info["timeline"].append(f"{step_name}: {duration:.3f}s")

    def _add_debug_data(
        self,
        debug_info: Dict[str, Any],
        source_name: str,
        data: Dict[str, Any]
    ):
        """添加数据来源"""
        debug_info["data_sources"][source_name] = data

    def _add_debug_reasoning(
        self,
        debug_info: Dict[str, Any],
        level: str,
        message: str
    ):
        """添加推理过程"""
        debug_info["reasoning"].append({
            "level": level,  # success/info/warning/error
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
