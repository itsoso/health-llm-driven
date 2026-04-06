"""健康分析服务（基于LLM）— 结构化多维分析 + 趋势预测"""
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from app.config import settings
from app.models.basic_health import BasicHealthData
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.disease import DiseaseRecord
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.health_analysis_cache import HealthAnalysisCache
from app.services.llm import get_llm_provider
import logging

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent / "knowledge_base"
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

logger = logging.getLogger(__name__)


class HealthAnalysisService:
    """健康分析服务"""

    def __init__(self):
        self._provider = None

    def _get_provider(self):
        """懒加载获取 LLM Provider"""
        if self._provider is None:
            try:
                self._provider = get_llm_provider()
            except Exception as e:
                logger.error(f"获取 LLM Provider 失败: {e}")
        return self._provider
    
    def collect_user_health_data(
        self,
        db: Session,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """收集用户健康数据用于分析"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # 获取基础健康数据
        basic_health = db.query(BasicHealthData).filter(
            BasicHealthData.user_id == user_id
        ).order_by(BasicHealthData.record_date.desc()).first()
        
        # 获取最近的体检数据
        recent_exams = db.query(MedicalExam).filter(
            MedicalExam.user_id == user_id
        ).order_by(MedicalExam.exam_date.desc()).limit(3).all()
        
        # 获取疾病记录
        active_diseases = db.query(DiseaseRecord).filter(
            DiseaseRecord.user_id == user_id,
            DiseaseRecord.status.in_(["active", "chronic"])
        ).all()
        
        # 获取Garmin数据（最近N天）
        garmin_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date
        ).order_by(GarminData.record_date.desc()).all()
        
        # 获取用户信息
        user = db.query(User).filter(User.id == user_id).first()
        
        return {
            "user": {
                "name": user.name if user else None,
                "birth_date": user.birth_date.isoformat() if user and user.birth_date else None,
                "gender": user.gender if user else None,
            },
            "basic_health": {
                "height": basic_health.height if basic_health else None,
                "weight": basic_health.weight if basic_health else None,
                "bmi": basic_health.bmi if basic_health else None,
                "systolic_bp": basic_health.systolic_bp if basic_health else None,
                "diastolic_bp": basic_health.diastolic_bp if basic_health else None,
                "total_cholesterol": basic_health.total_cholesterol if basic_health else None,
                "ldl_cholesterol": basic_health.ldl_cholesterol if basic_health else None,
                "hdl_cholesterol": basic_health.hdl_cholesterol if basic_health else None,
                "triglycerides": basic_health.triglycerides if basic_health else None,
                "blood_glucose": basic_health.blood_glucose if basic_health else None,
                "record_date": basic_health.record_date.isoformat() if basic_health and basic_health.record_date else None,
            },
            "medical_exams": [
                {
                    "exam_date": exam.exam_date.isoformat(),
                    "exam_type": exam.exam_type.value if hasattr(exam.exam_type, 'value') else exam.exam_type,
                    "body_system": exam.body_system.value if exam.body_system and hasattr(exam.body_system, 'value') else (exam.body_system if exam.body_system else None),
                    "overall_assessment": exam.overall_assessment,
                    "items": [
                        {
                            "item_name": item.item_name,
                            "value": item.value,
                            "unit": item.unit,
                            "reference_range": item.reference_range,
                            "result": item.result,
                            "is_abnormal": item.is_abnormal,
                        }
                        for item in exam.items
                    ]
                }
                for exam in recent_exams
            ],
            "diseases": [
                {
                    "disease_name": disease.disease_name,
                    "diagnosis_date": disease.diagnosis_date.isoformat(),
                    "severity": disease.severity,
                    "status": disease.status,
                    "treatment_plan": disease.treatment_plan,
                }
                for disease in active_diseases
            ],
            "garmin_data": [
                {
                    "record_date": data.record_date.isoformat(),
                    "avg_heart_rate": data.avg_heart_rate,
                    "resting_heart_rate": data.resting_heart_rate,
                    "hrv": data.hrv,
                    "sleep_score": data.sleep_score,
                    "total_sleep_duration": data.total_sleep_duration,
                    "deep_sleep_duration": data.deep_sleep_duration,
                    "rem_sleep_duration": data.rem_sleep_duration,
                    "body_battery_charged": data.body_battery_charged,
                    "stress_level": data.stress_level,
                    "steps": data.steps,
                }
                for data in garmin_data
            ],
        }
    
    def analyze_health_issues(
        self,
        db: Session,
        user_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        分析健康问题（带缓存）
        
        Args:
            user_id: 用户ID
            force_refresh: 是否强制刷新缓存
        
        返回：
        {
            "issues": [...],  # 识别的健康问题列表
            "recommendations": [...],  # 建议列表
            "summary": "..."  # 总结
            "cached": bool,  # 是否来自缓存
            "analysis_date": str  # 分析日期
        }
        """
        today = date.today()
        
        # 检查缓存（除非强制刷新）
        if not force_refresh:
            cached = db.query(HealthAnalysisCache).filter(
                HealthAnalysisCache.user_id == user_id,
                HealthAnalysisCache.analysis_date == today
            ).first()
            
            if cached and cached.analysis_result:
                logger.info(f"使用缓存的健康分析（用户 {user_id}，日期 {today}）")
                result = cached.analysis_result.copy()
                result["cached"] = True
                result["analysis_date"] = today.isoformat()
                return result
        
        # 生成新分析
        logger.info(f"生成新的健康分析（用户 {user_id}，日期 {today}）")

        provider = self._get_provider()
        if not provider:
            return {
                "error": "LLM Provider未配置",
                "issues": [],
                "recommendations": [],
                "summary": "请配置LLM Provider以使用健康分析功能",
                "cached": False,
                "analysis_date": today.isoformat()
            }

        # 收集数据
        health_data = self.collect_user_health_data(db, user_id)

        # 构建提示词
        prompt = self._build_analysis_prompt(health_data)

        try:
            analysis_text = asyncio.run(
                provider.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位专业的健康、营养专家，擅长分析个人健康数据，识别健康问题，并提供详细的健康指导建议。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                )
            )
            
            # 解析LLM返回的结果
            result = {
                "issues": self._extract_issues(analysis_text),
                "recommendations": self._extract_recommendations(analysis_text),
                "summary": analysis_text,
                "raw_analysis": analysis_text,
                "cached": False,
                "analysis_date": today.isoformat()
            }
            
            # 保存到缓存
            cached = db.query(HealthAnalysisCache).filter(
                HealthAnalysisCache.user_id == user_id,
                HealthAnalysisCache.analysis_date == today
            ).first()
            
            if cached:
                cached.analysis_result = result
                cached.updated_at = datetime.utcnow()
            else:
                cached = HealthAnalysisCache(
                    user_id=user_id,
                    analysis_date=today,
                    analysis_result=result
                )
                db.add(cached)
            
            db.commit()
            
            return result
        except Exception as e:
            logger.error(f"健康分析失败: {e}", exc_info=True)
            return {
                "error": str(e),
                "issues": [],
                "recommendations": [],
                "summary": f"分析过程中出现错误: {str(e)}",
                "cached": False,
                "analysis_date": today.isoformat()
            }
    
    def _build_analysis_prompt(self, health_data: Dict[str, Any]) -> str:
        """构建分析提示词"""
        prompt = f"""
请分析以下个人健康数据，识别存在的健康问题，并提供详细的健康指导建议。

## 个人基本信息
- 姓名: {health_data['user'].get('name', '未知')}
- 性别: {health_data['user'].get('gender', '未知')}
- 出生日期: {health_data['user'].get('birth_date', '未知')}

## 基础健康数据
{self._format_basic_health(health_data.get('basic_health', {}))}

## 体检数据
{self._format_medical_exams(health_data.get('medical_exams', []))}

## 疾病记录
{self._format_diseases(health_data.get('diseases', []))}

## Garmin可穿戴设备数据（最近30天）
{self._format_garmin_data(health_data.get('garmin_data', []))}

## 分析要求
请基于以上数据：
1. 明确指出当前存在的健康问题（按严重程度排序）
2. 分析每个问题的可能原因
3. 提供详细的、可执行的健康指导建议
4. 针对饮食、锻炼、睡眠、补剂等方面给出具体建议
5. 考虑个人的具体情况（年龄、性别、现有疾病等）

请用中文回答，结构清晰，建议具体可执行。
"""
        return prompt
    
    def _format_basic_health(self, data: Dict[str, Any]) -> str:
        """格式化基础健康数据"""
        if not data or not any(data.values()):
            return "暂无基础健康数据"
        
        lines = []
        if data.get('height'):
            lines.append(f"- 身高: {data['height']} cm")
        if data.get('weight'):
            lines.append(f"- 体重: {data['weight']} kg")
        if data.get('bmi'):
            lines.append(f"- BMI: {data['bmi']}")
        if data.get('systolic_bp') and data.get('diastolic_bp'):
            lines.append(f"- 血压: {data['systolic_bp']}/{data['diastolic_bp']} mmHg")
        if data.get('total_cholesterol'):
            lines.append(f"- 总胆固醇: {data['total_cholesterol']} mmol/L")
        if data.get('ldl_cholesterol'):
            lines.append(f"- LDL胆固醇: {data['ldl_cholesterol']} mmol/L")
        if data.get('hdl_cholesterol'):
            lines.append(f"- HDL胆固醇: {data['hdl_cholesterol']} mmol/L")
        if data.get('triglycerides'):
            lines.append(f"- 甘油三酯: {data['triglycerides']} mmol/L")
        if data.get('blood_glucose'):
            lines.append(f"- 血糖: {data['blood_glucose']} mmol/L")
        if data.get('record_date'):
            lines.append(f"- 记录日期: {data['record_date']}")
        
        return "\n".join(lines) if lines else "暂无基础健康数据"
    
    def _format_medical_exams(self, exams: List[Dict[str, Any]]) -> str:
        """格式化体检数据"""
        if not exams:
            return "暂无体检数据"
        
        lines = []
        for exam in exams:
            lines.append(f"\n### 体检日期: {exam.get('exam_date')}")
            lines.append(f"- 类型: {exam.get('exam_type')}")
            if exam.get('body_system'):
                lines.append(f"- 身体系统: {exam.get('body_system')}")
            if exam.get('overall_assessment'):
                lines.append(f"- 总体评价: {exam.get('overall_assessment')}")
            
            # 异常项目
            abnormal_items = [item for item in exam.get('items', []) if item.get('is_abnormal') != 'normal']
            if abnormal_items:
                lines.append("- 异常项目:")
                for item in abnormal_items:
                    lines.append(f"  * {item.get('item_name')}: {item.get('value')} {item.get('unit', '')} ({item.get('result', '')})")
        
        return "\n".join(lines)
    
    def _format_diseases(self, diseases: List[Dict[str, Any]]) -> str:
        """格式化疾病记录"""
        if not diseases:
            return "暂无疾病记录"
        
        lines = []
        for disease in diseases:
            lines.append(f"- {disease.get('disease_name')} (诊断日期: {disease.get('diagnosis_date')})")
            if disease.get('severity'):
                lines.append(f"  严重程度: {disease.get('severity')}")
            if disease.get('treatment_plan'):
                lines.append(f"  治疗方案: {disease.get('treatment_plan')}")
        
        return "\n".join(lines)
    
    def _format_garmin_data(self, garmin_data: List[Dict[str, Any]]) -> str:
        """格式化Garmin数据"""
        if not garmin_data:
            return "暂无Garmin数据"
        
        # 计算平均值
        avg_hr = sum(d.get('avg_heart_rate', 0) or 0 for d in garmin_data) / len(garmin_data) if garmin_data else 0
        avg_sleep_score = sum(d.get('sleep_score', 0) or 0 for d in garmin_data) / len(garmin_data) if garmin_data else 0
        avg_sleep_duration = sum(d.get('total_sleep_duration', 0) or 0 for d in garmin_data) / len(garmin_data) if garmin_data else 0
        avg_steps = sum(d.get('steps', 0) or 0 for d in garmin_data) / len(garmin_data) if garmin_data else 0
        
        lines = [
            f"- 平均心率: {avg_hr:.1f} bpm",
            f"- 平均睡眠分数: {avg_sleep_score:.1f}/100",
            f"- 平均睡眠时长: {avg_sleep_duration:.1f} 分钟",
            f"- 平均步数: {avg_steps:.0f} 步",
        ]
        
        return "\n".join(lines)
    
    def _extract_issues(self, analysis_text: str) -> List[str]:
        """从分析文本中提取健康问题（简化实现）"""
        # 这里可以要求LLM返回JSON格式，或者使用更复杂的文本解析
        # 简化实现：查找包含"问题"、"异常"等关键词的句子
        issues = []
        lines = analysis_text.split('\n')
        for line in lines:
            if any(keyword in line for keyword in ['问题', '异常', '偏高', '偏低', '不足', '缺乏']):
                issues.append(line.strip())
        return issues[:10]  # 最多返回10个问题
    
    def _extract_recommendations(self, analysis_text: str) -> List[str]:
        """从分析文本中提取建议（简化实现）"""
        recommendations = []
        lines = analysis_text.split('\n')
        for line in lines:
            if any(keyword in line for keyword in ['建议', '应该', '推荐', '可以', '需要']):
                recommendations.append(line.strip())
        return recommendations[:20]  # 最多返回20条建议
    
    def generate_personalized_advice(
        self,
        db: Session,
        user_id: int,
        checkin_date: date
    ) -> str:
        """为每日打卡生成个性化建议"""
        provider = self._get_provider()
        if not provider:
            return "个性化建议服务暂不可用"

        health_data = self.collect_user_health_data(db, user_id, days=7)
        
        # 检查是否有健康数据
        garmin_data = health_data.get('garmin_data', [])
        if not garmin_data:
            return f"该日期暂无健康数据记录，建议先同步Garmin数据或记录健康信息后再获取个性化建议。"
        
        # 检查是否有有效的健康数据（至少有一些非空字段）
        has_valid_data = any(
            data.get('sleep_score') or 
            data.get('steps') or 
            data.get('avg_heart_rate') or 
            data.get('resting_heart_rate')
            for data in garmin_data
        )
        
        if not has_valid_data:
            return f"该日期暂无有效的健康数据记录，建议先同步Garmin数据后再获取个性化建议。"
        
        prompt = f"""
基于以下个人健康数据，为{checkin_date}这一天的健康打卡提供个性化建议。

## 最近一周的健康数据
{self._format_garmin_data(garmin_data)}

请提供：
1. 今日锻炼建议（考虑最近的睡眠质量和身体电量）
2. 今日饮食建议
3. 今日作息建议
4. 其他个性化建议

请用中文回答，简洁明了，每条建议不超过50字。
"""
        
        try:
            result = asyncio.run(
                provider.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位专业的健康、营养专家，擅长提供每日个性化的健康建议。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.7,
                    max_tokens=500,
                )
            )
            return result
        except Exception as e:
            logger.error(f"生成个性化建议失败: {e}", exc_info=True)
            return f"生成建议时出现错误: {str(e)}"

    # ==================== 结构化多维分析（Phase 2 新增） ====================

    # 分析维度配置：每个维度对应的指标、知识库和参考文档
    ANALYSIS_DIMENSIONS = {
        "cardiovascular": {
            "label": "心血管",
            "metrics": ["resting_heart_rate", "hrv", "blood_pressure", "avg_heart_rate"],
            "knowledge_files": ["exercise_science/heart_rate_training.md", "feng_xue/cardiovascular.md"],
            "ref_file": "health-analysis/references/thresholds_and_evidence.md",
        },
        "metabolic": {
            "label": "代谢",
            "metrics": ["weight_trend", "bmi", "blood_glucose", "cholesterol", "triglycerides"],
            "knowledge_files": ["feng_xue/weight_management.md", "feng_xue/nutrition.md"],
            "ref_file": "health-analysis/references/thresholds_and_evidence.md",
        },
        "sleep_recovery": {
            "label": "睡眠恢复",
            "metrics": ["sleep_score", "deep_sleep_pct", "total_sleep_duration", "body_battery"],
            "knowledge_files": ["feng_xue/sleep.md", "exercise_science/recovery.md"],
            "ref_file": "health-analysis/references/thresholds_and_evidence.md",
        },
        "fitness": {
            "label": "运动体能",
            "metrics": ["steps", "calories_burned", "weekly_exercise_min", "vo2max"],
            "knowledge_files": ["exercise_science/running.md", "exercise_science/strength_training.md"],
            "ref_file": "health-analysis/references/thresholds_and_evidence.md",
        },
        "nutrition": {
            "label": "营养",
            "metrics": ["meal_regularity", "protein_intake", "calorie_balance"],
            "knowledge_files": ["feng_xue/nutrition.md"],
            "ref_file": "health-analysis/references/thresholds_and_evidence.md",
        },
    }

    # 跨维度协同效应规则
    SYNERGY_RULES = [
        {
            "id": "overtraining",
            "name": "过度训练风险",
            "condition": "sleep_recovery < 40 AND fitness > 70",
            "message": "睡眠恢复差但运动量大，存在过度训练风险，建议降低训练强度或增加休息",
            "penalty": -10,
        },
        {
            "id": "metabolic_syndrome",
            "name": "代谢综合征预警",
            "condition": "metabolic < 40 AND nutrition < 50",
            "message": "代谢指标和营养均不理想，需关注代谢综合征风险，建议改善饮食结构",
            "penalty": -8,
        },
        {
            "id": "stress_spiral",
            "name": "压力-睡眠恶性循环",
            "condition": "sleep_recovery < 50 AND cardiovascular contains high_stress",
            "message": "压力偏高且睡眠质量差，可能形成恶性循环，建议增加放松活动",
            "penalty": -5,
        },
        {
            "id": "positive_momentum",
            "name": "良性循环加分",
            "condition": "sleep_recovery >= 70 AND fitness >= 70 AND nutrition >= 60",
            "message": "睡眠、运动、营养三项良好，身体处于良性循环状态",
            "penalty": 5,
        },
    ]

    def analyze_health_structured(
        self,
        db: Session,
        user_id: int,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """结构化多维健康分析（新版本，分维度分析 + 知识库注入 + 趋势）"""
        today = date.today()

        # 缓存检查
        cache_key = f"structured_{today.isoformat()}"
        if not force_refresh:
            cached = db.query(HealthAnalysisCache).filter(
                HealthAnalysisCache.user_id == user_id,
                HealthAnalysisCache.analysis_date == today,
            ).first()
            if cached and cached.analysis_result and cached.analysis_result.get("structured"):
                result = cached.analysis_result.copy()
                result["cached"] = True
                return result

        provider = self._get_provider()
        if not provider:
            return {"error": "LLM Provider 未配置", "dimensions": {}, "cached": False}

        # 1. 收集数据（90天用于趋势，30天用于当前状态）
        health_data = self.collect_user_health_data(db, user_id, days=90)

        # 2. 计算趋势
        trends = self._compute_metric_trends(health_data)

        # 3. 分维度分析
        dimension_results = {}
        for dim_key, dim_config in self.ANALYSIS_DIMENSIONS.items():
            try:
                dim_result = self._analyze_dimension(
                    provider, dim_key, dim_config, health_data, trends
                )
                dimension_results[dim_key] = dim_result
            except Exception as e:
                logger.error(f"维度 {dim_key} 分析失败: {e}")
                dimension_results[dim_key] = {
                    "label": dim_config["label"],
                    "score": None,
                    "risk_level": "unknown",
                    "findings": [],
                    "recommendations": [],
                    "error": str(e),
                }

        # 4. 跨维度协同效应
        synergies = self._evaluate_synergies(dimension_results)

        # 5. 综合评分
        scored_dims = {k: v for k, v in dimension_results.items() if v.get("score") is not None}
        if scored_dims:
            avg_score = sum(v["score"] for v in scored_dims.values()) / len(scored_dims)
            synergy_adjustment = sum(s["penalty"] for s in synergies)
            total_score = max(0, min(100, round(avg_score + synergy_adjustment)))
        else:
            total_score = 0

        result = {
            "structured": True,
            "analysis_date": today.isoformat(),
            "cached": False,
            "total_score": total_score,
            "dimensions": dimension_results,
            "trends": trends,
            "synergies": synergies,
            "data_quality": self._assess_data_quality(health_data),
        }

        # 保存缓存
        try:
            cached = db.query(HealthAnalysisCache).filter(
                HealthAnalysisCache.user_id == user_id,
                HealthAnalysisCache.analysis_date == today,
            ).first()
            if cached:
                cached.analysis_result = result
                cached.updated_at = datetime.utcnow()
            else:
                cached = HealthAnalysisCache(
                    user_id=user_id, analysis_date=today, analysis_result=result
                )
                db.add(cached)
            db.commit()
        except Exception as e:
            logger.error(f"保存结构化分析缓存失败: {e}")

        return result

    def _analyze_dimension(
        self,
        provider,
        dim_key: str,
        dim_config: dict,
        health_data: dict,
        trends: dict,
    ) -> dict:
        """对单个维度进行 LLM 分析"""
        # 加载知识库上下文
        knowledge_context = self._load_knowledge_context(dim_config.get("knowledge_files", []))

        # 加载阈值参考
        ref_content = self._load_ref_content(dim_config.get("ref_file", ""))

        # 构建维度专用 prompt
        trend_text = self._format_trends_for_dimension(dim_key, trends)
        data_text = self._format_data_for_dimension(dim_key, health_data)

        prompt = f"""分析以下用户的{dim_config['label']}维度健康数据。

## 数据
{data_text}

## 趋势（过去90天）
{trend_text}

## 参考知识
{knowledge_context[:2000] if knowledge_context else '无额外参考'}

## 参考阈值
{ref_content[:1500] if ref_content else '使用通用标准'}

请以 JSON 格式返回分析结果，格式如下：
{{
  "score": 0-100的评分,
  "risk_level": "normal/caution/warning",
  "findings": ["发现1", "发现2"],
  "recommendations": ["建议1", "建议2"],
  "evidence_level": "A/B/C"
}}

只返回 JSON，不要其他内容。用中文填写 findings 和 recommendations。"""

        response = asyncio.run(
            provider.chat(
                messages=[
                    {"role": "system", "content": f"你是{dim_config['label']}领域的健康分析专家。基于循证医学给出评估。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
        )

        # 解析 JSON 响应
        try:
            # 提取 JSON（可能被 markdown 代码块包裹）
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            parsed = json.loads(json_str.strip())
            parsed["label"] = dim_config["label"]
            return parsed
        except (json.JSONDecodeError, IndexError):
            logger.warning(f"维度 {dim_key} LLM 返回非 JSON，使用文本解析")
            return {
                "label": dim_config["label"],
                "score": 60,
                "risk_level": "caution",
                "findings": self._extract_issues(response)[:3],
                "recommendations": self._extract_recommendations(response)[:3],
                "evidence_level": "C",
                "raw_response": response[:500],
            }

    def _compute_metric_trends(self, health_data: dict) -> dict:
        """计算关键指标的趋势（线性回归斜率）"""
        garmin_data = health_data.get("garmin_data", [])
        if len(garmin_data) < 7:
            return {"data_days": len(garmin_data), "insufficient_data": True}

        def _slope(values: list) -> Optional[float]:
            """简单线性回归斜率（不依赖 numpy）"""
            clean = [(i, v) for i, v in enumerate(values) if v is not None]
            if len(clean) < 3:
                return None
            n = len(clean)
            sum_x = sum(x for x, _ in clean)
            sum_y = sum(y for _, y in clean)
            sum_xy = sum(x * y for x, y in clean)
            sum_x2 = sum(x * x for x, _ in clean)
            denom = n * sum_x2 - sum_x * sum_x
            if denom == 0:
                return 0.0
            return (n * sum_xy - sum_x * sum_y) / denom

        def _direction(slope_val: Optional[float], threshold: float = 0.01) -> str:
            if slope_val is None:
                return "unknown"
            if slope_val > threshold:
                return "rising"
            elif slope_val < -threshold:
                return "falling"
            return "stable"

        # 按时间正序排列
        sorted_data = sorted(garmin_data, key=lambda d: d["record_date"])

        metrics = {
            "resting_heart_rate": [d.get("resting_heart_rate") for d in sorted_data],
            "hrv": [d.get("hrv") for d in sorted_data],
            "sleep_score": [d.get("sleep_score") for d in sorted_data],
            "deep_sleep_duration": [d.get("deep_sleep_duration") for d in sorted_data],
            "steps": [d.get("steps") for d in sorted_data],
            "stress_level": [d.get("stress_level") for d in sorted_data],
        }

        trends = {"data_days": len(sorted_data), "insufficient_data": False}
        for metric_name, values in metrics.items():
            slope = _slope(values)
            trends[metric_name] = {
                "slope": round(slope, 4) if slope is not None else None,
                "direction": _direction(slope),
                "latest": values[-1] if values else None,
                "avg_7d": self._safe_avg(values[-7:]),
                "avg_30d": self._safe_avg(values[-30:]),
            }

        return trends

    @staticmethod
    def _safe_avg(values: list) -> Optional[float]:
        clean = [v for v in values if v is not None]
        return round(sum(clean) / len(clean), 1) if clean else None

    def _evaluate_synergies(self, dimension_results: dict) -> list:
        """评估跨维度协同效应"""
        synergies = []
        scores = {k: v.get("score") for k, v in dimension_results.items() if v.get("score") is not None}

        for rule in self.SYNERGY_RULES:
            triggered = False
            if rule["id"] == "overtraining":
                triggered = scores.get("sleep_recovery", 100) < 40 and scores.get("fitness", 0) > 70
            elif rule["id"] == "metabolic_syndrome":
                triggered = scores.get("metabolic", 100) < 40 and scores.get("nutrition", 100) < 50
            elif rule["id"] == "stress_spiral":
                triggered = scores.get("sleep_recovery", 100) < 50 and scores.get("cardiovascular", 100) < 50
            elif rule["id"] == "positive_momentum":
                triggered = (
                    scores.get("sleep_recovery", 0) >= 70
                    and scores.get("fitness", 0) >= 70
                    and scores.get("nutrition", 0) >= 60
                )

            if triggered:
                synergies.append({
                    "id": rule["id"],
                    "name": rule["name"],
                    "message": rule["message"],
                    "penalty": rule["penalty"],
                })

        return synergies

    def _assess_data_quality(self, health_data: dict) -> dict:
        """评估数据质量"""
        garmin_data = health_data.get("garmin_data", [])
        total_days = len(garmin_data)

        # 计算各指标的完整率
        completeness = {}
        for field in ["resting_heart_rate", "hrv", "sleep_score", "steps", "stress_level"]:
            filled = sum(1 for d in garmin_data if d.get(field) is not None)
            completeness[field] = round(filled / total_days * 100, 1) if total_days > 0 else 0

        has_exams = len(health_data.get("medical_exams", [])) > 0
        has_diseases = len(health_data.get("diseases", [])) > 0

        if total_days >= 30 and all(v >= 80 for v in completeness.values()):
            grade = "A"
        elif total_days >= 14 and all(v >= 60 for v in completeness.values()):
            grade = "B"
        elif total_days >= 7:
            grade = "C"
        else:
            grade = "D"

        return {
            "grade": grade,
            "data_days": total_days,
            "completeness": completeness,
            "has_medical_exams": has_exams,
            "has_disease_records": has_diseases,
            "recommendation": self._data_quality_advice(grade, total_days),
        }

    @staticmethod
    def _data_quality_advice(grade: str, days: int) -> str:
        if grade == "A":
            return "数据质量优秀，分析结果可信度高"
        elif grade == "B":
            return "数据质量良好，建议持续记录以提高分析精准度"
        elif grade == "C":
            return f"仅有 {days} 天数据，趋势分析准确度有限，建议积累更多数据"
        return f"数据严重不足（{days} 天），建议先持续佩戴设备至少 7 天再做分析"

    def _load_knowledge_context(self, knowledge_files: list) -> str:
        """加载知识库文件内容"""
        parts = []
        for f in knowledge_files:
            path = KNOWLEDGE_BASE_DIR / f
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                    # 截取要点，避免 prompt 过长
                    parts.append(content[:1500])
                except Exception as e:
                    logger.warning(f"加载知识库 {f} 失败: {e}")
        return "\n---\n".join(parts)

    def _load_ref_content(self, ref_file: str) -> str:
        """加载 skill reference 文件"""
        if not ref_file:
            return ""
        path = SKILLS_DIR / ref_file
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")[:2000]
            except Exception:
                return ""
        return ""

    def _format_trends_for_dimension(self, dim_key: str, trends: dict) -> str:
        """格式化趋势数据为文本"""
        if trends.get("insufficient_data"):
            return "数据不足，无法计算趋势"

        metric_map = {
            "cardiovascular": ["resting_heart_rate", "hrv"],
            "metabolic": [],
            "sleep_recovery": ["sleep_score", "deep_sleep_duration"],
            "fitness": ["steps"],
            "nutrition": [],
        }

        relevant = metric_map.get(dim_key, [])
        lines = []
        direction_labels = {"rising": "上升↑", "falling": "下降↓", "stable": "稳定→", "unknown": "数据不足"}
        for m in relevant:
            t = trends.get(m, {})
            if t:
                d = direction_labels.get(t.get("direction", "unknown"), "")
                lines.append(f"- {m}: 趋势{d}，近7天均值={t.get('avg_7d')}，近30天均值={t.get('avg_30d')}")
        return "\n".join(lines) if lines else "该维度无趋势数据"

    def _format_data_for_dimension(self, dim_key: str, health_data: dict) -> str:
        """为特定维度格式化数据"""
        if dim_key == "cardiovascular":
            basic = health_data.get("basic_health", {})
            garmin = health_data.get("garmin_data", [])
            lines = [self._format_basic_health(basic)]
            if garmin:
                recent = garmin[:7]
                avg_rhr = self._safe_avg([d.get("resting_heart_rate") for d in recent])
                avg_hrv = self._safe_avg([d.get("hrv") for d in recent])
                avg_stress = self._safe_avg([d.get("stress_level") for d in recent])
                lines.append(f"近7天: 静息心率均值={avg_rhr}, HRV均值={avg_hrv}, 压力均值={avg_stress}")
            return "\n".join(lines)

        elif dim_key == "metabolic":
            return self._format_basic_health(health_data.get("basic_health", {}))

        elif dim_key == "sleep_recovery":
            garmin = health_data.get("garmin_data", [])[:14]
            if not garmin:
                return "无睡眠数据"
            lines = []
            avg_score = self._safe_avg([d.get("sleep_score") for d in garmin])
            avg_dur = self._safe_avg([d.get("total_sleep_duration") for d in garmin])
            avg_deep = self._safe_avg([d.get("deep_sleep_duration") for d in garmin])
            avg_bb = self._safe_avg([d.get("body_battery_charged") for d in garmin])
            lines.append(f"近14天: 睡眠评分={avg_score}, 总时长={avg_dur}分钟, 深睡={avg_deep}分钟, Body Battery充电={avg_bb}")
            return "\n".join(lines)

        elif dim_key == "fitness":
            garmin = health_data.get("garmin_data", [])[:30]
            if not garmin:
                return "无运动数据"
            avg_steps = self._safe_avg([d.get("steps") for d in garmin])
            return f"近30天: 日均步数={avg_steps}"

        elif dim_key == "nutrition":
            return "需结合饮食记录（由 nutrition-advisor skill 处理详细分析）"

        return "无数据"

