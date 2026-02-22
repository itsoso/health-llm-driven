"""好友关系和PK挑战模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Friendship(Base):
    """好友关系（双向）"""
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)       # 发起方
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False)     # 接收方
    status = Column(String(20), nullable=False, default="pending")          # pending/accepted/rejected
    message = Column(String(200), nullable=True)                            # 好友申请消息

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="sent_friend_requests")
    friend = relationship("User", foreign_keys=[friend_id], backref="received_friend_requests")

    __table_args__ = (
        Index('idx_friendship_user_friend', 'user_id', 'friend_id', unique=True),
        Index('idx_friendship_friend_status', 'friend_id', 'status'),
        Index('idx_friendship_user_status', 'user_id', 'status'),
    )


class PKChallenge(Base):
    """PK挑战"""
    __tablename__ = "pk_challenges"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)     # 创建者
    title = Column(String(100), nullable=False)                              # 挑战标题
    challenge_type = Column(String(30), nullable=False)                      # checkin / study_time
    # checkin: PK打卡完成率/连续天数
    # study_time: PK学习/活动时长

    # 挑战配置
    checkin_template_id = Column(Integer, ForeignKey("checkin_templates.id"), nullable=True)  # 关联打卡模板（checkin类型）
    activity_category = Column(String(50), nullable=True)                    # 活动分类（study_time类型）
    metric = Column(String(30), nullable=False, default="total_minutes")     # 比拼指标: total_minutes/streak/completion_rate/count
    duration_days = Column(Integer, nullable=False, default=7)               # 挑战持续天数

    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    status = Column(String(20), nullable=False, default="active")            # active/completed/cancelled
    is_public = Column(Boolean, default=False)                               # 是否公开（可扩展）

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", backref="created_challenges")
    participants = relationship("ChallengeParticipant", back_populates="challenge", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_pk_challenge_creator', 'creator_id', 'status'),
        Index('idx_pk_challenge_dates', 'start_date', 'end_date'),
    )


class ChallengeParticipant(Base):
    """挑战参与者"""
    __tablename__ = "challenge_participants"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(Integer, ForeignKey("pk_challenges.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 实时统计（定期更新）
    score = Column(Float, default=0)                    # 当前得分
    rank = Column(Integer, nullable=True)               # 排名

    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    challenge = relationship("PKChallenge", back_populates="participants")
    user = relationship("User", backref="challenge_participations")

    __table_args__ = (
        Index('idx_participant_challenge_user', 'challenge_id', 'user_id', unique=True),
        Index('idx_participant_user', 'user_id'),
    )
