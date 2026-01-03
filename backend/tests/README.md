# 测试说明

## 运行测试

### 运行所有测试

```bash
cd backend
pytest
```

### 运行特定测试文件

```bash
pytest tests/test_users.py
pytest tests/test_basic_health.py
pytest tests/test_goals.py
```

### 运行特定测试函数

```bash
pytest tests/test_users.py::test_create_user
```

### 查看测试覆盖率

```bash
pytest --cov=app --cov-report=html
```

生成的HTML报告在 `htmlcov/index.html`

### 详细输出

```bash
pytest -v  # 详细模式
pytest -vv  # 更详细
pytest -s   # 显示print输出
```

## 测试结构

```
tests/
├── __init__.py
├── conftest.py          # 测试配置和fixtures
├── test_users.py        # 用户API测试
├── test_basic_health.py # 基础健康数据测试
├── test_medical_exams.py # 体检数据测试
├── test_goals.py        # 目标管理测试
├── test_health_checkin.py # 健康打卡测试
├── test_services.py     # 服务层测试
├── test_integration.py  # 集成测试
└── README.md
```

## 测试覆盖

### API测试
- ✅ 用户管理API
- ✅ 基础健康数据API
- ✅ 体检数据API
- ✅ 目标管理API
- ✅ 健康打卡API

### 服务层测试
- ✅ 目标管理服务
- ✅ 健康分析服务（数据收集部分）

### 集成测试
- ✅ 完整用户工作流程
- ✅ 健康分析工作流程
- ✅ 目标完成追踪

## 注意事项

1. **测试数据库**：测试使用内存数据库（SQLite in-memory），不会影响开发数据库

2. **OpenAI API**：健康分析测试在没有API密钥的情况下会返回错误信息，但不会导致测试失败

3. **异步测试**：某些测试可能需要异步支持，已配置 `pytest-asyncio`

4. **测试隔离**：每个测试函数使用独立的数据库会话，确保测试之间不相互影响

## 添加新测试

1. 在 `tests/` 目录下创建新的测试文件 `test_*.py`
2. 使用 `conftest.py` 中定义的fixtures（如 `client`, `db`, `sample_user_data`）
3. 遵循命名规范：测试函数以 `test_` 开头
4. 使用断言验证预期结果

示例：

```python
def test_new_feature(client, sample_user_data):
    """测试新功能"""
    # 准备数据
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    # 执行操作
    response = client.get(f"/api/v1/new-endpoint/{user_id}")
    
    # 验证结果
    assert response.status_code == 200
    assert "expected_field" in response.json()
```

## CI/CD集成

可以在CI/CD流程中运行测试：

```yaml
# 示例 GitHub Actions
- name: Run tests
  run: |
    cd backend
    pip install -r requirements.txt
    pytest --cov=app --cov-report=xml
```

