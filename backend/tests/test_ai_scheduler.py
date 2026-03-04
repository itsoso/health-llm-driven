"""AI 调度器服务测试"""
import pytest
from datetime import datetime, date, time, timedelta
from unittest.mock import Mock, patch, MagicMock
from app.services.ai_scheduler import AIScheduler, Reminder, ReminderType


class TestAIScheduler:
    """AI 调度器核心测试"""

    @pytest.fixture
    def scheduler(self):
        """创建调度器实例"""
        return AIScheduler()

    @pytest.fixture
    def mock_db(self):
        """模拟数据库会话"""
        db = Mock()
        # 默认 query 链返回 None
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    def test_default_reminders_created(self, scheduler):
        """测试默认提醒列表已创建"""
        assert len(scheduler.default_reminders) > 0
        assert all(isinstance(r, Reminder) for r in scheduler.default_reminders)

    def test_reminder_to_dict(self, scheduler):
        """测试提醒对象转字典"""
        reminder = scheduler.default_reminders[0]
        d = reminder.to_dict()
        assert 'type' in d
        assert 'title' in d
        assert 'message' in d
        assert 'scheduled_time' in d
        assert 'priority' in d

    @patch('app.services.ai_scheduler.get_china_now')
    def test_time_greeting_morning(self, mock_now, scheduler):
        """测试早晨问候语"""
        mock_now.return_value = datetime(2026, 1, 17, 7, 0, 0)
        greeting = scheduler._get_time_greeting()
        assert '早安' in greeting

    @patch('app.services.ai_scheduler.get_china_now')
    def test_time_greeting_afternoon(self, mock_now, scheduler):
        """测试下午问候语"""
        mock_now.return_value = datetime(2026, 1, 17, 15, 0, 0)
        greeting = scheduler._get_time_greeting()
        assert '下午好' in greeting

    @patch('app.services.ai_scheduler.get_china_now')
    def test_time_greeting_evening(self, mock_now, scheduler):
        """测试晚间问候语"""
        mock_now.return_value = datetime(2026, 1, 17, 20, 0, 0)
        greeting = scheduler._get_time_greeting()
        assert '晚上好' in greeting

    @patch('app.services.ai_scheduler.get_china_now')
    def test_time_greeting_night(self, mock_now, scheduler):
        """测试深夜问候语"""
        mock_now.return_value = datetime(2026, 1, 17, 23, 30, 0)
        greeting = scheduler._get_time_greeting()
        assert '休息' in greeting

    def test_detect_checkin_action_water(self, scheduler):
        """测试识别喝水打卡"""
        assert scheduler._detect_checkin_action("喝水补充水分") == "water"
        assert scheduler._detect_checkin_action("饮水200ml") == "water"

    def test_detect_checkin_action_nasal(self, scheduler):
        """测试识别洗鼻打卡"""
        assert scheduler._detect_checkin_action("完成早间洗鼻") == "nasal_wash"

    def test_detect_checkin_action_exercise(self, scheduler):
        """测试识别运动打卡"""
        assert scheduler._detect_checkin_action("跑步30分钟") == "exercise"
        assert scheduler._detect_checkin_action("深蹲训练") == "exercise"

    def test_detect_checkin_action_none(self, scheduler):
        """测试无法识别的文本"""
        assert scheduler._detect_checkin_action("今天天气不错") is None


