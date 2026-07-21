"""数据导出 API"""
import csv
import io
import json
import logging
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.daily_health import GarminData, DietRecord, WaterIntake
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.checkin import CheckinRecord
from app.models.agent_audit_log import AgentAuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/health-data", summary="导出健康数据")
@limiter.limit("5/hour")
def export_health_data(
    request: Request,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    data_type: str = Query(default="garmin", pattern="^(garmin|diet|water|weight|blood_pressure|checkin|all)$"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    导出用户健康数据为 CSV 或 JSON 格式。
    - data_type: garmin/diet/water/weight/blood_pressure/checkin/all
    - format: csv/json
    - start_date/end_date: 可选日期范围（默认最近 90 天）
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=90)

    # 限制导出范围最多 365 天
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="导出范围不能超过365天")

    data_sections = {}

    if data_type in ("garmin", "all"):
        data_sections["garmin"] = _export_garmin(db, current_user.id, start_date, end_date)

    if data_type in ("diet", "all"):
        data_sections["diet"] = _export_diet(db, current_user.id, start_date, end_date)

    if data_type in ("water", "all"):
        data_sections["water"] = _export_water(db, current_user.id, start_date, end_date)

    if data_type in ("weight", "all"):
        data_sections["weight"] = _export_weight(db, current_user.id, start_date, end_date)

    if data_type in ("blood_pressure", "all"):
        data_sections["blood_pressure"] = _export_blood_pressure(db, current_user.id, start_date, end_date)

    if data_type in ("checkin", "all"):
        data_sections["checkin"] = _export_checkin(db, current_user.id, start_date, end_date)

    db.add(AgentAuditLog(
        user_id=current_user.id,
        agent_type="security_audit",
        action="health_data_exported",
        result_summary="用户导出健康数据",
        result_detail={
            "format": format,
            "data_type": data_type,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "row_counts": {name: len(rows) for name, rows in data_sections.items()},
        },
    ))
    db.commit()

    if format == "json":
        return _respond_json(data_sections, data_type)
    else:
        return _respond_csv(data_sections, data_type)


def _export_garmin(db: Session, user_id: int, start: date, end: date):
    records = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= start,
        GarminData.record_date <= end,
    ).order_by(GarminData.record_date).all()

    return [
        {
            "日期": str(r.record_date),
            "步数": r.steps,
            "静息心率": r.resting_heart_rate,
            "平均心率": r.avg_heart_rate,
            "HRV": r.hrv,
            "睡眠评分": r.sleep_score,
            "睡眠时长(分)": r.total_sleep_duration,
            "深度睡眠(分)": r.deep_sleep_duration,
            "压力": r.stress_level,
            "血氧": r.spo2_avg,
            "身体电量": r.body_battery_current,
            "卡路里": r.calories_burned,
            "活动分钟": r.active_minutes,
            "距离(米)": r.distance_meters,
        }
        for r in records
    ]


def _export_diet(db: Session, user_id: int, start: date, end: date):
    records = db.query(DietRecord).filter(
        DietRecord.user_id == user_id,
        DietRecord.record_date >= start,
        DietRecord.record_date <= end,
    ).order_by(DietRecord.record_date).all()

    return [
        {
            "日期": str(r.record_date),
            "餐次": r.meal_type,
            "食物": r.food_items or r.food_name,
            "卡路里": r.calories,
            "蛋白质(g)": r.protein,
            "碳水(g)": r.carbs,
            "脂肪(g)": r.fat,
        }
        for r in records
    ]


def _export_water(db: Session, user_id: int, start: date, end: date):
    records = db.query(WaterIntake).filter(
        WaterIntake.user_id == user_id,
        WaterIntake.record_date >= start,
        WaterIntake.record_date <= end,
    ).order_by(WaterIntake.record_date).all()

    return [
        {
            "日期": str(r.record_date),
            "饮水量(ml)": r.amount_ml,
            "饮品类型": r.drink_type or "水",
        }
        for r in records
    ]


def _export_weight(db: Session, user_id: int, start: date, end: date):
    records = db.query(WeightRecord).filter(
        WeightRecord.user_id == user_id,
        WeightRecord.record_date >= start,
        WeightRecord.record_date <= end,
    ).order_by(WeightRecord.record_date).all()

    return [
        {
            "日期": str(r.record_date),
            "体重(kg)": r.weight_kg,
            "BMI": r.bmi,
            "体脂率(%)": r.body_fat_percentage,
        }
        for r in records
    ]


def _export_blood_pressure(db: Session, user_id: int, start: date, end: date):
    records = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user_id,
        BloodPressureRecord.record_date >= start,
        BloodPressureRecord.record_date <= end,
    ).order_by(BloodPressureRecord.record_date).all()

    return [
        {
            "日期": str(r.record_date),
            "收缩压": r.systolic,
            "舒张压": r.diastolic,
            "心率": r.heart_rate,
        }
        for r in records
    ]


def _export_checkin(db: Session, user_id: int, start: date, end: date):
    records = db.query(CheckinRecord).filter(
        CheckinRecord.user_id == user_id,
        CheckinRecord.checkin_date >= start,
        CheckinRecord.checkin_date <= end,
    ).order_by(CheckinRecord.checkin_date).all()

    return [
        {
            "日期": str(r.checkin_date),
            "模板": r.template_name or "",
            "数值": r.value,
            "单位": r.unit or "",
            "备注": r.notes or "",
        }
        for r in records
    ]


def _respond_json(data_sections: dict, data_type: str):
    if data_type != "all" and data_type in data_sections:
        content = json.dumps(data_sections[data_type], ensure_ascii=False, indent=2)
    else:
        content = json.dumps(data_sections, ensure_ascii=False, indent=2)

    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=health_data_{data_type}.json"},
    )


def _respond_csv(data_sections: dict, data_type: str):
    output = io.StringIO()
    # BOM for Excel compatibility
    output.write('\ufeff')

    for section_name, rows in data_sections.items():
        if not rows:
            continue
        if len(data_sections) > 1:
            output.write(f"\n=== {section_name} ===\n")

        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=health_data_{data_type}.csv"},
    )
