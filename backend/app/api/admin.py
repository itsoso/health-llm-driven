"""管理员API"""
from typing import List, Literal, Optional
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel, ConfigDict

from app.database import get_db
from app.models.user import User, GarminCredential
from app.models.daily_health import GarminData
from app.models.daily_recommendation import DailyRecommendation
from app.models.medical_exam import MedicalExam
from app.models.account_deletion_request import AccountDeletionRequest
from app.models.agent_audit_log import AgentAuditLog
from app.api.auth import get_current_user_required
from app.services.account_deletion import build_deletion_verification_report

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
    is_approved: bool = False  # 是否已通过审核
    invite_code: Optional[str] = None  # 邀请码
    created_at: Optional[datetime]
    last_activity: Optional[datetime]
    has_garmin: bool
    health_records_count: int
    medical_exams_count: int

    model_config = ConfigDict(from_attributes=True)


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


class ApproveUserRequest(BaseModel):
    """审核用户请求"""
    is_approved: bool


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    new_password: str


class ResetPasswordByEmailRequest(BaseModel):
    """通过邮箱重置密码请求"""
    email: str
    new_password: str


class AdminCreateUserRequest(BaseModel):
    """管理员创建用户请求"""
    username: str
    email: str
    password: str
    name: str
    is_approved: bool = True


class AccountDeletionRequestUpdate(BaseModel):
    status: Literal["requested", "processing", "completed", "rejected"]
    note: Optional[str] = None
    data_deletion_verified: bool = False
    verification_reference: Optional[str] = None


# ========== 权限检查 ==========

