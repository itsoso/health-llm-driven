# 日志打点与单元测试完善计划

**创建时间**: 2026-01-23  
**目标**: 为核心模块添加完善的日志打点，确保可调试性和测试覆盖率

---

## 📋 核心模块清单

### 1. 补剂推荐模块 (supplement_recommendation.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 有基础测试 (test_supplements.py)
- **优先级**: 🔴 高

### 2. 饮食推荐模块 (diet_recommendation.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 有基础测试 (test_diet.py)
- **优先级**: 🔴 高

### 3. AI 调度器 (ai_scheduler.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 有测试 (test_ai_scheduler.py)
- **优先级**: 🟡 中

### 4. 运动分析模块 (workout_analysis.py, post_workout_analysis.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 部分日志
- **测试状态**: 部分测试
- **优先级**: 🔴 高

### 5. Garmin 会话管理 (garmin_session_manager.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 未知
- **优先级**: 🟡 中

### 6. 健康分析模块 (health_analysis.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 有测试 (test_basic_health.py)
- **优先级**: 🟡 中

### 7. LLM 健康分析器 (llm_health_analyzer.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 未知
- **优先级**: 🔴 高

### 8. 认证服务 (auth.py)
- **状态**: ⚠️ 需要增强
- **当前日志**: 基础日志
- **测试状态**: 有测试 (test_auth_secrets.py)
- **优先级**: 🔴 高（安全相关）

---

## 🎯 实施计划

### Phase 1: 日志增强 (第1周)

#### 1.1 创建统一日志工具类
```python
# backend/app/utils/logger.py
import logging
import functools
import time
from typing import Any, Callable
from datetime import datetime

class ModuleLogger:
    """模块级别的日志工具类"""
    
    def __init__(self, module_name: str):
        self.logger = logging.getLogger(module_name)
        self.module_name = module_name
    
    def log_function_call(self, func: Callable) -> Callable:
        """装饰器：记录函数调用"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            self.logger.info(f"[{func.__name__}] 开始执行")
            self.logger.debug(f"[{func.__name__}] 参数: args={args}, kwargs={kwargs}")
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                self.logger.info(f"[{func.__name__}] 执行成功，耗时 {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                self.logger.error(f"[{func.__name__}] 执行失败，耗时 {duration:.3f}s，错误: {str(e)}")
                raise
        
        return wrapper
    
    def log_data_flow(self, step: str, data: Any, mask_fields: list = None):
        """记录数据流转"""
        if mask_fields:
            # 脱敏处理
            pass
        self.logger.debug(f"[数据流转] {step}: {data}")
```

#### 1.2 为核心模块添加日志打点

**补剂推荐模块增强点**:
- ✅ 函数入口/出口日志
- ✅ 数据获取步骤日志
- ✅ LLM 调用前后日志
- ✅ 异常详细日志
- ✅ 性能监控日志

**饮食推荐模块增强点**:
- ✅ 用户画像加载日志
- ✅ Garmin 数据获取日志
- ✅ 饮食记录查询日志
- ✅ LLM 分析日志
- ✅ 推荐生成日志

**运动分析模块增强点**:
- ✅ 运动数据解析日志
- ✅ GPS 数据处理日志
- ✅ 心率分析日志
- ✅ 配速计算日志
- ✅ 分析结果日志

### Phase 2: 单元测试完善 (第2周)

#### 2.1 测试框架增强

```python
# tests/conftest.py 增强
import pytest
from unittest.mock import Mock, patch
from datetime import date, datetime

@pytest.fixture
def mock_db():
    """Mock 数据库会话"""
    db = Mock()
    return db

@pytest.fixture
def mock_user():
    """Mock 用户对象"""
    user = Mock()
    user.id = 1
    user.email = "test@example.com"
    return user

@pytest.fixture
def mock_garmin_data():
    """Mock Garmin 数据"""
    return {
        "sleep_score": 85,
        "total_sleep_duration": 450,  # 分钟
        "stress_level": 35,
        "resting_heart_rate": 55,
        "steps": 8500,
        "calories_burned": 2200
    }

@pytest.fixture
def mock_llm_response():
    """Mock LLM 响应"""
    return {
        "analysis": "健康状况良好",
        "recommendations": ["建议1", "建议2"],
        "rating": {"score": 8, "level": "优秀"}
    }
```

#### 2.2 核心模块测试用例

**补剂推荐模块测试**:
```python
# tests/test_supplement_recommendation_enhanced.py

class TestSupplementRecommendation:
    """补剂推荐服务测试"""
    
    def test_generate_recommendation_success(self, mock_db, mock_user):
        """测试成功生成推荐"""
        pass
    
    def test_generate_recommendation_no_data(self, mock_db, mock_user):
        """测试无数据情况"""
        pass
    
    def test_generate_recommendation_llm_failure(self, mock_db, mock_user):
        """测试 LLM 调用失败"""
        pass
    
    def test_calculate_overall_rating(self):
        """测试评分计算"""
        pass
    
    def test_get_health_data_with_cache(self, mock_db):
        """测试健康数据获取（带缓存）"""
        pass
```

