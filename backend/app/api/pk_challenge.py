"""PK挑战 API"""
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_, func as sa_func

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.friendship import Friendship, PKChallenge, ChallengeParticipant
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.activity_status import ActivityStatus
from app.schemas.friendship import (
    PKChallengeCreate, PKChallengeResponse, PKChallengeDetail,
    ParticipantInfo, PKStatsResponse,
)

router = APIRouter(prefix="/pk-challenges", tags=["PK挑战"])


def _is_friend(db: Session, user_id: int, other_id: int) -> bool:
    return db.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == user_id, Friendship.friend_id == other_id),
            and_(Friendship.user_id == other_id, Friendship.friend_id == user_id),
        ),
        Friendship.status == "accepted",
    ).first() is not None


def _calc_participant_score(
    db: Session, user_id: int, challenge: PKChallenge
) -> float:
    """计算参与者在挑战中的得分"""
    now = datetime.now(timezone.utc)
    start = challenge.start_date
    # 确保 datetime 比较安全（统一为 aware）
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end_dt = challenge.end_date
    if end_dt and end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    end = min(end_dt, now) if end_dt else now

    if challenge.challenge_type == "checkin" and challenge.checkin_template_id:
        start_date = start.date() if hasattr(start, 'date') else start
        end_date = end.date() if hasattr(end, 'date') else end
        records = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.template_id == challenge.checkin_template_id,
            CheckinRecord.checkin_date >= start_date,
            CheckinRecord.checkin_date <= end_date,
        ).all()

        if challenge.metric == "count":
            return float(len(records))
        elif challenge.metric == "completion_rate":
            if not records:
                return 0.0
            return round(sum(r.completion_rate or 0 for r in records) / len(records), 1)
        elif challenge.metric == "streak":
            # 计算挑战期间内的连续天数
            dates = sorted(set(r.checkin_date for r in records))
            if not dates:
                return 0.0
            streak = 1
            max_streak = 1
            for i in range(1, len(dates)):
                if (dates[i] - dates[i - 1]).days == 1:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 1
            return float(max_streak)
        else:  # total_minutes
            return float(sum(r.value or 0 for r in records))

    elif challenge.challenge_type == "study_time":
        category_filter = challenge.activity_category or "studying"
        activities = db.query(ActivityStatus).filter(
            ActivityStatus.user_id == user_id,
            ActivityStatus.category == category_filter,
            ActivityStatus.start_time >= start,
            ActivityStatus.start_time <= end,
        ).all()

        now = datetime.now(timezone.utc)
        total = 0
        for a in activities:
            end_time = a.actual_end_time or (now if a.is_active else a.estimated_end_time)
            if end_time and a.start_time:
                delta = end_time - a.start_time
                total += max(0, int(delta.total_seconds() // 60))

        if challenge.metric == "count":
            return float(len(activities))
        return float(total)  # total_minutes

    return 0.0


def _build_challenge_response(
    challenge: PKChallenge, db: Session, include_leaderboard: bool = False
) -> dict:
    """构建挑战响应"""
    creator = db.query(User).filter(User.id == challenge.creator_id).first()
    template_name = None
    if challenge.checkin_template_id:
        tmpl = db.query(CheckinTemplate).filter(CheckinTemplate.id == challenge.checkin_template_id).first()
        template_name = tmpl.name if tmpl else None

    participants = []
    for p in sorted(challenge.participants, key=lambda x: x.score or 0, reverse=True):
        u = db.query(User).filter(User.id == p.user_id).first()
        participants.append(ParticipantInfo(
            user_id=p.user_id,
            user_name=u.name if u else "未知",
            user_avatar=u.avatar_url if u else None,
            score=p.score or 0,
            rank=p.rank,
            joined_at=p.joined_at,
        ))

    data = dict(
        id=challenge.id,
        creator_id=challenge.creator_id,
        creator_name=creator.name if creator else None,
        title=challenge.title,
        challenge_type=challenge.challenge_type,
        checkin_template_id=challenge.checkin_template_id,
        checkin_template_name=template_name,
        activity_category=challenge.activity_category,
        metric=challenge.metric,
        duration_days=challenge.duration_days,
        start_date=challenge.start_date,
        end_date=challenge.end_date,
        status=challenge.status,
        participants=participants,
        created_at=challenge.created_at,
    )
    if include_leaderboard:
        data["leaderboard"] = participants
    return data


@router.post("", response_model=PKChallengeResponse, summary="创建PK挑战")
async def create_challenge(
    data: PKChallengeCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 验证挑战类型
    if data.challenge_type == "checkin" and not data.checkin_template_id:
        raise HTTPException(status_code=400, detail="打卡PK需要指定打卡模板")
    if data.challenge_type == "study_time" and not data.activity_category:
        data.activity_category = "studying"

    # 验证好友关系
    for fid in data.friend_ids:
        if not _is_friend(db, current_user.id, fid):
            raise HTTPException(status_code=400, detail=f"用户 {fid} 不是你的好友")

    now = datetime.now(timezone.utc)
    challenge = PKChallenge(
        creator_id=current_user.id,
        title=data.title,
        challenge_type=data.challenge_type,
        checkin_template_id=data.checkin_template_id,
        activity_category=data.activity_category,
        metric=data.metric,
        duration_days=data.duration_days,
        start_date=now,
        end_date=now + timedelta(days=data.duration_days),
        status="active",
    )
    db.add(challenge)
    db.flush()

    # 创建者自动参与
    creator_participant = ChallengeParticipant(
        challenge_id=challenge.id,
        user_id=current_user.id,
        score=0,
    )
    db.add(creator_participant)

    # 邀请好友
    for fid in data.friend_ids:
        p = ChallengeParticipant(
            challenge_id=challenge.id,
            user_id=fid,
            score=0,
        )
        db.add(p)

    db.commit()
    db.refresh(challenge)
    return PKChallengeResponse(**_build_challenge_response(challenge, db))


@router.get("", response_model=List[PKChallengeResponse], summary="我的PK挑战列表")
async def list_challenges(
    status: Optional[str] = Query(None, pattern="^(active|completed|cancelled)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 先找到我参与的挑战ID
    my_challenge_ids = db.query(ChallengeParticipant.challenge_id).filter(
        ChallengeParticipant.user_id == current_user.id,
    ).subquery()

    query = db.query(PKChallenge).filter(PKChallenge.id.in_(my_challenge_ids))
    if status:
        query = query.filter(PKChallenge.status == status)

    challenges = query.order_by(desc(PKChallenge.created_at)).limit(50).all()

    # 自动结束已过期的挑战
    now = datetime.now(timezone.utc)
    for c in challenges:
        end_dt = c.end_date
        if end_dt and end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if c.status == "active" and end_dt and end_dt < now:
            c.status = "completed"
            # 更新分数和排名
            _update_scores(db, c)
    db.commit()

    return [PKChallengeResponse(**_build_challenge_response(c, db)) for c in challenges]


@router.get("/stats/me", response_model=PKStatsResponse, summary="我的PK统计")
async def my_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    my_participations = db.query(ChallengeParticipant).filter(
        ChallengeParticipant.user_id == current_user.id,
    ).all()

    challenge_ids = [p.challenge_id for p in my_participations]
    if not challenge_ids:
        return PKStatsResponse()

    challenges = db.query(PKChallenge).filter(PKChallenge.id.in_(challenge_ids)).all()

    total = len(challenges)
    active = sum(1 for c in challenges if c.status == "active")
    wins = 0
    for c in challenges:
        if c.status == "completed":
            # 排名第1就是赢
            p = next((pp for pp in my_participations if pp.challenge_id == c.id), None)
            if p and p.rank == 1:
                wins += 1

    return PKStatsResponse(
        total_challenges=total,
        wins=wins,
        active_challenges=active,
    )


@router.get("/{challenge_id}", response_model=PKChallengeDetail, summary="PK挑战详情")
async def get_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    challenge = db.query(PKChallenge).filter(PKChallenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="挑战不存在")

    # 检查是否是参与者
    participant = db.query(ChallengeParticipant).filter(
        ChallengeParticipant.challenge_id == challenge_id,
        ChallengeParticipant.user_id == current_user.id,
    ).first()
    if not participant:
        raise HTTPException(status_code=403, detail="你不是这个挑战的参与者")

    # 自动结束
    now = datetime.now(timezone.utc)
    end_dt = challenge.end_date
    if end_dt and end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    if challenge.status == "active" and end_dt and end_dt < now:
        challenge.status = "completed"

    # 实时更新分数
    _update_scores(db, challenge)
    db.commit()

    return PKChallengeDetail(**_build_challenge_response(challenge, db, include_leaderboard=True))


@router.post("/{challenge_id}/refresh", response_model=PKChallengeDetail, summary="刷新挑战分数")
async def refresh_scores(
    challenge_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    challenge = db.query(PKChallenge).filter(PKChallenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="挑战不存在")

    participant = db.query(ChallengeParticipant).filter(
        ChallengeParticipant.challenge_id == challenge_id,
        ChallengeParticipant.user_id == current_user.id,
    ).first()
    if not participant:
        raise HTTPException(status_code=403, detail="你不是这个挑战的参与者")

    _update_scores(db, challenge)
    db.commit()

    return PKChallengeDetail(**_build_challenge_response(challenge, db, include_leaderboard=True))


@router.delete("/{challenge_id}", summary="取消挑战（仅创建者）")
async def cancel_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    challenge = db.query(PKChallenge).filter(
        PKChallenge.id == challenge_id,
        PKChallenge.creator_id == current_user.id,
    ).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="挑战不存在或无权操作")
    if challenge.status != "active":
        raise HTTPException(status_code=400, detail="只能取消进行中的挑战")

    challenge.status = "cancelled"
    db.commit()
    return {"message": "挑战已取消"}


def _update_scores(db: Session, challenge: PKChallenge):
    """更新所有参与者的分数和排名"""
    for p in challenge.participants:
        p.score = _calc_participant_score(db, p.user_id, challenge)

    # 更新排名
    sorted_ps = sorted(challenge.participants, key=lambda x: x.score or 0, reverse=True)
    for i, p in enumerate(sorted_ps):
        p.rank = i + 1
