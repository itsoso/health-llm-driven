"""
疾病追踪服务

提供疾病管理、症状追踪、趋势分析等功能
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from app.models.disease_tracking import (
    DiseaseTemplate, UserDiseaseProfile, SymptomLog,
    VisionRecord, DailyEyeHabit
)
from app.services.environment import environment_advisor

logger = logging.getLogger(__name__)


# 预定义的疾病模板
DEFAULT_DISEASE_TEMPLATES = [
    {
        "name": "allergic_rhinitis",
        "display_name": "过敏性鼻炎",
        "category": "respiratory",
        "icon": "👃",
        "symptoms": ["鼻塞", "流涕", "打喷嚏", "鼻痒", "嗅觉减退", "眼痒", "流泪"],
        "triggers": ["花粉", "尘螨", "冷空气", "油烟", "香水", "宠物毛发", "霉菌"],
        "environment_sensitive": True,
        "sensitive_factors": ["air_quality", "humidity", "pollen"],
        "daily_tips": [
            "每日使用生理盐水洗鼻1-2次",
            "保持室内湿度在40-60%",
            "勤换床单被套，定期清洗",
            "空气质量差时佩戴口罩",
            "避免接触已知过敏原"
        ],
        "medication_types": ["抗组胺药", "鼻用糖皮质激素", "减充血剂"],
        "prevention_tips": [
            "了解并记录个人过敏原",
            "关注空气质量预报",
            "花粉季节减少外出"
        ],
        "tracking_frequency": "daily"
    },
    {
        "name": "chronic_pharyngitis",
        "display_name": "慢性咽炎",
        "category": "respiratory",
        "icon": "🗣️",
        "symptoms": ["咽干", "咽痒", "异物感", "咳嗽", "声音嘶哑", "咽痛"],
        "triggers": ["干燥空气", "辛辣食物", "烟酒", "熬夜", "说话过多", "粉尘"],
        "environment_sensitive": True,
        "sensitive_factors": ["air_quality", "humidity"],
        "daily_tips": [
            "多喝温水，保持咽喉湿润",
            "避免辛辣刺激食物",
            "戒烟限酒",
            "保持室内空气湿润",
            "减少大声说话"
        ],
        "medication_types": ["咽喉含片", "中成药", "雾化治疗"],
        "prevention_tips": [
            "保持良好作息",
            "增强体质",
            "避免反复感冒"
        ],
        "tracking_frequency": "daily"
    },
    {
        "name": "myopia",
        "display_name": "近视",
        "category": "vision",
        "icon": "👁️",
        "symptoms": ["视物模糊", "眼疲劳", "眯眼看东西", "头痛"],
        "triggers": ["长时间近距离用眼", "户外活动不足", "光线不足", "电子屏幕"],
        "environment_sensitive": False,
        "sensitive_factors": [],
        "daily_tips": [
            "每天户外活动2小时以上",
            "遵守20-20-20法则",
            "保持正确读写姿势",
            "保证充足睡眠",
            "控制电子屏幕使用时间"
        ],
        "medication_types": ["低浓度阿托品"],
        "prevention_tips": [
            "定期检查视力",
            "及时配镜矫正",
            "考虑OK镜等干预措施"
        ],
        "tracking_frequency": "daily"
    },
    {
        "name": "hypertension",
        "display_name": "高血压",
        "category": "cardiovascular",
        "icon": "❤️",
        "symptoms": ["头痛", "头晕", "心悸", "胸闷"],
        "triggers": ["高盐饮食", "压力", "熬夜", "缺乏运动", "肥胖"],
        "environment_sensitive": True,
        "sensitive_factors": ["temperature"],
        "daily_tips": [
            "每日监测血压",
            "低盐饮食",
            "规律作息",
            "适量运动",
            "按时服药"
        ],
        "medication_types": ["降压药"],
        "prevention_tips": [
            "控制体重",
            "戒烟限酒",
            "保持心情舒畅"
        ],
        "tracking_frequency": "daily"
    },
    {
        "name": "diabetes",
        "display_name": "糖尿病",
        "category": "metabolic",
        "icon": "🩸",
        "symptoms": ["多饮", "多尿", "多食", "体重下降", "疲劳"],
        "triggers": ["高糖饮食", "缺乏运动", "压力"],
        "environment_sensitive": False,
        "sensitive_factors": [],
        "daily_tips": [
            "定时监测血糖",
            "控制饮食碳水摄入",
            "规律运动",
            "按时服药/注射胰岛素",
            "注意足部护理"
        ],
        "medication_types": ["口服降糖药", "胰岛素"],
        "prevention_tips": [
            "保持健康体重",
            "均衡饮食",
            "定期检查"
        ],
        "tracking_frequency": "daily"
    }
]


class DiseaseTrackingService:
    """疾病追踪服务"""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    # ========== 疾病模板管理 ==========

    def init_default_templates(self) -> int:
        """初始化默认疾病模板"""
        created = 0
        for template_data in DEFAULT_DISEASE_TEMPLATES:
            existing = self.db.query(DiseaseTemplate).filter(
                DiseaseTemplate.name == template_data["name"]
            ).first()
            if not existing:
                template = DiseaseTemplate(**template_data)
                self.db.add(template)
                created += 1
        self.db.commit()
        return created

    def get_templates(self, category: str = None) -> List[DiseaseTemplate]:
        """获取疾病模板列表"""
        query = self.db.query(DiseaseTemplate)
        if category:
            query = query.filter(DiseaseTemplate.category == category)
        return query.all()

    # ========== 用户疾病档案 ==========

    def create_disease_profile(
        self,
        disease_name: str,
        template_name: str = None,
        diagnosis_date: date = None,
        severity: str = "moderate",
        personal_triggers: List[str] = None,
        current_medications: List[Dict] = None
    ) -> UserDiseaseProfile:
        """创建用户疾病档案"""
        template = None
        if template_name:
            template = self.db.query(DiseaseTemplate).filter(
                DiseaseTemplate.name == template_name
            ).first()

        profile = UserDiseaseProfile(
            user_id=self.user_id,
            template_id=template.id if template else None,
            disease_name=disease_name,
            diagnosis_date=diagnosis_date,
            severity=severity,
            personal_triggers=personal_triggers or [],
            current_medications=current_medications or [],
            personal_symptoms=template.symptoms if template else []
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def get_user_disease_profiles(self) -> List[UserDiseaseProfile]:
        """获取用户所有疾病档案"""
        return self.db.query(UserDiseaseProfile).filter(
            UserDiseaseProfile.user_id == self.user_id
        ).all()

    def get_disease_profile(self, profile_id: int) -> Optional[UserDiseaseProfile]:
        """获取指定疾病档案"""
        return self.db.query(UserDiseaseProfile).filter(
            UserDiseaseProfile.id == profile_id,
            UserDiseaseProfile.user_id == self.user_id
        ).first()

    # ========== 症状记录 ==========

    def log_symptoms(
        self,
        profile_id: int,
        log_date: date,
        overall_severity: int,
        symptoms: List[Dict] = None,
        triggers: List[str] = None,
        medications_taken: List[Dict] = None,
        treatments: List[str] = None,
        notes: str = None
    ) -> SymptomLog:
        """
        记录症状

        Args:
            profile_id: 疾病档案ID
            log_date: 记录日期
            overall_severity: 总体严重程度 (0-10)
            symptoms: 具体症状列表
            triggers: 触发因素
            medications_taken: 用药记录
            treatments: 采取的治疗措施
            notes: 备注
        """
        # 检查是否已有当日记录
        existing = self.db.query(SymptomLog).filter(
            SymptomLog.user_id == self.user_id,
            SymptomLog.disease_profile_id == profile_id,
            SymptomLog.log_date == log_date
        ).first()

        if existing:
            # 更新现有记录
            existing.overall_severity = overall_severity
            existing.symptoms = symptoms or []
            existing.triggers = triggers or []
            existing.medications_taken = medications_taken or []
            existing.treatments = treatments or []
            existing.notes = notes
            self.db.commit()
            self.db.refresh(existing)

            # 更新连续无症状天数
            self._update_streak(profile_id)
            return existing

        # 创建新记录
        log = SymptomLog(
            user_id=self.user_id,
            disease_profile_id=profile_id,
            log_date=log_date,
            overall_severity=overall_severity,
            symptoms=symptoms or [],
            triggers=triggers or [],
            medications_taken=medications_taken or [],
            treatments=treatments or []
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

        # 更新连续无症状天数
        self._update_streak(profile_id)

        return log

    def _update_streak(self, profile_id: int):
        """更新连续无症状天数"""
        profile = self.get_disease_profile(profile_id)
        if not profile:
            return

        # 计算连续无症状天数
        streak = 0
        check_date = date.today()

        while True:
            log = self.db.query(SymptomLog).filter(
                SymptomLog.user_id == self.user_id,
                SymptomLog.disease_profile_id == profile_id,
                SymptomLog.log_date == check_date
            ).first()

            if log and log.overall_severity == 0:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break

        profile.current_streak = streak
        if streak > profile.best_streak:
            profile.best_streak = streak

        self.db.commit()

    def get_symptom_logs(
        self,
        profile_id: int,
        start_date: date = None,
        end_date: date = None,
        limit: int = 30
    ) -> List[SymptomLog]:
        """获取症状记录"""
        query = self.db.query(SymptomLog).filter(
            SymptomLog.user_id == self.user_id,
            SymptomLog.disease_profile_id == profile_id
        )

        if start_date:
            query = query.filter(SymptomLog.log_date >= start_date)
        if end_date:
            query = query.filter(SymptomLog.log_date <= end_date)

        return query.order_by(SymptomLog.log_date.desc()).limit(limit).all()

    # ========== 统计分析 ==========

    def get_symptom_stats(
        self,
        profile_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取症状统计

        Returns:
            统计数据包括：平均严重程度、症状频率、触发因素分析等
        """
        start_date = date.today() - timedelta(days=days)
        logs = self.get_symptom_logs(profile_id, start_date=start_date)

        if not logs:
            return {
                "period_days": days,
                "total_logs": 0,
                "message": "暂无记录"
            }

        # 计算平均严重程度
        avg_severity = sum(log.overall_severity for log in logs) / len(logs)

        # 统计症状频率
        symptom_counts = {}
        for log in logs:
            for symptom in log.symptoms:
                name = symptom.get("name", "")
                if name:
                    symptom_counts[name] = symptom_counts.get(name, 0) + 1

        # 统计触发因素
        trigger_counts = {}
        for log in logs:
            for trigger in log.triggers:
                trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1

        # 按严重程度分组
        severity_distribution = {"无症状": 0, "轻度": 0, "中度": 0, "重度": 0}
        for log in logs:
            if log.overall_severity == 0:
                severity_distribution["无症状"] += 1
            elif log.overall_severity <= 3:
                severity_distribution["轻度"] += 1
            elif log.overall_severity <= 6:
                severity_distribution["中度"] += 1
            else:
                severity_distribution["重度"] += 1

        # 每日趋势
        daily_trend = []
        for log in sorted(logs, key=lambda x: x.log_date):
            daily_trend.append({
                "date": log.log_date.isoformat(),
                "severity": log.overall_severity
            })

        return {
            "period_days": days,
            "total_logs": len(logs),
            "avg_severity": round(avg_severity, 1),
            "symptom_free_days": severity_distribution["无症状"],
            "symptom_free_rate": round(severity_distribution["无症状"] / len(logs) * 100, 1),
            "top_symptoms": sorted(symptom_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "top_triggers": sorted(trigger_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "severity_distribution": severity_distribution,
            "daily_trend": daily_trend
        }

    # ========== 环境预警 ==========

    async def get_environment_alert(
        self,
        profile_id: int,
        city: str = None
    ) -> Dict[str, Any]:
        """
        获取环境相关的疾病预警

        基于用户疾病档案和当前环境数据，生成预警建议
        """
        profile = self.get_disease_profile(profile_id)
        if not profile:
            return {"error": "疾病档案不存在"}

        template = profile.template
        if not template or not template.environment_sensitive:
            return {
                "alert_level": "none",
                "message": "此疾病不受环境因素影响"
            }

        # 获取环境数据
        conditions = [profile.disease_name]
        advice = await environment_advisor.get_comprehensive_advice(
            city=city,
            user_conditions=conditions
        )

        # 分析预警
        alert_level = "low"
        warnings = []
        recommendations = []

        # 检查空气质量
        aqi = advice["air_quality"].get("aqi", 50)
        if "air_quality" in template.sensitive_factors:
            if aqi > 150:
                alert_level = "high"
                warnings.append(f"空气质量差（AQI {aqi}），可能加重症状")
                recommendations.append("尽量待在室内，使用空气净化器")
            elif aqi > 100:
                alert_level = max(alert_level, "moderate")
                warnings.append(f"空气质量一般（AQI {aqi}）")
                recommendations.append("外出时佩戴口罩")

        # 检查湿度
        humidity = advice["weather"].get("humidity", 50)
        if "humidity" in template.sensitive_factors:
            if humidity < 40:
                alert_level = max(alert_level, "moderate")
                warnings.append(f"空气干燥（湿度{humidity}%）")
                recommendations.append("使用加湿器，多喝水")
            elif humidity > 80:
                alert_level = max(alert_level, "moderate")
                warnings.append(f"空气潮湿（湿度{humidity}%）")
                recommendations.append("注意防霉，保持通风")

        # 检查温度
        temp = advice["weather"].get("temperature", 20)
        if "temperature" in template.sensitive_factors:
            if temp < 10:
                alert_level = max(alert_level, "moderate")
                warnings.append(f"天气寒冷（{temp}°C）")
                recommendations.append("注意保暖，避免受凉")

        # 添加模板的日常建议
        if template.daily_tips:
            recommendations.extend(template.daily_tips[:3])

        return {
            "disease_name": profile.disease_name,
            "alert_level": alert_level,
            "warnings": warnings,
            "recommendations": list(set(recommendations))[:6],
            "environment": {
                "weather": advice["weather"].get("weather", ""),
                "temperature": temp,
                "humidity": humidity,
                "aqi": aqi,
                "aqi_description": advice["air_quality"].get("description", "")
            }
        }

    # ========== 视力追踪 ==========

    def add_vision_record(
        self,
        record_date: date,
        left_eye_naked: float = None,
        right_eye_naked: float = None,
        left_eye_sphere: float = None,
        right_eye_sphere: float = None,
        left_eye_cylinder: float = None,
        right_eye_cylinder: float = None,
        left_eye_axial: float = None,
        right_eye_axial: float = None,
        exam_type: str = "routine",
        exam_location: str = None,
        interventions: List[str] = None,
        notes: str = None
    ) -> VisionRecord:
        """添加视力记录"""
        record = VisionRecord(
            user_id=self.user_id,
            record_date=record_date,
            left_eye_naked=left_eye_naked,
            right_eye_naked=right_eye_naked,
            left_eye_sphere=left_eye_sphere,
            right_eye_sphere=right_eye_sphere,
            left_eye_cylinder=left_eye_cylinder,
            right_eye_cylinder=right_eye_cylinder,
            left_eye_axial=left_eye_axial,
            right_eye_axial=right_eye_axial,
            exam_type=exam_type,
            exam_location=exam_location,
            interventions=interventions or [],
            notes=notes
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_vision_records(self, limit: int = 10) -> List[VisionRecord]:
        """获取视力记录"""
        return self.db.query(VisionRecord).filter(
            VisionRecord.user_id == self.user_id
        ).order_by(VisionRecord.record_date.desc()).limit(limit).all()

    def get_vision_trend(self) -> Dict[str, Any]:
        """获取视力变化趋势"""
        records = self.get_vision_records(limit=12)
        if not records:
            return {"message": "暂无视力记录"}

        # 计算度数变化
        latest = records[0]
        oldest = records[-1]

        left_change = None
        right_change = None

        if latest.left_eye_sphere and oldest.left_eye_sphere:
            left_change = round(latest.left_eye_sphere - oldest.left_eye_sphere, 2)
        if latest.right_eye_sphere and oldest.right_eye_sphere:
            right_change = round(latest.right_eye_sphere - oldest.right_eye_sphere, 2)

        # 生成趋势数据
        trend_data = []
        for record in sorted(records, key=lambda x: x.record_date):
            trend_data.append({
                "date": record.record_date.isoformat(),
                "left_sphere": record.left_eye_sphere,
                "right_sphere": record.right_eye_sphere,
                "left_axial": record.left_eye_axial,
                "right_axial": record.right_eye_axial
            })

        return {
            "latest_record": {
                "date": latest.record_date.isoformat(),
                "left_sphere": latest.left_eye_sphere,
                "right_sphere": latest.right_eye_sphere
            },
            "period_months": (latest.record_date - oldest.record_date).days // 30,
            "left_eye_change": left_change,
            "right_eye_change": right_change,
            "trend": "控制良好" if (left_change and left_change >= -0.25) else "需要关注",
            "trend_data": trend_data
        }

    def log_daily_eye_habit(
        self,
        record_date: date,
        outdoor_minutes: int = 0,
        screen_minutes: int = 0,
        reading_minutes: int = 0,
        eye_rest_count: int = 0,
        interventions_done: List[str] = None,
        eye_fatigue: int = 0,
        notes: str = None
    ) -> DailyEyeHabit:
        """记录每日用眼习惯"""
        # 检查是否已有当日记录
        existing = self.db.query(DailyEyeHabit).filter(
            DailyEyeHabit.user_id == self.user_id,
            DailyEyeHabit.record_date == record_date
        ).first()

        if existing:
            existing.outdoor_minutes = outdoor_minutes
            existing.screen_minutes = screen_minutes
            existing.reading_minutes = reading_minutes
            existing.eye_rest_count = eye_rest_count
            existing.interventions_done = interventions_done or []
            existing.eye_fatigue = eye_fatigue
            existing.notes = notes
            self.db.commit()
            self.db.refresh(existing)
            return existing

        habit = DailyEyeHabit(
            user_id=self.user_id,
            record_date=record_date,
            outdoor_minutes=outdoor_minutes,
            screen_minutes=screen_minutes,
            reading_minutes=reading_minutes,
            eye_rest_count=eye_rest_count,
            interventions_done=interventions_done or [],
            eye_fatigue=eye_fatigue,
            notes=notes
        )
        self.db.add(habit)
        self.db.commit()
        self.db.refresh(habit)
        return habit

    def get_eye_habit_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取用眼习惯统计"""
        start_date = date.today() - timedelta(days=days)
        habits = self.db.query(DailyEyeHabit).filter(
            DailyEyeHabit.user_id == self.user_id,
            DailyEyeHabit.record_date >= start_date
        ).all()

        if not habits:
            return {"message": "暂无用眼习惯记录"}

        avg_outdoor = sum(h.outdoor_minutes for h in habits) / len(habits)
        avg_screen = sum(h.screen_minutes for h in habits) / len(habits)
        target_outdoor_days = sum(1 for h in habits if h.outdoor_minutes >= 120)

        return {
            "period_days": days,
            "total_records": len(habits),
            "avg_outdoor_minutes": round(avg_outdoor, 0),
            "avg_screen_minutes": round(avg_screen, 0),
            "target_outdoor_days": target_outdoor_days,
            "outdoor_achievement_rate": round(target_outdoor_days / len(habits) * 100, 1),
            "recommendation": "继续保持户外活动！" if avg_outdoor >= 120 else "建议增加户外活动时间到每天2小时"
        }
