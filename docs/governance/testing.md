# 测试规范 🧪

> 从 `AGENTS.md §3` 拆出（2026-05-31, Agent Operating Harness Phase 2,见 [`docs/design-agent-operating-harness.md`](design-agent-operating-harness.md)）。`AGENTS.md` 现在只留章节导航,本文件是本章权威全文 —— 硬规范裁判权不变。


### 3.1 测试覆盖要求

| 类型 | 覆盖率要求 | 说明 |
|------|-----------|------|
| 单元测试 | ≥ 80% | 核心业务逻辑 |
| 集成测试 | ≥ 60% | API 端点 |
| E2E 测试 | 关键路径 | 用户主流程 |

### 3.2 测试文件结构

```
tests/
├── unit/                    # 单元测试
│   ├── test_services/       # 服务层测试
│   ├── test_models/         # 模型测试
│   └── test_utils/          # 工具函数测试
├── integration/             # 集成测试
│   ├── test_api/            # API 测试
│   └── test_database/       # 数据库测试
├── e2e/                     # 端到端测试
├── conftest.py              # 测试配置和 fixtures
└── README.md                # 测试说明
```

### 3.3 测试命名规范

```python
# 测试函数命名：test_<功能>_<场景>_<预期结果>
def test_user_login_with_valid_credentials_returns_token():
    """有效凭证登录应返回 token"""
    pass

def test_user_login_with_invalid_password_raises_401():
    """无效密码登录应返回 401"""
    pass

def test_garmin_sync_with_expired_token_triggers_refresh():
    """Token 过期时应自动刷新"""
    pass
```

### 3.4 测试示例

```python
# tests/unit/test_services/test_ai_scheduler.py
import pytest
from datetime import date, time
from unittest.mock import Mock, patch

from app.services.ai_scheduler import AIScheduler, ReminderType


class TestAIScheduler:
    """AI 日程编排引擎测试"""
    
    @pytest.fixture
    def scheduler(self):
        return AIScheduler()
    
    @pytest.fixture
    def mock_db(self):
        return Mock()
    
    def test_get_time_greeting_morning(self, scheduler):
        """测试早间问候语"""
        with patch('app.services.ai_scheduler.get_china_now') as mock_now:
            mock_now.return_value.hour = 7
            greeting = scheduler._get_time_greeting()
            assert "早安" in greeting
    
    def test_get_reminders_filters_by_time(self, scheduler, mock_db):
        """测试提醒按时间过滤"""
        with patch('app.services.ai_scheduler.get_china_now') as mock_now:
            mock_now.return_value.hour = 7
            mock_now.return_value.minute = 5
            
            reminders = scheduler.get_reminders_for_time(mock_db, user_id=1)
            
            # 7:00-7:15 应该有早间洗鼻提醒
            assert any(r['type'] == ReminderType.NASAL_WASH.value for r in reminders)
    
    def test_generate_morning_briefing_includes_sleep_data(self, scheduler, mock_db):
        """测试早间简报包含睡眠数据"""
        # 设置 mock 数据
        mock_db.query.return_value.filter.return_value.first.return_value = Mock(
            sleep_score=85,
            sleep_duration_hours=7.5
        )
        
        briefing = scheduler.generate_morning_briefing(mock_db, user_id=1)
        
        assert 'sections' in briefing
        sleep_section = next(
            (s for s in briefing['sections'] if '睡眠' in s.get('title', '')),
            None
        )
        assert sleep_section is not None


# 运行测试：pytest tests/unit/test_services/test_ai_scheduler.py -v
```

### 3.5 CI/CD 集成

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      
      - name: Run tests with coverage
        run: |
          cd backend
          pytest --cov=app --cov-report=xml --cov-fail-under=80
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

---
