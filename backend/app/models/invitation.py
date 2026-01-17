"""邀请码和用户申请模型"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum
import secrets
import string


class ApplicationStatus(str, enum.Enum):
    """申请状态"""
    PENDING = "pending"      # 待审批
    APPROVED = "approved"    # 已通过
    REJECTED = "rejected"    # 已拒绝


class InvitationCode(Base):
    """邀请码"""
    __tablename__ = "invitation_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 邀请码
    code = Column(String(32), unique=True, index=True, nullable=False)
    
    # 创建信息
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL 表示系统生成
    note = Column(String(200), nullable=True)  # 备注（如：给张三的邀请码）
    
    # 使用限制
    max_uses = Column(Integer, default=1)  # 最大使用次数
    used_count = Column(Integer, default=0)  # 已使用次数
    expires_at = Column(DateTime(timezone=True), nullable=True)  # 过期时间，NULL 表示永不过期
    
    # 状态
    is_active = Column(Boolean, default=True)  # 是否有效
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    creator = relationship("User", foreign_keys=[created_by])
    applications = relationship("UserApplication", back_populates="invitation")
    
    @staticmethod
    def generate_code(length: int = 8) -> str:
        """生成随机邀请码"""
        # 使用大写字母和数字，排除易混淆字符(0,O,1,I,L)
        alphabet = string.ascii_uppercase.replace('O', '').replace('I', '').replace('L', '')
        digits = string.digits.replace('0', '').replace('1', '')
        chars = alphabet + digits
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    @property
    def is_valid(self) -> bool:
        """检查邀请码是否可用"""
        from datetime import datetime, timezone
        
        if not self.is_active:
            return False
        if self.used_count >= self.max_uses:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True
    
    @property
    def remaining_uses(self) -> int:
        """剩余可用次数"""
        return max(0, self.max_uses - self.used_count)


class UserApplication(Base):
    """用户注册申请"""
    __tablename__ = "user_applications"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 申请人信息
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    
    # 邀请码
    invitation_code_id = Column(Integer, ForeignKey("invitation_codes.id"), nullable=False)
    
    # 健康问卷（JSON格式存储）
    health_questionnaire = Column(Text, nullable=True)  # {
    #   "age": 30,
    #   "gender": "male",
    #   "height_cm": 175,
    #   "weight_kg": 70,
    #   "health_goals": ["减脂", "提升睡眠质量"],
    #   "chronic_conditions": ["慢性鼻炎"],
    #   "wearable_devices": ["Garmin", "华为体脂秤"],
    #   "exercise_frequency": "每周3-4次",
    #   "why_join": "希望通过AI改善健康状态",
    # }
    
    # 审批信息
    status = Column(String, default=ApplicationStatus.PENDING.value, index=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)  # 审批备注
    
    # 关联的用户（审批通过后创建）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    invitation = relationship("InvitationCode", back_populates="applications")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    user = relationship("User", foreign_keys=[user_id])
