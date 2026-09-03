"""
补剂科学推荐服务
基于用户健康数据、运动数据、饮食数据，提供个性化补剂推荐
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import timedelta, date
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData, WorkoutRecord, DietRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.services.knowledge_evidence import build_advice_knowledge_context
from app.services.supplement_evidence import (
    enrich_supplement_recommendations,
    evidence_warnings_to_precautions,
)
from app.services.supplement_safety_context import build_supplement_safety_context
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class SupplementRecommendationService:
    """补剂科学推荐服务"""

    def generate_supplement_recommendation(
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
            debug: 是否返回调试信息（默认False）

        Returns:
            补剂科学推荐结果
        """
        try:
            logger.info(f"[补剂推荐] 开始为用户 {user_id} 生成推荐 (debug={debug})")

            if target_date is None:
                target_date = get_china_now().date()

            # 1. 获取用户基本信息
            profile = db.query(UserProfile).filter_by(user_id=user_id).first()

            # 2. 获取最近健康数据
            health_data = self._get_recent_health_data(db, user_id, target_date)

            # 3. 获取最近运动数据
            workout_data = self._get_recent_workout_data(db, user_id, target_date)

            # 4. 获取最近饮食数据
            diet_data = self._get_recent_diet_data(db, user_id, target_date)

            # 5. 获取当前补剂服用情况
            supplement_status = self._get_supplement_status(db, user_id, target_date)

            # 6. 分析健康状况
            health_analysis = self._analyze_health_status(
                profile, health_data, workout_data, diet_data
            )

            # 7. 生成补剂推荐
            recommendations = self._generate_recommendations(
                profile, health_analysis, supplement_status
            )
            knowledge_evidence = self._build_knowledge_evidence(health_analysis, recommendations)
            self._attach_knowledge_evidence(recommendations, knowledge_evidence)
            evidence_summary = enrich_supplement_recommendations(
                recommendations,
                build_supplement_safety_context(db, user_id, profile, target_date),
            )

            # 8. 生成服用时间建议
            timing_suggestions = self._generate_timing_suggestions(
                recommendations, workout_data
            )

            # 9. 生成注意事项
            precautions = self._generate_precautions(
                profile, health_analysis, recommendations
            )
            precautions = self._merge_precautions(
                precautions,
                evidence_warnings_to_precautions(evidence_summary),
            )

            # 10. 计算整体评分
            overall_rating = self._calculate_overall_rating(
                supplement_status, health_analysis
            )

            result = {
                "success": True,
                "generated_at": get_china_now().isoformat(),
                "target_date": target_date.isoformat(),
                "health_analysis": health_analysis,
                "recommendations": recommendations,
                "timing_suggestions": timing_suggestions,
                "precautions": precautions,
                "supplement_status": supplement_status,
                "knowledge_evidence": knowledge_evidence,
                "evidence_summary": evidence_summary,
                "overall_rating": overall_rating,
                # 兼容小程序字段
                "overall_score": overall_rating.get("score", 0) * 10,
                "rating": overall_rating.get("rating", "一般")
            }

            logger.info(f"[补剂推荐] 推荐生成完成 - 推荐数量: {len(recommendations)}")
            logger.info(f"[补剂推荐] 推荐列表: {[r['name'] for r in recommendations]}")
            return result

        except Exception as e:
            logger.error(f"[补剂推荐] 生成失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "生成补剂推荐失败，请稍后重试"
            }

    def _get_recent_health_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """获取最近健康数据"""
        try:
            # 获取最近7天的数据
            start_date = target_date - timedelta(days=7)
            records = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= start_date,
                GarminData.record_date <= target_date
            ).order_by(GarminData.record_date.desc()).all()

            if not records:
                return None

            # 计算平均值
            # total_sleep_duration 是分钟，转换为小时
            avg_sleep = sum((r.total_sleep_duration or 0) / 60 for r in records) / len(records)
            avg_stress = sum(r.stress_level or 0 for r in records) / len(records)
            avg_rhr = sum(r.resting_heart_rate or 0 for r in records if r.resting_heart_rate) / max(
                len([r for r in records if r.resting_heart_rate]), 1
            )

            return {
                "avg_sleep_hours": round(avg_sleep, 1),
                "avg_stress_level": round(avg_stress, 1),
                "avg_resting_hr": round(avg_rhr, 0),
                "latest_sleep_score": records[0].sleep_score if records[0].sleep_score else None,
                "latest_body_battery": records[0].body_battery_current if records[0].body_battery_current else None,
                "data_count": len(records)
            }
        except Exception as e:
            logger.error(f"[补剂推荐] 获取健康数据失败: {e}")
            return None

    def _get_recent_workout_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """获取最近运动数据"""
        try:
            # 获取最近7天的运动记录
            start_date = target_date - timedelta(days=7)
            workouts = db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= start_date,
                WorkoutRecord.workout_date <= target_date
            ).all()

            if not workouts:
                return None

            total_duration = sum(w.duration_seconds or 0 for w in workouts) / 60  # 转换为分钟
            total_calories = sum(w.calories or 0 for w in workouts)

            # 统计运动类型
            workout_types = {}
            for w in workouts:
                wtype = w.workout_type or "其他"
                workout_types[wtype] = workout_types.get(wtype, 0) + 1

            return {
                "workout_count": len(workouts),
                "total_duration_minutes": round(total_duration, 0),
                "total_calories": total_calories,
                "workout_types": workout_types,
                "has_high_intensity": any(
                    (w.avg_heart_rate or 0) > 150 for w in workouts
                )
            }
        except Exception as e:
            logger.error(f"[补剂推荐] 获取运动数据失败: {e}")
            return None

    def _get_recent_diet_data(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Optional[Dict[str, Any]]:
        """获取最近饮食数据"""
        try:
            # 获取最近3天的饮食记录
            start_date = target_date - timedelta(days=3)
            diet_records = db.query(DietRecord).filter(
                DietRecord.user_id == user_id,
                DietRecord.record_date >= start_date,
                DietRecord.record_date <= target_date
            ).all()

            if not diet_records:
                return None

            total_protein = sum(r.protein or 0 for r in diet_records)
            total_carbs = sum(r.carbs or 0 for r in diet_records)
            total_fat = sum(r.fat or 0 for r in diet_records)

            return {
                "meal_count": len(diet_records),
                "avg_daily_protein": round(total_protein / 3, 1),
                "avg_daily_carbs": round(total_carbs / 3, 1),
                "avg_daily_fat": round(total_fat / 3, 1),
                "has_diet_tracking": True
            }
        except Exception as e:
            logger.error(f"[补剂推荐] 获取饮食数据失败: {e}")
            return None

    def _get_supplement_status(
        self,
        db: Session,
        user_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """获取补剂服用状态"""
        try:
            # 获取用户的所有补剂定义
            supplements = db.query(SupplementDefinition).filter(
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.is_active.is_(True),
            ).all()

            # 获取今天的打卡记录
            records = db.query(SupplementRecord).filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.record_date == target_date
            ).all()

            taken_ids = {r.supplement_id for r in records if r.taken}

            # 获取最近7天的完成率
            start_date = target_date - timedelta(days=7)
            recent_records = db.query(SupplementRecord).filter(
                SupplementRecord.user_id == user_id,
                SupplementRecord.record_date >= start_date,
                SupplementRecord.record_date <= target_date
            ).all()

            total_expected = len(supplements) * 7
            total_taken = sum(1 for r in recent_records if r.taken)
            completion_rate = round(total_taken / total_expected * 100, 1) if total_expected > 0 else 0

            # 按分类统计
            categories = {}
            for supp in supplements:
                cat = supp.category
                if cat not in categories:
                    categories[cat] = {"total": 0, "taken_today": 0}
                categories[cat]["total"] += 1
                if supp.id in taken_ids:
                    categories[cat]["taken_today"] += 1

            return {
                "total_supplements": len(supplements),
                "taken_today": len(taken_ids),
                "completion_rate_7days": completion_rate,
                "categories": categories,
                "has_supplements": len(supplements) > 0
            }
        except Exception as e:
            logger.error(f"[补剂推荐] 获取补剂状态失败: {e}")
            return {
                "total_supplements": 0,
                "taken_today": 0,
                "completion_rate_7days": 0,
                "categories": {},
                "has_supplements": False
            }

    def _analyze_health_status(
        self,
        profile: Optional[UserProfile],
        health_data: Optional[Dict[str, Any]],
        workout_data: Optional[Dict[str, Any]],
        diet_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析健康状况"""
        analysis = {
            "sleep_quality": "未知",
            "stress_level": "未知",
            "exercise_intensity": "未知",
            "nutrition_status": "未知",
            "risk_factors": [],
            "positive_factors": []
        }

        # 1. 睡眠质量分析
        if health_data and health_data.get("avg_sleep_hours"):
            sleep_hours = health_data["avg_sleep_hours"]
            if sleep_hours < 6:
                analysis["sleep_quality"] = "不足"
                analysis["risk_factors"].append("睡眠不足（平均 {:.1f} 小时/天）".format(sleep_hours))
            elif sleep_hours < 7:
                analysis["sleep_quality"] = "偏少"
                analysis["risk_factors"].append("睡眠偏少（平均 {:.1f} 小时/天）".format(sleep_hours))
            elif sleep_hours <= 9:
                analysis["sleep_quality"] = "良好"
                analysis["positive_factors"].append("睡眠充足（平均 {:.1f} 小时/天）".format(sleep_hours))
            else:
                analysis["sleep_quality"] = "过多"

        # 2. 压力水平分析
        if health_data and health_data.get("avg_stress_level"):
            stress = health_data["avg_stress_level"]
            if stress < 25:
                analysis["stress_level"] = "低"
                analysis["positive_factors"].append("压力水平较低")
            elif stress < 50:
                analysis["stress_level"] = "中等"
            elif stress < 75:
                analysis["stress_level"] = "偏高"
                analysis["risk_factors"].append("压力水平偏高")
            else:
                analysis["stress_level"] = "高"
                analysis["risk_factors"].append("压力水平较高")

        # 3. 运动强度分析
        if workout_data:
            workout_count = workout_data.get("workout_count", 0)

            if workout_count == 0:
                analysis["exercise_intensity"] = "缺乏"
                analysis["risk_factors"].append("最近7天无运动记录")
            elif workout_count < 3:
                analysis["exercise_intensity"] = "偏少"
                analysis["risk_factors"].append("运动频率偏低（{} 次/周）".format(workout_count))
            elif workout_count <= 5:
                analysis["exercise_intensity"] = "适中"
                analysis["positive_factors"].append("运动频率适中（{} 次/周）".format(workout_count))
            else:
                analysis["exercise_intensity"] = "高"
                if workout_data.get("has_high_intensity"):
                    analysis["positive_factors"].append("高强度训练（{} 次/周）".format(workout_count))
                else:
                    analysis["positive_factors"].append("运动频率较高（{} 次/周）".format(workout_count))

        # 4. 营养状况分析
        if diet_data:
            protein = diet_data.get("avg_daily_protein", 0)
            if profile and profile.current_weight_kg:
                protein_per_kg = protein / profile.current_weight_kg
                if protein_per_kg < 0.8:
                    analysis["nutrition_status"] = "蛋白质不足"
                    analysis["risk_factors"].append("蛋白质摄入不足（{:.1f}g/kg）".format(protein_per_kg))
                elif protein_per_kg < 1.2:
                    analysis["nutrition_status"] = "基本充足"
                elif protein_per_kg <= 2.0:
                    analysis["nutrition_status"] = "充足"
                    analysis["positive_factors"].append("蛋白质摄入充足（{:.1f}g/kg）".format(protein_per_kg))
                else:
                    analysis["nutrition_status"] = "过量"
            else:
                analysis["nutrition_status"] = "有记录"

        return analysis

    def _generate_recommendations(
        self,
        profile: Optional[UserProfile],
        health_analysis: Dict[str, Any],
        supplement_status: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        生成补剂推荐

        基于益家知研 AI 和皮皮妈妈知识库的智能推荐系统
        """
        recommendations = []

        # 1. 基于睡眠质量推荐
        if health_analysis["sleep_quality"] in ["不足", "偏少"]:
            recommendations.append({
                "category": "sleep",
                "name": "镁补充剂（益家知研推荐）",
                "reason": "【益家知研分析】睡眠不足，镁有助于放松神经、改善睡眠质量。根据皮皮妈妈知识库，镁是天然的放松剂。",
                "dosage": "300-400mg",
                "timing": "睡前30分钟",
                "priority": "高",
                "icon": "😴"
            })
            recommendations.append({
                "category": "sleep",
                "name": "褪黑素（益家知研推荐）",
                "reason": "【益家知研分析】睡眠不足，褪黑素可以帮助调节睡眠周期。建议从低剂量开始。",
                "dosage": "0.5-3mg",
                "timing": "睡前1小时",
                "priority": "中",
                "icon": "🌙"
            })

        # 2. 基于压力水平推荐
        if health_analysis["stress_level"] in ["偏高", "高"]:
            recommendations.append({
                "category": "stress",
                "name": "维生素B族",
                "reason": "压力较大，B族维生素有助于神经系统健康和能量代谢",
                "dosage": "B-Complex",
                "timing": "早餐后",
                "priority": "高",
                "icon": "💊"
            })
            recommendations.append({
                "category": "stress",
                "name": "Omega-3 鱼油",
                "reason": "压力较大，Omega-3有助于减轻炎症、改善情绪",
                "dosage": "1000-2000mg EPA+DHA",
                "timing": "随餐",
                "priority": "中",
                "icon": "🐟"
            })

        # 3. 基于运动强度推荐
        if health_analysis["exercise_intensity"] in ["适中", "高"]:
            recommendations.append({
                "category": "exercise",
                "name": "蛋白粉",
                "reason": "运动量较大，蛋白质有助于肌肉恢复和生长",
                "dosage": "20-30g",
                "timing": "运动后30分钟内",
                "priority": "高",
                "icon": "💪"
            })
            recommendations.append({
                "category": "exercise",
                "name": "肌酸",
                "reason": "运动量较大，肌酸可以提升力量和运动表现",
                "dosage": "5g",
                "timing": "运动前或运动后",
                "priority": "中",
                "icon": "🔥"
            })

        # 4. 基于营养状况推荐
        if health_analysis["nutrition_status"] == "蛋白质不足":
            recommendations.append({
                "category": "nutrition",
                "name": "蛋白粉",
                "reason": "蛋白质摄入不足，建议补充优质蛋白",
                "dosage": "20-30g",
                "timing": "早餐或加餐",
                "priority": "高",
                "icon": "🥛"
            })

        # 5. 基础推荐（适用于所有人 - 确保至少有推荐）
        if len(recommendations) < 3:  # 如果推荐少于3个，添加基础推荐
            recommendations.append({
                "category": "basic",
                "name": "维生素D3（益家知研精选）",
                "reason": "【益家知研 + 皮皮妈妈知识库】基础营养补充，有助于骨骼健康和免疫力。现代人普遍缺乏维生素D。",
                "dosage": "1000-2000 IU",
                "timing": "早餐后",
                "priority": "高",
                "icon": "☀️"
            })

        if len(recommendations) < 3:
            recommendations.append({
                "category": "basic",
                "name": "复合维生素（益家知研精选）",
                "reason": "【益家知研 + 皮皮妈妈知识库】基础营养补充，确保每日所需维生素和矿物质的全面摄入。",
                "dosage": "1片",
                "timing": "早餐后",
                "priority": "中",
                "icon": "💊"
            })

        # 按优先级排序
        priority_order = {"高": 0, "中": 1, "低": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return recommendations[:6]  # 最多返回6条推荐

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

    def _build_knowledge_evidence(
        self,
        health_analysis: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """用 LLM Wiki 为补剂推荐补证据, 仅作为健康管理依据."""
        signals = []
        signals.extend(health_analysis.get("risk_factors", []))
        signals.extend(health_analysis.get("positive_factors", []))
        signals.extend(rec.get("name", "") for rec in recommendations)
        return build_advice_knowledge_context(
            domains=["supplement", "nutrition"],
            user_signals=[str(s) for s in signals if s],
        )

    def _attach_knowledge_evidence(
        self,
        recommendations: List[Dict[str, Any]],
        knowledge_evidence: Dict[str, Any],
    ) -> None:
        """把可追溯证据挂到每条建议上, 避免裸推荐."""
        sources = knowledge_evidence.get("sources") or []
        boundary = knowledge_evidence.get("claim_boundary") or ""
        if not sources and not boundary:
            return
        for recommendation in recommendations:
            recommendation["knowledge_sources"] = sources[:3]
            recommendation["claim_boundary"] = boundary

    def _generate_timing_suggestions(
        self,
        recommendations: List[Dict[str, Any]],
        workout_data: Optional[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """生成服用时间建议"""
        suggestions = {
            "morning": [],
            "noon": [],
            "evening": [],
            "bedtime": [],
            "workout": []
        }

        for rec in recommendations:
            timing = rec["timing"]
            name = rec["name"]

            if "早餐" in timing or "早晨" in timing:
                suggestions["morning"].append(name)
            elif "午餐" in timing or "中午" in timing:
                suggestions["noon"].append(name)
            elif "晚餐" in timing or "晚上" in timing:
                suggestions["evening"].append(name)
            elif "睡前" in timing:
                suggestions["bedtime"].append(name)
            elif "运动" in timing:
                suggestions["workout"].append(name)

        return suggestions

    def _generate_precautions(
        self,
        profile: Optional[UserProfile],
        health_analysis: Dict[str, Any],
        recommendations: List[Dict[str, Any]]
    ) -> List[str]:
        """生成注意事项"""
        precautions = []

        # 通用注意事项
        precautions.append("⚠️ 补剂不能替代均衡饮食，应优先从食物中获取营养")
        precautions.append("💊 开始新的补剂前，建议咨询医生或营养师")
        precautions.append("📊 补剂效果因人而异，建议持续服用 4-8 周后评估效果")

        # 基于推荐的注意事项
        rec_names = [r["name"] for r in recommendations]

        if "镁补充剂" in rec_names:
            precautions.append("🚫 镁过量可能导致腹泻，建议从小剂量开始")

        if "褪黑素" in rec_names:
            precautions.append("🌙 褪黑素不建议长期每日使用，可按需服用")

        if "肌酸" in rec_names:
            precautions.append("💧 服用肌酸期间需要多喝水（每天 3-4 升）")

        if "蛋白粉" in rec_names:
            precautions.append("🥛 蛋白粉应分散在全天摄入，不要一次性大量摄入")

        # 基于健康状况的注意事项
        if health_analysis["stress_level"] == "高":
            precautions.append("🧘 除了补剂，建议配合冥想、瑜伽等减压方式")

        return precautions[:5]  # 最多5条

    def _calculate_overall_rating(
        self,
        supplement_status: Dict[str, Any],
        health_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """计算整体评分"""
        score = 5  # 基础分

        # 1. 基于补剂完成率
        completion_rate = supplement_status.get("completion_rate_7days", 0)
        if completion_rate >= 90:
            score += 3
        elif completion_rate >= 70:
            score += 2
        elif completion_rate >= 50:
            score += 1

        # 2. 基于健康状况
        positive_count = len(health_analysis.get("positive_factors", []))
        risk_count = len(health_analysis.get("risk_factors", []))

        score += min(positive_count, 3)  # 最多加3分
        score -= min(risk_count, 2)  # 最多减2分

        score = max(0, min(score, 10))  # 限制在0-10之间

        if score >= 8:
            rating = "优秀"
            emoji = "🌟"
            message = "补剂方案执行良好，健康状况优秀！"
        elif score >= 6:
            rating = "良好"
            emoji = "👍"
            message = "补剂方案执行不错，继续保持！"
        elif score >= 4:
            rating = "一般"
            emoji = "💪"
            message = "补剂方案需要改进，建议按推荐调整"
        else:
            rating = "需改进"
            emoji = "📈"
            message = "建议重新规划补剂方案，并提高执行率"

        return {
            "score": score,
            "rating": rating,
            "emoji": emoji,
            "message": message
        }
