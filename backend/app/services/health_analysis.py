"""健康分析服务（基于LLM）"""
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from openai import OpenAI
from app.config import settings
from app.models.basic_health import BasicHealthData
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.disease import DiseaseRecord
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.health_analysis_cache import HealthAnalysisCache
import logging

logger = logging.getLogger(__name__)


class HealthAnalysisService:
    """健康分析服务"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
    
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
                    "exam_type": exam.exam_type.value,
                    "body_system": exam.body_system.value if exam.body_system else None,
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
        
        if not self.client:
            return {
                "error": "OpenAI API未配置",
                "issues": [],
                "recommendations": [],
                "summary": "请配置OPENAI_API_KEY以使用健康分析功能",
                "cached": False,
                "analysis_date": today.isoformat()
            }
        
        # 收集数据
        health_data = self.collect_user_health_data(db, user_id)
        
        # 构建提示词
        prompt = self._build_analysis_prompt(health_data)
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
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
            )
            
            analysis_text = response.choices[0].message.content
            
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
        if not self.client:
            return "请配置OpenAI API以获取个性化建议"
        
        health_data = self.collect_user_health_data(db, user_id, days=7)
        
        prompt = f"""
基于以下个人健康数据，为{checkin_date}这一天的健康打卡提供个性化建议。

## 最近一周的健康数据
{self._format_garmin_data(health_data.get('garmin_data', []))}

请提供：
1. 今日锻炼建议（考虑最近的睡眠质量和身体电量）
2. 今日饮食建议
3. 今日作息建议
4. 其他个性化建议

请用中文回答，简洁明了，每条建议不超过50字。
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
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
            
            return response.choices[0].message.content
        except Exception as e:
            return f"生成建议时出现错误: {str(e)}"

