"""好友关系和PK挑战 Schemas"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ===== 好友关系 =====

class FriendRequestCreate(BaseModel):
    friend_id: int
    message: Optional[str] = Field(None, max_length=200)


class FriendRequestResponse(BaseModel):
    id: int
    user_id: int
    friend_id: int
    status: str
    message: Optional[str] = None
    created_at: datetime
    # 对方用户简要信息
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None
    friend_name: Optional[str] = None
    friend_avatar: Optional[str] = None

    class Config:
        from_attributes = True


class FriendInfo(BaseModel):
    """好友信息"""
    user_id: int
    name: str
    avatar_url: Optional[str] = None
    friendship_id: int
    since: datetime  # 成为好友的时间


class UserSearchResult(BaseModel):
    """用户搜索结果"""
    id: int
    name: str
    avatar_url: Optional[str] = None
    is_friend: bool = False
    request_pending: bool = False


# ===== PK挑战 =====

class PKChallengeCreate(BaseModel):
    title: str = Field(..., max_length=100)
    challenge_type: str = Field(..., pattern="^(checkin|study_time)$")
    checkin_template_id: Optional[int] = None  # checkin类型需要
    activity_category: Optional[str] = None    # study_time类型需要
    metric: str = Field(default="total_minutes", pattern="^(total_minutes|streak|completion_rate|count)$")
    duration_days: int = Field(default=7, ge=1, le=90)
    friend_ids: List[int] = Field(default_factory=list)  # 邀请的好友ID


class ParticipantInfo(BaseModel):
    user_id: int
    user_name: str
    user_avatar: Optional[str] = None
    score: float = 0
    rank: Optional[int] = None
    joined_at: datetime

    class Config:
        from_attributes = True


class PKChallengeResponse(BaseModel):
    id: int
    creator_id: int
    creator_name: Optional[str] = None
    title: str
    challenge_type: str
    checkin_template_id: Optional[int] = None
    checkin_template_name: Optional[str] = None
    activity_category: Optional[str] = None
    metric: str
    duration_days: int
    start_date: datetime
    end_date: datetime
    status: str
    participants: List[ParticipantInfo] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class PKChallengeDetail(PKChallengeResponse):
    """挑战详情，包含排行榜"""
    leaderboard: List[ParticipantInfo] = Field(default_factory=list)


class PKStatsResponse(BaseModel):
    """PK统计"""
    total_challenges: int = 0
    wins: int = 0
    active_challenges: int = 0
