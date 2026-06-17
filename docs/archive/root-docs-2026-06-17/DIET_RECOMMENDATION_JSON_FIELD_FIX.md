# 饮食推荐 JSON 字段解析错误修复

**问题时间**: 2026-01-23  
**错误表现**: 过敏提醒显示 Unicode 转义字符而不是中文  
**影响**: 过敏提醒和慢性病警告显示异常

## 🐛 问题描述

用户在饮食推荐页面看到过敏提醒显示为：

```
🚫 过敏提醒：避免 [, ", \, u, 5, 1, b, 7, \, u, 7, a, 7, a, \, u, 6, c, 1, 4, ", ]
```

而不是正确的中文：

```
🚫 过敏提醒：避免 冷空气
```

## 🔍 问题根源

### 数据库存储格式

在 PostgreSQL 数据库中，`user_profiles` 表的 `allergies` 和 `chronic_conditions` 字段使用 JSON 类型存储：

```python
# backend/app/models/user_profile.py
class UserProfile(Base):
    chronic_conditions = Column(JSON, default=list)  # ["鼻炎", "咽炎", "高血压"]
    allergies = Column(JSON, default=list)  # ["花粉", "海鲜", "青霉素"]
```

### 实际存储的数据

数据库中存储的是 JSON 字符串：

```python
# 数据库实际存储
allergies = '["\\u51b7\\u7a7a\\u6c14"]'  # JSON 字符串

# SQLAlchemy 读取后
type(profile.allergies)  # <class 'str'>
profile.allergies        # '["\\u51b7\\u7a7a\\u6c14"]'
```

### 代码中的错误处理

原代码直接将字符串当作列表使用：

```python
# ❌ 错误代码
allergies = profile.allergies or []
warnings.append(f"🚫 过敏提醒：避免 {', '.join(allergies)}")

# 结果：将字符串的每个字符拼接
# '["\\u51b7\\u7a7a\\u6c14"]' → [, ", \, u, 5, 1, b, 7, ...
```

## ✅ 解决方案

### 1. 添加 JSON 解析辅助方法

```python
# backend/app/services/diet_recommendation.py

import json

class DietRecommendationService:
    @staticmethod
    def _parse_json_field(field_value: Any) -> List:
        """
        解析 JSON 字段，处理可能是字符串的情况
        
        Args:
            field_value: 字段值（可能是列表或 JSON 字符串）
            
        Returns:
            解析后的列表
        """
        if not field_value:
            return []
        
        # 如果已经是列表，直接返回
        if isinstance(field_value, list):
            return field_value
        
        # 如果是字符串，尝试解析 JSON
        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value)
                return parsed if isinstance(parsed, list) else []
            except:
                return []
        
        return []
```

### 2. 使用辅助方法解析字段

#### 修复前

```python
# ❌ 错误代码
allergies = profile.allergies or []
chronic_conditions = profile.chronic_conditions or []

if allergies:
    warnings.append(f"🚫 过敏提醒：避免 {', '.join(allergies)}")
```

#### 修复后

```python
# ✅ 正确代码
allergies = self._parse_json_field(profile.allergies)
chronic_conditions = self._parse_json_field(profile.chronic_conditions)

if allergies:
    warnings.append(f"🚫 过敏提醒：避免 {', '.join(allergies)}")
```

### 3. 修复所有使用这些字段的地方

在 `diet_recommendation.py` 中有 4 处使用：

1. **`_generate_warnings_and_tips` 方法** - 生成警告和提示
2. **`_generate_food_recommendations` 方法** - 生成食物推荐
3. **`_get_scientific_insights` 方法** - 获取科学见解

所有地方都已修复。

## 📊 测试结果

### 测试用例

```python
from app.services.diet_recommendation import DietRecommendationService

service = DietRecommendationService()

test_cases = [
    ('["冷空气"]', ['冷空气']),           # JSON 字符串
    ('[]', []),                          # 空 JSON 数组
    (None, []),                          # None 值
    (['冷空气'], ['冷空气']),             # 已经是列表
    ('invalid json', []),                # 无效 JSON
]

for input_val, expected in test_cases:
    result = service._parse_json_field(input_val)
    assert result == expected, f"Failed: {input_val}"
```

### 测试结果

```
✅ 输入: '["冷空气"]'      => 输出: ['冷空气']
✅ 输入: '[]'            => 输出: []
✅ 输入: None           => 输出: []
✅ 输入: ['冷空气']       => 输出: ['冷空气']
✅ 输入: 'invalid json' => 输出: []
```

**所有测试通过！** ✅

## 🎯 修复前后对比

### 修复前

```
🚫 过敏提醒：避免 [, ", \, u, 5, 1, b, 7, \, u, 7, a, 7, a, \, u, 6, c, 1, 4, ", ]
```

**问题**:
- 将 JSON 字符串当作普通字符串处理
- `', '.join()` 将字符串的每个字符拼接
- Unicode 转义字符未被解析

### 修复后

```
🚫 过敏提醒：避免 冷空气
```

**改进**:
- ✅ 正确解析 JSON 字符串
- ✅ Unicode 转义字符被正确解码
- ✅ 显示正确的中文文字

