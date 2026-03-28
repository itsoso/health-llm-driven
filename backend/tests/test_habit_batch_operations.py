"""习惯批量操作测试 - 测试优化后的批量计算函数"""
import pytest
from datetime import date, timedelta
from app.models.user import User
from app.models.habit import HabitDefinition, HabitRecord
from app.api.habits import calculate_streak, calculate_streaks_batch


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="batchtest",
        email="batch@example.com",
        hashed_password="hashed_password",
        name="批量测试用户",
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_habit(db, test_user):
    """创建测试习惯"""
    habit = HabitDefinition(
        user_id=test_user.id,
        name="测试习惯",
        category="健康",
        is_active=True
    )
    db.add(habit)
    db.commit()
    db.refresh(habit)
    return habit


class TestCalculateStreak:
    """测试单个习惯连续打卡计算"""

    def test_streak_no_records(self, db, test_habit):
        """测试没有记录时连续天数为0"""
        streak = calculate_streak(db, test_habit.id, date.today())
        assert streak == 0

    def test_streak_today_only(self, db, test_user, test_habit):
        """测试只有今天打卡"""
        today = date.today()
        record = HabitRecord(
            habit_id=test_habit.id,
            user_id=test_user.id,
            record_date=today,
            completed=True
        )
        db.add(record)
        db.commit()

        streak = calculate_streak(db, test_habit.id, today)
        assert streak == 1

    def test_streak_consecutive_days(self, db, test_user, test_habit):
        """测试连续5天打卡"""
        today = date.today()
        for i in range(5):
            record = HabitRecord(
                habit_id=test_habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=True
            )
            db.add(record)
        db.commit()

        streak = calculate_streak(db, test_habit.id, today)
        assert streak == 5

    def test_streak_broken_chain(self, db, test_user, test_habit):
        """测试中断的连续打卡（第3天未打卡）"""
        today = date.today()
        # 今天和昨天打卡
        for i in range(2):
            record = HabitRecord(
                habit_id=test_habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=True
            )
            db.add(record)
        # 跳过第3天，第4、5天打卡
        for i in range(3, 5):
            record = HabitRecord(
                habit_id=test_habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=True
            )
            db.add(record)
        db.commit()

        streak = calculate_streak(db, test_habit.id, today)
        assert streak == 2  # 只计算今天和昨天

    def test_streak_not_completed(self, db, test_user, test_habit):
        """测试打卡但未完成的记录不计入连续天数"""
        today = date.today()
        for i in range(3):
            record = HabitRecord(
                habit_id=test_habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=i != 1  # 昨天未完成
            )
            db.add(record)
        db.commit()

        streak = calculate_streak(db, test_habit.id, today)
        assert streak == 1  # 只有今天

    def test_streak_max_90_days(self, db, test_user, test_habit):
        """测试连续天数上限为90天"""
        today = date.today()
        # 创建100天的记录
        for i in range(100):
            record = HabitRecord(
                habit_id=test_habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=True
            )
            db.add(record)
        db.commit()

        streak = calculate_streak(db, test_habit.id, today)
        # 由于只查询90天内的记录，最多返回91天
        assert streak <= 91


