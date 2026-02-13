"""身体成分分析服务"""
import logging
from typing import Optional, Dict, Any, List
from datetime import date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.weight import WeightRecord

logger = logging.getLogger(__name__)


class BodyCompositionService:
    """身体成分分析服务"""

    def get_composition_trend(
        self,
        db: Session,
        user_id: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """获取身体成分趋势数据"""
        logger.info(f"[BodyComp] 获取趋势: user={user_id}, days={days}")

        start_date = date.today() - timedelta(days=days - 1)
        records = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= start_date,
        ).order_by(WeightRecord.record_date).all()

        if not records:
            return {"data_points": [], "summary": {}}

        data_points = []
        for r in records:
            point = {
                "date": str(r.record_date),
                "weight": r.weight,
                "body_fat_percentage": r.body_fat_percentage,
                "muscle_mass_kg": r.muscle_mass_kg,
                "visceral_fat": r.visceral_fat,
                "bone_mass_kg": r.bone_mass_kg,
                "water_percentage": r.water_percentage,
                "bmi": r.bmi,
                "bmr": r.bmr,
                "skeletal_muscle_pct": r.skeletal_muscle_pct,
            }
            data_points.append(point)

        # 计算摘要
        latest = records[-1]
        earliest = records[0]

        summary = {
            "current_weight": latest.weight,
            "weight_change": round(latest.weight - earliest.weight, 2) if len(records) >= 2 else None,
            "current_body_fat": latest.body_fat_percentage,
            "current_muscle_mass": latest.muscle_mass_kg,
            "current_bmi": latest.bmi or self._calculate_bmi(latest.weight, db, user_id),
            "record_count": len(records),
            "date_range": f"{records[0].record_date} ~ {records[-1].record_date}",
        }

        # 身体成分变化
        if len(records) >= 2 and earliest.body_fat_percentage and latest.body_fat_percentage:
            summary["body_fat_change"] = round(latest.body_fat_percentage - earliest.body_fat_percentage, 2)
        if len(records) >= 2 and earliest.muscle_mass_kg and latest.muscle_mass_kg:
            summary["muscle_mass_change"] = round(latest.muscle_mass_kg - earliest.muscle_mass_kg, 2)

        logger.info(f"[BodyComp] 趋势数据: {len(data_points)} 个数据点")
        return {"data_points": data_points, "summary": summary}

    def get_body_analysis(
        self,
        db: Session,
        user_id: int,
    ) -> Dict[str, Any]:
        """获取身体成分分析（基于最新数据）"""
        logger.info(f"[BodyComp] 获取身体分析: user={user_id}")

        latest = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
        ).order_by(desc(WeightRecord.record_date)).first()

        if not latest:
            return {"status": "no_data", "analysis": []}

        analysis = []

        # BMI 分析
        bmi = latest.bmi or self._calculate_bmi(latest.weight, db, user_id)
        if bmi:
            if bmi < 18.5:
                analysis.append({"metric": "BMI", "value": round(bmi, 1), "status": "偏低", "advice": "体重偏轻，建议增加优质蛋白和碳水摄入"})
            elif bmi < 24:
                analysis.append({"metric": "BMI", "value": round(bmi, 1), "status": "正常", "advice": "BMI 在正常范围，继续保持"})
            elif bmi < 28:
                analysis.append({"metric": "BMI", "value": round(bmi, 1), "status": "偏高", "advice": "建议控制饮食热量摄入，增加有氧运动"})
            else:
                analysis.append({"metric": "BMI", "value": round(bmi, 1), "status": "肥胖", "advice": "建议咨询医生制定减重计划"})

        # 体脂率分析
        bf = latest.body_fat_percentage
        if bf:
            if bf < 15:
                analysis.append({"metric": "体脂率", "value": f"{bf}%", "status": "偏低", "advice": "体脂率较低，注意不要过度减脂"})
            elif bf < 25:
                analysis.append({"metric": "体脂率", "value": f"{bf}%", "status": "正常", "advice": "体脂率在健康范围内"})
            elif bf < 30:
                analysis.append({"metric": "体脂率", "value": f"{bf}%", "status": "偏高", "advice": "建议增加有氧运动和力量训练"})
            else:
                analysis.append({"metric": "体脂率", "value": f"{bf}%", "status": "过高", "advice": "体脂率过高，建议系统性减脂"})

        # 内脏脂肪分析
        vf = latest.visceral_fat
        if vf:
            if vf <= 9:
                analysis.append({"metric": "内脏脂肪", "value": vf, "status": "正常", "advice": "内脏脂肪在安全范围"})
            elif vf <= 14:
                analysis.append({"metric": "内脏脂肪", "value": vf, "status": "偏高", "advice": "内脏脂肪偏高，注意减少高脂高糖食物"})
            else:
                analysis.append({"metric": "内脏脂肪", "value": vf, "status": "过高", "advice": "内脏脂肪过高，有健康风险，建议就医检查"})

        # 水分率分析
        wp = latest.water_percentage
        if wp:
            if wp < 50:
                analysis.append({"metric": "水分率", "value": f"{wp}%", "status": "偏低", "advice": "身体水分偏低，建议增加饮水量"})
            elif wp < 65:
                analysis.append({"metric": "水分率", "value": f"{wp}%", "status": "正常", "advice": "身体水分充足"})
            else:
                analysis.append({"metric": "水分率", "value": f"{wp}%", "status": "充足", "advice": "水分状态良好"})

        return {
            "status": "ok",
            "record_date": str(latest.record_date),
            "analysis": analysis,
        }

    @staticmethod
    def _calculate_bmi(weight: float, db: Session, user_id: int) -> Optional[float]:
        """计算 BMI（需要身高数据）"""
        from app.models.basic_health import BasicHealthData
        basic = db.query(BasicHealthData).filter(
            BasicHealthData.user_id == user_id,
        ).order_by(desc(BasicHealthData.record_date)).first()

        if basic and basic.height:
            height_m = basic.height / 100
            return round(weight / (height_m ** 2), 1)
        return None


body_composition_service = BodyCompositionService()