## 💡 为什么会出现这个问题？

### SQLAlchemy JSON 字段的行为

在不同的数据库中，SQLAlchemy 的 JSON 字段行为不同：

#### SQLite (开发环境)

```python
# SQLite 自动解析 JSON
profile.allergies  # ['冷空气']  (list)
type(profile.allergies)  # <class 'list'>
```

#### PostgreSQL (生产环境)

```python
# PostgreSQL 返回 JSON 字符串
profile.allergies  # '["\\u51b7\\u7a7a\\u6c14"]'  (str)
type(profile.allergies)  # <class 'str'>
```

### 解决方案的兼容性

新的 `_parse_json_field` 方法兼容两种情况：

```python
def _parse_json_field(field_value):
    # 处理 SQLite 的情况（已经是列表）
    if isinstance(field_value, list):
        return field_value
    
    # 处理 PostgreSQL 的情况（JSON 字符串）
    if isinstance(field_value, str):
        try:
            return json.loads(field_value)
        except:
            return []
    
    return []
```

## 📝 修复步骤

### 1. 添加 JSON 解析方法

```bash
vim backend/app/services/diet_recommendation.py

# 在 DietRecommendationService 类中添加 _parse_json_field 方法
```

### 2. 替换所有使用

```bash
# 查找所有使用 allergies 和 chronic_conditions 的地方
grep -n "profile.allergies\|profile.chronic_conditions" backend/app/services/diet_recommendation.py

# 替换为 self._parse_json_field(...)
```

### 3. 提交代码

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
git add backend/app/services/diet_recommendation.py
git commit -m "fix: 修复饮食推荐中 JSON 字段解析问题（allergies, chronic_conditions）"
git push
```

### 4. 部署到服务器

```bash
ssh root@39.98.206.178
cd /opt/health-app
git pull
systemctl restart health-backend
```

## 🔧 相关字段检查

### UserProfile 中的 JSON 字段

| 字段名 | 类型 | 说明 | 是否修复 |
|--------|------|------|---------|
| `chronic_conditions` | JSON | 慢性病列表 | ✅ 已修复 |
| `allergies` | JSON | 过敏源列表 | ✅ 已修复 |
| `family_history` | JSON | 家族病史 | ⚠️ 暂未使用 |
| `surgeries` | JSON | 手术历史 | ⚠️ 暂未使用 |

**建议**: 如果将来使用 `family_history` 和 `surgeries`，也应该使用 `_parse_json_field` 方法。

## 💡 经验教训

### 1. 数据库差异

开发环境和生产环境使用不同的数据库时，要注意数据类型的差异：

```python
# ❌ 假设总是列表
allergies = profile.allergies or []

# ✅ 兼容多种情况
allergies = self._parse_json_field(profile.allergies)
```

### 2. JSON 字段处理

使用 SQLAlchemy 的 JSON 字段时，要考虑：

- 不同数据库的行为差异
- 字符串编码问题（Unicode 转义）
- 空值处理

### 3. 测试覆盖

为 JSON 字段解析编写单元测试：

```python
def test_parse_json_field():
    """测试 JSON 字段解析"""
    service = DietRecommendationService()
    
    # 测试 JSON 字符串
    assert service._parse_json_field('["a", "b"]') == ["a", "b"]
    
    # 测试已经是列表
    assert service._parse_json_field(["a", "b"]) == ["a", "b"]
    
    # 测试空值
    assert service._parse_json_field(None) == []
    assert service._parse_json_field('') == []
    
    # 测试无效 JSON
    assert service._parse_json_field('invalid') == []
```

### 4. 代码复用

提取公共逻辑为辅助方法，避免重复代码：

```python
# ❌ 重复代码
if isinstance(allergies, str):
    try:
        allergies = json.loads(allergies)
    except:
        allergies = []

if isinstance(chronic_conditions, str):
    try:
        chronic_conditions = json.loads(chronic_conditions)
    except:
        chronic_conditions = []

# ✅ 使用辅助方法
allergies = self._parse_json_field(profile.allergies)
chronic_conditions = self._parse_json_field(profile.chronic_conditions)
```

## ✅ 修复完成

### 修复内容

- ✅ 添加 `_parse_json_field` 辅助方法
- ✅ 修复 `allergies` 字段解析（4 处）
- ✅ 修复 `chronic_conditions` 字段解析（4 处）
- ✅ 兼容 SQLite 和 PostgreSQL
- ✅ 正确处理 Unicode 转义字符

### 部署状态

- ✅ 代码已提交到 Git
- ✅ 后端服务已重启
- ✅ 功能测试通过

### 验证清单

- ✅ 过敏提醒显示正确的中文
- ✅ 慢性病警告显示正确
- ✅ 食物推荐排除过敏源
- ✅ 无 Unicode 转义字符

## 📄 相关文档

- `backend/app/models/user_profile.py` - UserProfile 模型定义
- `backend/app/services/diet_recommendation.py` - 饮食推荐服务
- `DIET_RECOMMENDATION_FIELD_ERRORS_FIX.md` - 字段名错误修复

---

**修复完成时间**: 2026-01-23 10:33  
**后端服务状态**: ✅ Running  
**功能状态**: ✅ 完全正常
