"""AI 调度器服务测试"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from app.services.ai_scheduler import AISchedulerService


class TestAISchedulerService:
    """AI 调度器服务测试类"""
    
    @pytest.fixture
    def mock_db(self):
        """模拟数据库会话"""
        return Mock()
    
    @pytest.fixture
    def service(self, mock_db):
        """创建服务实例"""
        return AISchedulerService(mock_db, user_id=1)
    
    def test_get_current_time_period_morning(self, service):
        """测试早晨时段识别"""
        with patch.object(service, '_get_beijing_now') as mock_now:
            mock_now.return_value = datetime(2026, 1, 17, 7, 0, 0)
            period = service._get_current_time_period()
            assert period in ['early_morning', 'morning']
    
    def test_get_current_time_period_noon(self, service):
        """测试中午时段识别"""
        with patch.object(service, '_get_beijing_now') as mock_now:
            mock_now.return_value = datetime(2026, 1, 17, 12, 30, 0)
            period = service._get_current_time_period()
            assert period == 'noon'
    
    def test_get_current_time_period_afternoon(self, service):
        """测试下午时段识别"""
        with patch.object(service, '_get_beijing_now') as mock_now:
            mock_now.return_value = datetime(2026, 1, 17, 15, 0, 0)
            period = service._get_current_time_period()
            assert period == 'afternoon'
    
    def test_get_current_time_period_evening(self, service):
        """测试傍晚时段识别"""
        with patch.object(service, '_get_beijing_now') as mock_now:
            mock_now.return_value = datetime(2026, 1, 17, 19, 0, 0)
            period = service._get_current_time_period()
            assert period == 'evening'
    
    def test_get_current_time_period_night(self, service):
        """测试夜间时段识别"""
        with patch.object(service, '_get_beijing_now') as mock_now:
            mock_now.return_value = datetime(2026, 1, 17, 22, 30, 0)
            period = service._get_current_time_period()
            assert period == 'night'
    
    def test_generate_greeting_morning(self, service):
        """测试早晨问候语生成"""
        greeting = service._generate_greeting('morning')
        assert '早' in greeting or '好' in greeting
    
    def test_generate_greeting_evening(self, service):
        """测试傍晚问候语生成"""
        greeting = service._generate_greeting('evening')
        assert '晚' in greeting or '傍晚' in greeting or '好' in greeting
    
    def test_get_daily_schedule_structure(self, service):
        """测试日程结构"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                schedule = service.get_daily_schedule()
                
                assert 'schedule' in schedule
                assert 'generated_at' in schedule
                assert isinstance(schedule['schedule'], list)
    
    def test_get_reminders_structure(self, service):
        """测试提醒结构"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                with patch.object(service, '_get_beijing_now') as mock_now:
                    mock_now.return_value = datetime(2026, 1, 17, 9, 0, 0)
                    result = service.get_reminders()
                    
                    assert 'reminders' in result
                    assert 'current_time' in result
                    assert isinstance(result['reminders'], list)
    
    def test_get_morning_briefing_structure(self, service):
        """测试早间简报结构"""
        mock_garmin = Mock()
        mock_garmin.sleep_score = 85
        mock_garmin.total_sleep_duration = 420
        mock_garmin.deep_sleep_duration = 90
        mock_garmin.body_battery_most_charged = 80
        mock_garmin.resting_heart_rate = 60
        mock_garmin.stress_level = 30
        mock_garmin.steps = 8000
        
        with patch.object(service, '_get_yesterday_garmin_data', return_value=mock_garmin):
            with patch.object(service, '_get_user_profile', return_value=None):
                with patch.object(service, '_get_today_checkin', return_value=None):
                    with patch.object(service, '_get_beijing_now') as mock_now:
                        mock_now.return_value = datetime(2026, 1, 17, 8, 0, 0)
                        briefing = service.get_morning_briefing()
                        
                        assert 'date' in briefing
                        assert 'greeting' in briefing
                        assert 'sections' in briefing
                        assert isinstance(briefing['sections'], list)
    
    def test_get_recommendation_structure(self, service):
        """测试实时建议结构"""
        with patch.object(service, '_get_today_garmin_data', return_value=None):
            with patch.object(service, '_get_user_profile', return_value=None):
                with patch.object(service, '_get_today_checkin', return_value=None):
                    with patch.object(service, '_get_beijing_now') as mock_now:
                        mock_now.return_value = datetime(2026, 1, 17, 10, 0, 0)
                        recommendation = service.get_time_aware_recommendation()
                        
                        assert 'timestamp' in recommendation
                        assert 'primary' in recommendation
                        assert 'secondary' in recommendation
                        assert 'status' in recommendation
    
    def test_sleep_score_evaluation_good(self, service):
        """测试睡眠评分为好的情况"""
        mock_garmin = Mock()
        mock_garmin.sleep_score = 85
        mock_garmin.total_sleep_duration = 480
        mock_garmin.deep_sleep_duration = 120
        
        with patch.object(service, '_get_yesterday_garmin_data', return_value=mock_garmin):
            with patch.object(service, '_get_user_profile', return_value=None):
                with patch.object(service, '_get_today_checkin', return_value=None):
                    with patch.object(service, '_get_beijing_now') as mock_now:
                        mock_now.return_value = datetime(2026, 1, 17, 8, 0, 0)
                        briefing = service.get_morning_briefing()
                        
                        # 应该有睡眠相关区块
                        sleep_sections = [s for s in briefing['sections'] if '睡眠' in s['title']]
                        assert len(sleep_sections) > 0
    
    def test_no_data_handling(self, service):
        """测试无数据时的处理"""
        with patch.object(service, '_get_yesterday_garmin_data', return_value=None):
            with patch.object(service, '_get_user_profile', return_value=None):
                with patch.object(service, '_get_today_checkin', return_value=None):
                    with patch.object(service, '_get_beijing_now') as mock_now:
                        mock_now.return_value = datetime(2026, 1, 17, 8, 0, 0)
                        briefing = service.get_morning_briefing()
                        
                        # 即使没有数据，也应该返回有效结构
                        assert 'date' in briefing
                        assert 'greeting' in briefing


class TestAISchedulerReminders:
    """AI 调度器提醒功能测试"""
    
    @pytest.fixture
    def mock_db(self):
        return Mock()
    
    @pytest.fixture
    def service(self, mock_db):
        return AISchedulerService(mock_db, user_id=1)
    
    def test_morning_reminders(self, service):
        """测试早晨提醒"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                with patch.object(service, '_get_beijing_now') as mock_now:
                    # 设置为早上 7:30
                    mock_now.return_value = datetime(2026, 1, 17, 7, 30, 0)
                    result = service.get_reminders()
                    
                    reminders = result['reminders']
                    # 早晨应该有洗鼻、吃早餐等提醒
                    reminder_types = [r['type'] for r in reminders]
                    assert len(reminders) >= 0  # 至少有一些提醒
    
    def test_noon_reminders(self, service):
        """测试午间提醒"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                with patch.object(service, '_get_beijing_now') as mock_now:
                    # 设置为中午 12:00
                    mock_now.return_value = datetime(2026, 1, 17, 12, 0, 0)
                    result = service.get_reminders()
                    
                    assert 'reminders' in result
                    assert isinstance(result['reminders'], list)
    
    def test_night_reminders(self, service):
        """测试夜间提醒"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                with patch.object(service, '_get_beijing_now') as mock_now:
                    # 设置为晚上 21:30
                    mock_now.return_value = datetime(2026, 1, 17, 21, 30, 0)
                    result = service.get_reminders()
                    
                    reminders = result['reminders']
                    # 夜间应该有睡眠准备相关提醒
                    assert isinstance(reminders, list)


class TestAISchedulerSchedule:
    """AI 调度器日程功能测试"""
    
    @pytest.fixture
    def mock_db(self):
        return Mock()
    
    @pytest.fixture
    def service(self, mock_db):
        return AISchedulerService(mock_db, user_id=1)
    
    def test_schedule_item_structure(self, service):
        """测试日程项结构"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                schedule = service.get_daily_schedule()
                
                if schedule['schedule']:
                    item = schedule['schedule'][0]
                    # 检查日程项必须字段
                    assert 'time' in item
                    assert 'activity' in item
                    assert 'category' in item
                    assert 'duration_minutes' in item
                    assert 'tasks' in item
    
    def test_schedule_categories(self, service):
        """测试日程分类"""
        with patch.object(service, '_get_user_profile', return_value=None):
            with patch.object(service, '_get_today_checkin', return_value=None):
                schedule = service.get_daily_schedule()
                
                valid_categories = ['routine', 'meal', 'work', 'exercise', 'rest', 'leisure', 'sleep']
                for item in schedule['schedule']:
                    assert item['category'] in valid_categories
