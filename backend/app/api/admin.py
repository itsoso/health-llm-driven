"""管理员API"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User, GarminCredential
from app.models.daily_health import GarminData
from app.models.medical_exam import MedicalExam
from app.api.auth import get_current_user_required

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== 响应模型 ==========

class AdminUserResponse(BaseModel):
    """管理员视角的用户信息"""
    id: int
    username: Optional[str]
    email: Optional[str]
    name: str
    gender: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime]
    last_activity: Optional[datetime]
    has_garmin: bool
    health_records_count: int
    medical_exams_count: int

    class Config:
        from_attributes = True


class AdminStatsResponse(BaseModel):
    """管理后台统计数据"""
    total_users: int
    active_users: int
    admin_users: int
    users_with_garmin: int
    total_health_records: int
    total_medical_exams: int
    new_users_today: int
    new_users_week: int


class UserListResponse(BaseModel):
    """用户列表响应"""
    users: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


class SetAdminRequest(BaseModel):
    """设置管理员请求"""
    is_admin: bool


class SetActiveRequest(BaseModel):
    """设置用户状态请求"""
    is_active: bool


# ========== 权限检查 ==========

async def get_admin_user(
    current_user: User = Depends(get_current_user_required)
) -> User:
    """获取当前管理员用户"""
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user


# ========== API端点 ==========

@router.get("/stats", response_model=AdminStatsResponse, summary="获取统计数据")
async def get_admin_stats(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """获取管理后台统计数据"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today_start - timedelta(days=7)
    
    # 统计用户数据
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0
    admin_users = db.query(func.count(User.id)).filter(User.is_admin == True).scalar() or 0
    users_with_garmin = db.query(func.count(GarminCredential.id)).scalar() or 0
    
    # 统计记录数据
    total_health_records = db.query(func.count(GarminData.id)).scalar() or 0
    total_medical_exams = db.query(func.count(MedicalExam.id)).scalar() or 0
    
    # 新增用户
    new_users_today = db.query(func.count(User.id)).filter(
        User.created_at >= today_start
    ).scalar() or 0
    new_users_week = db.query(func.count(User.id)).filter(
        User.created_at >= week_ago
    ).scalar() or 0
    
    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        admin_users=admin_users,
        users_with_garmin=users_with_garmin,
        total_health_records=total_health_records,
        total_medical_exams=total_medical_exams,
        new_users_today=new_users_today,
        new_users_week=new_users_week
    )