**饮食推荐模块测试**:
```python
# tests/test_diet_recommendation_enhanced.py

class TestDietRecommendation:
    """饮食推荐服务测试"""
    
    def test_generate_recommendation_complete_data(self):
        """测试完整数据推荐"""
        pass
    
    def test_generate_recommendation_partial_data(self):
        """测试部分数据推荐"""
        pass
    
    def test_allergy_filtering(self):
        """测试过敏原过滤"""
        pass
    
    def test_nutrition_calculation(self):
        """测试营养计算"""
        pass
```

**运动分析模块测试**:
```python
# tests/test_workout_analysis_enhanced.py

class TestWorkoutAnalysis:
    """运动分析服务测试"""
    
    def test_parse_gps_data(self):
        """测试 GPS 数据解析"""
        pass
    
    def test_calculate_pace(self):
        """测试配速计算"""
        pass
    
    def test_heart_rate_zones(self):
        """测试心率区间分析"""
        pass
    
    def test_workout_intensity_rating(self):
        """测试运动强度评级"""
        pass
```

### Phase 3: 集成测试 (第3周)

#### 3.1 端到端测试

```python
# tests/test_e2e_supplement_flow.py

class TestSupplementE2E:
    """补剂推荐端到端测试"""
    
    def test_full_recommendation_flow(self, client, test_user):
        """测试完整推荐流程"""
        # 1. 登录
        # 2. 获取推荐
        # 3. 验证响应
        # 4. 验证数据库记录
        pass
```

#### 3.2 性能测试

```python
# tests/test_performance.py

class TestPerformance:
    """性能测试"""
    
    def test_recommendation_response_time(self):
        """测试推荐响应时间 < 5s"""
        pass
    
    def test_concurrent_requests(self):
        """测试并发请求处理"""
        pass
```

---

## 📊 测试覆盖率目标

| 模块 | 当前覆盖率 | 目标覆盖率 | 优先级 |
|------|-----------|-----------|--------|
| supplement_recommendation | 未知 | ≥ 85% | 🔴 高 |
| diet_recommendation | 未知 | ≥ 85% | 🔴 高 |
| workout_analysis | 未知 | ≥ 80% | 🔴 高 |
| ai_scheduler | 未知 | ≥ 80% | 🟡 中 |
| health_analysis | 未知 | ≥ 75% | 🟡 中 |
| auth | 未知 | ≥ 90% | 🔴 高 |
| garmin_session_manager | 未知 | ≥ 75% | 🟡 中 |
| llm_health_analyzer | 未知 | ≥ 80% | 🔴 高 |

---

## 🔧 工具和配置

### 测试运行命令

```bash
# 运行所有测试
pytest tests/

# 运行特定模块测试
pytest tests/test_supplement_recommendation_enhanced.py -v

# 生成覆盖率报告
pytest --cov=app --cov-report=html --cov-report=term

# 运行性能测试
pytest tests/test_performance.py -v --durations=10
```

### CI/CD 集成

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
          pip install pytest pytest-cov pytest-asyncio pytest-mock
      
      - name: Run tests with coverage
        run: |
          cd backend
          pytest --cov=app --cov-report=xml --cov-fail-under=80
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

---

## 📝 日志监控

### 日志聚合配置

```python
# backend/app/utils/logging_config.py

import logging
from logging.handlers import RotatingFileHandler
import sys

def setup_logging(level: str = "INFO"):
    """配置日志系统"""
    
    # 格式化
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # 文件输出（按大小轮转）
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    
    # 错误日志单独文件
    error_handler = RotatingFileHandler(
        "logs/error.log",
        maxBytes=10*1024*1024,
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # 根日志配置
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
```

### 日志告警规则

```yaml
# 告警规则示例
alerts:
  - name: HighErrorRate
    condition: error_count > 10 in 5m
    action: notify_admin
  
  - name: SlowResponse
    condition: response_time > 5s
    action: log_warning
  
  - name: LLMFailure
    condition: llm_error_count > 3 in 10m
    action: notify_admin
```

---

## ✅ 验收标准

### 日志完善标准
- ✅ 所有核心函数有入口/出口日志
- ✅ 所有外部调用（LLM、数据库）有日志
- ✅ 所有异常有详细错误日志
- ✅ 性能关键点有耗时日志
- ✅ 敏感信息已脱敏

### 测试完善标准
- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 核心模块有完整测试用例
- ✅ 边界条件有测试覆盖
- ✅ 异常情况有测试覆盖
- ✅ 所有测试可独立运行
- ✅ CI/CD 自动运行测试

---

## 📅 时间表

| 周次 | 任务 | 交付物 |
|------|------|--------|
| 第1周 | 日志工具类 + 补剂/饮食模块日志增强 | logger.py + 增强代码 |
| 第2周 | 运动/认证模块日志增强 + 单元测试框架 | 增强代码 + conftest.py |
| 第3周 | 核心模块单元测试编写 | 测试文件 + 覆盖率报告 |
| 第4周 | 集成测试 + CI/CD 配置 | E2E 测试 + GitHub Actions |

---

## 🔗 相关文档

- [AGENTS.md - 日志规范](./AGENTS.md#2-日志规范-)
- [AGENTS.md - 测试规范](./AGENTS.md#3-测试规范-)
- [pytest 文档](https://docs.pytest.org/)
- [Python logging 文档](https://docs.python.org/3/library/logging.html)

---

**状态**: 📋 计划中  
**负责人**: AI Agent  
**最后更新**: 2026-01-23
