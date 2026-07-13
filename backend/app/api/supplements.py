"""补剂管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any
from datetime import date, timedelta
from pydantic import BaseModel
from app.database import get_db
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.supplement import (
    SupplementDefinitionCreate,
    SupplementDefinitionUpdate,
    SupplementDefinitionResponse,
    SupplementRecordCreate,
    SupplementRecordUpdate,
    SupplementRecordResponse,
    SupplementBatchCheckin,
    SupplementWithRecord,
    FrequentSupplement,
)
from app.services.supplement_recommendation import SupplementRecommendationService
from app.services.daily_supplement_guide import get_daily_supplement_guide
from app.services.supplement_evidence import (
    SUPPLEMENT_EVIDENCE_CATALOG_VERSION,
    get_supplement_evidence_profile,
    list_supplement_evidence_catalog,
    list_supplement_evidence_sources,
)
from app.utils.redis_cache import (
    cache_supplement_recommendation,
    get_cached_supplement_recommendation,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


def _ensure_self_or_admin(current_user: User, user_id: int) -> None:
    """Legacy /user/{user_id} routes must not leak another user's health data."""
    if current_user.id != user_id and not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="无权访问他人的补剂数据")


def _get_owned_supplement(db: Session, user_id: int, supplement_id: int) -> SupplementDefinition:
    supplement = db.query(SupplementDefinition).filter(
        SupplementDefinition.id == supplement_id,
        SupplementDefinition.user_id == user_id,
    ).first()
    if not supplement:
        raise HTTPException(status_code=404, detail="补剂不存在")
    return supplement


def _get_owned_supplement_record(db: Session, user_id: int, record_id: int) -> SupplementRecord:
    record = db.query(SupplementRecord).filter(
        SupplementRecord.id == record_id,
        SupplementRecord.user_id == user_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="补剂打卡记录不存在")
    return record


# ========== 补剂定义 ==========