class TestMorningBriefing:
    """早间简报测试"""

    @pytest.fixture
    def scheduler(self):
        return AIScheduler()

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @patch('app.services.ai_scheduler.get_china_now')
    @patch('app.services.ai_scheduler.get_china_today')
    def test_briefing_structure(self, mock_today, mock_now, scheduler, mock_db):
        """测试早间简报结构"""
        mock_today.return_value = date(2026, 1, 17)
        mock_now.return_value = datetime(2026, 1, 17, 8, 0, 0)

        briefing = scheduler.generate_morning_briefing(mock_db, user_id=1)

        assert 'date' in briefing
        assert 'greeting' in briefing
        assert 'sections' in briefing
        assert isinstance(briefing['sections'], list)

    @patch('app.services.ai_scheduler.get_china_now')
    @patch('app.services.ai_scheduler.get_china_today')
    def test_briefing_with_sleep_data(self, mock_today, mock_now, scheduler, mock_db):
        """测试有睡眠数据时的简报"""
        mock_today.return_value = date(2026, 1, 17)
        mock_now.return_value = datetime(2026, 1, 17, 8, 0, 0)

        mock_garmin = Mock()
        mock_garmin.sleep_score = 85
        mock_garmin.total_sleep_duration = 480
        mock_garmin.deep_sleep_duration = 120
        mock_garmin.body_battery_most_charged = 80
        mock_garmin.resting_heart_rate = 60
        mock_garmin.stress_level = 30
        mock_garmin.record_date = date(2026, 1, 17)

        # 第一次 query(GarminData) 返回 mock_garmin（今天的数据）
        # 第二次 query(CheckinRecord) 返回 None
        # 第三次 query(UserProfile) 返回 None
        call_count = [0]
        def side_effect_filter(*args, **kwargs):
            result = Mock()
            call_count[0] += 1
            if call_count[0] <= 2:
                # UserProfile query 和 GarminData query
                result.first.return_value = mock_garmin if call_count[0] == 2 else None
            else:
                result.first.return_value = None
            return result

        # 简化：让所有 query 都返回正确的链
        mock_filter = Mock()
        mock_filter.first.return_value = None

        # UserProfile -> None, GarminData(today) -> mock_garmin, GarminData(yesterday) -> skip, CheckinRecord -> None
        query_results = [None, mock_garmin, None]
        call_idx = [0]
        def query_side_effect(*args, **kwargs):
            mock_q = Mock()
            def filter_side_effect(*a, **kw):
                mock_f = Mock()
                idx = call_idx[0]
                call_idx[0] += 1
                if idx < len(query_results):
                    mock_f.first.return_value = query_results[idx]
                else:
                    mock_f.first.return_value = None
                return mock_f
            mock_q.filter.return_value = filter_side_effect()
            # 用 side_effect 让 filter 每次调用返回不同值不太方便
            # 直接用 side_effect on filter
            mock_q.filter = Mock(side_effect=lambda *a, **kw: Mock(first=Mock(return_value=query_results[min(call_idx[0], len(query_results)-1)])))
            return mock_q

        # 更简单的方式：直接 patch db.query 的 filter chain
        # 按调用顺序：1. UserProfile(None), 2. GarminData today(mock_garmin), 3. CheckinRecord(None)
        filter_results = iter([None, mock_garmin, None])
        def make_filter(*args, **kwargs):
            result_mock = Mock()
            result_mock.first.return_value = next(filter_results, None)
            return result_mock
        mock_db.query.return_value.filter.side_effect = make_filter

        briefing = scheduler.generate_morning_briefing(mock_db, user_id=1)

        # 应该有睡眠相关区块
        sleep_sections = [s for s in briefing['sections'] if '睡眠' in s['title']]
        assert len(sleep_sections) > 0
        assert briefing['sections'][0]['status'] == 'good'

    @patch('app.services.ai_scheduler.get_china_now')
    @patch('app.services.ai_scheduler.get_china_today')
    def test_briefing_no_data(self, mock_today, mock_now, scheduler, mock_db):
        """测试无数据时的简报"""
        mock_today.return_value = date(2026, 1, 17)
        mock_now.return_value = datetime(2026, 1, 17, 8, 0, 0)

        briefing = scheduler.generate_morning_briefing(mock_db, user_id=1)

        assert 'date' in briefing
        assert 'greeting' in briefing
        # 即使没有 Garmin 数据，也应有目标和提醒 sections
        assert len(briefing['sections']) >= 2


