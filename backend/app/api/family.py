"""家庭健康管理 API"""
import logging
from typing import Optional, List
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.family import FamilyGroup, FamilyMember
from app.api.deps import get_current_user_required
from app.services.auth import auth_service
from app.services.web_session import (
    WEB_SESSION_AUTH_SENTINEL,
    set_web_session_cookie,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/family", tags=["family"])


# ── Schemas ───────────────────────────────────────────────

class FamilyGroupCreate(BaseModel):
    name: str = Field(..., max_length=100, description="家庭组名称")


class FamilyMemberAdd(BaseModel):
    name: str = Field(..., max_length=100, description="成员姓名")
    relationship_type: str = Field(..., description="关系: self/father/mother/spouse/child/sibling/other")
    nickname: Optional[str] = Field(None, max_length=50, description="家庭内昵称（如爸爸）")
    gender: Optional[str] = Field(None, description="性别: 男/女")
    birth_date: Optional[date] = Field(None, description="出生日期")
    existing_user_id: Optional[int] = Field(None, description="已有用户ID（关联已注册用户）")


class FamilySwitchRequest(BaseModel):
    user_id: int = Field(..., description="要切换到的家庭成员 user_id")


# ── Endpoints ─────────────────────────────────────────────

@router.post("/groups", summary="创建家庭组")
async def create_family_group(
    req: FamilyGroupCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建一个家庭组，自动将创建者加为 owner"""
    # 检查是否已有家庭组
    existing = db.query(FamilyGroup).filter(FamilyGroup.owner_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="你已有家庭组，每人只能创建一个")

    group = FamilyGroup(name=req.name, owner_id=current_user.id)
    db.add(group)
    db.flush()

    # 自动将创建者加为成员
    self_member = FamilyMember(
        family_group_id=group.id,
        user_id=current_user.id,
        relationship_type="self",
        role="owner",
        nickname=current_user.name,
        can_view=True,
        can_edit=True,
    )
    db.add(self_member)
    db.commit()

    return {
        "id": group.id,
        "name": group.name,
        "members_count": 1,
        "message": "家庭组创建成功",
    }


@router.get("/groups", summary="我的家庭组")
async def get_my_groups(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户所在的家庭组"""
    memberships = db.query(FamilyMember).filter(FamilyMember.user_id == current_user.id).all()
    groups = []
    for m in memberships:
        group = db.query(FamilyGroup).filter(FamilyGroup.id == m.family_group_id).first()
        if group:
            member_count = db.query(FamilyMember).filter(
                FamilyMember.family_group_id == group.id
            ).count()
            groups.append({
                "id": group.id,
                "name": group.name,
                "role": m.role,
                "members_count": member_count,
                "is_owner": group.owner_id == current_user.id,
            })
    return {"groups": groups}


@router.post("/members", summary="添加家庭成员")
async def add_family_member(
    req: FamilyMemberAdd,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    添加家庭成员。两种模式：
    - 提供 existing_user_id: 关联已注册用户
    - 不提供: 创建 shadow user（代管模式，父母不需要注册）
    """
    # 获取用户所属的家庭组（必须是 owner）
    group = db.query(FamilyGroup).filter(FamilyGroup.owner_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="你还没有家庭组，请先创建")

    if req.existing_user_id:
        # 模式 1：关联已有用户
        target_user = db.query(User).filter(User.id == req.existing_user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="用户不存在")
        # 检查是否已在组内
        exists = db.query(FamilyMember).filter(
            FamilyMember.family_group_id == group.id,
            FamilyMember.user_id == target_user.id,
        ).first()
        if exists:
            raise HTTPException(status_code=400, detail="该用户已在家庭组中")
        user_id = target_user.id
    else:
        # 模式 2：创建 shadow user（代管模式）
        shadow_user = User(
            name=req.name,
            gender=req.gender,
            birth_date=req.birth_date,
            is_active=True,
            is_approved=True,
            is_managed=True,
            managed_by=current_user.id,
        )
        db.add(shadow_user)
        db.flush()
        user_id = shadow_user.id
        logger.info(f"创建 shadow user: id={user_id}, name={req.name}, managed_by={current_user.id}")

    member = FamilyMember(
        family_group_id=group.id,
        user_id=user_id,
        relationship_type=req.relationship_type,
        role="member",
        nickname=req.nickname or req.name,
        can_view=True,
        can_edit=True,
    )
    db.add(member)
    db.commit()

    return {
        "id": member.id,
        "user_id": user_id,
        "name": req.name,
        "relationship_type": req.relationship_type,
        "message": f"已添加家庭成员: {req.nickname or req.name}",
    }


@router.get("/members", summary="家庭成员列表")
async def get_family_members(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取家庭组内所有成员"""
    group = db.query(FamilyGroup).filter(FamilyGroup.owner_id == current_user.id).first()
    if not group:
        # 也查作为成员加入的组
        membership = db.query(FamilyMember).filter(FamilyMember.user_id == current_user.id).first()
        if membership:
            group = db.query(FamilyGroup).filter(FamilyGroup.id == membership.family_group_id).first()
    if not group:
        return {"members": []}

    members = db.query(FamilyMember).filter(FamilyMember.family_group_id == group.id).all()
    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        result.append({
            "id": m.id,
            "user_id": m.user_id,
            "name": user.name if user else "未知",
            "nickname": m.nickname,
            "relationship_type": m.relationship_type,
            "role": m.role,
            "is_managed": user.is_managed if user else False,
            "gender": user.gender if user else None,
            "birth_date": str(user.birth_date) if user and user.birth_date else None,
            "can_view": m.can_view,
            "can_edit": m.can_edit,
        })

    return {"group_name": group.name, "members": result}


@router.delete("/members/{member_id}", summary="移除家庭成员")
async def remove_family_member(
    member_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """移除家庭成员（仅 owner 可操作，不能移除自己）"""
    member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")

    group = db.query(FamilyGroup).filter(FamilyGroup.id == member.family_group_id).first()
    if not group or group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有家庭组创建者可以移除成员")

    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能移除自己")

    db.delete(member)
    db.commit()
    return {"message": "已移除成员"}


@router.post("/switch", summary="切换到家庭成员视角")
async def switch_to_member(
    req: FamilySwitchRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    切换到指定家庭成员的视角。返回包含 acting_as 的新 JWT Token。
    使用该 Token 后，所有 API 操作将以目标成员身份执行。
    """
    target_user_id = req.user_id

    # 自己不需要切换
    if target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不需要切换到自己")

    # 验证权限：目标用户必须在同一家庭组，且当前用户是 owner 或有编辑权限
    my_groups = db.query(FamilyMember.family_group_id).filter(
        FamilyMember.user_id == current_user.id
    ).scalar_subquery()

    target_member = db.query(FamilyMember).filter(
        FamilyMember.user_id == target_user_id,
        FamilyMember.family_group_id.in_(my_groups),
    ).first()

    if not target_member:
        raise HTTPException(status_code=403, detail="该用户不在你的家庭组中")

    # 验证编辑权限
    my_member = db.query(FamilyMember).filter(
        FamilyMember.family_group_id == target_member.family_group_id,
        FamilyMember.user_id == current_user.id,
    ).first()

    if not my_member or (my_member.role != "owner" and not target_member.can_edit):
        raise HTTPException(status_code=403, detail="你没有权限操作该成员的数据")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    # 生成带 acting_as 的 JWT Token（有效期 4 小时）
    from app.services.auth import SECRET_KEY, ALGORITHM
    import jwt
    from datetime import UTC, datetime, timedelta
    token_data = {
        "sub": str(target_user_id),
        "acting_as": target_user_id,
        "original_user": current_user.id,
        "exp": datetime.now(UTC) + timedelta(hours=4),
    }
    proxy_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    cookie_auth = getattr(request.state, "auth_type", None) == "cookie"
    if cookie_auth:
        set_web_session_cookie(response, proxy_token, max_age=4 * 3600)

    return {
        "access_token": WEB_SESSION_AUTH_SENTINEL if cookie_auth else proxy_token,
        "token_type": "bearer",
        "acting_as": target_user_id,
        "acting_as_name": target_user.name,
        "original_user_id": current_user.id,
        "expires_in": 4 * 3600,
        "message": f"已切换到 {target_member.nickname or target_user.name} 的视角",
    }


@router.get("/proxy-status", summary="获取家庭代管会话状态")
async def proxy_status(
    request: Request,
    current_user: User = Depends(get_current_user_required),
):
    original_user_id = getattr(request.state, "original_user_id", None)
    return {
        "is_proxy_mode": bool(getattr(request.state, "is_proxy_mode", False)),
        "acting_as": current_user.id,
        "acting_as_name": current_user.name,
        "original_user_id": original_user_id,
    }


@router.post("/switch-back", summary="切回家庭代管发起人")
async def switch_back(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    original_user_id = getattr(request.state, "original_user_id", None)
    if not getattr(request.state, "is_proxy_mode", False) or not original_user_id:
        raise HTTPException(status_code=400, detail="当前不在家庭代管模式")

    original_user = db.query(User).filter(User.id == int(original_user_id)).first()
    if not original_user or not original_user.is_active or not original_user.is_approved:
        raise HTTPException(status_code=403, detail="原账号当前不可用")

    original_token = auth_service.create_access_token({"sub": str(original_user.id)})
    cookie_auth = getattr(request.state, "auth_type", None) == "cookie"
    if cookie_auth:
        set_web_session_cookie(response, original_token)
    return {
        "access_token": WEB_SESSION_AUTH_SENTINEL if cookie_auth else original_token,
        "token_type": "bearer",
        "user_id": original_user.id,
        "message": "已切回自己",
    }


@router.get("/dashboard", summary="家庭健康仪表盘")
async def family_dashboard(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """家庭成员健康概览"""
    group = db.query(FamilyGroup).filter(FamilyGroup.owner_id == current_user.id).first()
    if not group:
        membership = db.query(FamilyMember).filter(FamilyMember.user_id == current_user.id).first()
        if membership:
            group = db.query(FamilyGroup).filter(FamilyGroup.id == membership.family_group_id).first()
    if not group:
        return {"group_name": None, "members": []}

    members = db.query(FamilyMember).filter(FamilyMember.family_group_id == group.id).all()
    today = date.today()

    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        if not user:
            continue

        member_data = {
            "user_id": m.user_id,
            "name": user.name,
            "nickname": m.nickname,
            "relationship_type": m.relationship_type,
            "is_managed": user.is_managed,
        }

        # 最新体重
        try:
            from app.models.weight import WeightRecord
            latest_weight = db.query(WeightRecord).filter(
                WeightRecord.user_id == m.user_id
            ).order_by(WeightRecord.record_date.desc()).first()
            member_data["latest_weight"] = latest_weight.weight if latest_weight else None
        except Exception:
            member_data["latest_weight"] = None

        # 今日步数（从 Garmin）
        try:
            from app.models.daily_health import GarminData
            garmin = db.query(GarminData).filter(
                GarminData.user_id == m.user_id,
                GarminData.record_date == today,
            ).first()
            member_data["today_steps"] = garmin.steps if garmin else None
            member_data["sleep_score"] = garmin.sleep_score if garmin else None
            member_data["resting_hr"] = garmin.resting_heart_rate if garmin else None
        except Exception:
            member_data["today_steps"] = None
            member_data["sleep_score"] = None
            member_data["resting_hr"] = None

        # 今日饮水
        try:
            from app.models.daily_health import WaterIntake
            water = db.query(WaterIntake).filter(
                WaterIntake.user_id == m.user_id,
                WaterIntake.record_date == today,
            ).all()
            member_data["today_water_ml"] = sum(w.amount_ml or 0 for w in water)
        except Exception:
            member_data["today_water_ml"] = 0

        # 未读健康预警
        try:
            from app.models.anomaly_alert import AnomalyAlert
            alert_count = db.query(AnomalyAlert).filter(
                AnomalyAlert.user_id == m.user_id,
                AnomalyAlert.acknowledged == False,
                AnomalyAlert.detection_date >= today - timedelta(days=7),
            ).count()
            member_data["unread_alerts"] = alert_count
        except Exception:
            member_data["unread_alerts"] = 0

        result.append(member_data)

    return {"group_name": group.name, "members": result}


# ============================================================================
# G Phase 2: 家庭邀请码 (纯内存, 30min TTL, 重启丢失但够用)
#
# 流程:
#   主人 POST /family/invitation/create → 6 位码 'AB12CD'
#   分享给家人
#   家人 POST /family/invitation/accept {code, relationship_type, nickname?} → 加入
#
# 安全:
#   - 6 位 base32 (无 0/O/I/1) 36^6 ≈ 2 亿组合, 30min 窗口冲撞概率忽略
#   - 一码一用 (accept 后即销毁)
#   - 主人必须先 POST /family/groups 建过组
# ============================================================================

import secrets
import time as _time

_INVITE_CACHE: dict[str, dict] = {}  # code → {group_id, owner_user_id, expires_at}
_INVITE_TTL_SECONDS = 1800  # 30 min
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去歧义字符


def _gen_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(6))


def _gc_invite_cache():
    """惰性清理过期 invite. 每次 create/accept 时调."""
    now = _time.time()
    for code, info in list(_INVITE_CACHE.items()):
        if info["expires_at"] < now:
            _INVITE_CACHE.pop(code, None)


class InviteCodeResponse(BaseModel):
    code: str
    expires_in_seconds: int
    group_name: str


class InviteAcceptRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=12)
    relationship_type: str = Field(..., description="self/father/mother/spouse/child/sibling/other")
    nickname: Optional[str] = None


@router.post("/invitation/create", summary="创建家庭邀请码", response_model=InviteCodeResponse)
async def create_invitation(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """生成 6 位邀请码, 30min 有效. 调用方必须已是某家庭组的 owner."""
    _gc_invite_cache()

    group = db.query(FamilyGroup).filter(FamilyGroup.owner_id == current_user.id).first()
    if not group:
        raise HTTPException(
            status_code=400,
            detail="请先创建家庭组 (POST /family/groups)",
        )

    # 复用未过期的码 (避免用户每次按按钮都生成新码; 同一 owner 30min 内同一码)
    now = _time.time()
    for code, info in _INVITE_CACHE.items():
        if info["owner_user_id"] == current_user.id and info["group_id"] == group.id:
            if info["expires_at"] > now:
                return InviteCodeResponse(
                    code=code,
                    expires_in_seconds=int(info["expires_at"] - now),
                    group_name=group.name,
                )

    # 新生成
    for _ in range(10):  # 最多重试 10 次防撞
        code = _gen_invite_code()
        if code not in _INVITE_CACHE:
            break
    _INVITE_CACHE[code] = {
        "owner_user_id": current_user.id,
        "group_id": group.id,
        "expires_at": now + _INVITE_TTL_SECONDS,
    }
    logger.info(f"[family.invitation] user={current_user.id} group={group.id} 创建邀请码 {code}")
    return InviteCodeResponse(
        code=code,
        expires_in_seconds=_INVITE_TTL_SECONDS,
        group_name=group.name,
    )


@router.post("/invitation/accept", summary="接受家庭邀请")
async def accept_invitation(
    req: InviteAcceptRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """凭邀请码加入家庭组. 一码一用."""
    _gc_invite_cache()

    code = req.code.upper().strip()
    info = _INVITE_CACHE.get(code)
    if not info:
        raise HTTPException(status_code=404, detail="邀请码无效或已过期")

    group = db.query(FamilyGroup).filter(FamilyGroup.id == info["group_id"]).first()
    if not group:
        _INVITE_CACHE.pop(code, None)
        raise HTTPException(status_code=404, detail="家庭组已不存在")

    # 已经是成员 → 幂等返回
    existing = db.query(FamilyMember).filter(
        FamilyMember.family_group_id == group.id,
        FamilyMember.user_id == current_user.id,
    ).first()
    if existing:
        _INVITE_CACHE.pop(code, None)
        return {
            "message": "你已经是该家庭的成员了",
            "group_name": group.name,
            "member_id": existing.id,
        }

    # 加入
    member = FamilyMember(
        family_group_id=group.id,
        user_id=current_user.id,
        relationship_type=req.relationship_type,
        nickname=req.nickname or current_user.name,
        role="member",
        can_view=True,
        can_edit=False,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    # 一码一用: 销毁
    _INVITE_CACHE.pop(code, None)

    logger.info(
        f"[family.invitation] user={current_user.id} 加入 group={group.id} "
        f"as {req.relationship_type} via code={code}"
    )
    return {
        "message": f"已加入家庭 '{group.name}'",
        "group_name": group.name,
        "member_id": member.id,
        "relationship_type": req.relationship_type,
    }