class TestCalculateStreaksBatch:
    """测试批量计算多个习惯的连续打卡天数"""

    def test_batch_empty_list(self, db):
        """测试空习惯列表"""
        result = calculate_streaks_batch(db, [], date.today())
        assert result == {}

    def test_batch_single_habit(self, db, test_user, test_habit):
        """测试单个习惯的批量计算"""
        today = date.today()
        for i in range(3):
            record = HabitRecord(
                habit_id=test_habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=True
            )
            db.add(record)
        db.commit()

        result = calculate_streaks_batch(db, [test_habit.id], today)
        assert test_habit.id in result
        assert result[test_habit.id] == 3

    def test_batch_multiple_habits(self, db, test_user):
        """测试多个习惯的批量计算"""
        today = date.today()
        habits = []

        # 创建3个习惯，每个有不同的连续天数
        for j in range(3):
            habit = HabitDefinition(
                user_id=test_user.id,
                name=f"习惯{j+1}",
                category="健康",
                is_active=True
            )
            db.add(habit)
            db.commit()
            db.refresh(habit)
            habits.append(habit)

            # 第1个习惯5天连续，第2个3天，第3个0天
            streak_days = [5, 3, 0][j]
            for i in range(streak_days):
                record = HabitRecord(
                    habit_id=habit.id,
                    user_id=test_user.id,
                    record_date=today - timedelta(days=i),
                    completed=True
                )
                db.add(record)
        db.commit()

        habit_ids = [h.id for h in habits]
        result = calculate_streaks_batch(db, habit_ids, today)

        assert len(result) == 3
        assert result[habits[0].id] == 5
        assert result[habits[1].id] == 3
        assert result[habits[2].id] == 0

    def test_batch_efficiency(self, db, test_user):
        """测试批量计算的效率（结果正确性验证）"""
        today = date.today()
        habits = []

        # 创建2个习惯
        for j in range(2):
            habit = HabitDefinition(
                user_id=test_user.id,
                name=f"习惯{j+1}",
                category="健康",
                is_active=True
            )
            db.add(habit)
            db.commit()
            db.refresh(habit)
            habits.append(habit)

            # 每个习惯创建2天记录
            for i in range(2):
                record = HabitRecord(
                    habit_id=habit.id,
                    user_id=test_user.id,
                    record_date=today - timedelta(days=i),
                    completed=True
                )
                db.add(record)
        db.commit()

        # 批量计算
        habit_ids = [h.id for h in habits]
        result = calculate_streaks_batch(db, habit_ids, today)

        # 验证结果正确
        assert result[habits[0].id] == 2
        assert result[habits[1].id] == 2

        # 验证单独计算也得到相同结果
        for habit in habits:
            individual_streak = calculate_streak(db, habit.id, today)
            assert individual_streak == result[habit.id]

    def test_batch_nonexistent_habits(self, db, test_user):
        """测试不存在的习惯ID"""
        result = calculate_streaks_batch(db, [9999, 9998], date.today())
        assert result[9999] == 0
        assert result[9998] == 0

    def test_batch_mixed_completion(self, db, test_user):
        """测试混合完成状态的记录"""
        today = date.today()
        habit = HabitDefinition(
            user_id=test_user.id,
            name="混合习惯",
            category="健康",
            is_active=True
        )
        db.add(habit)
        db.commit()
        db.refresh(habit)

        # 今天完成，昨天未完成，前天完成
        for i, completed in enumerate([True, False, True]):
            record = HabitRecord(
                habit_id=habit.id,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                completed=completed
            )
            db.add(record)
        db.commit()

        result = calculate_streaks_batch(db, [habit.id], today)
        assert result[habit.id] == 1  # 只有今天


class TestHabitEndpointOptimization:
    """测试习惯API端点的N+1查询优化（注意：habits路由已在main.py中禁用）"""

    def test_batch_streak_calculation_integration(self, db, test_user):
        """测试批量连续天数计算的集成场景"""
        today = date.today()

        # 创建5个习惯，每个有不同的连续天数
        habits = []
        for j in range(5):
            habit = HabitDefinition(
                user_id=test_user.id,
                name=f"习惯{j+1}",
                category="健康",
                is_active=True
            )
            db.add(habit)
            db.commit()
            db.refresh(habit)
            habits.append(habit)

            # 每个习惯创建连续记录：第1个1天，第2个2天...
            for i in range(j + 1):
                record = HabitRecord(
                    habit_id=habit.id,
                    user_id=test_user.id,
                    record_date=today - timedelta(days=i),
                    completed=True
                )
                db.add(record)
        db.commit()

        # 使用批量函数计算
        habit_ids = [h.id for h in habits]
        result = calculate_streaks_batch(db, habit_ids, today)

        # 验证每个习惯的连续天数
        for i, habit in enumerate(habits):
            assert result[habit.id] == i + 1

    def test_today_summary_data(self, db, test_user):
        """测试今日汇总数据计算"""
        today = date.today()

        # 创建10个习惯，5个已完成
        habit_ids = []
        for j in range(10):
            habit = HabitDefinition(
                user_id=test_user.id,
                name=f"习惯{j+1}",
                category="健康",
                is_active=True
            )
            db.add(habit)
            db.commit()
            db.refresh(habit)
            habit_ids.append(habit.id)

            if j < 5:  # 前5个今天完成
                record = HabitRecord(
                    habit_id=habit.id,
                    user_id=test_user.id,
                    record_date=today,
                    completed=True
                )
                db.add(record)
        db.commit()

        # 查询今日完成的记录数
        from sqlalchemy import and_
        completed_count = db.query(HabitRecord).filter(
            HabitRecord.habit_id.in_(habit_ids),
            HabitRecord.record_date == today,
            HabitRecord.completed == True
        ).count()

        assert completed_count == 5

        # 验证批量计算连续天数
        completed_habits = habit_ids[:5]
        streaks = calculate_streaks_batch(db, completed_habits, today)

        for habit_id in completed_habits:
            assert streaks[habit_id] == 1  # 只有今天
