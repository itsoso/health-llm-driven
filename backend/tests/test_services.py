"""服务层测试"""
import pytest
from datetime import date, timedelta
from app.services.goal_management import GoalManagementService
from app.services.health_analysis import HealthAnalysisService
from app.models.user import User
from app.models.goal import Goal, GoalType, GoalPeriod, GoalStatus
from app.schemas.goal import GoalCreate


def test_goal_management_service_create_goal(db, sample_user_data):
    """测试目标管理服务创建目标"""
    # 创建用户
    user = User(**sample_user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 创建目标
    service = GoalManagementService()
    goal_create = GoalCreate(
        user_id=user.id,
        goal_type=GoalType.EXERCISE,
        goal_period=GoalPeriod.DAILY,
        title="每日运动",
        target_value=30.0,
        target_unit="分钟",
        start_date=date.today()
    )
    
    goal = service.create_goal(db, goal_create)
    assert goal.id is not None
    assert goal.title == goal_create.title
    assert goal.user_id == user.id


def test_goal_management_service_get_user_goals(db, sample_user_data):
    """测试获取用户目标"""
    # 创建用户和目标
    user = User(**sample_user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    goal = Goal(
        user_id=user.id,
        goal_type=GoalType.EXERCISE,
        goal_period=GoalPeriod.DAILY,
        title="每日运动",
        target_value=30.0,
        target_unit="分钟",
        start_date=date.today()
    )
    db.add(goal)
    db.commit()
    
    # 获取目标
    service = GoalManagementService()
    goals = service.get_user_goals(db, user.id)
    assert len(goals) > 0
    assert goals[0].user_id == user.id


def test_goal_management_service_update_progress(db, sample_user_data):
    """测试更新目标进展"""
    # 创建用户和目标
    user = User(**sample_user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    goal = Goal(
        user_id=user.id,
        goal_type=GoalType.EXERCISE,
        goal_period=GoalPeriod.DAILY,
        title="每日运动",
        target_value=30.0,
        target_unit="分钟",
        start_date=date.today()
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    
    # 更新进展
    service = GoalManagementService()
    progress = service.update_goal_progress(db, goal.id, date.today(), 25.0)
    assert progress.progress_value == 25.0
    assert progress.completion_percentage is not None


def test_health_analysis_service_collect_data(db, sample_user_data):
    """测试健康分析服务数据收集"""
    # 创建用户
    user = User(**sample_user_data)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 收集数据
    service = HealthAnalysisService()
    health_data = service.collect_user_health_data(db, user.id, days=30)
    
    assert "user" in health_data
    assert "basic_health" in health_data
    assert "medical_exams" in health_data
    assert "diseases" in health_data
    assert "garmin_data" in health_data

