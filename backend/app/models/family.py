"""家庭健康管理模型"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class FamilyGroup(Base):
    """家庭组"""
    __tablename__ = "family_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("FamilyMember", back_populates="group", cascade="all, delete-orphan")


class FamilyMember(Base):
    """家庭成员（关联 User，可以是 shadow user）"""
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    family_group_id = Column(Integer, ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    relationship_type = Column(String(20), nullable=False)  # self/father/mother/spouse/child/sibling/other
    role = Column(String(20), nullable=False, default="member")  # owner/admin/member
    nickname = Column(String(50), nullable=True)  # 在家庭组内的昵称（如"爸爸"）
    can_view = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("FamilyGroup", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_family_member_group_user', 'family_group_id', 'user_id', unique=True),
    )