@router.get("/users", response_model=UserListResponse, summary="获取用户列表")
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """获取所有用户列表"""
    query = db.query(User)
    
    # 搜索过滤
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (User.username.ilike(search_pattern)) |
            (User.email.ilike(search_pattern)) |
            (User.name.ilike(search_pattern))
        )
    
    # 总数
    total = query.count()
    
    # 分页
    offset = (page - 1) * page_size
    users = query.order_by(desc(User.created_at)).offset(offset).limit(page_size).all()
    
    # 构建响应
    user_responses = []
    for user in users:
        # 获取相关统计
        has_garmin = db.query(GarminCredential).filter(
            GarminCredential.user_id == user.id
        ).first() is not None
        
        health_records_count = db.query(func.count(GarminData.id)).filter(
            GarminData.user_id == user.id
        ).scalar() or 0
        
        medical_exams_count = db.query(func.count(MedicalExam.id)).filter(
            MedicalExam.user_id == user.id
        ).scalar() or 0
        
        # 最后活动时间（取最近的健康记录日期）
        last_health = db.query(GarminData.record_date).filter(
            GarminData.user_id == user.id
        ).order_by(desc(GarminData.record_date)).first()
        last_activity = datetime.combine(last_health[0], datetime.min.time()) if last_health else None
        
        user_responses.append(AdminUserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            name=user.name,
            gender=user.gender,
            is_active=user.is_active if user.is_active is not None else True,
            is_admin=getattr(user, 'is_admin', False) or False,
            created_at=user.created_at,
            last_activity=last_activity,
            has_garmin=has_garmin,
            health_records_count=health_records_count,
            medical_exams_count=medical_exams_count
        ))
    
    return UserListResponse(
        users=user_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/users/{user_id}", response_model=AdminUserResponse, summary="获取用户详情")
async def get_user_detail(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """获取指定用户详情"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 获取统计信息
    has_garmin = db.query(GarminCredential).filter(
        GarminCredential.user_id == user.id
    ).first() is not None
    
    health_records_count = db.query(func.count(GarminData.id)).filter(
        GarminData.user_id == user.id
    ).scalar() or 0
    
    medical_exams_count = db.query(func.count(MedicalExam.id)).filter(
        MedicalExam.user_id == user.id
    ).scalar() or 0
    
    last_health = db.query(GarminData.record_date).filter(
        GarminData.user_id == user.id
    ).order_by(desc(GarminData.record_date)).first()
    last_activity = datetime.combine(last_health[0], datetime.min.time()) if last_health else None
    
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        gender=user.gender,
        is_active=user.is_active if user.is_active is not None else True,
        is_admin=getattr(user, 'is_admin', False) or False,
        created_at=user.created_at,
        last_activity=last_activity,
        has_garmin=has_garmin,
        health_records_count=health_records_count,
        medical_exams_count=medical_exams_count
    )


@router.put("/users/{user_id}/admin", summary="设置管理员权限")
async def set_user_admin(
    user_id: int,
    request: SetAdminRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """设置或取消用户的管理员权限"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不能取消自己的管理员权限
    if user.id == admin_user.id and not request.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能取消自己的管理员权限"
        )
    
    user.is_admin = request.is_admin
    db.commit()
    
    return {"message": f"已{'设置' if request.is_admin else '取消'}{user.name}的管理员权限"}


@router.put("/users/{user_id}/active", summary="设置用户状态")
async def set_user_active(
    user_id: int,
    request: SetActiveRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """启用或禁用用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不能禁用自己
    if user.id == admin_user.id and not request.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用自己的账户"
        )
    
    user.is_active = request.is_active
    db.commit()
    
    return {"message": f"已{'启用' if request.is_active else '禁用'}用户{user.name}"}


@router.delete("/users/{user_id}", summary="删除用户")
async def delete_user(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """删除用户及其所有数据"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不能删除自己
    if user.id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己的账户"
        )
    
    # 删除关联数据
    db.query(GarminCredential).filter(GarminCredential.user_id == user_id).delete()
    db.query(GarminData).filter(GarminData.user_id == user_id).delete()
    db.query(MedicalExam).filter(MedicalExam.user_id == user_id).delete()
    
    # 删除用户
    db.delete(user)
    db.commit()
    
    return {"message": f"已删除用户{user.name}及其所有数据"}


# ========== Garmin同步管理 ==========

class SyncAllUsersResponse(BaseModel):
    """全部用户同步响应"""
    total_users: int
    success_users: int
    failed_users: int
    details: list


class SyncUserResponse(BaseModel):
    """单用户同步响应"""
    user_id: int
    success: bool
    success_count: int
    error_count: int
    message: str


@router.post("/garmin/sync-all", response_model=SyncAllUsersResponse, summary="同步所有用户的Garmin数据")
async def sync_all_users_garmin(
    days: int = Query(default=3, ge=1, le=30, description="同步最近N天的数据"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    触发所有启用同步的用户的Garmin数据同步
    
    - **days**: 同步最近N天的数据（默认3天，最多30天）
    - 仅管理员可访问
    """
    from app.scheduler import sync_all_users_garmin_task
    
    logger.info(f"管理员 {admin_user.name} 触发全部用户Garmin同步，天数: {days}")
    
    # 执行同步任务
    result = await sync_all_users_garmin_task(days=days)
    
    return SyncAllUsersResponse(**result)


@router.post("/garmin/sync-user/{user_id}", response_model=SyncUserResponse, summary="同步指定用户的Garmin数据")
async def sync_user_garmin(
    user_id: int,
    days: int = Query(default=7, ge=1, le=365, description="同步最近N天的数据"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    触发指定用户的Garmin数据同步
    
    - **user_id**: 用户ID
    - **days**: 同步最近N天的数据（默认7天）
    - 仅管理员可访问
    """
    from app.scheduler import sync_user_garmin_data
    from app.services.auth import garmin_credential_service
    
    # 检查用户是否存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 获取用户的Garmin凭证
    credentials = garmin_credential_service.get_decrypted_credentials(db, user_id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该用户未配置Garmin凭证"
        )
    
    logger.info(f"管理员 {admin_user.name} 触发用户 {user_id} 的Garmin同步，天数: {days}")
    
    # 执行同步
    result = await sync_user_garmin_data(
        db,
        user_id,
        credentials["email"],
        credentials["password"],
        days
    )
    
    return SyncUserResponse(**result)


@router.get("/garmin/sync-status", summary="获取所有用户的Garmin同步状态")
async def get_all_users_sync_status(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取所有配置了Garmin的用户的同步状态
    
    - 仅管理员可访问
    """
    credentials = db.query(GarminCredential).all()
    
    result = []
    for cred in credentials:
        user = db.query(User).filter(User.id == cred.user_id).first()
        
        # 获取最新的Garmin数据日期
        latest_data = db.query(GarminData).filter(
            GarminData.user_id == cred.user_id
        ).order_by(desc(GarminData.record_date)).first()
        
        # 统计该用户的数据量
        data_count = db.query(func.count(GarminData.id)).filter(
            GarminData.user_id == cred.user_id
        ).scalar()
        
        result.append({
            "user_id": cred.user_id,
            "username": user.username if user else None,
            "name": user.name if user else None,
            "garmin_email": cred.garmin_email,
            "sync_enabled": cred.sync_enabled,
            "last_sync_at": cred.last_sync_at.isoformat() if cred.last_sync_at else None,
            "latest_data_date": latest_data.record_date.isoformat() if latest_data else None,
            "total_records": data_count
        })
    
    return {
        "total_configured_users": len(credentials),
        "users": result
    }

