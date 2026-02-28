"""健康事件流服务 - 事件摄入、推理、确认、写入"""
import logging
from datetime import datetime, date, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, func as sa_func

from app.models.health_event import HealthEvent, EventSource, EventStatus
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import WaterIntake
from app.models.excretion import ExcretionRecord

logger = logging.getLogger(__name__)

# 事件类型 → 目标记录表的映射
RECORD_TYPE_MAP = {
    "weight": "weight_records",
    "blood_pressure": "blood_pressure_records",
    "water": "water_intakes",
    "excretion": "excretion_records",
}


class HealthEventService:
    """健康事件流服务"""

    def __init__(self, db: Session):
        self.db = db

    # ========== 事件摄入 ==========

    def ingest_event(self, user_id: int, event_type: str, source: str,
                     raw_data: Optional[dict] = None,
                     source_device_id: Optional[str] = None,
                     event_time: Optional[datetime] = None) -> HealthEvent:
        """摄入一个健康事件"""
        now = datetime.now(timezone.utc)

        # 1. AI 推理（Phase 1: 简单规则引擎）
        ai_inference = self._infer(event_type, source, raw_data)
        confidence = self._compute_confidence(event_type, source, raw_data, ai_inference)

        # 2. 查找对应的 EventSource 配置
        auto_threshold = 0.8
        if source_device_id:
            event_source = self.db.query(EventSource).filter(
                EventSource.device_id == source_device_id,
                EventSource.user_id == user_id,
                EventSource.is_active == "true",
            ).first()
            if event_source:
                auto_threshold = event_source.auto_confirm_threshold

        # 3. 判断是否自动确认
        status = EventStatus.pending
        confirmed_data = None
        confirmed_at = None
        if confidence >= auto_threshold:
            status = EventStatus.auto_confirmed
            confirmed_data = ai_inference
            confirmed_at = now

        # 4. 创建事件
        event = HealthEvent(
            user_id=user_id,
            event_type=event_type,
            source=source,
            source_device_id=source_device_id,
            raw_data=raw_data,
            ai_inference=ai_inference,
            confidence=confidence,
            status=status,
            confirmed_data=confirmed_data,
            target_record_type=RECORD_TYPE_MAP.get(event_type),
            event_time=event_time or now,
            confirmed_at=confirmed_at,
        )
        self.db.add(event)
        self.db.flush()

        # 5. 自动确认 → 立刻写入目标表
        if status == EventStatus.auto_confirmed:
            self._write_to_target(event)

        self.db.commit()
        self.db.refresh(event)
        logger.info(f"Event ingested: type={event_type}, source={source}, "
                     f"confidence={confidence:.2f}, status={status.value}")
        return event

    # ========== 待确认事件 ==========

    def get_pending_events(self, user_id: int, event_type: Optional[str] = None,
                           limit: int = 50) -> List[HealthEvent]:
        """获取用户待确认的事件"""
        query = self.db.query(HealthEvent).filter(
            HealthEvent.user_id == user_id,
            HealthEvent.status == EventStatus.pending,
        )
        if event_type:
            query = query.filter(HealthEvent.event_type == event_type)
        return query.order_by(desc(HealthEvent.event_time)).limit(limit).all()

    def get_pending_summary(self, user_id: int) -> dict:
        """获取待确认事件摘要"""
        rows = self.db.query(
            HealthEvent.event_type,
            sa_func.count(HealthEvent.id),
        ).filter(
            HealthEvent.user_id == user_id,
            HealthEvent.status == EventStatus.pending,
        ).group_by(HealthEvent.event_type).all()

        by_type = {row[0]: row[1] for row in rows}
        return {
            "total": sum(by_type.values()),
            "by_type": by_type,
        }

    # ========== 确认/修正/忽略 ==========

    def confirm_event(self, user_id: int, event_id: int,
                      confirmed_data: Optional[dict] = None,
                      status: str = "confirmed") -> HealthEvent:
        """用户确认或修正一个事件"""
        event = self.db.query(HealthEvent).filter(
            HealthEvent.id == event_id,
            HealthEvent.user_id == user_id,
        ).first()
        if not event:
            raise ValueError("事件不存在")

        now = datetime.now(timezone.utc)

        if status == "dismissed":
            event.status = EventStatus.dismissed
            event.confirmed_at = now
        elif confirmed_data:
            event.status = EventStatus.corrected
            event.confirmed_data = confirmed_data
            event.confirmed_at = now
            self._write_to_target(event)
        else:
            # 接受 AI 推理结果
            event.status = EventStatus.confirmed
            event.confirmed_data = event.ai_inference
            event.confirmed_at = now
            self._write_to_target(event)

        self.db.commit()
        self.db.refresh(event)
        return event

    def batch_confirm(self, user_id: int, event_ids: List[int]) -> List[HealthEvent]:
        """批量确认事件（接受 AI 推理结果）"""
        events = self.db.query(HealthEvent).filter(
            HealthEvent.id.in_(event_ids),
            HealthEvent.user_id == user_id,
            HealthEvent.status == EventStatus.pending,
        ).all()

        now = datetime.now(timezone.utc)
        for event in events:
            event.status = EventStatus.confirmed
            event.confirmed_data = event.ai_inference
            event.confirmed_at = now
            self._write_to_target(event)

        self.db.commit()
        for event in events:
            self.db.refresh(event)
        return events

    # ========== 事件历史 ==========

    def get_events(self, user_id: int, event_type: Optional[str] = None,
                   status: Optional[str] = None, limit: int = 50) -> List[HealthEvent]:
        """查询事件历史"""
        query = self.db.query(HealthEvent).filter(
            HealthEvent.user_id == user_id,
        )
        if event_type:
            query = query.filter(HealthEvent.event_type == event_type)
        if status:
            query = query.filter(HealthEvent.status == status)
        return query.order_by(desc(HealthEvent.event_time)).limit(limit).all()

    # ========== EventSource CRUD ==========

    def create_source(self, user_id: int, source_type: str, device_id: str,
                      name: str, event_type: str,
                      config: Optional[dict] = None,
                      auto_confirm_threshold: float = 0.8) -> EventSource:
        """注册事件来源"""
        source = EventSource(
            user_id=user_id,
            source_type=source_type,
            device_id=device_id,
            name=name,
            event_type=event_type,
            config=config or {},
            auto_confirm_threshold=auto_confirm_threshold,
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def get_sources(self, user_id: int) -> List[EventSource]:
        """获取用户的所有事件来源"""
        return self.db.query(EventSource).filter(
            EventSource.user_id == user_id,
        ).order_by(desc(EventSource.created_at)).all()

    def update_source(self, user_id: int, source_id: int,
                      update_data: dict) -> EventSource:
        """更新事件来源"""
        source = self.db.query(EventSource).filter(
            EventSource.id == source_id,
            EventSource.user_id == user_id,
        ).first()
        if not source:
            raise ValueError("事件来源不存在")

        for key, value in update_data.items():
            if value is not None:
                setattr(source, key, value)

        self.db.commit()
        self.db.refresh(source)
        return source

    def delete_source(self, user_id: int, source_id: int) -> None:
        """删除事件来源"""
        source = self.db.query(EventSource).filter(
            EventSource.id == source_id,
            EventSource.user_id == user_id,
        ).first()
        if not source:
            raise ValueError("事件来源不存在")
        self.db.delete(source)
        self.db.commit()

    # ========== 内部方法 ==========

    def _infer(self, event_type: str, source: str, raw_data: Optional[dict]) -> dict:
        """Phase 1: 简单规则引擎推理。后续可接入 LLM。"""
        if not raw_data:
            return {}

        if event_type == "weight":
            return self._infer_weight(raw_data)
        elif event_type == "blood_pressure":
            return self._infer_blood_pressure(raw_data)
        elif event_type == "water":
            return self._infer_water(raw_data)
        elif event_type == "excretion":
            return self._infer_excretion(raw_data)

        # 未知类型 → 原样返回
        return raw_data

    def _infer_weight(self, raw_data: dict) -> dict:
        """推理体重数据"""
        result = {"record_date": date.today().isoformat()}
        if "weight" in raw_data:
            result["weight"] = float(raw_data["weight"])
        if "body_fat" in raw_data or "body_fat_percentage" in raw_data:
            result["body_fat_percentage"] = float(
                raw_data.get("body_fat") or raw_data.get("body_fat_percentage")
            )
        if "muscle_mass" in raw_data or "muscle_mass_kg" in raw_data:
            result["muscle_mass_kg"] = float(
                raw_data.get("muscle_mass") or raw_data.get("muscle_mass_kg")
            )
        # 传入更多字段直接透传
        for key in ("bmi", "bmr", "visceral_fat", "bone_mass_kg", "water_percentage"):
            if key in raw_data:
                result[key] = raw_data[key]
        return result

    def _infer_blood_pressure(self, raw_data: dict) -> dict:
        """推理血压数据"""
        result = {"record_date": date.today().isoformat()}
        for key in ("systolic", "diastolic", "pulse", "notes"):
            if key in raw_data:
                result[key] = raw_data[key]
        return result

    def _infer_water(self, raw_data: dict) -> dict:
        """推理喝水数据"""
        result = {"record_date": date.today().isoformat()}
        if "amount_ml" in raw_data:
            result["amount_ml"] = int(raw_data["amount_ml"])
        elif "amount" in raw_data:
            result["amount_ml"] = int(raw_data["amount"])
        return result

    def _infer_excretion(self, raw_data: dict) -> dict:
        """推理排泄数据"""
        result = {"record_date": date.today().isoformat()}
        for key in ("type", "stool_type", "color", "amount", "urine_color",
                     "urine_amount", "urgency", "pain_level", "notes"):
            if key in raw_data:
                result[key] = raw_data[key]
        if "type" not in result:
            result["type"] = "bowel"  # 默认大便
        return result

    def _compute_confidence(self, event_type: str, source: str,
                            raw_data: Optional[dict],
                            ai_inference: dict) -> float:
        """计算置信度"""
        if not ai_inference:
            return 0.0

        # 蓝牙体重秤 → 高置信度（数据来自硬件传感器）
        if source in ("bluetooth_scale", "bluetooth_bp"):
            return 0.95

        # NFC 标签（用户主动碰触 = 明确意图）
        if source == "nfc_tag":
            return 0.85

        # API（来自其他系统同步）
        if source == "api":
            return 0.90

        # 手动输入 → 中等置信度
        if source == "manual":
            return 0.70

        # 语音/照片（需 AI 解析，置信度视质量而定）
        if source in ("voice", "photo"):
            return 0.60

        return 0.50

    def _write_to_target(self, event: HealthEvent) -> None:
        """将确认后的事件数据写入目标记录表"""
        data = event.confirmed_data
        if not data:
            return

        try:
            record = None
            if event.event_type == "weight":
                record = self._write_weight(event.user_id, data)
            elif event.event_type == "blood_pressure":
                record = self._write_blood_pressure(event.user_id, data)
            elif event.event_type == "water":
                record = self._write_water(event.user_id, data)
            elif event.event_type == "excretion":
                record = self._write_excretion(event.user_id, data)

            if record:
                self.db.flush()
                event.target_record_id = record.id
                logger.info(f"Event {event.id} written to {event.target_record_type} "
                            f"as record {record.id}")
        except Exception as e:
            logger.error(f"Failed to write event {event.id} to target: {e}")

    def _write_weight(self, user_id: int, data: dict) -> WeightRecord:
        record_date = date.fromisoformat(data.get("record_date", date.today().isoformat()))
        record = WeightRecord(
            user_id=user_id,
            record_date=record_date,
            weight=data["weight"],
            body_fat_percentage=data.get("body_fat_percentage"),
            muscle_mass_kg=data.get("muscle_mass_kg"),
            bmi=data.get("bmi"),
            bmr=data.get("bmr"),
            visceral_fat=data.get("visceral_fat"),
            bone_mass_kg=data.get("bone_mass_kg"),
            water_percentage=data.get("water_percentage"),
            source="health_event",
        )
        self.db.add(record)
        return record

    def _write_blood_pressure(self, user_id: int, data: dict) -> BloodPressureRecord:
        record_date = date.fromisoformat(data.get("record_date", date.today().isoformat()))
        record = BloodPressureRecord(
            user_id=user_id,
            record_date=record_date,
            systolic=data["systolic"],
            diastolic=data["diastolic"],
            pulse=data.get("pulse"),
            notes=data.get("notes"),
        )
        self.db.add(record)
        return record

    def _write_water(self, user_id: int, data: dict) -> WaterIntake:
        record_date = date.fromisoformat(data.get("record_date", date.today().isoformat()))
        record = WaterIntake(
            user_id=user_id,
            record_date=record_date,
            amount_ml=data["amount_ml"],
        )
        self.db.add(record)
        return record

    def _write_excretion(self, user_id: int, data: dict) -> ExcretionRecord:
        record_date = date.fromisoformat(data.get("record_date", date.today().isoformat()))
        record = ExcretionRecord(
            user_id=user_id,
            record_date=record_date,
            type=data.get("type", "bowel"),
            stool_type=data.get("stool_type"),
            color=data.get("color"),
            amount=data.get("amount"),
            urine_color=data.get("urine_color"),
            urine_amount=data.get("urine_amount"),
            urgency=data.get("urgency"),
            pain_level=data.get("pain_level"),
            notes=data.get("notes"),
        )
        self.db.add(record)
        return record
