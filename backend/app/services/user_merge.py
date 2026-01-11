"""用户合并服务 - 合并小程序用户和PC用户"""
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.models.user import User, GarminCredential
from app.models.daily_health import GarminData, HealthCheckin
from app.models.basic_health import Weight, BloodPressure
from app.models.goal import Goal
from app.models.habit import Habit
from app.models.supplement import Supplement
from app.models.medical_exam import MedicalExam

logger = logging.getLogger(__name__)


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
    def merge_users(
        db: Session,
        source_user_id: int,  # 被合并的用户（将被删除）
        target_user_id: int   # 目标用户（保留）
    ) -> Dict[str, Any]:
        """
        合并两个用户
        
        策略：
        - 保留target_user，删除source_user
        - 将所有source_user的数据迁移到target_user
        - 合并用户信息（保留更完整的信息）
        """
        source_user = db.query(User).filter(User.id == source_user_id).first()
        target_user = db.query(User).filter(User.id == target_user_id).first()
        
        if not source_user or not target_user:
            raise ValueError("用户不存在")
        
        if source_user.id == target_user.id:
            raise ValueError("不能合并同一个用户")
        
        merge_stats = {
            "garmin_credentials": 0,
            "garmin_data": 0,
            "health_checkins": 0,
            "weights": 0,
            "blood_pressures": 0,
            "goals": 0,
            "habits": 0,
            "supplements": 0,
            "medical_exams": 0,
        }
        
        try:
            # 1. 合并Garmin凭证（如果target没有，source有）
            source_cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == source_user_id
            ).first()
            target_cred = db.query(GarminCredential).filter(
                GarminCredential.user_id == target_user_id
            ).first()
            
            if source_cred and not target_cred:
                source_cred.user_id = target_user_id
                merge_stats["garmin_credentials"] = 1
                logger.info(f"迁移Garmin凭证: {source_user_id} -> {target_user_id}")
            elif source_cred and target_cred:
                # 如果target已有凭证，删除source的凭证
                db.delete(source_cred)
                logger.info(f"删除重复的Garmin凭证: {source_user_id}")
            
            # 2. 合并健康数据
            # Garmin数据
            garmin_data_count = db.query(GarminData).filter(
                GarminData.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["garmin_data"] = garmin_data_count
            
            # 健康打卡
            checkin_count = db.query(HealthCheckin).filter(
                HealthCheckin.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["health_checkins"] = checkin_count
            
            # 体重
            weight_count = db.query(Weight).filter(
                Weight.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["weights"] = weight_count
            
            # 血压
            bp_count = db.query(BloodPressure).filter(
                BloodPressure.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["blood_pressures"] = bp_count
            
            # 目标
            goal_count = db.query(Goal).filter(
                Goal.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["goals"] = goal_count
            
            # 习惯
            habit_count = db.query(Habit).filter(
                Habit.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["habits"] = habit_count
            
            # 补剂
            supplement_count = db.query(Supplement).filter(
                Supplement.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["supplements"] = supplement_count
            
            # 体检记录
            exam_count = db.query(MedicalExam).filter(
                MedicalExam.user_id == source_user_id
            ).update({"user_id": target_user_id})
            merge_stats["medical_exams"] = exam_count
            
            # 3. 合并用户基础信息（保留更完整的信息）
            # 如果target没有某些字段，使用source的
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
            
            # 合并微信信息（如果source有微信信息，target没有）
            if not target_user.wechat_openid and source_user.wechat_openid:
                target_user.wechat_openid = source_user.wechat_openid
            if not target_user.wechat_unionid and source_user.wechat_unionid:
                target_user.wechat_unionid = source_user.wechat_unionid
            if not target_user.wechat_session_key and source_user.wechat_session_key:
                target_user.wechat_session_key = source_user.wechat_session_key
            
            # 合并密码（如果target没有密码，使用source的）
            if not target_user.hashed_password and source_user.hashed_password:
                target_user.hashed_password = source_user.hashed_password
            
            # 4. 删除source用户
            db.delete(source_user)
            
            # 5. 提交事务
            db.commit()
            
            logger.info(f"✅ 成功合并用户: {source_user_id} -> {target_user_id}, 统计数据: {merge_stats}")
            
            return {
                "success": True,
                "source_user_id": source_user_id,
                "target_user_id": target_user_id,
                "stats": merge_stats
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ 合并用户失败: {e}")
            raise
