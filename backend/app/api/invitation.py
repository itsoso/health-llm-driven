"""邀请码和用户申请管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import json

from app.database import get_db
from app.models.invitation import InvitationCode, UserApplication, ApplicationStatus
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.notification import NotificationLog
from app.api.users import get_current_user_required
from app.services.auth import AuthService
from app.config import settings

router = APIRouter(prefix="/invitation", tags=["邀请码管理"])


def _require_legacy_registration_open() -> None:
    if settings.registration_invitation_enforcement_enabled:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "REGISTRATION_INVITATION_REQUIRED",
                "message": "新用户需要管理员发送的手机号注册邀请",
            },
        )


def _pending_wechat_user_filters():
    """Single SQL definition of a reviewable pending WeChat account."""

    return (
        User.wechat_openid.is_not(None),
        User.is_approved.is_(False),
        User.is_active.is_(True),
    )


# ==================== Pydantic 模型 ====================

class InvitationCodeCreate(BaseModel):
    """创建邀请码请求"""
    note: Optional[str] = None  # 备注
    max_uses: int = 1  # 最大使用次数
    expires_days: Optional[int] = None  # 几天后过期，None表示永不过期


class InvitationCodeResponse(BaseModel):
    """邀请码响应"""
    id: int
    code: str
    note: Optional[str]
    max_uses: int
    used_count: int
    remaining_uses: int
    is_active: bool
    is_valid: bool
    expires_at: Optional[datetime]
    created_at: datetime
    creator_name: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class InvitationCodeVerify(BaseModel):
    """验证邀请码请求"""
    code: str


class InvitationCodeVerifyResponse(BaseModel):
    """验证邀请码响应"""
    valid: bool
    message: str
    remaining_uses: Optional[int] = None


class HealthQuestionnaire(BaseModel):
    """健康问卷"""
    age: Optional[int] = None
    gender: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    health_goals: Optional[List[str]] = []
    chronic_conditions: Optional[List[str]] = []
    wearable_devices: Optional[List[str]] = []
    exercise_frequency: Optional[str] = None
    why_join: Optional[str] = None


class UserApplicationCreate(BaseModel):
    """用户注册申请"""
    email: EmailStr
    name: str
    phone: Optional[str] = None
    invitation_code: str
    password: str
    health_questionnaire: Optional[HealthQuestionnaire] = None


class UserApplicationResponse(BaseModel):
    """用户申请响应"""
    id: int
    email: str
    name: str
    phone: Optional[str]
    status: str
    health_questionnaire: Optional[dict]
    review_note: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]
    reviewer_name: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ApplicationReview(BaseModel):
    """审批申请"""
    approved: bool
    note: Optional[str] = None


# ==================== 邀请码 API ====================

@router.post("/codes", response_model=InvitationCodeResponse, summary="创建邀请码")
async def create_invitation_code(
    data: InvitationCodeCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    创建新的邀请码（仅管理员可操作）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以创建邀请码")

    # 生成唯一邀请码
    code = InvitationCode.generate_code()
    while db.query(InvitationCode).filter(InvitationCode.code == code).first():
        code = InvitationCode.generate_code()

    # 计算过期时间
    expires_at = None
    if data.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)

    invitation = InvitationCode(
        code=code,
        created_by=current_user.id,
        note=data.note,
        max_uses=data.max_uses,
        expires_at=expires_at,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return InvitationCodeResponse(
        id=invitation.id,
        code=invitation.code,
        note=invitation.note,
        max_uses=invitation.max_uses,
        used_count=invitation.used_count,
        remaining_uses=invitation.remaining_uses,
        is_active=invitation.is_active,
        is_valid=invitation.is_valid,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        creator_name=current_user.name
    )


@router.get("/codes", response_model=List[InvitationCodeResponse], summary="获取邀请码列表")
async def list_invitation_codes(
    active_only: bool = Query(False, description="只显示有效的邀请码"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取邀请码列表（仅管理员可操作）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以查看邀请码")

    # N+1 修复: joinedload(creator) 把 creator 一并取出, 避免每个邀请码触发懒加载
    query = (
        db.query(InvitationCode)
        .options(joinedload(InvitationCode.creator))
        .order_by(InvitationCode.created_at.desc())
    )

    if active_only:
        query = query.filter(InvitationCode.is_active.is_(True))

    invitations = query.all()

    result = []
    for inv in invitations:
        creator_name = None
        if inv.creator:
            creator_name = inv.creator.name

        result.append(InvitationCodeResponse(
            id=inv.id,
            code=inv.code,
            note=inv.note,
            max_uses=inv.max_uses,
            used_count=inv.used_count,
            remaining_uses=inv.remaining_uses,
            is_active=inv.is_active,
            is_valid=inv.is_valid,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            creator_name=creator_name
        ))

    return result


@router.post("/codes/verify", response_model=InvitationCodeVerifyResponse, summary="验证邀请码")
async def verify_invitation_code(
    data: InvitationCodeVerify,
    db: Session = Depends(get_db)
):
    """
    验证邀请码是否有效（公开接口，注册前调用）
    """
    invitation = db.query(InvitationCode).filter(
        InvitationCode.code == data.code.upper()
    ).first()

    if not invitation:
        return InvitationCodeVerifyResponse(
            valid=False,
            message="邀请码不存在"
        )

    if not invitation.is_active:
        return InvitationCodeVerifyResponse(
            valid=False,
            message="邀请码已被禁用"
        )

    if invitation.used_count >= invitation.max_uses:
        return InvitationCodeVerifyResponse(
            valid=False,
            message="邀请码已达到使用上限"
        )

    if invitation.expires_at and datetime.now(timezone.utc) > invitation.expires_at:
        return InvitationCodeVerifyResponse(
            valid=False,
            message="邀请码已过期"
        )

    return InvitationCodeVerifyResponse(
        valid=True,
        message="邀请码有效",
        remaining_uses=invitation.remaining_uses
    )


@router.delete("/codes/{code_id}", summary="禁用邀请码")
async def disable_invitation_code(
    code_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    禁用邀请码（仅管理员可操作）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以禁用邀请码")

    invitation = db.query(InvitationCode).filter(InvitationCode.id == code_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    invitation.is_active = False
    db.commit()

    return {"message": "邀请码已禁用"}


# ==================== 用户申请 API ====================

@router.post("/apply", response_model=UserApplicationResponse, summary="提交注册申请")
async def submit_application(
    data: UserApplicationCreate,
    db: Session = Depends(get_db)
):
    """
    提交用户注册申请（公开接口）

    流程：
    1. 验证邀请码
    2. 检查邮箱是否已注册或已申请
    3. 创建申请记录
    4. 等待管理员审批
    """
    _require_legacy_registration_open()
    # 1. 验证邀请码
    invitation = db.query(InvitationCode).filter(
        InvitationCode.code == data.invitation_code.upper()
    ).first()

    if not invitation or not invitation.is_valid:
        raise HTTPException(status_code=400, detail="邀请码无效或已过期")

    # 2. 检查邮箱是否已注册
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    # 检查是否有待审批的申请
    existing_app = db.query(UserApplication).filter(
        UserApplication.email == data.email,
        UserApplication.status == ApplicationStatus.PENDING.value
    ).first()
    if existing_app:
        raise HTTPException(status_code=400, detail="该邮箱已有待审批的申请")

    # 3. 创建申请记录
    questionnaire_json = None
    if data.health_questionnaire:
        questionnaire_json = json.dumps(data.health_questionnaire.model_dump(), ensure_ascii=False)

    # 加密用户密码
    hashed_password = AuthService.get_password_hash(data.password)

    application = UserApplication(
        email=data.email,
        name=data.name,
        phone=data.phone,
        hashed_password=hashed_password,  # 保存加密后的密码
        invitation_code_id=invitation.id,
        health_questionnaire=questionnaire_json,
    )

    db.add(application)

    # 原子递增邀请码使用次数（防止并发超额）
    from sqlalchemy import and_
    updated = db.query(InvitationCode).filter(
        and_(
            InvitationCode.id == invitation.id,
            InvitationCode.used_count < InvitationCode.max_uses
        )
    ).update(
        {InvitationCode.used_count: InvitationCode.used_count + 1},
        synchronize_session=False
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="邀请码已达到使用上限")

    # 邀请码已验证有效，自动创建用户账号并审核通过
    new_user = User(
        email=data.email,
        name=data.name,
        phone=data.phone,
        hashed_password=hashed_password,
        is_active=True,
        is_approved=True,
        invite_code=data.invitation_code.upper(),
    )
    db.add(new_user)
    db.flush()  # 获取 user id

    application.status = ApplicationStatus.APPROVED.value
    application.user_id = new_user.id
    application.reviewed_at = datetime.now(timezone.utc)
    application.review_note = "邀请码有效，自动审核通过"

    # 同步健康问卷数据到 UserProfile
    if data.health_questionnaire:
        q = data.health_questionnaire
        from datetime import date as date_type
        birth_date = None
        if q.age:
            # 根据年龄推算大致出生日期
            today = date_type.today()
            birth_date = today.replace(year=today.year - q.age)

        profile = UserProfile(
            user_id=new_user.id,
            gender=q.gender,
            birth_date=birth_date,
            height_cm=q.height_cm,
            current_weight_kg=q.weight_kg,
            chronic_conditions=q.chronic_conditions or [],
            devices=q.wearable_devices or [],
            exercise_frequency=q.exercise_frequency,
        )
        db.add(profile)

        # 同步 gender 到 User 表
        if q.gender:
            new_user.gender = q.gender

    db.commit()
    db.refresh(application)

    return UserApplicationResponse(
        id=application.id,
        email=application.email,
        name=application.name,
        phone=application.phone,
        status=application.status,
        health_questionnaire=json.loads(application.health_questionnaire) if application.health_questionnaire else None,
        review_note=application.review_note,
        created_at=application.created_at,
        reviewed_at=application.reviewed_at,
        reviewer_name=None
    )


@router.get("/applications", response_model=List[UserApplicationResponse], summary="获取申请列表")
async def list_applications(
    status: Optional[str] = Query(None, description="筛选状态: pending/approved/rejected"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取用户申请列表（仅管理员可操作）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以查看申请列表")

    query = db.query(UserApplication).order_by(UserApplication.created_at.desc())

    if status:
        query = query.filter(UserApplication.status == status)

    applications = query.all()

    result = []
    for app in applications:
        reviewer_name = None
        if app.reviewer:
            reviewer_name = app.reviewer.name

        result.append(UserApplicationResponse(
            id=app.id,
            email=app.email,
            name=app.name,
            phone=app.phone,
            status=app.status,
            health_questionnaire=json.loads(app.health_questionnaire) if app.health_questionnaire else None,
            review_note=app.review_note,
            created_at=app.created_at,
            reviewed_at=app.reviewed_at,
            reviewer_name=reviewer_name
        ))

    # 如果查询 pending 状态，也包含 User 表中未审核的微信用户
    if status == "pending" or status is None:
        pending_users = db.query(User).filter(
            *_pending_wechat_user_filters(),
        ).order_by(User.created_at.desc()).all()

        for user in pending_users:
            # 检查是否已经在 UserApplication 中
            existing = db.query(UserApplication).filter(
                UserApplication.user_id == user.id
            ).first()
            if not existing:
                # 创建虚拟的申请记录用于显示
                result.append(UserApplicationResponse(
                    id=user.id * -1,  # 使用负数ID区分
                    email=f"wechat_{user.wechat_openid[-6:] if user.wechat_openid else 'unknown'}@wechat.user",
                    name=user.name or "微信用户",
                    phone=None,
                    status="pending",
                    health_questionnaire=None,
                    review_note=f"微信用户，邀请码: {user.invite_code or '无'}",
                    created_at=user.created_at,
                    reviewed_at=None,
                    reviewer_name=None
                ))

    return result


@router.get("/applications/{app_id}", response_model=UserApplicationResponse, summary="获取申请详情")
async def get_application(
    app_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取申请详情（仅管理员可操作）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以查看申请详情")

    application = db.query(UserApplication).filter(UserApplication.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="申请不存在")

    reviewer_name = None
    if application.reviewer:
        reviewer_name = application.reviewer.name

    return UserApplicationResponse(
        id=application.id,
        email=application.email,
        name=application.name,
        phone=application.phone,
        status=application.status,
        health_questionnaire=json.loads(application.health_questionnaire) if application.health_questionnaire else None,
        review_note=application.review_note,
        created_at=application.created_at,
        reviewed_at=application.reviewed_at,
        reviewer_name=reviewer_name
    )


@router.post("/applications/{app_id}/review", summary="审批申请")
async def review_application(
    app_id: int,
    review: ApplicationReview,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    审批用户申请（仅管理员可操作）

    如果通过：
    1. 创建用户账号（或审核微信用户）
    2. 更新申请状态
    3. 记录站内通知
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以审批申请")

    # Approval changes account admission in both branches. Gate it before the
    # negative-id WeChat compatibility branch so no legacy approval can bypass
    # invitation enforcement. Rejection remains available for cleanup.
    if review.approved:
        _require_legacy_registration_open()

    # 处理微信用户审核（负数ID）
    if app_id < 0:
        user_id = abs(app_id)
        user = db.query(User).filter(
            User.id == user_id,
            *_pending_wechat_user_filters(),
        ).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        if user.is_approved:
            raise HTTPException(status_code=400, detail="该用户已被审核")

        if review.approved:
            user.is_approved = True
            db.commit()
            return {
                "message": "微信用户审核已通过",
                "user_id": user.id,
                "name": user.name
            }
        else:
            # 拒绝：可以选择删除用户或标记
            user.is_active = False
            db.commit()
            return {
                "message": "微信用户申请已拒绝",
                "reason": review.note
            }

    # 处理普通申请
    application = db.query(UserApplication).filter(UserApplication.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="申请不存在")

    if application.status != ApplicationStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="该申请已被处理")

    # 更新审批信息
    application.reviewed_by = current_user.id
    application.reviewed_at = datetime.now(timezone.utc)
    application.review_note = review.note

    if review.approved:
        # 创建用户账号，使用申请时保存的密码
        new_user = User(
            email=application.email,
            name=application.name,
            phone=application.phone,
            hashed_password=application.hashed_password,  # 使用申请时保存的密码
            is_active=True,
            is_approved=True,
            invite_code=application.invitation.code,
        )

        db.add(new_user)
        db.flush()  # 获取 user id

        application.status = ApplicationStatus.APPROVED.value
        application.user_id = new_user.id

        db.commit()

        # 记录站内通知：申请已通过
        _log_application_notification(
            db, new_user.id, "申请已通过",
            "您的注册申请已通过审核，欢迎使用健康管理平台！"
        )

        return {
            "message": "申请已通过，用户账号已创建",
            "user_id": new_user.id,
            "email": new_user.email
        }
    else:
        application.status = ApplicationStatus.REJECTED.value
        db.commit()

        # 记录站内通知：申请已拒绝（如果有关联邮箱，通知信息存入日志供后续查看）
        reason_text = f"原因：{review.note}" if review.note else ""
        _log_application_notification(
            db, None, "申请未通过",
            f"您的注册申请未通过审核。{reason_text}",
            data={"application_id": app_id, "email": application.email},
        )

        return {
            "message": "申请已拒绝",
            "reason": review.note
        }


def _log_application_notification(
    db: Session,
    user_id: int | None,
    title: str,
    content: str,
    data: dict | None = None,
):
    """向 notification_logs 表插入一条站内通知记录"""
    try:
        log = NotificationLog(
            user_id=user_id or 0,
            notification_type="application_review",
            channel="in_app",
            title=title,
            content=content,
            data=data,
            status="sent",
            sent_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()  # 通知记录失败不应影响主流程


@router.get("/applications/check/{email}", summary="检查申请状态")
async def check_application_status(
    email: str,
    db: Session = Depends(get_db)
):
    """
    检查邮箱的申请状态（公开接口，用于用户查询自己的申请进度）
    """
    application = db.query(UserApplication).filter(
        UserApplication.email == email
    ).order_by(UserApplication.created_at.desc()).first()

    if not application:
        return {
            "found": False,
            "message": "未找到相关申请记录"
        }

    status_messages = {
        ApplicationStatus.PENDING.value: "您的申请正在审核中，请耐心等待",
        ApplicationStatus.APPROVED.value: "您的申请已通过，请使用邮箱登录",
        ApplicationStatus.REJECTED.value: f"您的申请未通过，原因：{application.review_note or '未说明'}"
    }

    return {
        "found": True,
        "status": application.status,
        "message": status_messages.get(application.status, "未知状态"),
        "applied_at": application.created_at,
        "reviewed_at": application.reviewed_at
    }


# ==================== 统计 API ====================

@router.get("/stats", summary="获取邀请统计")
async def get_invitation_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取邀请码和申请统计（仅管理员可操作）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以查看统计")

    # 邀请码统计
    total_codes = db.query(func.count(InvitationCode.id)).scalar()
    active_codes = db.query(func.count(InvitationCode.id)).filter(
        InvitationCode.is_active.is_(True)
    ).scalar()
    total_uses = db.query(func.sum(InvitationCode.used_count)).scalar() or 0

    # 申请统计
    total_applications = db.query(func.count(UserApplication.id)).scalar()
    pending_applications = db.query(func.count(UserApplication.id)).filter(
        UserApplication.status == ApplicationStatus.PENDING.value
    ).scalar()
    approved_applications = db.query(func.count(UserApplication.id)).filter(
        UserApplication.status == ApplicationStatus.APPROVED.value
    ).scalar()
    rejected_applications = db.query(func.count(UserApplication.id)).filter(
        UserApplication.status == ApplicationStatus.REJECTED.value
    ).scalar()

    # 统计未审核的微信用户
    pending_wechat_users = db.query(func.count(User.id)).filter(
        *_pending_wechat_user_filters(),
    ).scalar()

    return {
        "invitation_codes": {
            "total": total_codes,
            "active": active_codes,
            "total_uses": total_uses
        },
        "applications": {
            "total": total_applications + pending_wechat_users,
            "pending": pending_applications + pending_wechat_users,
            "approved": approved_applications,
            "rejected": rejected_applications,
            "pending_wechat_users": pending_wechat_users  # 单独显示微信用户数
        }
    }