@router.post("/definitions", response_model=SupplementDefinitionResponse)
def create_supplement(
    supplement: SupplementDefinitionCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建补剂（需要登录，自动使用当前用户）"""
    # 使用当前登录用户的 ID
    supplement_data = supplement.model_dump()
    supplement_data['user_id'] = current_user.id

    db_supplement = SupplementDefinition(**supplement_data)
    db.add(db_supplement)
    db.commit()
    db.refresh(db_supplement)
    _invalidate_twin(current_user.id)
    return db_supplement


@router.get("/definitions/user/{user_id}", response_model=List[SupplementDefinitionResponse])
def get_user_supplements(
    user_id: int,
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的补剂列表"""
    _ensure_self_or_admin(current_user, user_id)
    query = db.query(SupplementDefinition).filter(SupplementDefinition.user_id == user_id)
    if active_only:
        query = query.filter(SupplementDefinition.is_active)
    return query.order_by(SupplementDefinition.sort_order, SupplementDefinition.id).all()


@router.put("/definitions/{supplement_id}", response_model=SupplementDefinitionResponse)
def update_supplement(
    supplement_id: int,
    update_data: SupplementDefinitionUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新补剂"""
    supplement = db.query(SupplementDefinition).filter(
        SupplementDefinition.id == supplement_id,
        SupplementDefinition.user_id == current_user.id,
    ).first()
    if not supplement:
        raise HTTPException(status_code=404, detail="补剂不存在")

    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(supplement, key, value)

    db.commit()
    db.refresh(supplement)
    _invalidate_twin(current_user.id)
    return supplement


@router.delete("/definitions/{supplement_id}")
def delete_supplement(
    supplement_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除补剂"""
    supplement = db.query(SupplementDefinition).filter(
        SupplementDefinition.id == supplement_id,
        SupplementDefinition.user_id == current_user.id,
    ).first()
    if not supplement:
        raise HTTPException(status_code=404, detail="补剂不存在")

    db.delete(supplement)
    db.commit()
    _invalidate_twin(current_user.id)
    return {"message": "删除成功"}


# ========== 补剂打卡 ==========

@router.post("/records", response_model=SupplementRecordResponse)
def create_supplement_record(
    record: SupplementRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建/更新补剂打卡记录"""
    user_id = current_user.id
    _get_owned_supplement(db, user_id, record.supplement_id)

    # 检查是否已存在记录
    existing = db.query(SupplementRecord).filter(
        SupplementRecord.user_id == user_id,
        SupplementRecord.supplement_id == record.supplement_id,
        SupplementRecord.record_date == record.record_date
    ).first()

    if existing:
        existing.taken = record.taken
        existing.taken_time = record.taken_time
        existing.notes = record.notes
        db.commit()
        db.refresh(existing)
        _invalidate_twin(user_id)
        return existing

    record_data = record.model_dump()
    record_data["user_id"] = user_id
    db_record = SupplementRecord(**record_data)
    db.add(db_record)
    try:
        db.commit()
    except IntegrityError:
        # 依从写回幂等:并发另一个请求已为 (补剂, 日期) 落行(uq_supprec_supp_date)→ 回滚
        # 重读, 把本次 toggle 合并写到既有行, 不静默落第二条虚高依从。
        db.rollback()
        existing = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.supplement_id == record.supplement_id,
            SupplementRecord.record_date == record.record_date,
        ).first()
        if existing is None:  # 撞唯一约束却查不到 → 反常, fail loud
            raise
        existing.taken = record.taken
        existing.taken_time = record.taken_time
        existing.notes = record.notes
        db.commit()
        db.refresh(existing)
        _invalidate_twin(user_id)
        return existing
    db.refresh(db_record)
    _invalidate_twin(user_id)
    return db_record


@router.post("/records/batch")
def batch_checkin(
    batch: SupplementBatchCheckin,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """批量补剂打卡（需要登录，自动使用当前用户）"""
    # 使用当前登录用户的 ID，忽略请求中的 user_id
    user_id = current_user.id

    results = []
    for checkin in batch.checkins:
        supplement_id = checkin.get("supplement_id")
        taken = checkin.get("taken", False)
        if isinstance(supplement_id, bool) or not isinstance(supplement_id, int):
            raise HTTPException(status_code=400, detail="supplement_id 无效")
        _get_owned_supplement(db, user_id, supplement_id)

        existing = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.supplement_id == supplement_id,
            SupplementRecord.record_date == batch.record_date
        ).first()

        if existing:
            existing.taken = taken
            db.commit()
            results.append({"supplement_id": supplement_id, "action": "updated"})
        else:
            record = SupplementRecord(
                supplement_id=supplement_id,
                user_id=user_id,  # 使用当前登录用户的 ID
                record_date=batch.record_date,
                taken=taken
            )
            db.add(record)
            results.append({"supplement_id": supplement_id, "action": "created"})

    db.commit()
    _invalidate_twin(user_id)
    return {"message": "批量打卡成功", "results": results}


@router.get("/records/user/{user_id}/date/{record_date}", response_model=List[SupplementWithRecord])
def get_user_supplements_with_records(
    user_id: int,
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户某天的补剂列表及打卡状态"""
    _ensure_self_or_admin(current_user, user_id)
    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.is_active
    ).order_by(SupplementDefinition.timing, SupplementDefinition.sort_order).all()

    result = []
    for supp in supplements:
        record = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.supplement_id == supp.id,
            SupplementRecord.record_date == record_date
        ).first()

        result.append(SupplementWithRecord(
            supplement=SupplementDefinitionResponse.model_validate(supp),
            record=SupplementRecordResponse.model_validate(record) if record else None
        ))

    return result


@router.get("/records/user/{user_id}/stats")
def get_supplement_stats(
    user_id: int,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取补剂统计"""
    _ensure_self_or_admin(current_user, user_id)
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)

    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.is_active
    ).all()

    stats = []
    for supp in supplements:
        records = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.supplement_id == supp.id,
            SupplementRecord.record_date >= start_date,
            SupplementRecord.record_date <= end_date
        ).all()

        taken_count = sum(1 for r in records if r.taken)

        stats.append({
            "supplement_id": supp.id,
            "supplement_name": supp.name,
            "category": supp.category,
            "total_days": days,
            "taken_days": taken_count,
            "completion_rate": round(taken_count / days * 100, 1)
        })

    return stats


# ========== /me 端点 ==========

@router.get("/me/definitions", response_model=List[SupplementDefinitionResponse])
def get_my_supplements(
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的补剂列表（需要登录）"""
    query = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == current_user.id
    )
    if active_only:
        query = query.filter(SupplementDefinition.is_active)
    return query.order_by(SupplementDefinition.sort_order, SupplementDefinition.id).all()


@router.get("/me/records", response_model=List[SupplementRecordResponse])
def get_my_records(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    supplement_id: Optional[int] = Query(None, description="补剂ID筛选"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的补剂打卡记录（需要登录，支持日期范围和补剂筛选）"""
    query = db.query(SupplementRecord).filter(
        SupplementRecord.user_id == current_user.id
    )
    if start_date:
        query = query.filter(SupplementRecord.record_date >= start_date)
    if end_date:
        query = query.filter(SupplementRecord.record_date <= end_date)
    if supplement_id:
        query = query.filter(SupplementRecord.supplement_id == supplement_id)
    return query.order_by(SupplementRecord.record_date.desc()).limit(limit).all()


@router.put("/records/{record_id}", response_model=SupplementRecordResponse)
def update_supplement_record(
    record_id: int,
    update: SupplementRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新当前用户的一条补剂打卡记录。"""
    record = _get_owned_supplement_record(db, current_user.id, record_id)
    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    _invalidate_twin(current_user.id)
    return record


@router.delete("/records/{record_id}")
def delete_supplement_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除当前用户的一条补剂打卡记录。"""
    record = _get_owned_supplement_record(db, current_user.id, record_id)
    db.delete(record)
    db.commit()
    _invalidate_twin(current_user.id)
    return {"message": "删除成功", "record_id": record_id}


@router.get("/me/frequent", response_model=List[FrequentSupplement])
def get_my_frequent_supplements(
    days: int = Query(default=30, ge=7, le=180),
    limit: int = Query(default=8, ge=1, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前用户最近 N 天最常打卡的补剂, 按 taken 次数倒序 (供一键打卡).

    只统计 taken=True 的打卡记录, 按 supplement_id 聚合; 只返回仍 active 的补剂
    定义 (停用的不再推荐). 同频次按 name 稳定排序.
    """
    start_date = date.today() - timedelta(days=days)
    records = db.query(SupplementRecord).filter(
        SupplementRecord.user_id == current_user.id,
        SupplementRecord.record_date >= start_date,
        SupplementRecord.taken.is_(True),
    ).all()

    counts: dict[int, int] = {}
    for r in records:
        counts[r.supplement_id] = counts.get(r.supplement_id, 0) + 1
    if not counts:
        return []

    # 取仍 active 的补剂定义, 拼上次数
    defs = db.query(SupplementDefinition).filter(
        SupplementDefinition.id.in_(counts.keys()),
        SupplementDefinition.user_id == current_user.id,
        SupplementDefinition.is_active,
    ).all()

    items = [
        FrequentSupplement(
            supplement_id=d.id,
            name=d.name,
            dosage=d.dosage,
            timing=d.timing,
            count=counts.get(d.id, 0),
        )
        for d in defs
    ]
    items.sort(key=lambda s: (-s.count, s.name))
    return items[:limit]


class CopyDayRequest(BaseModel):
    from_date: date
    to_date: date


@router.post("/records/copy-day")
def copy_day_records(
    request: CopyDayRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """复制某天的补剂打卡记录到另一天（实现"补剂同昨天"）"""
    # 获取源日期已服用的记录
    source_records = db.query(SupplementRecord).filter(
        SupplementRecord.user_id == current_user.id,
        SupplementRecord.record_date == request.from_date,
        SupplementRecord.taken
    ).all()

    if not source_records:
        raise HTTPException(status_code=404, detail=f"{request.from_date} 没有补剂服用记录")

    results = []
    for src in source_records:
        # 检查目标日期是否已有记录
        existing = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == current_user.id,
            SupplementRecord.supplement_id == src.supplement_id,
            SupplementRecord.record_date == request.to_date
        ).first()

        if existing:
            existing.taken = True
            results.append({"supplement_id": src.supplement_id, "action": "updated"})
        else:
            record = SupplementRecord(
                supplement_id=src.supplement_id,
                user_id=current_user.id,
                record_date=request.to_date,
                taken=True
            )
            db.add(record)
            results.append({"supplement_id": src.supplement_id, "action": "created"})

    db.commit()
    _invalidate_twin(current_user.id)
    return {
        "message": f"已将 {request.from_date} 的 {len(results)} 条记录复制到 {request.to_date}",
        "copied_count": len(results),
        "results": results
    }


@router.put("/records/{record_id}", response_model=SupplementRecordResponse)
def update_supplement_record(
    record_id: int,
    update_data: SupplementRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新当前用户的单条补剂打卡记录。"""
    record = _get_owned_supplement_record(db, current_user.id, record_id)
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/records/{record_id}")
def delete_supplement_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除当前用户的单条补剂打卡记录。"""
    record = _get_owned_supplement_record(db, current_user.id, record_id)
    db.delete(record)
    db.commit()
    return {"message": "删除成功", "record_id": record_id}


@router.get("/me/date/{record_date}", response_model=List[SupplementWithRecord])
def get_my_supplements_with_records(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户某天的补剂列表及打卡状态（需要登录）"""
    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == current_user.id,
        SupplementDefinition.is_active
    ).order_by(SupplementDefinition.timing, SupplementDefinition.sort_order).all()

    result = []
    for supp in supplements:
        record = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == current_user.id,
            SupplementRecord.supplement_id == supp.id,
            SupplementRecord.record_date == record_date
        ).first()

        result.append(SupplementWithRecord(
            supplement=SupplementDefinitionResponse.model_validate(supp),
            record=SupplementRecordResponse.model_validate(record) if record else None
        ))

    return result


@router.get("/me/stats")
def get_my_supplement_stats(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户补剂统计（需要登录）"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)

    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == current_user.id,
        SupplementDefinition.is_active
    ).all()

    stats = []
    for supp in supplements:
        records = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == current_user.id,
            SupplementRecord.supplement_id == supp.id,
            SupplementRecord.record_date >= start_date,
            SupplementRecord.record_date <= end_date
        ).all()

        taken_count = sum(1 for r in records if r.taken)

        stats.append({
            "supplement_id": supp.id,
            "supplement_name": supp.name,
            "category": supp.category,
            "total_days": days,
            "taken_days": taken_count,
            "completion_rate": round(taken_count / days * 100, 1)
        })

    return stats


# ========== 每日补剂动态指南 ==========

@router.get("/daily-guide")
def get_supplement_daily_guide(
    target_date: Optional[date] = Query(None, description="目标日期，默认今天"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """每日补剂动态指南 — 基于身体状况/运动/鼻炎/天气等生成个性化提醒"""
    try:
        guide = get_daily_supplement_guide(db, current_user.id, target_date)
        return guide
    except Exception as e:
        logger.error(f"[补剂指南] 生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成每日补剂指南失败: {str(e)}")


# ========== 补剂科学推荐 ==========

@router.get("/evidence/catalog", response_model=Dict[str, Any])
def get_evidence_catalog(
    current_user: User = Depends(get_current_user_required),
):
    """获取已审校的补剂证据目录"""
    return {
        "catalog_version": SUPPLEMENT_EVIDENCE_CATALOG_VERSION,
        "items": list_supplement_evidence_catalog(),
    }


@router.get("/evidence/sources", response_model=Dict[str, Any])
def get_evidence_sources(
    current_user: User = Depends(get_current_user_required),
):
    """获取补剂证据来源登记表"""
    return {
        "catalog_version": SUPPLEMENT_EVIDENCE_CATALOG_VERSION,
        "sources": list_supplement_evidence_sources(),
    }


@router.get("/evidence/profile/{name_or_key}", response_model=Dict[str, Any])
def get_evidence_profile(
    name_or_key: str,
    current_user: User = Depends(get_current_user_required),
):
    """按补剂名称、别名或 key 获取证据画像"""
    profile = get_supplement_evidence_profile(name_or_key)
    if not profile:
        raise HTTPException(status_code=404, detail="未找到该补剂的证据画像")
    return {
        "catalog_version": SUPPLEMENT_EVIDENCE_CATALOG_VERSION,
        "profile": profile,
    }


class SupplementRecommendationRequest(BaseModel):
    """补剂推荐请求参数"""
    target_date: Optional[date] = None
    debug: bool = False
    use_llm: bool = True
    force_refresh: bool = False  # 强制刷新，忽略缓存

@router.post("/scientific-recommendation", response_model=Dict[str, Any])
async def get_supplement_recommendation(
    request: SupplementRecommendationRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取补剂科学推荐

    基于益家知研 AI + 皮皮妈妈知识库

    缓存策略：结果缓存24小时，除非用户主动刷新

    Args:
        request: 请求参数（target_date, debug, use_llm, force_refresh）

    Returns:
        补剂科学推荐结果（debug模式下包含决策过程）
    """
    target_date = request.target_date or date.today()
    debug = request.debug
    use_llm = request.use_llm
    force_refresh = request.force_refresh

    date_str = target_date.isoformat()

    logger.info(f"[补剂科学推荐API] 收到请求 - user_id={current_user.id}, target_date={date_str}, debug={debug}, use_llm={use_llm}, force_refresh={force_refresh}")

    try:
        # 检查缓存（非 debug 模式且非强制刷新时使用缓存）
        if not debug and not force_refresh:
            cached = get_cached_supplement_recommendation(current_user.id, date_str)
            if cached:
                logger.info(f"[补剂科学推荐API] 返回缓存结果 - user_id={current_user.id}, date={date_str}")
                cached['from_cache'] = True
                return cached

        if use_llm:
            # 使用 LLM + 知识库推荐
            from app.services.supplement_recommendation_llm import SupplementRecommendationServiceLLM
            service = SupplementRecommendationServiceLLM()
            recommendation = await service.generate_supplement_recommendation(
                db=db,
                user_id=current_user.id,
                target_date=target_date,
                debug=debug
            )
        else:
            # 使用规则推荐
            service = SupplementRecommendationService()
            recommendation = service.generate_supplement_recommendation(
                db=db,
                user_id=current_user.id,
                target_date=target_date,
                debug=debug
            )

        logger.info(f"[补剂科学推荐API] 生成成功 - success={recommendation.get('success')}, use_llm={use_llm}")

        # 转换字段名以匹配前端期望的格式
        health_analysis = recommendation.get('health_analysis', {})
        overall_rating = recommendation.get('overall_rating', {})

        transformed_response = {
            "success": recommendation.get('success', True),
            "generated_at": recommendation.get('generated_at'),
            "target_date": recommendation.get('target_date'),
            # 前端期望 'rating'，后端返回 'overall_rating'
            "rating": {
                "score": overall_rating.get('score', 0),
                "level": overall_rating.get('rating', '评估中'),  # rating -> level
                "emoji": overall_rating.get('emoji', '⭐'),
                "message": overall_rating.get('message', '')
            },
            # 前端期望 'analysis'，后端返回 'health_analysis'
            "analysis": {
                "sleep_quality": health_analysis.get('sleep_quality', '未知'),
                "stress_level": health_analysis.get('stress_level', '未知'),
                "exercise_intensity": health_analysis.get('exercise_intensity', '未知'),
                "nutrition_status": health_analysis.get('nutrition_status', '未知'),
                "key_factors": health_analysis.get('positive_factors', []) + health_analysis.get('risk_factors', [])
            },
            "recommendations": recommendation.get('recommendations', []),
            "timing_suggestions": recommendation.get('timing_suggestions', {}),
            "precautions": recommendation.get('precautions', []),
            "evidence_summary": recommendation.get('evidence_summary', {}),
            "knowledge_evidence": recommendation.get('knowledge_evidence', {}),
        }

        if debug:
            transformed_response["debug_info"] = recommendation.get('debug')

        # 缓存结果（非 debug 模式时）
        if not debug:
            cache_supplement_recommendation(current_user.id, date_str, transformed_response)
            logger.info(f"[补剂科学推荐API] 已缓存结果 - user_id={current_user.id}, date={date_str}")

        transformed_response['from_cache'] = False
        return transformed_response
    except Exception as e:
        logger.error(f"[补剂科学推荐API] 生成失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"生成补剂科学推荐失败: {str(e)}"
        )
