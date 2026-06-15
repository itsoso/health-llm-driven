"""饮食记录API"""
import os
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta, datetime, time

from app.database import get_db
from app.models.daily_health import DietRecord as DietRecordModel
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.diet import (
    MealType,
    DietRecordCreate,
    DietRecordUpdate,
    DietRecordResponse,
    DailyDietSummary,
    DietStats,
    FrequentFood,
    FoodRecognitionRequest,
    FoodRecognitionResponse,
    CreateDietFromImageRequest,
    VoiceFoodParseRequest,
    VoiceFoodParseResponse,
)
from statistics import median
from app.services.ai.food_recognition import food_recognition_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/records", response_model=DietRecordResponse)
def create_diet_record(
    record: DietRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建饮食记录（需要登录）"""
    try:
        logger.info(f"用户 {current_user.id} 创建饮食记录: {record.meal_type}, {record.food_items[:50] if record.food_items else ''}")

        # 转换meal_time为字符串
        record_dict = record.model_dump()
        if record_dict.get('meal_time'):
            record_dict['meal_time'] = record_dict['meal_time'].strftime('%H:%M')

        # 处理图片上传
        image_url = record_dict.get('image_url')
        if record_dict.get('image_base64'):
            try:
                from app.api.upload import ensure_upload_dir, generate_filename, UPLOAD_DIR
                import base64 as b64

                ensure_upload_dir()
                image_type = (record_dict.get('image_type') or 'jpeg').lower()
                if image_type == "jpg":
                    image_type = "jpeg"

                # 解码并保存图片
                base64_data = record_dict['image_base64']
                if "," in base64_data:
                    base64_data = base64_data.split(",", 1)[1]

                image_data = b64.b64decode(base64_data)
                filename = generate_filename(image_type, "diet")
                filepath = os.path.join(UPLOAD_DIR, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                with open(filepath, "wb") as f:
                    f.write(image_data)

                image_url = f"/api/v1/upload/files/{filename}"
                logger.info(f"保存饮食图片: {filename}")
            except Exception as e:
                logger.warning(f"保存图片失败: {e}")

        # 确保 meal_type 是字符串
        meal_type_value = record_dict['meal_type']
        if isinstance(meal_type_value, MealType):
            meal_type_value = meal_type_value.value

        # food_name 使用 food_items 的值（数据库要求 NOT NULL）
        food_name = record_dict['food_items']
        if food_name and len(food_name) > 100:
            food_name = food_name[:100]  # 截断过长的名称

        db_record = DietRecordModel(
            user_id=current_user.id,
            record_date=record_dict['record_date'],
            meal_type=meal_type_value,
            food_name=food_name,  # 必填字段
            food_items=record_dict['food_items'],
            calories=record_dict.get('calories'),
            protein=record_dict.get('protein'),
            carbs=record_dict.get('carbs'),
            fat=record_dict.get('fat'),
            fiber=record_dict.get('fiber'),
            notes=record_dict.get('notes'),
            image_url=image_url,
            health_tips=record_dict.get('health_tips'),
        )
        db.add(db_record)
        db.commit()
        db.refresh(db_record)

        logger.info(f"饮食记录创建成功: id={db_record.id}")
        return _convert_to_response(db_record)

    except Exception as e:
        logger.error(f"创建饮食记录失败: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建记录失败: {str(e)}")


def _convert_to_response(record) -> DietRecordResponse:
    """转换为响应模型"""
    meal_time = None
    if hasattr(record, 'meal_time') and record.meal_time:
        if isinstance(record.meal_time, str):
            try:
                meal_time = datetime.strptime(record.meal_time, '%H:%M').time()
            except (ValueError, TypeError):
                meal_time = None
        elif isinstance(record.meal_time, time):
            meal_time = record.meal_time

    return DietRecordResponse(
        id=record.id,
        user_id=record.user_id,
        record_date=record.record_date,
        meal_type=MealType(record.meal_type) if record.meal_type else MealType.EXTRA,
        meal_time=meal_time,
        food_items=record.food_items or '',
        calories=record.calories,
        protein=record.protein,
        carbs=record.carbs,
        fat=record.fat,
        fiber=record.fiber,
        notes=record.notes,
        image_url=getattr(record, 'image_url', None),
        ai_recognized=getattr(record, 'ai_recognized', 0),
        ai_confidence=getattr(record, 'ai_confidence', None),
        health_tips=getattr(record, 'health_tips', None),
        created_at=record.created_at,
        updated_at=record.updated_at if hasattr(record, 'updated_at') else None,
    )



@router.get("/records/user/{user_id}", response_model=List[DietRecordResponse])
def get_user_diet_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户饮食记录"""
    query = db.query(DietRecordModel).filter(DietRecordModel.user_id == user_id)

    if start_date:
        query = query.filter(DietRecordModel.record_date >= start_date)
    if end_date:
        query = query.filter(DietRecordModel.record_date <= end_date)
    if meal_type:
        query = query.filter(DietRecordModel.meal_type == meal_type)

    records = query.order_by(desc(DietRecordModel.record_date)).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/user/{user_id}/date/{record_date}", response_model=DailyDietSummary)
def get_daily_diet_summary(
    user_id: int,
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取某日饮食汇总"""
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        DietRecordModel.record_date == record_date
    ).order_by(DietRecordModel.created_at).all()

    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)

    return DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_convert_to_response(r) for r in records]
    )


@router.get("/records/user/{user_id}/stats", response_model=DietStats)
def get_diet_stats(
    user_id: int,
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取饮食统计"""
    start_date = date.today() - timedelta(days=days)

    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        DietRecordModel.record_date >= start_date
    ).all()

    if not records:
        return DietStats(total_records=0, days_recorded=0)

    # 按日期分组统计
    daily_data = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_data:
            daily_data[d] = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        daily_data[d]['calories'] += r.calories or 0
        daily_data[d]['protein'] += r.protein or 0
        daily_data[d]['carbs'] += r.carbs or 0
        daily_data[d]['fat'] += r.fat or 0

    days_count = len(daily_data)

    return DietStats(
        average_daily_calories=round(sum(d['calories'] for d in daily_data.values()) / days_count, 0) if days_count else None,
        average_daily_protein=round(sum(d['protein'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_carbs=round(sum(d['carbs'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_fat=round(sum(d['fat'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        total_records=len(records),
        days_recorded=days_count
    )


# ========== /me 端点 ==========

@router.get("/records/me", response_model=List[DietRecordResponse])
def get_my_diet_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户饮食记录（需要登录）"""
    query = db.query(DietRecordModel).filter(DietRecordModel.user_id == current_user.id)

    if start_date:
        query = query.filter(DietRecordModel.record_date >= start_date)
    if end_date:
        query = query.filter(DietRecordModel.record_date <= end_date)
    if meal_type:
        query = query.filter(DietRecordModel.meal_type == meal_type)

    records = query.order_by(desc(DietRecordModel.record_date)).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/me/date/{record_date}", response_model=DailyDietSummary)
def get_my_daily_diet_summary(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户某日饮食汇总（需要登录）"""
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date == record_date
    ).order_by(DietRecordModel.created_at).all()

    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)

    return DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_convert_to_response(r) for r in records]
    )


@router.get("/records/me/stats", response_model=DietStats)
def get_my_diet_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户饮食统计（需要登录）"""
    start_date = date.today() - timedelta(days=days)

    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date >= start_date
    ).all()

    if not records:
        return DietStats(total_records=0, days_recorded=0)

    # 按日期分组统计
    daily_data = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_data:
            daily_data[d] = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        daily_data[d]['calories'] += r.calories or 0
        daily_data[d]['protein'] += r.protein or 0
        daily_data[d]['carbs'] += r.carbs or 0
        daily_data[d]['fat'] += r.fat or 0

    days_count = len(daily_data)

    return DietStats(
        average_daily_calories=round(sum(d['calories'] for d in daily_data.values()) / days_count, 0) if days_count else None,
        average_daily_protein=round(sum(d['protein'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_carbs=round(sum(d['carbs'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_fat=round(sum(d['fat'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        total_records=len(records),
        days_recorded=days_count
    )


def _median_or_none(values: List[float]) -> Optional[float]:
    """对非空数值取中位数, 全空返回 None (诚实表达"无历史营养数据")."""
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(float(median(nums)), 1)


@router.get("/records/me/frequent", response_model=List[FrequentFood])
def get_my_frequent_foods(
    days: int = Query(default=30, ge=7, le=180),
    limit: int = Query(default=8, ge=1, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前用户最近 N 天的"常吃"食物, 按出现频次倒序 (供一键复用).

    按 food_items (去空白后) 分组; 同名食物的营养素取历次中位数, meal_type 取众数.
    无历史营养数据的项营养素返回 null —— 不编造数值 (rule#1).
    """
    start_date = date.today() - timedelta(days=days)
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date >= start_date,
    ).all()

    # 按归一化 food_items 分组
    groups: dict[str, list] = {}
    for r in records:
        key = (r.food_items or "").strip()
        if not key:
            continue
        groups.setdefault(key, []).append(r)

    items: List[FrequentFood] = []
    for food, rs in groups.items():
        # meal_type 众数 (并列时取最近一次)
        meal_counts: dict[str, int] = {}
        for r in rs:
            mt = r.meal_type or "extra"
            meal_counts[mt] = meal_counts.get(mt, 0) + 1
        top_meal = max(meal_counts.items(), key=lambda kv: kv[1])[0]
        items.append(FrequentFood(
            food_items=food,
            meal_type=MealType(top_meal) if top_meal in MealType._value2member_map_ else MealType.EXTRA,
            count=len(rs),
            calories=_median_or_none([r.calories for r in rs]),
            protein=_median_or_none([r.protein for r in rs]),
            carbs=_median_or_none([r.carbs for r in rs]),
            fat=_median_or_none([r.fat for r in rs]),
        ))

    # 频次倒序, 同频次按字母稳定排序
    items.sort(key=lambda f: (-f.count, f.food_items))
    return items[:limit]


@router.put("/records/{record_id}", response_model=DietRecordResponse)
def update_diet_record(
    record_id: int,
    update_data: DietRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """更新饮食记录（需登录，且只能更新自己的记录）"""
    record = db.query(DietRecordModel).filter(DietRecordModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权更新他人的饮食记录")

    update_dict = update_data.model_dump(exclude_unset=True)
    if 'meal_type' in update_dict and update_dict['meal_type']:
        update_dict['meal_type'] = update_dict['meal_type'].value
    if 'meal_time' in update_dict and update_dict['meal_time']:
        update_dict['meal_time'] = update_dict['meal_time'].strftime('%H:%M')

    for key, value in update_dict.items():
        setattr(record, key, value)

    db.commit()
    db.refresh(record)
    return _convert_to_response(record)


@router.delete("/records/{record_id}")
def delete_diet_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """删除饮食记录（需登录，且只能删除自己的记录）"""
    record = db.query(DietRecordModel).filter(DietRecordModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除他人的饮食记录")

    db.delete(record)
    db.commit()
    return {"message": "Record deleted successfully"}


# ========== AI食物识别端点 ==========

@router.post("/voice/parse", response_model=VoiceFoodParseResponse)
async def parse_voice_food_endpoint(
    request: VoiceFoodParseRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """语音转写文本 → 结构化食物草稿(Apple Watch Companion / R5)。

    只解析不写库;客户端确认后再 POST /diet/records。分层:规则(餐次/风险标签)+
    记忆(常吃中位营养)+ LLM(自由文本→结构化)。LLM 不可用则降级 + 标 needs_confirmation。
    """
    from app.services.diet_voice_parser import parse_voice_food

    return await parse_voice_food(db, current_user.id, request.raw_text, request.meal_type)


@router.post("/recognize", response_model=FoodRecognitionResponse)
async def recognize_food(
    request: FoodRecognitionRequest,
    current_user: User = Depends(get_current_user_required)
):
    """
    AI识别食物图片

    上传Base64编码的图片，AI会识别出食物并估算营养信息
    """
    if not food_recognition_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="智能食物识别服务不可用"
        )

    try:
        result = await food_recognition_service.recognize_food_from_base64(
            request.image_base64,
            request.image_type
        )

        if not result.get("success"):
            return FoodRecognitionResponse(
                success=False,
                error=result.get("error", "识别失败"),
                foods=[]
            )

        return FoodRecognitionResponse(
            success=True,
            foods=result.get("foods", []),
            meal_description=result.get("meal_description"),
            health_tips=result.get("health_tips"),
            total_calories=result.get("total_calories"),
            total_protein=result.get("total_protein"),
            total_carbs=result.get("total_carbs"),
            total_fat=result.get("total_fat")
        )

    except Exception as e:
        logger.error(f"食物识别失败: {e}")
        raise HTTPException(status_code=500, detail=f"识别失败: {str(e)}")


@router.post("/recognize-and-save", response_model=DietRecordResponse)
async def recognize_and_save_diet(
    request: CreateDietFromImageRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    AI识别食物图片并直接保存为饮食记录

    一键拍照 -> AI识别 -> 保存记录
    """
    if not food_recognition_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="智能食物识别服务不可用"
        )

    try:
        # AI识别
        result = await food_recognition_service.recognize_food_from_base64(
            request.image_base64,
            request.image_type
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "智能识别失败")
            )

        foods = result.get("foods", [])
        if not foods:
            raise HTTPException(
                status_code=400,
                detail="未识别到任何食物，请重新拍照"
            )

        # 组合食物名称
        food_names = [f.get("name", "") for f in foods if f.get("name")]
        food_items = ", ".join([f.get("name", "") + (f" ({f.get('quantity', '')})" if f.get('quantity') else "") for f in foods])

        # 取第一个食物名称作为主名称（兼容旧字段）
        primary_food_name = food_names[0] if food_names else "智能识别食物"

        # 计算平均置信度
        confidences = [f.get("confidence", 0) for f in foods if f.get("confidence")]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        # 保存图片（如果有）
        image_url = None
        if request.image_base64:
            try:
                from app.api.upload import ensure_upload_dir, generate_filename, UPLOAD_DIR
                import base64 as b64

                ensure_upload_dir()
                image_type = request.image_type.lower()
                if image_type == "jpg":
                    image_type = "jpeg"

                # 解码并保存图片
                base64_data = request.image_base64
                if "," in base64_data:
                    base64_data = base64_data.split(",", 1)[1]

                image_data = b64.b64decode(base64_data)
                filename = generate_filename(image_type, "diet")
                filepath = os.path.join(UPLOAD_DIR, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                with open(filepath, "wb") as f:
                    f.write(image_data)

                image_url = f"/api/v1/upload/files/{filename}"
                logger.info(f"保存饮食图片: {filename}")
            except Exception as e:
                logger.warning(f"保存图片失败: {e}")

        # 创建饮食记录
        db_record = DietRecordModel(
            user_id=current_user.id,
            record_date=request.record_date,
            meal_type=request.meal_type.value,
            food_name=primary_food_name,  # 必填字段
            food_items=food_items,
            calories=result.get("total_calories"),
            protein=result.get("total_protein"),
            carbs=result.get("total_carbs"),
            fat=result.get("total_fat"),
            notes=request.notes,
            image_url=image_url,  # 保存图片URL
            ai_recognized=True,  # 布尔类型，不是整数
            ai_confidence=avg_confidence,
            ai_raw_result=json.dumps(result, ensure_ascii=False),
            health_tips=result.get("health_tips")
        )

        db.add(db_record)
        db.commit()
        db.refresh(db_record)

        logger.info(f"用户 {current_user.id} 通过AI识别创建饮食记录: {food_items}")

        return _convert_to_response(db_record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI识别并保存失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.post("/estimate-nutrition", response_model=FoodRecognitionResponse)
async def estimate_nutrition_from_text(
    food_description: str = Query(..., description="食物描述文字"),
    current_user: User = Depends(get_current_user_required)
):
    """
    根据文字描述估算营养信息（不需要图片）

    例如: "两个鸡蛋，一碗米饭，炒青菜"
    """
    if not food_recognition_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="智能服务不可用"
        )

    try:
        result = food_recognition_service.estimate_nutrition_from_text(food_description)

        if not result.get("success"):
            return FoodRecognitionResponse(
                success=False,
                error=result.get("error", "估算失败"),
                foods=[]
            )

        return FoodRecognitionResponse(
            success=True,
            foods=result.get("foods", []),
            health_tips=result.get("health_tips"),
            total_calories=result.get("total_calories"),
            total_protein=result.get("total_protein"),
            total_carbs=result.get("total_carbs"),
            total_fat=result.get("total_fat")
        )

    except Exception as e:
        logger.error(f"营养估算失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
