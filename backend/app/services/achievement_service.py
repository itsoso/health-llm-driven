"""成就徽章服务"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from sqlalchemy.exc import IntegrityError

from app.models.achievement import BadgeDefinition, UserBadge, BADGE_SEED_DATA

logger = logging.getLogger(__name__)
from app.models.checkin import CheckinRecord
from app.models.daily_health import WaterIntake, GarminData, DietRecord
from app.models.chat import ChatConversation


class AchievementService:
    def __init__(self, db: Session):
        self.db = db

    def seed_badges(self) -> int:
        """幂等插入种子徽章定义，返回新增数量"""
        existing_codes = {
            b.code for b in self.db.query(BadgeDefinition.code).all()
        }
        created = 0
        for data in BADGE_SEED_DATA:
            if data["code"] not in existing_codes:
                self.db.add(BadgeDefinition(**data))
                created += 1
        if created > 0:
            self.db.commit()
        return created

    def get_all_definitions(self) -> List[BadgeDefinition]:
        """获取所有活跃徽章定义"""
        return (
            self.db.query(BadgeDefinition)
            .filter(BadgeDefinition.is_active == True)
            .order_by(BadgeDefinition.sort_order)
            .all()
        )

    def get_user_achievements(self, user_id: int) -> List[Dict]:
        """获取用户所有徽章 + 进度"""
        definitions = self.get_all_definitions()
        user_badges = {
            ub.badge_id: ub
            for ub in self.db.query(UserBadge)
            .filter(UserBadge.user_id == user_id)
            .all()
        }

        results = []
        for badge_def in definitions:
            ub = user_badges.get(badge_def.id)
            progress = self._calculate_progress(user_id, badge_def)
            results.append({
                "id": badge_def.id,
                "code": badge_def.code,
                "name": badge_def.name,
                "description": badge_def.description,
                "icon": badge_def.icon,
                "category": badge_def.category,
                "rarity": badge_def.rarity,
                "criteria_value": badge_def.criteria_value,
                "progress": progress,
                "unlocked": ub is not None,
                "unlocked_at": ub.unlocked_at.isoformat() if ub else None,
            })
        return results

    def check_and_award(self, user_id: int, trigger: Optional[str] = None) -> List[UserBadge]:
        """检查并授予新徽章，返回新解锁列表"""
        definitions = self.get_all_definitions()
        already_unlocked = {
            ub.badge_id
            for ub in self.db.query(UserBadge)
            .filter(UserBadge.user_id == user_id)
            .all()
        }

        newly_awarded = []
        for badge_def in definitions:
            if badge_def.id in already_unlocked:
                continue
            progress = self._calculate_progress(user_id, badge_def)
            if progress >= badge_def.criteria_value:
                ub = UserBadge(
                    user_id=user_id,
                    badge_id=badge_def.id,
                    progress_value=progress,
                )
                self.db.add(ub)
                newly_awarded.append(ub)

        if newly_awarded:
            try:
                self.db.commit()
                for ub in newly_awarded:
                    self.db.refresh(ub)
                # 标记通知状态并记录解锁信息
                badge_map = {d.id: d for d in definitions}
                for ub in newly_awarded:
                    badge = badge_map.get(ub.badge_id)
                    if badge:
                        logger.info(f"成就解锁: user={user_id} badge={badge.name} ({badge.code})")
                        ub.notified = True
                self.db.commit()
            except IntegrityError:
                # 并发请求已授予同一徽章，回滚重试
                self.db.rollback()
                logger.info(f"成就并发冲突 user={user_id}，已回滚")
                newly_awarded = []
        return newly_awarded

    # ── Progress calculators ──

    def _calculate_progress(self, user_id: int, badge_def: BadgeDefinition) -> float:
        ct = badge_def.criteria_type
        if ct == "checkin_streak":
            return self._get_checkin_streak(user_id)
        elif ct == "water_count":
            return self._get_water_total_count(user_id)
        elif ct == "run_distance":
            return self._get_total_run_distance(user_id)
        elif ct == "first_checkin":
            return 1.0 if self._has_any_checkin(user_id) else 0.0
        elif ct == "first_ai_chat":
            return 1.0 if self._has_any_chat(user_id) else 0.0
        elif ct == "checkin_total":
            return self._get_checkin_total(user_id)
        elif ct == "diet_count":
            return self._get_diet_count(user_id)
        return 0.0

    def _get_checkin_streak(self, user_id: int) -> float:
        """计算当前连续打卡天数（往前回溯直到断开）"""
        dates = (
            self.db.query(distinct(CheckinRecord.checkin_date))
            .filter(CheckinRecord.user_id == user_id)
            .order_by(CheckinRecord.checkin_date.desc())
            .all()
        )
        if not dates:
            return 0

        sorted_dates = sorted([d[0] for d in dates], reverse=True)
        today = date.today()
        # 允许今天或昨天作为起点
        if sorted_dates[0] != today and sorted_dates[0] != today - timedelta(days=1):
            return 0

        streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i - 1] - timedelta(days=1):
                streak += 1
            else:
                break
        return float(streak)

    def _get_water_total_count(self, user_id: int) -> float:
        count = (
            self.db.query(func.count(WaterIntake.id))
            .filter(WaterIntake.user_id == user_id)
            .scalar()
        )
        return float(count or 0)

    def _get_total_run_distance(self, user_id: int) -> float:
        """累计跑步距离（km），使用 GarminData.distance_meters"""
        total_meters = (
            self.db.query(func.sum(GarminData.distance_meters))
            .filter(
                GarminData.user_id == user_id,
                GarminData.distance_meters != None,
            )
            .scalar()
        )
        return round((total_meters or 0) / 1000, 2)

    def _has_any_checkin(self, user_id: int) -> bool:
        return (
            self.db.query(CheckinRecord.id)
            .filter(CheckinRecord.user_id == user_id)
            .first()
            is not None
        )

    def _has_any_chat(self, user_id: int) -> bool:
        return (
            self.db.query(ChatConversation.id)
            .filter(ChatConversation.user_id == user_id)
            .first()
            is not None
        )

    def _get_checkin_total(self, user_id: int) -> float:
        count = (
            self.db.query(func.count(CheckinRecord.id))
            .filter(CheckinRecord.user_id == user_id)
            .scalar()
        )
        return float(count or 0)

    def _get_diet_count(self, user_id: int) -> float:
        count = (
            self.db.query(func.count(DietRecord.id))
            .filter(DietRecord.user_id == user_id)
            .scalar()
        )
        return float(count or 0)