class TestReminders:
    """提醒功能测试"""

    @pytest.fixture
    def scheduler(self):
        return AIScheduler()

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @patch('app.services.ai_scheduler.get_china_now')
    def test_reminders_at_7am(self, mock_now, scheduler, mock_db):
        """测试早上7点的提醒"""
        current = datetime(2026, 1, 17, 7, 0, 0)
        mock_now.return_value = current

        reminders = scheduler.get_reminders_for_time(mock_db, user_id=1, current_time=current)

        assert isinstance(reminders, list)
        # 7:00 应该有洗鼻提醒 (scheduled_time=7:00)
        if reminders:
            types = [r['type'] for r in reminders]
            assert 'nasal_wash' in types

    @patch('app.services.ai_scheduler.get_china_now')
    def test_reminders_at_noon(self, mock_now, scheduler, mock_db):
        """测试中午12点的提醒"""
        current = datetime(2026, 1, 17, 12, 0, 0)
        mock_now.return_value = current

        reminders = scheduler.get_reminders_for_time(mock_db, user_id=1, current_time=current)

        assert isinstance(reminders, list)
        # 12:00 应该有午餐提醒
        if reminders:
            types = [r['type'] for r in reminders]
            assert 'meal' in types

    @patch('app.services.ai_scheduler.get_china_now')
    def test_reminders_at_night(self, mock_now, scheduler, mock_db):
        """测试晚上21点的提醒"""
        current = datetime(2026, 1, 17, 21, 0, 0)
        mock_now.return_value = current

        reminders = scheduler.get_reminders_for_time(mock_db, user_id=1, current_time=current)

        assert isinstance(reminders, list)
        # 21:00 应该有洗鼻提醒
        if reminders:
            types = [r['type'] for r in reminders]
            assert 'nasal_wash' in types

    @patch('app.services.ai_scheduler.get_china_today')
    @patch('app.services.ai_scheduler.get_china_now')
    def test_exercise_reminder_skipped_if_workout_done(self, mock_now, mock_today, scheduler, mock_db):
        """测试已运动时跳过运动提醒"""
        current = datetime(2026, 1, 17, 18, 30, 0)
        mock_now.return_value = current
        mock_today.return_value = date(2026, 1, 17)

        # 模拟今天已有运动记录
        mock_workout = Mock()
        filter_results = iter([None, mock_workout])  # UserProfile=None, WorkoutRecord=exists
        def make_filter(*args, **kwargs):
            result_mock = Mock()
            result_mock.first.return_value = next(filter_results, None)
            return result_mock
        mock_db.query.return_value.filter.side_effect = make_filter

        reminders = scheduler.get_reminders_for_time(mock_db, user_id=1, current_time=current)

        # 运动提醒应该被跳过
        exercise_reminders = [r for r in reminders if r['type'] == 'exercise']
        assert len(exercise_reminders) == 0


class TestDailySchedule:
    """日程生成测试"""

    @pytest.fixture
    def scheduler(self):
        return AIScheduler()

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @patch('app.services.ai_scheduler.get_china_today')
    def test_schedule_structure(self, mock_today, scheduler, mock_db):
        """测试日程结构"""
        mock_today.return_value = date(2026, 1, 17)

        schedule = scheduler.generate_daily_schedule(mock_db, user_id=1)

        assert isinstance(schedule, list)
        assert len(schedule) > 0

        item = schedule[0]
        assert 'time' in item
        assert 'activity' in item
        assert 'category' in item
        assert 'duration_minutes' in item
        assert 'tasks' in item

    @patch('app.services.ai_scheduler.get_china_today')
    def test_schedule_categories(self, mock_today, scheduler, mock_db):
        """测试日程分类有效性"""
        mock_today.return_value = date(2026, 1, 17)

        schedule = scheduler.generate_daily_schedule(mock_db, user_id=1)

        valid_categories = ['routine', 'meal', 'work', 'exercise', 'rest', 'leisure', 'sleep']
        for item in schedule:
            assert item['category'] in valid_categories

    @patch('app.services.ai_scheduler.get_china_today')
    def test_schedule_with_profile(self, mock_today, scheduler, mock_db):
        """测试有用户画像时的日程"""
        mock_today.return_value = date(2026, 1, 17)

        mock_profile = Mock()
        mock_profile.usual_wake_time = "06:30"
        mock_profile.usual_sleep_time = "22:00"
        mock_profile.target_exercise_minutes = 45
        mock_profile.target_sleep_hours = 8

        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        schedule = scheduler.generate_daily_schedule(mock_db, user_id=1)

        # 起床时间应该是 06:30
        assert schedule[0]['time'] == '06:30'
        # 睡觉时间应该是 22:00
        assert schedule[-1]['time'] == '22:00'


