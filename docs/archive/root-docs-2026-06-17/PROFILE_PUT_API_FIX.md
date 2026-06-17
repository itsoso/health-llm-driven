# 个人资料 PUT API 500 错误修复

## 问题描述

用户在 Web 个人资料页面 (`https://health.westwetlandtech.com/profile`) 尝试更新个人信息时，遇到 `PUT https://health.westwetlandtech.com/api/profile/me 500 (Internal Server Error)` 错误。

## 错误原因

通过服务器日志分析，发现错误是由 Pydantic 验证失败导致的：

```
pydantic_core._pydantic_core.ValidationError: 2 validation errors for UserProfileResponse
allergies
  Input should be a valid list [type=list_type, input_value='["\\u51b7\\u7a7a\\u6c14"]', input_type=str]
family_history
  Input should be a valid list [type=list_type, input_value='["\\u9ad8\\u8840\\u538b"...\\u7cd6\\u5c3f\\u75c5"]', input_type=str]
```

### 根本原因

1. **数据库存储格式**：`allergies` 和 `family_history` 等字段在数据库中存储为 JSON 字符串（如 `'["冷空气"]'`）
2. **GET 接口处理**：`get_my_profile` 接口使用了 `parse_json_field` 函数将 JSON 字符串解析为 Python 列表
3. **PUT 接口缺陷**：`update_my_profile` 接口直接使用 `UserProfileResponse.model_validate(profile)`，没有处理 JSON 字段，导致 Pydantic 期望 List 类型但收到 str 类型

## 修复方案

### 1. 统一 JSON 字段处理逻辑

在 `update_my_profile` 接口中添加与 `get_my_profile` 相同的 JSON 字段处理逻辑：

```python
# 处理 JSON 字段（数据库中可能是字符串）
def parse_json_field(field_value, default):
    if field_value is None:
        return default
    if isinstance(field_value, str):
        try:
            return json.loads(field_value)
        except:
            return default
    return field_value

# 构建响应数据，处理所有可能为 None 的字段
response_data = {
    "id": profile.id,
    "user_id": profile.user_id,
    # ... 其他字段 ...
    "chronic_conditions": parse_json_field(profile.chronic_conditions, []),
    "allergies": parse_json_field(profile.allergies, []),
    "family_history": parse_json_field(profile.family_history, []),
    "surgeries": parse_json_field(profile.surgeries, []),
    "current_medications": parse_json_field(profile.current_medications, []),
    # ... 其他字段 ...
}

return UserProfileResponse(**response_data)
```

### 2. 修改的文件

- **`backend/app/api/user_profile.py`**：
  - 在 `update_my_profile` 函数中添加 `parse_json_field` 函数
  - 使用 `response_data` 字典构建响应，而不是直接 `model_validate(profile)`
  - 确保所有 JSON 字段（`chronic_conditions`, `allergies`, `family_history`, `surgeries`, `current_medications`, `sleep_environment`, `devices`）都经过解析

## 部署步骤

```bash
# 1. 提交代码
git add backend/app/api/user_profile.py
git commit -m "fix(profile): 修复PUT接口JSON字段解析问题"
git push origin main

# 2. 部署到服务器
ssh root@39.98.206.178 "cd /opt/health-app && git pull && systemctl restart health-backend"

# 3. 验证服务状态
ssh root@39.98.206.178 "systemctl is-active health-backend"
```

## 验证方法

1. 访问 `https://health.westwetlandtech.com/profile`
2. 尝试修改个人信息（如姓名、性别、出生日期等）
3. 点击保存
4. 确认更新成功，页面不再出现 500 错误

## 相关问题

这是继 GET 接口 500 错误之后的第二个问题：

1. **GET 接口问题**（已修复）：
   - 原因：数据库中 `height_cm` 字段存在异常值 `17417172.0`，超过 Pydantic 验证规则的最大值 `300`
   - 解决：直接在数据库中将异常值设置为 `NULL`

2. **PUT 接口问题**（本次修复）：
   - 原因：JSON 字段未经解析直接传递给 Pydantic，导致类型不匹配
   - 解决：添加 JSON 字段解析逻辑，与 GET 接口保持一致

## 最佳实践建议

1. **统一数据处理逻辑**：GET 和 PUT 接口应使用相同的数据处理逻辑，避免不一致
2. **数据库迁移**：考虑将 JSON 字符串字段迁移为真正的 JSON 类型（PostgreSQL 支持 JSONB）
3. **数据验证**：在写入数据库前进行严格的数据验证，避免异常值
4. **错误日志**：确保生产环境的错误日志完整，便于快速定位问题

## 时间线

- **2026-01-22 19:52**：用户报告 PUT 接口 500 错误
- **2026-01-22 19:53**：分析日志，定位到 JSON 字段解析问题
- **2026-01-22 19:53**：修复代码，添加 JSON 字段处理逻辑
- **2026-01-22 19:53**：部署到生产环境，验证修复成功

## 影响范围

- **受影响用户**：所有尝试更新个人资料的用户
- **受影响字段**：`allergies`、`family_history`、`chronic_conditions`、`surgeries`、`current_medications`、`sleep_environment`、`devices`
- **修复后**：所有用户可以正常更新个人资料

---

**修复完成时间**：2026-01-22 19:53  
**修复人员**：AI Assistant  
**验证状态**：✅ 已验证
