"""测试目标管理功能"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.services.goal_management import GoalManagementService
from app.schemas.goal import GoalCreate
from app.models.goal import GoalType, GoalPeriod


def test_goals():
    """测试目标管理功能"""
    db: Session = SessionLocal()
    service = GoalManagementService()
    
    try:
        print("=" * 60)
        print("测试目标管理功能")
        print("=" * 60)
        
        # 1. 创建一个每日运动目标
        print("\n1. 创建每日运动目标...")
        exercise_goal = GoalCreate(
            user_id=1,
            goal_type=GoalType.EXERCISE,
            goal_period=GoalPeriod.DAILY,
            title="每日运动30分钟",
            description="保持每天至少30分钟中等强度运动",
            target_value=30.0,
            target_unit="分钟",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            implementation_steps="1. 早起慢跑15分钟\n2. 晚上做力量训练15分钟\n3. 可以分多次完成",
            priority=8
        )
        
        goal = service.create_goal(db, exercise_goal)
        print(f"✅ 成功创建目标: {goal.title} (ID: {goal.id})")
        print(f"   类型: {goal.goal_type.value}")
        print(f"   周期: {goal.goal_period.value}")
        print(f"   目标值: {goal.target_value} {goal.target_unit}")
        print(f"   优先级: {goal.priority}/10")
        
        # 2. 创建一个每日睡眠目标
        print("\n2. 创建每日睡眠目标...")
        sleep_goal = GoalCreate(
            user_id=1,
            goal_type=GoalType.SLEEP,
            goal_period=GoalPeriod.DAILY,
            title="保证充足睡眠",
            description="每晚保证7-8小时优质睡眠",
            target_value=8.0,
            target_unit="小时",
            start_date=date.today(),
            implementation_steps="1. 晚上10:30上床\n2. 早上6:30起床\n3. 睡前1小时不使用电子设备",
            priority=9
        )
        
        sleep_goal_db = service.create_goal(db, sleep_goal)
        print(f"✅ 成功创建目标: {sleep_goal_db.title} (ID: {sleep_goal_db.id})")
        
        # 3. 创建一个每周目标
        print("\n3. 创建每周运动目标...")
        weekly_goal = GoalCreate(
            user_id=1,
            goal_type=GoalType.EXERCISE,
            goal_period=GoalPeriod.WEEKLY,
            title="每周跑步3次",
            description="每周至少跑步3次，每次5公里",
            target_value=3.0,
            target_unit="次",
            start_date=date.today(),
            implementation_steps="1. 周一/三/五早起跑步\n2. 每次至少5公里\n3. 控制配速在6-7分钟/公里",
            priority=7
        )
        
        weekly_goal_db = service.create_goal(db, weekly_goal)
        print(f"✅ 成功创建目标: {weekly_goal_db.title} (ID: {weekly_goal_db.id})")
        
        # 4. 获取用户的所有目标
        print("\n4. 获取用户的所有目标...")
        user_goals = service.get_user_goals(db, user_id=1)
        print(f"✅ 找到 {len(user_goals)} 个目标:")
        for g in user_goals:
            print(f"   - {g.title} ({g.goal_type.value}, {g.goal_period.value})")
            print(f"     目标: {g.target_value} {g.target_unit}, 当前: {g.current_value or 0} {g.target_unit}")
        
        # 5. 更新目标进度
        print("\n5. 更新目标进度...")
        progress = service.update_goal_progress(
            db,
            goal_id=goal.id,
            progress_date=date.today(),
            progress_value=25.0
        )
        print(f"✅ 成功更新进度: {progress.progress_value} {goal.target_unit}")
        print(f"   完成百分比: {progress.completion_percentage:.1f}%")
        
        # 6. 检查目标完成情况
        print("\n6. 检查目标完成情况...")
        completion = service.check_goal_completion(db, goal_id=goal.id)
        print(f"✅ 目标完成情况:")
        print(f"   目标: {completion['goal_title']}")
        print(f"   当前值: {completion['current_value']} / {completion['target_value']}")
        print(f"   完成度: {completion['completion_percentage']:.1f}%")
        print(f"   是否完成: {'是' if completion['is_completed'] else '否'}")
        
        # 7. 获取目标的进展记录
        print("\n7. 获取目标的进展记录...")
        progress_list = service.get_goal_progress(db, goal_id=goal.id)
        print(f"✅ 找到 {len(progress_list)} 条进展记录:")
        for p in progress_list:
            print(f"   - {p.progress_date}: {p.progress_value} ({p.completion_percentage:.1f}%)")
        
        # 8. 测试按类型筛选
        print("\n8. 按类型筛选目标...")
        exercise_goals = service.get_user_goals(db, user_id=1, goal_type=GoalType.EXERCISE)
        print(f"✅ 找到 {len(exercise_goals)} 个运动类目标:")
        for g in exercise_goals:
            print(f"   - {g.title}")
        
        # 9. 测试按周期筛选
        print("\n9. 按周期筛选目标...")
        daily_goals = service.get_user_goals(db, user_id=1, goal_period=GoalPeriod.DAILY)
        print(f"✅ 找到 {len(daily_goals)} 个每日目标:")
        for g in daily_goals:
            print(f"   - {g.title}")
        
        print("\n" + "=" * 60)
        print("✅ 目标管理功能测试完成!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()
    
    return True


if __name__ == "__main__":
    success = test_goals()
    sys.exit(0 if success else 1)

