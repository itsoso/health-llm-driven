"""Deterministic, revocable family grants. A relationship alone is not a grant."""

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.family import FamilyGroup, FamilyMember
from app.models.user import User


def require_family_access(
    db: Session, actor_id: int, target_id: int, *, edit: bool = False
):
    """Only the authenticated owner may use another member's explicit grant."""
    target = db.get(User, target_id)
    actor = db.get(User, actor_id)
    if not all(u and u.is_active and u.is_approved for u in (actor, target)):
        raise HTTPException(status_code=403, detail="家庭成员授权不可用")
    if actor_id == target_id and not edit:
        member = (
            db.query(FamilyMember)
            .filter_by(user_id=actor_id)
            .order_by(FamilyMember.id)
            .first()
        )
        if member:
            return member, target
    member = (
        db.query(FamilyMember)
        .join(FamilyGroup, FamilyGroup.id == FamilyMember.family_group_id)
        .filter(
            FamilyGroup.owner_id == actor_id,
            FamilyMember.user_id == target_id,
            FamilyMember.can_view.is_(True),
        )
        .first()
    )
    if member:
        owner = (
            db.query(FamilyMember)
            .filter_by(
                family_group_id=member.family_group_id,
                user_id=actor_id,
                role="owner",
            )
            .first()
        )
        managed = bool(target.is_managed and target.managed_by == actor_id)
        # Old direct-ID attachment created editable registered memberships without
        # target consent. Only authenticated invite acceptance created readonly
        # registered memberships; those may read but must never impersonate.
        invited = target.is_managed is False and member.can_edit is False
        if owner and (
            (managed and (not edit or member.can_edit)) or (invited and not edit)
        ):
            return member, target
    raise HTTPException(status_code=403, detail="没有查看或操作该家庭成员的授权")


def visible_family_members(db: Session, group: FamilyGroup, actor_id: int):
    query = (
        db.query(FamilyMember)
        .join(User, User.id == FamilyMember.user_id)
        .filter(
            FamilyMember.family_group_id == group.id,
            User.is_active.is_(True),
            User.is_approved.is_(True),
        )
    )
    if group.owner_id == actor_id:
        grant = FamilyMember.can_view.is_(True) & (
            (User.is_managed.is_(True) & (User.managed_by == actor_id))
            | (User.is_managed.is_(False) & FamilyMember.can_edit.is_(False))
        )
        query = query.filter((FamilyMember.user_id == actor_id) | grant)
    else:
        query = query.filter(FamilyMember.user_id == actor_id)
    return query.order_by(FamilyMember.id).all()