class TestTimeAwareRecommendation:
    """时间感知建议测试"""

    @pytest.fixture
    def scheduler(self):
        return AIScheduler()

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @patch('app.services.ai_scheduler.get_china_today')
    @patch('app.services.ai_scheduler.get_china_now')
    def test_recommendation_structure(self, mock_now, mock_today, scheduler, mock_db):
        """测试建议结构"""
        current = datetime(2026, 1, 17, 10, 0, 0)
        mock_now.return_value = current
        mock_today.return_value = date(2026, 1, 17)

        rec = scheduler.get_time_aware_recommendation(mock_db, user_id=1, current_time=current)

        assert 'timestamp' in rec
        assert 'primary' in rec
        assert 'secondary' in rec
        assert 'status' in rec

    @patch('app.services.ai_scheduler.get_china_today')
    @patch('app.services.ai_scheduler.get_china_now')
    def test_morning_recommendation(self, mock_now, mock_today, scheduler, mock_db):
        """测试早晨建议"""
        current = datetime(2026, 1, 17, 7, 0, 0)
        mock_now.return_value = current
        mock_today.return_value = date(2026, 1, 17)

        rec = scheduler.get_time_aware_recommendation(mock_db, user_id=1, current_time=current)

        assert rec['primary']['icon'] == '🌅'
        assert '早安' in rec['primary']['title']

    @patch('app.services.ai_scheduler.get_china_today')
    @patch('app.services.ai_scheduler.get_china_now')
    def test_noon_recommendation(self, mock_now, mock_today, scheduler, mock_db):
        """测试午间建议"""
        current = datetime(2026, 1, 17, 12, 30, 0)
        mock_now.return_value = current
        mock_today.return_value = date(2026, 1, 17)

        rec = scheduler.get_time_aware_recommendation(mock_db, user_id=1, current_time=current)

        assert rec['primary']['icon'] == '🍱'
        assert '午餐' in rec['primary']['title']

    @patch('app.services.ai_scheduler.get_china_today')
    @patch('app.services.ai_scheduler.get_china_now')
    def test_night_recommendation(self, mock_now, mock_today, scheduler, mock_db):
        """测试晚间建议"""
        current = datetime(2026, 1, 17, 22, 0, 0)
        mock_now.return_value = current
        mock_today.return_value = date(2026, 1, 17)

        rec = scheduler.get_time_aware_recommendation(mock_db, user_id=1, current_time=current)

        assert rec['primary']['icon'] == '🌙'
        assert '睡前' in rec['primary']['title']

    @patch('app.services.ai_scheduler.get_china_today')
    @patch('app.services.ai_scheduler.get_china_now')
    def test_evening_with_workout_done(self, mock_now, mock_today, scheduler, mock_db):
        """测试傍晚已运动的建议"""
        current = datetime(2026, 1, 17, 19, 0, 0)
        mock_now.return_value = current
        mock_today.return_value = date(2026, 1, 17)

        mock_workout = Mock()
        # UserProfile=None, GarminData=None, WorkoutRecord=exists
        filter_results = iter([None, None, mock_workout])
        def make_filter(*args, **kwargs):
            result_mock = Mock()
            result_mock.first.return_value = next(filter_results, None)
            return result_mock
        mock_db.query.return_value.filter.side_effect = make_filter

        rec = scheduler.get_time_aware_recommendation(mock_db, user_id=1, current_time=current)

        assert rec['primary']['icon'] == '✅'
        assert '已完成' in rec['primary']['title']