async def get_admin_user(
    request: Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> User:
    """获取当前管理员用户"""
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        db.add(AgentAuditLog(
            user_id=current_user.id,
            agent_type="security_audit",
            action="privileged_request_authorized",
            result_summary="管理员变更请求已通过权限校验",
            result_detail={
                "method": request.method.upper(),
                "path": request.url.path,
            },
        ))
        db.commit()
    return current_user


# ========== API端点 ==========

def _admin_deletion_request_payload(request: AccountDeletionRequest) -> dict:
    return {
        "request_id": request.id,
        "user_id": request.user_id,
        "status": request.status,
        "channel": request.channel,
        "requested_at": request.requested_at,
        "updated_at": request.updated_at,
        "completed_at": request.completed_at,
        "processing_admin_id": request.processing_admin_id,
        "processing_note": request.processing_note,
        "verification_reference": request.verification_reference,
    }


@router.get("/account-deletion-requests", summary="账号删除请求队列")
async def list_account_deletion_requests(
    request_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    query = db.query(AccountDeletionRequest)
    if request_status:
        query = query.filter(AccountDeletionRequest.status == request_status)
    rows = query.order_by(AccountDeletionRequest.requested_at.asc()).limit(limit).all()
    return {"total": len(rows), "requests": [_admin_deletion_request_payload(row) for row in rows]}


@router.get(
    "/account-deletion-requests/{request_id}/verification-report",
    summary="生成账号删除核验报告",
)
async def get_account_deletion_verification_report(
    request_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Return a redacted, machine-generated purge verification report."""
    request = (
        db.query(AccountDeletionRequest)
        .filter(AccountDeletionRequest.id == request_id)
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="删除请求不存在")
    return {
        "request_id": request.id,
        "user_id": request.user_id,
        "status": request.status,
        "report": build_deletion_verification_report(db, request.user_id),
    }


@router.patch("/account-deletion-requests/{request_id}", summary="更新账号删除请求")
async def update_account_deletion_request(
    request_id: int,
    update: AccountDeletionRequestUpdate,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    request = db.query(AccountDeletionRequest).filter(AccountDeletionRequest.id == request_id).first()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="删除请求不存在")

    allowed = {
        "requested": {"requested", "processing", "completed", "rejected"},
        "processing": {"processing", "completed", "rejected"},
        "completed": {"completed"},
        "rejected": {"rejected"},
    }
    if update.status not in allowed.get(request.status, set()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不允许的状态变更")
    if update.status == "completed" and (
        not update.data_deletion_verified
        or not (update.verification_reference or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="完成删除请求前必须提供数据清除核验结果和核验引用",
        )
    if update.status == "completed":
        verification = build_deletion_verification_report(db, request.user_id)
        if not verification["can_finalize"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "删除核验未通过，请先清理账号、用户数据、私有文件和缓存；"
                    f"scope_digest={verification['scope_digest']}"
                ),
            )

    now = datetime.now(UTC)
    request.status = update.status
    request.processing_admin_id = admin_user.id
    request.processing_note = update.note
    if update.verification_reference:
        request.verification_reference = update.verification_reference.strip()
    request.updated_at = now
    if update.status in {"completed", "rejected"}:
        request.active_user_id = None
        request.completed_at = now

    db.add(AgentAuditLog(
        user_id=request.user_id,
        agent_type="account_privacy",
        action="account_deletion_status_updated",
        result_summary=f"账号删除请求状态更新为 {update.status}",
        result_detail={
            "request_id": request.id,
            "admin_user_id": admin_user.id,
            "status": update.status,
            "note": update.note,
            "data_deletion_verified": update.data_deletion_verified,
            "verification_reference": request.verification_reference,
        },
    ))
    db.commit()
    db.refresh(request)
    return _admin_deletion_request_payload(request)

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
            is_approved=getattr(user, 'is_approved', False) or False,
            invite_code=getattr(user, 'invite_code', None),
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
        is_approved=getattr(user, 'is_approved', False) or False,
        invite_code=getattr(user, 'invite_code', None),
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


@router.put("/users/{user_id}/approve", summary="审核用户")
async def approve_user(
    user_id: int,
    request: ApproveUserRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """审核通过或拒绝用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    user.is_approved = request.is_approved
    db.commit()

    logger.info(f"管理员 {admin_user.name} {'通过' if request.is_approved else '拒绝'}了用户 {user.name} (ID: {user_id}) 的审核")

    return {"message": f"已{'通过' if request.is_approved else '拒绝'}用户{user.name}的审核"}


@router.put("/users/{user_id}/password", summary="重置用户密码")
async def reset_user_password(
    user_id: int,
    request: ResetPasswordRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """重置用户密码（仅管理员）"""
    from app.services.auth import AuthService

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 密码长度验证
    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少6位"
        )

    # 哈希新密码
    hashed_password = AuthService.get_password_hash(request.new_password)
    user.hashed_password = hashed_password
    db.commit()

    logger.info(f"管理员 {admin_user.name} 重置了用户 {user.name} (ID: {user_id}) 的密码")

    return {"message": f"已重置用户 {user.name} 的密码"}


@router.post("/users/reset-password", summary="通过邮箱重置密码")
async def reset_password_by_email(
    request: ResetPasswordByEmailRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """通过邮箱重置用户密码（仅管理员）"""
    from app.services.auth import AuthService

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"邮箱 {request.email} 对应的用户不存在"
        )

    # 密码长度验证
    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少6位"
        )

    # 哈希新密码
    hashed_password = AuthService.get_password_hash(request.new_password)
    user.hashed_password = hashed_password
    db.commit()

    from app.utils.redact import mask_email
    logger.info(f"管理员 {admin_user.name} 通过邮箱重置了用户 {user.name} (email: {mask_email(request.email)}) 的密码")

    return {"message": f"已重置用户 {user.name} ({request.email}) 的密码"}


@router.post("/users/create", summary="管理员创建用户")
async def admin_create_user(
    request: AdminCreateUserRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """管理员直接创建用户（无需邀请码）"""
    from app.services.auth import AuthService

    # 检查用户名和邮箱是否已存在
    existing = db.query(User).filter(
        (User.username == request.username) | (User.email == request.email)
    ).first()
    if existing:
        detail = "用户名已存在" if existing.username == request.username else "邮箱已存在"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if len(request.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码长度至少6位")

    hashed_password = AuthService.get_password_hash(request.password)
    new_user = User(
        username=request.username,
        email=request.email,
        hashed_password=hashed_password,
        name=request.name,
        is_active=True,
        is_approved=request.is_approved,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"管理员 {admin_user.name} 创建了用户 {new_user.name} (ID: {new_user.id})")

    return {"message": f"用户 {new_user.name} 创建成功", "user_id": new_user.id}


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
        days,
        is_cn=credentials.get("is_cn", False)
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
    valid_count = 0
    invalid_count = 0

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

        # 检查凭证是否有效（兼容旧数据，None视为有效）
        credentials_valid = cred.credentials_valid if hasattr(cred, 'credentials_valid') and cred.credentials_valid is not None else True

        if credentials_valid:
            valid_count += 1
        else:
            invalid_count += 1

        # 限流/锁定状态
        login_locked = False
        lock_remaining_minutes = 0
        if hasattr(cred, 'login_locked_until') and cred.login_locked_until:
            from datetime import datetime
            now = datetime.now(UTC)
            locked_until = cred.login_locked_until
            if hasattr(locked_until, 'tzinfo') and locked_until.tzinfo is not None:
                locked_until = locked_until.replace(tzinfo=None)
            if locked_until > now:
                login_locked = True
                lock_remaining_minutes = int((locked_until - now).total_seconds() / 60) + 1

        # Token 缓存状态
        from app.services.data_collection.garmin_native_auth import has_native_token_store

        has_cached_token = has_native_token_store(getattr(cred, 'garth_session', None))
        token_expires_at = cred.session_expires_at.isoformat() if hasattr(cred, 'session_expires_at') and cred.session_expires_at else None

        # 同步锁状态
        sync_in_progress = getattr(cred, 'sync_in_progress', False) or False

        result.append({
            "user_id": cred.user_id,
            "username": user.username if user else None,
            "name": user.name if user else None,
            "garmin_email": cred.garmin_email,
            "sync_enabled": cred.sync_enabled,
            "credentials_valid": credentials_valid,
            "last_error": getattr(cred, 'last_error', None),
            "error_count": getattr(cred, 'error_count', 0) or 0,
            "login_locked": login_locked,
            "lock_remaining_minutes": lock_remaining_minutes,
            "has_cached_token": has_cached_token,
            "token_expires_at": token_expires_at,
            "sync_in_progress": sync_in_progress,
            "last_sync_at": cred.last_sync_at.isoformat() if cred.last_sync_at else None,
            "latest_data_date": latest_data.record_date.isoformat() if latest_data else None,
            "total_records": data_count
        })

    return {
        "total_configured_users": len(credentials),
        "valid_credentials": valid_count,
        "invalid_credentials": invalid_count,
        "users": result
    }


@router.post("/garmin/reset-credentials/{user_id}", summary="重置用户凭证状态")
async def reset_user_credentials(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    重置用户的Garmin凭证状态（标记为有效，清除错误）

    - 仅管理员可访问
    """
    from app.services.auth import garmin_credential_service

    success = garmin_credential_service.reset_credential_status(db, user_id)
    if success:
        return {"message": f"已重置用户 {user_id} 的凭证状态"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户未配置Garmin凭证"
        )


class SetSyncEnabledRequest(BaseModel):
    """设置同步状态请求"""
    sync_enabled: bool


class ClearCacheResponse(BaseModel):
    """清理缓存响应"""
    message: str
    deleted_count: int


@router.delete("/users/{user_id}/cache", response_model=ClearCacheResponse, summary="清理用户缓存")
async def clear_user_cache(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    清理指定用户的缓存数据（每日建议缓存）

    - **user_id**: 用户ID
    - 仅管理员可访问
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 删除用户的每日建议缓存
    deleted_count = db.query(DailyRecommendation).filter(
        DailyRecommendation.user_id == user_id
    ).delete()

    db.commit()

    logger.info(f"管理员 {admin_user.name} 清理了用户 {user_id} 的缓存，删除 {deleted_count} 条记录")

    return ClearCacheResponse(
        message=f"已清理用户 {user.name} 的缓存",
        deleted_count=deleted_count
    )


@router.delete("/cache/all", response_model=ClearCacheResponse, summary="清理所有用户缓存")
async def clear_all_cache(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    清理所有用户的缓存数据（每日建议缓存）

    - 仅管理员可访问
    """
    # 删除所有每日建议缓存
    deleted_count = db.query(DailyRecommendation).delete()
    db.commit()

    logger.info(f"管理员 {admin_user.name} 清理了所有用户缓存，删除 {deleted_count} 条记录")

    return ClearCacheResponse(
        message="已清理所有用户的缓存",
        deleted_count=deleted_count
    )


@router.delete("/cache/no-data", response_model=ClearCacheResponse, summary="清理无数据缓存")
async def clear_no_data_cache(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    清理所有状态为 no_data 的缓存记录

    - 仅管理员可访问
    """
    from sqlalchemy import text

    # 删除状态为 no_data 的记录
    result = db.execute(text(
        "DELETE FROM daily_recommendations WHERE one_day_recommendation LIKE '%\"status\": \"no_data\"%'"
    ))
    deleted_count = result.rowcount
    db.commit()

    logger.info(f"管理员 {admin_user.name} 清理了 no_data 缓存，删除 {deleted_count} 条记录")

    return ClearCacheResponse(
        message="已清理所有无数据缓存",
        deleted_count=deleted_count
    )


@router.put("/garmin/sync-enabled/{user_id}", summary="启用或禁用用户Garmin同步")
async def set_user_sync_enabled(
    user_id: int,
    request: SetSyncEnabledRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    启用或禁用用户的Garmin后台自动同步

    - **user_id**: 用户ID
    - **sync_enabled**: 是否启用同步
    - 禁用后，后台定时任务将不再同步该用户的Garmin数据
    - 仅管理员可访问
    """
    credential = db.query(GarminCredential).filter(
        GarminCredential.user_id == user_id
    ).first()

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该用户未配置Garmin凭证"
        )

    credential.sync_enabled = request.sync_enabled
    db.commit()

    action = "启用" if request.sync_enabled else "禁用"
    logger.info(f"管理员 {admin_user.name} {action}了用户 {user_id} 的Garmin同步")

    return {
        "message": f"已{action}用户 {user_id} 的Garmin同步",
        "user_id": user_id,
        "sync_enabled": request.sync_enabled
    }


# ========== 用户合并（管理员） ==========

class AdminMergeRequest(BaseModel):
    """管理员合并用户请求"""
    source_user_id: int  # 被合并的用户ID（将被删除）
    target_user_id: int  # 目标用户ID（保留）


@router.post("/users/merge", summary="合并两个用户（管理员）")
async def admin_merge_users(
    request: AdminMergeRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    管理员合并两个用户账号

    - source_user 的所有数据迁移到 target_user
    - source_user 被删除
    - target_user 继承两个账号的微信/Web登录能力
    """
    from app.services.user_merge import UserMergeService

    source = db.query(User).filter(User.id == request.source_user_id).first()
    target = db.query(User).filter(User.id == request.target_user_id).first()

    if not source or not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if source.id == target.id:
        raise HTTPException(status_code=400, detail="不能合并同一个用户")

    logger.info(
        f"管理员 {admin_user.name} 发起合并: "
        f"source={source.id}({source.name}) -> target={target.id}({target.name})"
    )

    try:
        result = UserMergeService.merge_users(
            db=db,
            source_user_id=request.source_user_id,
            target_user_id=request.target_user_id
        )
        return {
            "message": f"合并成功: {source.name}(ID:{source.id}) -> {target.name}(ID:{target.id})",
            **result
        }
    except Exception as e:
        logger.error(f"管理员合并用户失败: {e}")
        raise HTTPException(status_code=500, detail=f"合并失败: {str(e)}")
