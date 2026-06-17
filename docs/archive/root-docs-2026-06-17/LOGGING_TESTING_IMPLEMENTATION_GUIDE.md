# 日志打点与单元测试实施指南

**创建时间**: 2026-01-23  
**目的**: 指导开发者如何在现有代码中应用日志打点和单元测试

---

## 📚 快速开始

### 1. 在服务类中添加日志

#### 步骤 1: 导入日志工具

```python
from app.utils.logger import get_module_logger

# 创建模块日志器
logger = get_module_logger(__name__)
```

#### 步骤 2: 在类中使用日志器

```python
class YourService:
    def __init__(self):
        self.logger = logger
    
    def your_method(self, param1: str, param2: int):
        # 1. 记录函数开始
        self.logger.log_step("开始处理", {"param1": param1, "param2": param2})
        
        try:
            # 2. 记录数据获取
            self.logger.log_step("获取用户数据")
            user_data = self._get_user_data(param1)
            self.logger.log_data_flow("用户数据", user_data)
            
            # 3. 记录外部调用
            self.logger.log_external_call("Database", "query", {"table": "users"})
            
            # 4. 记录性能
            import time
            start = time.time()
            result = self._process_data(user_data)
            self.logger.log_performance("数据处理", time.time() - start, threshold=1.0)
            
            # 5. 记录业务事件
            self.logger.log_business_event("处理完成", {"result_count": len(result)})
            
            return result
            
        except Exception as e:
            # 6. 记录错误
            self.logger.logger.error(
                f"处理失败: {str(e)}",
                exc_info=True
            )
            raise
```

### 2. 使用装饰器自动记录函数调用

```python
from app.utils.logger import get_module_logger

logger = get_module_logger(__name__)

class YourService:
    @logger.log_function_call(log_args=True, log_result=False)
    def your_method(self, param1: str, param2: int):
        # 函数入口/出口、参数、耗时会自动记录
        result = self._do_something(param1, param2)
        return result
```

### 3. 编写单元测试

#### 步骤 1: 创建测试文件

```python
# tests/test_your_service.py

import pytest
from unittest.mock import Mock, patch
from app.services.your_service import YourService

class TestYourService:
    """YourService 测试套件"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return YourService()
    
    @pytest.fixture
    def mock_db(self):
        """Mock 数据库"""
        return Mock()
    
    def test_your_method_success(self, service, mock_db):
        """测试：成功场景"""
        # Arrange
        param1 = "test"
        param2 = 123
        
        # Act
        result = service.your_method(param1, param2)
        
        # Assert
        assert result is not None
        assert len(result) > 0
    
    def test_your_method_error(self, service, mock_db):
        """测试：异常场景"""
        # Arrange
        param1 = "invalid"
        
        # Act & Assert
        with pytest.raises(ValueError):
            service.your_method(param1, 0)
```

#### 步骤 2: 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_your_service.py -v

# 生成覆盖率报告
pytest tests/ --cov=app --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

---

## 🎯 核心模块实施清单

### ✅ 已完成

- [x] 日志工具类 (`app/utils/logger.py`)
- [x] 测试 fixtures (`tests/conftest_enhanced.py`)
- [x] 补剂推荐示例 (`supplement_recommendation_enhanced_logging.py`)
- [x] 补剂推荐测试示例 (`test_supplement_recommendation_enhanced.py`)

### 🔄 进行中

#### 1. 补剂推荐模块 (supplement_recommendation.py)

**需要添加的日志点**:
```python
# 在 generate_supplement_recommendation 方法中

# 1. 函数入口
logger.log_step("开始生成补剂推荐", {"user_id": user_id, "debug": debug})

# 2. 获取用户画像
logger.log_step("获取用户画像")
profile_start = time.time()
profile = self._get_user_profile(db, user_id)
logger.log_performance("获取用户画像", time.time() - profile_start, 0.5)

# 3. 获取健康数据
logger.log_step("获取健康数据")
health_data = self._get_health_data(db, user_id, target_date)
logger.log_data_flow("健康数据", health_data)

# 4. LLM 调用
logger.log_external_call("DigitalTwin", "analyze_supplement_needs")
llm_start = time.time()
recommendations = twin.analyze_supplement_needs(...)
logger.log_performance("LLM 分析", time.time() - llm_start, 5.0)

# 5. 函数出口
logger.log_business_event("补剂推荐生成成功", {
    "user_id": user_id,
    "recommendation_count": len(recommendations)
})
```

**需要添加的测试**:
- ✅ 成功生成推荐（完整数据）
- ✅ 成功生成推荐（部分数据）
- ✅ 用户画像不存在
- ✅ 过敏原过滤
- ✅ 慢性病考虑
- ✅ 数据库错误
- ✅ LLM 超时
- ✅ 性能测试
- ✅ 评分计算
- ✅ Debug 模式

