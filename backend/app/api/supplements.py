"""补剂管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict, Any
from datetime import date, timedelta
from app.database import get_db
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.supplement import (
    SupplementDefinitionCreate,
    SupplementDefinitionUpdate,
    SupplementDefinitionResponse,
    SupplementRecordCreate,
    SupplementRecordResponse,
    SupplementBatchCheckin,
    SupplementWithRecord
)
from app.services.supplement_recommendation import SupplementRecommendationService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


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
    return db_supplement


@router.get("/definitions/user/{user_id}", response_model=List[SupplementDefinitionResponse])
def get_user_supplements(
    user_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """获取用户的补剂列表"""
    query = db.query(SupplementDefinition).filter(SupplementDefinition.user_id == user_id)
    if active_only:
        query = query.filter(SupplementDefinition.is_active == True)
    return query.order_by(SupplementDefinition.sort_order, SupplementDefinition.id).all()


@router.put("/definitions/{supplement_id}", response_model=SupplementDefinitionResponse)
def update_supplement(
    supplement_id: int,
    update_data: SupplementDefinitionUpdate,
    db: Session = Depends(get_db)
):
    """更新补剂"""
    supplement = db.query(SupplementDefinition).filter(SupplementDefinition.id == supplement_id).first()
    if not supplement:
        raise HTTPException(status_code=404, detail="补剂不存在")
    
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(supplement, key, value)
    
    db.commit()
    db.refresh(supplement)
    return supplement


@router.delete("/definitions/{supplement_id}")
def delete_supplement(
    supplement_id: int,
    db: Session = Depends(get_db)
):
    """删除补剂"""
    supplement = db.query(SupplementDefinition).filter(SupplementDefinition.id == supplement_id).first()
    if not supplement:
        raise HTTPException(status_code=404, detail="补剂不存在")
    
    db.delete(supplement)
    db.commit()
    return {"message": "删除成功"}


# ========== 补剂打卡 ==========

@router.post("/records", response_model=SupplementRecordResponse)
def create_supplement_record(
    record: SupplementRecordCreate,
    db: Session = Depends(get_db)
):
    """创建/更新补剂打卡记录"""
    # 检查是否已存在记录
    existing = db.query(SupplementRecord).filter(
        SupplementRecord.supplement_id == record.supplement_id,
        SupplementRecord.record_date == record.record_date
    ).first()
    
    if existing:
        existing.taken = record.taken
        existing.taken_time = record.taken_time
        existing.notes = record.notes
        db.commit()
        db.refresh(existing)
        return existing
    
    db_record = SupplementRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
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
        
        existing = db.query(SupplementRecord).filter(
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
    return {"message": "批量打卡成功", "results": results}


@router.get("/records/user/{user_id}/date/{record_date}", response_model=List[SupplementWithRecord])
def get_user_supplements_with_records(
    user_id: int,
    record_date: date,
    db: Session = Depends(get_db)
):
    """获取用户某天的补剂列表及打卡状态"""
    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.is_active == True
    ).order_by(SupplementDefinition.timing, SupplementDefinition.sort_order).all()
    
    result = []
    for supp in supplements:
        record = db.query(SupplementRecord).filter(
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
    db: Session = Depends(get_db)
):
    """获取补剂统计"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == user_id,
        SupplementDefinition.is_active == True
    ).all()
    
    stats = []
    for supp in supplements:
        records = db.query(SupplementRecord).filter(
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

@router.get("/me/date/{record_date}", response_model=List[SupplementWithRecord])
def get_my_supplements_with_records(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户某天的补剂列表及打卡状态（需要登录）"""
    supplements = db.query(SupplementDefinition).filter(
        SupplementDefinition.user_id == current_user.id,
        SupplementDefinition.is_active == True
    ).order_by(SupplementDefinition.timing, SupplementDefinition.sort_order).all()
    
    result = []
    for supp in supplements:
        record = db.query(SupplementRecord).filter(
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
        SupplementDefinition.is_active == True
    ).all()
    
    stats = []
    for supp in supplements:
        records = db.query(SupplementRecord).filter(
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


# ========== 补剂科学推荐 ==========

@router.post("/scientific-recommendation", response_model=Dict[str, Any])
async def get_supplement_recommendation(
    target_date: Optional[date] = None,
    debug: bool = Query(default=False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取补剂科学推荐
    
    Args:
        target_date: 目标日期（可选，默认今天）
        debug: 是否返回调试信息，展示AI决策过程（默认False）
    
    Returns:
        补剂科学推荐结果（debug模式下包含决策过程）
    """
    logger.info(f"[补剂科学推荐API] 收到请求 - user_id={current_user.id}, target_date={target_date}, debug={debug}")
    
    try:
        service = SupplementRecommendationService()
        recommendation = service.generate_supplement_recommendation(
            db=db,
            user_id=current_user.id,
            target_date=target_date,
            debug=debug
        )
        
        logger.info(f"[补剂科学推荐API] 生成成功 - success={recommendation.get('success')}")
        return recommendation
    except Exception as e:
        logger.error(f"[补剂科学推荐API] 生成失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"生成补剂科学推荐失败: {str(e)}"
        )

