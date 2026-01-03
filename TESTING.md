# 测试指南

## 测试概述

本项目包含完整的单元测试和集成测试，覆盖了主要的API端点和业务逻辑。

## 快速开始

### 运行所有测试

```bash
cd backend
pytest
```

### 运行特定测试

```bash
# 运行用户相关测试
pytest tests/test_users.py

# 运行目标管理测试
pytest tests/test_goals.py

# 运行集成测试
pytest tests/test_integration.py
```

### 查看测试覆盖率

```bash
cd backend
pytest --cov=app --cov-report=html
```

然后在浏览器中打开 `htmlcov/index.html` 查看详细的覆盖率报告。

## 测试结构

```
backend/tests/
├── __init__.py
├── conftest.py              # 测试配置和共享fixtures
├── test_users.py            # 用户API测试 (6个测试)
├── test_basic_health.py     # 基础健康数据测试 (4个测试)
├── test_medical_exams.py     # 体检数据测试 (3个测试)
├── test_goals.py             # 目标管理测试 (5个测试)
├── test_health_checkin.py    # 健康打卡测试 (4个测试)
├── test_services.py          # 服务层测试 (3个测试)
├── test_integration.py      # 集成测试 (3个测试)
└── README.md
```

## 测试覆盖范围

### ✅ API端点测试

- **用户管理**
  - 创建用户
  - 获取用户列表
  - 获取单个用户
  - 错误处理

- **基础健康数据**
  - 创建健康数据
  - 获取用户健康数据
  - 获取最新健康数据
  - BMI自动计算

- **体检数据**
  - 创建体检记录
  - 获取体检记录
  - JSON格式导入

- **目标管理**
  - 创建目标
  - 获取用户目标
  - 更新目标进展
  - 获取目标进展
  - 检查目标完成情况

- **健康打卡**
  - 创建打卡
  - 获取打卡记录
  - 获取今日打卡
  - 更新已存在的打卡

### ✅ 服务层测试

- 目标管理服务
- 健康分析服务（数据收集）

### ✅ 集成测试

- 完整用户工作流程
- 健康分析工作流程
- 目标完成追踪

## 测试示例

### 示例1：创建用户并获取

```python
def test_create_and_get_user(client, sample_user_data):
    # 创建用户
    response = client.post("/api/v1/users", json=sample_user_data)
    assert response.status_code == 200
    user_id = response.json()["id"]
    
    # 获取用户
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["name"] == sample_user_data["name"]
```

### 示例2：目标进展追踪

```python
def test_goal_progress_tracking(client, sample_user_data):
    # 创建用户和目标
    user = create_user(client, sample_user_data)
    goal = create_goal(client, user["id"])
    
    # 更新进展
    update_progress(client, goal["id"], 25.0)
    
    # 检查完成情况
    completion = check_completion(client, goal["id"])
    assert completion["completion_percentage"] < 100
    assert completion["is_completed"] == False
```

## 测试数据

测试使用 `conftest.py` 中定义的fixtures提供测试数据：

- `sample_user_data` - 示例用户数据
- `sample_basic_health_data` - 示例基础健康数据
- `sample_medical_exam_data` - 示例体检数据

## 测试数据库

测试使用SQLite内存数据库，确保：
- 测试之间相互隔离
- 不影响开发数据库
- 测试运行速度快

## 运行测试的最佳实践

1. **在提交代码前运行测试**
   ```bash
   pytest
   ```

2. **查看覆盖率确保代码质量**
   ```bash
   pytest --cov=app --cov-report=term-missing
   ```

3. **运行特定测试进行调试**
   ```bash
   pytest tests/test_users.py::test_create_user -v -s
   ```

4. **使用标记运行特定类型的测试**
   ```bash
   pytest -m "not slow"  # 跳过慢速测试
   ```

## 持续集成

测试可以在CI/CD流程中自动运行：

```yaml
# GitHub Actions 示例
- name: Install dependencies
  run: |
    cd backend
    pip install -r requirements.txt

- name: Run tests
  run: |
    cd backend
    pytest --cov=app --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./backend/coverage.xml
```

## 添加新测试

1. 在 `tests/` 目录创建新的测试文件
2. 使用 `conftest.py` 中的fixtures
3. 遵循命名规范：`test_*.py` 和 `test_*` 函数
4. 编写清晰的测试文档字符串

示例：

```python
def test_new_feature(client, sample_user_data):
    """测试新功能"""
    # 准备
    user = create_user(client, sample_user_data)
    
    # 执行
    response = client.get(f"/api/v1/new-feature/{user['id']}")
    
    # 验证
    assert response.status_code == 200
    assert "expected_field" in response.json()
```

## 故障排除

### 测试失败：导入错误

确保在 `backend` 目录下运行测试：
```bash
cd backend
pytest
```

### 测试失败：数据库错误

测试使用内存数据库，如果遇到数据库错误，检查 `conftest.py` 中的数据库配置。

### 测试失败：依赖缺失

确保安装了所有依赖：
```bash
pip install -r requirements.txt
```

## 测试统计

当前测试套件包含：
- **28个测试用例**
- **覆盖主要API端点**
- **包含集成测试**
- **使用内存数据库，运行快速**

运行 `pytest --collect-only` 查看所有测试用例列表。

