"""语音指令快速执行服务"""
import re
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models.daily_health import WaterIntake
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.utils.timezone import get_china_today, get_china_now

logger = logging.getLogger(__name__)

# 饮水量映射
WATER_AMOUNT_MAP = {
    "一杯": 250,
    "两杯": 500,
    "三杯": 750,
    "半杯": 125,
    "一瓶": 500,
    "半瓶": 250,
}

# 中文数字映射
CN_NUM_MAP = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_cn_number(text: str) -> Optional[float]:
    """解析中文数字，如 '七十二' -> 72, '七二点五' -> 72.5"""
    # 先尝试直接解析阿拉伯数字
    try:
        return float(text)
    except (ValueError, TypeError):
        pass

    if not text:
        return None

    # 简单中文数字解析
    result = 0
    for ch in text:
        if ch in CN_NUM_MAP:
            val = CN_NUM_MAP[ch]
            if ch == "十":
                if result == 0:
                    result = 10
                else:
                    result *= 10
            else:
                result = result * 10 + val if result >= 10 else result + val
    return float(result) if result > 0 else None


class VoiceCommandService:
    """语音指令快速执行服务"""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def try_execute(self, text: str) -> Optional[Dict[str, Any]]:
        """
        尝试匹配并执行语音指令。
        返回 {"command_type": str, "message": str, "data": dict} 或 None
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # 按优先级依次尝试匹配
        matchers = [
            self._match_water,
            self._match_weight,
            self._match_blood_pressure,
            self._match_checkin,
        ]

        for matcher in matchers:
            try:
                result = matcher(text)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"语音指令匹配异常 [{matcher.__name__}]: {e}")

        return None

    def _match_water(self, text: str) -> Optional[Dict[str, Any]]:
        """匹配饮水指令"""
        # 模式1: "喝了一杯水"、"喝水一杯"、"喝了两杯水"
        for cn_amount, ml in WATER_AMOUNT_MAP.items():
            if cn_amount in text and ("喝" in text or "水" in text):
                return self._record_water(ml)

        # 模式2: "喝水250"、"喝了250ml水"、"喝水250毫升"
        m = re.search(r"喝[了]?\s*(?:水\s*)?(\d+)\s*(?:ml|毫升|m)?", text)
        if m:
            return self._record_water(int(m.group(1)))

        # 模式3: "喝水" (无数量，默认250ml)
        if re.match(r"^喝[了]?水$", text):
            return self._record_water(250)

        return None

    def _match_weight(self, text: str) -> Optional[Dict[str, Any]]:
        """匹配体重指令"""
        # 模式1: "体重72公斤"、"体重72.5kg"、"体重72.5千克"
        m = re.search(r"体重\s*(\d+\.?\d*)\s*(?:公斤|kg|千克|KG)?", text, re.IGNORECASE)
        if m:
            weight = float(m.group(1))
            return self._record_weight(weight)

        # 模式2: "72.5公斤"、"72kg"
        m = re.search(r"(\d+\.?\d*)\s*(?:公斤|kg|千克|KG)", text, re.IGNORECASE)
        if m:
            weight = float(m.group(1))
            if 20 <= weight <= 300:
                return self._record_weight(weight)

        # 模式3: "体重 一百三十斤" → 65kg
        m = re.search(r"(\d+\.?\d*)\s*斤", text)
        if m:
            jin = float(m.group(1))
            if 40 <= jin <= 600:
                return self._record_weight(jin / 2)

        return None

    def _match_blood_pressure(self, text: str) -> Optional[Dict[str, Any]]:
        """匹配血压指令"""
        # 模式1: "血压120/80"、"血压120 80"
        m = re.search(r"血压\s*(\d{2,3})\s*[/／]\s*(\d{2,3})", text)
        if m:
            return self._record_blood_pressure(int(m.group(1)), int(m.group(2)))

        # 模式2: "高压120低压80"
        m = re.search(r"高压\s*(\d{2,3})\s*低压\s*(\d{2,3})", text)
        if m:
            return self._record_blood_pressure(int(m.group(1)), int(m.group(2)))

        # 模式3: "收缩压120舒张压80"
        m = re.search(r"收缩压?\s*(\d{2,3})\s*舒张压?\s*(\d{2,3})", text)
        if m:
            return self._record_blood_pressure(int(m.group(1)), int(m.group(2)))

        return None

    def _match_checkin(self, text: str) -> Optional[Dict[str, Any]]:
        """匹配打卡指令"""
        # 获取用户所有活跃模板
        templates = self.db.query(CheckinTemplate).filter(
            CheckinTemplate.user_id == self.user_id,
            CheckinTemplate.is_active == True,
        ).all()

        if not templates:
            return None

        # 模式1: "打卡{模板名}" 或 "{模板名}打卡"
        for t in templates:
            if t.name in text and "打卡" in text:
                return self._record_checkin(t)

        # 模式2: 纯 "打卡" + 只有一个模板
        if re.match(r"^打[个]?卡$", text) and len(templates) == 1:
            return self._record_checkin(templates[0])

        return None

    def _record_water(self, amount_ml: int) -> Dict[str, Any]:
        """记录饮水"""
        now = get_china_now()
        record = WaterIntake(
            user_id=self.user_id,
            record_date=now.date(),
            amount=amount_ml,
            intake_time=now,
            drink_type="水",
        )
        self.db.add(record)
        self.db.commit()
        return {
            "command_type": "water",
            "message": f"已记录 {amount_ml}ml 饮水",
            "data": {"amount_ml": amount_ml, "record_id": record.id},
        }

    def _record_weight(self, weight_kg: float) -> Dict[str, Any]:
        """记录体重"""
        today = get_china_today()
        weight_kg = round(weight_kg, 1)

        # 检查今天是否已有记录，有则更新
        existing = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == self.user_id,
            WeightRecord.record_date == today,
        ).first()

        if existing:
            existing.weight = weight_kg
            self.db.commit()
            record_id = existing.id
        else:
            record = WeightRecord(
                user_id=self.user_id,
                record_date=today,
                weight=weight_kg,
            )
            self.db.add(record)
            self.db.commit()
            record_id = record.id

        return {
            "command_type": "weight",
            "message": f"已记录体重 {weight_kg} 公斤",
            "data": {"weight_kg": weight_kg, "record_id": record_id},
        }

    def _record_blood_pressure(self, systolic: int, diastolic: int) -> Dict[str, Any]:
        """记录血压"""
        now = get_china_now()
        record = BloodPressureRecord(
            user_id=self.user_id,
            record_date=now.date(),
            systolic=systolic,
            diastolic=diastolic,
            measured_at=now,
        )
        self.db.add(record)
        self.db.commit()

        # 简单分类
        if systolic < 120 and diastolic < 80:
            category = "正常"
        elif systolic <= 129 and diastolic <= 84:
            category = "正常偏高"
        elif systolic >= 140 or diastolic >= 90:
            category = "高血压"
        else:
            category = "高血压前期"

        return {
            "command_type": "blood_pressure",
            "message": f"已记录血压 {systolic}/{diastolic} mmHg（{category}）",
            "data": {
                "systolic": systolic,
                "diastolic": diastolic,
                "category": category,
                "record_id": record.id,
            },
        }

    def _record_checkin(self, template: CheckinTemplate) -> Dict[str, Any]:
        """记录打卡"""
        today = get_china_today()

        # 检查今天是否已打卡
        existing = self.db.query(CheckinRecord).filter(
            CheckinRecord.template_id == template.id,
            CheckinRecord.user_id == self.user_id,
            CheckinRecord.checkin_date == today,
        ).first()

        if existing:
            return {
                "command_type": "checkin",
                "message": f"{template.name} 今天已经打过卡了",
                "data": {"template_name": template.name, "already_done": True},
            }

        value = template.default_target or 1
        target = template.default_target or 1
        completion_rate = (value / target * 100) if target > 0 else 100

        record = CheckinRecord(
            template_id=template.id,
            user_id=self.user_id,
            checkin_date=today,
            value=value,
            target=target,
            completion_rate=completion_rate,
        )
        self.db.add(record)

        # 更新模板统计
        template.total_checkins = (template.total_checkins or 0) + 1
        template.total_value = (template.total_value or 0) + value
        template.last_checkin_date = today

        self.db.commit()

        return {
            "command_type": "checkin",
            "message": f"已完成 {template.name} 打卡",
            "data": {
                "template_name": template.name,
                "template_icon": template.icon,
                "record_id": record.id,
            },
        }