#### 2. 饮食推荐模块 (diet_recommendation.py)

**需要添加的日志点**:
```python
# 1. 函数入口
logger.log_step("开始生成饮食推荐", {"user_id": user_id})

# 2. 获取用户画像
logger.log_step("获取用户画像")
profile = self._get_user_profile(db, user_id)
logger.log_data_flow("用户画像", {
    "age": profile.age,
    "allergies": profile.allergies,
    "diet_preference": profile.diet_preference
})

# 3. 获取 Garmin 数据
logger.log_step("获取 Garmin 数据")
garmin_data = self._get_garmin_data(db, user_id)

# 4. 获取饮食记录
logger.log_step("获取饮食记录")
diet_records = self._get_diet_records(db, user_id)

# 5. 营养计算
logger.log_step("计算营养摄入")
nutrition = self._calculate_nutrition(diet_records)
logger.log_data_flow("营养数据", nutrition)

# 6. LLM 调用
logger.log_external_call("DigitalTwin", "analyze_diet_needs")

# 7. 过敏原过滤
logger.log_step("过滤过敏原")
filtered_recommendations = self._filter_allergens(recommendations, profile.allergies)

# 8. 函数出口
logger.log_business_event("饮食推荐生成成功", {
    "user_id": user_id,
    "recommendation_count": len(filtered_recommendations)
})
```

**需要添加的测试**:
- [ ] 成功生成推荐（完整数据）
- [ ] 成功生成推荐（部分数据）
- [ ] 过敏原过滤
- [ ] 营养计算准确性
- [ ] 饮食偏好考虑
- [ ] 运动量调整
- [ ] LLM 调用失败
- [ ] 性能测试

#### 3. 运动分析模块 (workout_analysis.py)

**需要添加的日志点**:
```python
# 1. 函数入口
logger.log_step("开始分析运动", {"workout_id": workout_id})

# 2. 获取运动数据
logger.log_step("获取运动数据")
workout = self._get_workout(db, workout_id)
logger.log_data_flow("运动数据", {
    "type": workout.workout_type,
    "duration": workout.duration_minutes,
    "calories": workout.calories
})

# 3. GPS 数据解析
if workout.gps_data:
    logger.log_step("解析 GPS 数据")
    gps_start = time.time()
    gps_analysis = self._parse_gps_data(workout.gps_data)
    logger.log_performance("GPS 解析", time.time() - gps_start, 2.0)

# 4. 心率分析
logger.log_step("分析心率数据")
hr_zones = self._analyze_heart_rate(workout)
logger.log_data_flow("心率区间", hr_zones)

# 5. 配速计算
logger.log_step("计算配速")
pace_analysis = self._calculate_pace(workout)

# 6. 强度评估
logger.log_step("评估运动强度")
intensity = self._assess_intensity(workout, hr_zones)

# 7. 函数出口
logger.log_business_event("运动分析完成", {
    "workout_id": workout_id,
    "intensity": intensity
})
```

**需要添加的测试**:
- [ ] GPS 数据解析
- [ ] 配速计算
- [ ] 心率区间分析
- [ ] 强度评估
- [ ] 无 GPS 数据处理
- [ ] 异常心率处理
- [ ] 性能测试

#### 4. 认证服务 (auth.py)

**需要添加的日志点**:
```python
# 1. 用户登录
logger.log_business_event("用户登录尝试", {"email": email})

# 2. 密码验证
logger.log_step("验证密码")
if not verify_password(password, user.hashed_password):
    logger.log_validation_error("password", "***", "密码错误")
    logger.log_business_event("登录失败", {"email": email, "reason": "密码错误"})
    raise HTTPException(401, "密码错误")

# 3. Token 生成
logger.log_step("生成访问令牌")
access_token = create_access_token({"sub": user.email})

# 4. 登录成功
logger.log_business_event("登录成功", {
    "user_id": user.id,
    "email": user.email
})
```

**需要添加的测试**:
- [ ] 成功登录
- [ ] 密码错误
- [ ] 用户不存在
- [ ] 用户未激活
- [ ] Token 生成
- [ ] Token 验证
- [ ] Token 过期
- [ ] 刷新 Token

---

## 📊 测试覆盖率检查

### 运行覆盖率测试

```bash
# 生成覆盖率报告
pytest tests/ --cov=app --cov-report=html --cov-report=term

# 查看报告
open htmlcov/index.html

# 检查特定模块覆盖率
pytest tests/ --cov=app.services.supplement_recommendation --cov-report=term
```

