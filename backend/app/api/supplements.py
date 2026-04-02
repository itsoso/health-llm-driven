"""补剂管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
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
    SupplementRecordResponse,
    SupplementBatchCheckin,
    SupplementWithRecord
)
from app.services.supplement_recommendation import SupplementRecommendationService
from app.utils.redis_cache import (
    cache_supplement_recommendation,
    get_cached_supplement_recommendation,
    invalidate_supplement_recommendation
)
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
        query = query.filter(SupplementDefinition.is_active == True)
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
        SupplementRecord.taken == True
    ).all()

    if not source_records:
        raise HTTPException(status_code=404, detail=f"{request.from_date} 没有补剂服用记录")

    results = []
    for src in source_records:
        # 检查目标日期是否已有记录
        existing = db.query(SupplementRecord).filter(
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
    return {
        "message": f"已将 {request.from_date} 的 {len(results)} 条记录复制到 {request.to_date}",
        "copied_count": len(results),
        "results": results
    }


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
            "precautions": recommendation.get('precautions', [])
        }

        # 为每个推荐项附加匹配的联盟产品
        try:
            from app.services.product_matching import find_products, get_user_gene_tags
            gene_tags = get_user_gene_tags(db, current_user.id)
            for rec in transformed_response.get("recommendations", []):
                rec_name = rec.get("name", "")
                rec_category = rec.get("category", "")
                if rec_name:
                    rec["products"] = find_products(db, rec_name, rec_category, gene_tags, limit=3)
        except Exception as e:
            logger.warning(f"[补剂推荐] 产品匹配失败: {e}")

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

