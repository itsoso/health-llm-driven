"""用户合并服务 - 合并小程序用户和PC用户"""
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from app.models.user import User

logger = logging.getLogger(__name__)
post_commit_observability_logger = logging.getLogger(
    f"{__name__}.post_commit_observability"
)

# user_id 字段有 unique=True 的表（一个用户只有一条记录）
UNIQUE_USER_TABLES = {
    "garmin_credentials",
    "user_profiles",
    "user_notification_settings",
}

# user_id 参与复合唯一约束的表: {表名: [额外唯一字段]}
COMPOSITE_UNIQUE_TABLES = {
    "garmin_data": ["record_date", "data_source"],
    "daily_recommendations": ["recommendation_date"],
    "monthly_reports": ["year", "month"],
}


class UserMergeIneligible(ValueError):
    """The locked source/target state is not eligible for an admin merge."""


class UserMergeService:
    """用户合并服务"""

    @staticmethod
    def _log_committed_merge_best_effort(
        source_user_id: int,
        target_user_id: int,
        merge_stats: Dict[str, int],
    ) -> None:
        """Emit bounded post-commit telemetry without changing the outcome."""
        try:
            logger.info(
                "成功合并用户: %s -> %s, 迁移表数: %s",
                source_user_id,
                target_user_id,
                len(merge_stats),
            )
        except Exception:  # noqa: BLE001 - observability must not undo a commit
            try:
                post_commit_observability_logger.error(
                    "用户合并已提交，但成功日志写入失败"
                )
            except Exception:  # noqa: BLE001 - never rethrow after the commit
                return

    @staticmethod
    def find_potential_merge_candidates(
        db: Session,
        wechat_user: User
    ) -> List[User]:
        """
        查找可能合并的PC用户

        匹配条件：
        1. 手机号相同
        2. 邮箱相同
        3. UnionID相同（如果微信用户有unionid）
        """
        candidates = []

        # 1. 通过手机号匹配
        if wechat_user.phone:
            pc_user = db.query(User).filter(
                User.phone == wechat_user.phone,
                User.id != wechat_user.id,
                User.wechat_openid.is_(None)  # PC用户（没有微信openid）
            ).first()
            if pc_user:
                candidates.append(pc_user)

        # 2. 通过邮箱匹配
        if wechat_user.email:
            pc_user = db.query(User).filter(
                User.email == wechat_user.email,
                User.id != wechat_user.id,
                User.wechat_openid.is_(None)
            ).first()
            if pc_user and pc_user not in candidates:
                candidates.append(pc_user)

        # 3. 通过UnionID匹配（如果微信用户有unionid）
        if wechat_user.wechat_unionid:
            pc_user = db.query(User).filter(
                User.wechat_unionid == wechat_user.wechat_unionid,
                User.id != wechat_user.id
            ).first()
            if pc_user and pc_user not in candidates:
                candidates.append(pc_user)

        return candidates

    @staticmethod
    def _get_all_user_tables(db: Session) -> List[str]:
        """获取所有包含 user_id 列的表名（排除 users 表本身）"""
        # Reuse the Session connection. Opening a second inspector connection can
        # observe a different transaction and, with SQLite StaticPool tests, its
        # cleanup rollback can undo the in-flight merge transaction.
        insp = inspect(db.connection())
        result = []
        for table_name in insp.get_table_names():
            columns = [col['name'] for col in insp.get_columns(table_name)]
            if 'user_id' in columns and table_name != 'users':
                result.append(table_name)
        return result

    @staticmethod
    def _migrate_unique_table(db: Session, table_name: str, source_id: int, target_id: int) -> int:
        """迁移 user_id 唯一约束的表。target 已有则删除 source 的，否则迁移。"""
        target_exists = db.execute(
            text(f"SELECT 1 FROM \"{table_name}\" WHERE user_id = :tid LIMIT 1"),
            {"tid": target_id}
        ).fetchone()
        if target_exists:
            result = db.execute(
                text(f"DELETE FROM \"{table_name}\" WHERE user_id = :sid"),
                {"sid": source_id}
            )
            logger.info(f"  {table_name}: target已有记录, 删除source {result.rowcount} 条")
            return 0
        else:
            result = db.execute(
                text(f"UPDATE \"{table_name}\" SET user_id = :tid WHERE user_id = :sid"),
                {"tid": target_id, "sid": source_id}
            )
            logger.info(f"  {table_name}: 迁移 {result.rowcount} 条")
            return result.rowcount

    @staticmethod
    def _migrate_composite_unique_table(
        db: Session, table_name: str, unique_cols: List[str],
        source_id: int, target_id: int
    ) -> int:
        """迁移有复合唯一约束的表。先删冲突记录，再迁移剩余。"""
        join_conds = " AND ".join(f"s.\"{col}\" = t.\"{col}\"" for col in unique_cols)
        # 删除由真实唯一约束确认的冲突记录。任何 SQL/结构错误交给
        # merge_users 的外层事务整体 rollback；绝不降级为删除 source 全表。
        db.execute(text(
            f'DELETE FROM "{table_name}" WHERE user_id = :sid AND id IN '
            f'(SELECT s.id FROM "{table_name}" s '
            f'INNER JOIN "{table_name}" t ON {join_conds} AND t.user_id = :tid '
            f'WHERE s.user_id = :sid2)'
        ), {"sid": source_id, "tid": target_id, "sid2": source_id})
        # 迁移剩余
        result = db.execute(
            text(f'UPDATE "{table_name}" SET user_id = :tid WHERE user_id = :sid'),
            {"tid": target_id, "sid": source_id}
        )
        logger.info(f"  {table_name}: 迁移 {result.rowcount} 条")
        return result.rowcount

    @staticmethod
    def merge_users(
        db: Session,
        source_user_id: int,  # 被合并的用户（将被删除）
        target_user_id: int,  # 目标用户（保留）
        *,
        require_active_approved: bool = False,
    ) -> Dict[str, Any]:
        """
        合并两个用户

        策略：
        - 保留target_user，删除source_user
        - 自动发现所有含 user_id 的表并迁移数据
        - 合并用户信息（保留更完整的信息）
        """
        locked_users = (
            db.query(User)
            .filter(User.id.in_((source_user_id, target_user_id)))
            .order_by(User.id)
            .with_for_update()
            .all()
        )
        users_by_id = {user.id: user for user in locked_users}
        source_user = users_by_id.get(source_user_id)
        target_user = users_by_id.get(target_user_id)

        if not source_user or not target_user:
            raise ValueError("用户不存在")

        if source_user.id == target_user.id:
            raise ValueError("不能合并同一个用户")
        if require_active_approved and not all((
            source_user.is_active,
            source_user.is_approved,
            target_user.is_active,
            target_user.is_approved,
        )):
            db.rollback()
            raise UserMergeIneligible("仅可合并已启用且已审核的既有账号")

        merge_stats = {}

        try:
            # 1. 自动发现并迁移所有包含 user_id 的表
            all_user_tables = UserMergeService._get_all_user_tables(db)
            logger.info(f"发现 {len(all_user_tables)} 个包含 user_id 的表")

            for table_name in all_user_tables:
                if table_name in UNIQUE_USER_TABLES:
                    count = UserMergeService._migrate_unique_table(
                        db, table_name, source_user_id, target_user_id
                    )
                elif table_name in COMPOSITE_UNIQUE_TABLES:
                    count = UserMergeService._migrate_composite_unique_table(
                        db, table_name, COMPOSITE_UNIQUE_TABLES[table_name],
                        source_user_id, target_user_id
                    )
                else:
                    result = db.execute(
                        text(f'UPDATE "{table_name}" SET user_id = :tid WHERE user_id = :sid'),
                        {"tid": target_user_id, "sid": source_user_id}
                    )
                    count = result.rowcount
                    if count > 0:
                        logger.info(f"  {table_name}: 迁移 {count} 条")

                if count > 0:
                    merge_stats[table_name] = count

            # 2. 合并用户基础信息（保留更完整的信息）
            if not target_user.email and source_user.email:
                target_user.email = source_user.email
            if not target_user.username and source_user.username:
                target_user.username = source_user.username
            if not target_user.phone and source_user.phone:
                target_user.phone = source_user.phone
            if not target_user.name or target_user.name.startswith("微信用户"):
                if source_user.name and not source_user.name.startswith("微信用户"):
                    target_user.name = source_user.name
            if not target_user.avatar_url and source_user.avatar_url:
                target_user.avatar_url = source_user.avatar_url
            if not target_user.birth_date and source_user.birth_date:
                target_user.birth_date = source_user.birth_date
            if not target_user.gender and source_user.gender:
                target_user.gender = source_user.gender

            # 合并微信信息
            if not target_user.wechat_openid and source_user.wechat_openid:
                target_user.wechat_openid = source_user.wechat_openid
            if not target_user.wechat_unionid and source_user.wechat_unionid:
                target_user.wechat_unionid = source_user.wechat_unionid
            if not target_user.wechat_session_key and source_user.wechat_session_key:
                target_user.wechat_session_key = source_user.wechat_session_key

            # 合并密码
            if not target_user.hashed_password and source_user.hashed_password:
                target_user.hashed_password = source_user.hashed_password

            # 确保合并后用户是已审批已激活
            if source_user.is_approved:
                target_user.is_approved = True
            if source_user.is_active:
                target_user.is_active = True

            # 3. 删除source用户
            db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": source_user_id})

            # 4. 提交事务
            db.commit()

        except Exception:
            db.rollback()
            logger.error("合并用户事务失败")
            raise

        result = {
            "success": True,
            "source_user_id": source_user_id,
            "target_user_id": target_user_id,
            "stats": merge_stats,
        }
        UserMergeService._log_committed_merge_best_effort(
            source_user_id,
            target_user_id,
            merge_stats,
        )
        return result