### 覆盖率目标

| 模块 | 当前 | 目标 | 状态 |
|------|------|------|------|
| supplement_recommendation | - | 85% | 🔄 进行中 |
| diet_recommendation | - | 85% | ⏳ 待开始 |
| workout_analysis | - | 80% | ⏳ 待开始 |
| auth | - | 90% | ⏳ 待开始 |
| ai_scheduler | - | 80% | ⏳ 待开始 |
| health_analysis | - | 75% | ⏳ 待开始 |

---

## 🔍 日志监控和调试

### 查看日志

```bash
# 查看应用日志
tail -f logs/app.log

# 查看错误日志
tail -f logs/error.log

# 搜索特定用户的日志
grep "user_id=123" logs/app.log

# 搜索性能警告
grep "性能警告" logs/app.log

# 搜索 LLM 调用
grep "外部调用.*LLM" logs/app.log
```

### 动态调整日志级别

```bash
# 通过 API 调整（需要管理员权限）
curl -X POST http://localhost:8000/api/v1/admin/log-level \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"level": "DEBUG"}'
```

### 日志分析

```python
# 分析日志文件
import re
from collections import Counter

# 统计错误类型
with open('logs/error.log') as f:
    errors = re.findall(r'error_type=(\w+)', f.read())
    print(Counter(errors))

# 统计慢操作
with open('logs/app.log') as f:
    slow_ops = re.findall(r'\[性能\] (\w+) 耗时 ([\d.]+)s', f.read())
    for op, duration in slow_ops:
        if float(duration) > 5.0:
            print(f"{op}: {duration}s")
```

---

## 🚀 CI/CD 集成

### GitHub Actions 配置

创建 `.github/workflows/test.yml`:

```yaml
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
      
      - name: Run tests
        run: |
          cd backend
          pytest --cov=app --cov-report=xml --cov-fail-under=80
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./backend/coverage.xml
```

---

## 📚 最佳实践

### 日志最佳实践

1. **使用合适的日志级别**
   - DEBUG: 详细调试信息
   - INFO: 正常业务流程
   - WARNING: 异常但可恢复
   - ERROR: 错误但不影响服务
   - CRITICAL: 严重错误

2. **记录关键信息**
   - 函数入口/出口
   - 外部调用（数据库、LLM、API）
   - 性能关键点
   - 业务事件
   - 异常情况

3. **敏感信息脱敏**
   - 密码、Token、API Key
   - 手机号、邮箱、身份证
   - 信用卡号、银行账号

4. **性能监控**
   - 设置合理的阈值
   - 记录慢操作
   - 追踪瓶颈

### 测试最佳实践

1. **测试结构**
   - Arrange: 准备测试数据
   - Act: 执行被测试代码
   - Assert: 验证结果

2. **测试命名**
   - `test_<功能>_<场景>_<预期结果>`
   - 例如: `test_login_with_valid_credentials_returns_token`

3. **使用 Mock**
   - 隔离外部依赖
   - 提高测试速度
   - 确保测试稳定性

4. **测试覆盖**
   - 成功场景
   - 边界条件
   - 异常情况
   - 性能测试

---

## 🆘 常见问题

### Q1: 如何在现有代码中添加日志？

A: 逐步添加，优先添加关键路径的日志：
1. 函数入口/出口
2. 外部调用
3. 异常处理
4. 性能关键点

### Q2: 测试覆盖率达不到目标怎么办？

A: 
1. 先覆盖核心业务逻辑
2. 再覆盖边界条件
3. 最后覆盖异常情况
4. 使用覆盖率报告找出未覆盖的代码

### Q3: Mock 太复杂怎么办？

A: 
1. 使用 `conftest_enhanced.py` 中的 fixtures
2. 创建测试辅助函数
3. 考虑重构代码，降低耦合度

### Q4: 日志太多影响性能怎么办？

A: 
1. 线上环境使用 INFO 级别
2. 使用异步日志写入
3. 定期清理旧日志
4. 使用日志采样（高频操作）

---

## 📖 参考资料

- [AGENTS.md - 日志规范](./AGENTS.md#2-日志规范-)
- [AGENTS.md - 测试规范](./AGENTS.md#3-测试规范-)
- [LOGGING_AND_TESTING_PLAN.md](./LOGGING_AND_TESTING_PLAN.md)
- [pytest 文档](https://docs.pytest.org/)
- [Python logging 文档](https://docs.python.org/3/library/logging.html)
- [unittest.mock 文档](https://docs.python.org/3/library/unittest.mock.html)

---

**最后更新**: 2026-01-23  
**维护者**: AI Agent  
**状态**: ✅ 可用
