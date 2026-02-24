"""用户合并服务 - 合并小程序用户和PC用户"""
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from app.models.user import User, GarminCredential

logger = logging.getLogger(__name__)

# user_id 字段有 unique=True 的表（一个用户只有一条记录）
UNIQUE_USER_TABLES = {
    "garmin_credentials",
    "user_profiles",
    "user_notification_settings",
    "kids_pets",
}

# user_id 参与复合唯一约束的表: {表名: [额外唯一字段]}
COMPOSITE_UNIQUE_TABLES = {
    "daily_recommendations": ["recommendation_date"],
    "vocabularies": ["word"],
    "friendships": ["friend_id"],
    "challenge_participants": ["challenge_id"],
}


class UserMergeService:
    """用户合并服务"""
    
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
        insp = inspect(db.bind)
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
        # 删除冲突记录
        try:
            db.execute(text(
                f'DELETE FROM "{table_name}" WHERE user_id = :sid AND id IN '
                f'(SELECT s.id FROM "{table_name}" s '
                f'INNER JOIN "{table_name}" t ON {join_conds} AND t.user_id = :tid '
                f'WHERE s.user_id = :sid2)'
            ), {"sid": source_id, "tid": target_id, "sid2": source_id})
        except Exception:
            logger.warning(f"  {table_name}: 冲突检测失败，删除source所有记录")
            db.execute(text(f'DELETE FROM "{table_name}" WHERE user_id = :sid'), {"sid": source_id})
            return 0
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
        target_user_id: int   # 目标用户（保留）
    ) -> Dict[str, Any]:
        """
        合并两个用户

        策略：
        - 保留target_user，删除source_user
        - 自动发现所有含 user_id 的表并迁移数据
        - 合并用户信息（保留更完整的信息）
        """
        source_user = db.query(User).filter(User.id == source_user_id).first()
        target_user = db.query(User).filter(User.id == target_user_id).first()

        if not source_user or not target_user:
            raise ValueError("用户不存在")

        if source_user.id == target_user.id:
            raise ValueError("不能合并同一个用户")

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

            # 合并积分（取较大值）
            target_user.kids_points = max(
                target_user.kids_points or 0,
                source_user.kids_points or 0
            )

            # 确保合并后用户是已审批已激活
            if source_user.is_approved:
                target_user.is_approved = True
            if source_user.is_active:
                target_user.is_active = True

            # 3. 删除source用户
            db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": source_user_id})

            # 4. 提交事务
            db.commit()

            logger.info(f"成功合并用户: {source_user_id} -> {target_user_id}, 统计: {merge_stats}")

            return {
                "success": True,
                "source_user_id": source_user_id,
                "target_user_id": target_user_id,
                "stats": merge_stats
            }

        except Exception as e:
            db.rollback()
            logger.error(f"合并用户失败: {e}")
            raise
