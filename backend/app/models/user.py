"""用户模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """用户基础信息"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # 认证信息
    email = Column(String, unique=True, index=True, nullable=True)  # 登录邮箱
    username = Column(String, unique=True, index=True, nullable=True)  # 用户名
    hashed_password = Column(String, nullable=True)  # 加密后的密码
    is_active = Column(Boolean, default=True)  # 账户是否激活
    is_admin = Column(Boolean, default=False)  # 是否管理员
    is_approved = Column(Boolean, default=False)  # 是否已通过管理员审核
    invite_code = Column(String, nullable=True)  # 注册时使用的邀请码

    # 微信小程序认证
    wechat_openid = Column(String, unique=True, index=True, nullable=True)  # 微信 OpenID
    wechat_unionid = Column(String, index=True, nullable=True)  # 微信 UnionID（多平台统一）
    wechat_session_key = Column(String, nullable=True)  # 微信会话密钥（加密数据解密用）

    # 基础信息
    name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)  # 头像URL
    birth_date = Column(Date, nullable=True)  # 用于计算年龄
    gender = Column(String, nullable=True)  # 男/女
    phone = Column(String, unique=True, index=True, nullable=True)  # E.164 手机号
    phone_verified_at = Column(DateTime(timezone=True), nullable=True)  # 手机号归属验证时间
    onboarding_completed = Column(Boolean, default=False)  # 是否完成新手引导

    # Concierge: 保健医生邮箱 (Doctor Weekly Report 接收人)
    # 空时 fallback 到 Telegram / APNs
    doctor_email = Column(String, nullable=True)

    # Phase 3 P3-1 (2026-05-11): Coach Persona — orchestrator 合成时切换语气
    #   strict_coach    严厉教练: 直接, 命令式, 数字驱动, 不允许借口
    #   gentle_advisor  温和顾问 (默认): 共情, 建议式, 解释原因
    #   data_driven     数据派: 专注指标, 每条建议必带具体数据/阈值
    # 不影响任何 specialist 逻辑, 只切 prompt 风格.
    coach_persona = Column(String(20), nullable=True, default="gentle_advisor")

    # 家庭代管（shadow user，不需要登录凭据，由管理员代管）
    is_managed = Column(Boolean, default=False)
    managed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    daily_recommendations = relationship("DailyRecommendation", back_populates="user")
    health_analysis_cache = relationship("HealthAnalysisCache", back_populates="user")
    garmin_credentials = relationship("GarminCredential", back_populates="user", uselist=False)
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    checkin_templates = relationship("CheckinTemplate", backref="user")
    checkin_records = relationship("CheckinRecord", backref="user")
    health_goals = relationship("HealthGoal", backref="user")
    notification_settings = relationship("UserNotificationSetting", back_populates="user", uselist=False)


class GarminCredential(Base):
    """用户Garmin凭证（加密存储）"""
    __tablename__ = "garmin_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    # Garmin登录凭证（加密存储）
    garmin_email = Column(String, nullable=False)  # Garmin邮箱
    encrypted_password = Column(Text, nullable=False)  # 加密后的Garmin密码
    is_cn = Column(Boolean, default=False)  # 是否使用中国服务器 (garmin.cn)

    # 同步状态
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_enabled = Column(Boolean, default=True)
    credentials_valid = Column(Boolean, default=True)  # 凭证是否有效（登录失败时设为False）
    requires_mfa = Column(Boolean, default=False)  # 是否需要两步验证（MFA）
    last_error = Column(Text, nullable=True)  # 最后一次错误信息
    error_count = Column(Integer, default=0)  # 连续错误次数
    login_locked_until = Column(DateTime(timezone=True), nullable=True)  # 登录锁定截止时间（防止频繁登录导致 Garmin 账号被锁）

    # 同步去重锁 - 防止多个入口并发同步同一用户
    sync_in_progress = Column(Boolean, default=False, server_default="false")
    sync_started_at = Column(DateTime(timezone=True), nullable=True)

    # Garmin 原生 token 缓存；字段名为历史兼容，内容是带版本的加密 envelope
    garth_session = Column(Text, nullable=True)
    session_expires_at = Column(DateTime(timezone=True), nullable=True)  # 仅作历史/观测元数据

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="garmin_credentials")
