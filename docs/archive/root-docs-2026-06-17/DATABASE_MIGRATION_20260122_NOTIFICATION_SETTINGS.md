# 数据库迁移：user_notification_settings 表结构更新

## 迁移时间
2026-01-22 20:15

## 问题描述

小程序调用 `/api/wechat/subscribe/settings` 接口时持续报 500 错误：

```
psycopg2.errors.UndefinedColumn: column user_notification_settings.morning_briefing_enabled does not exist
```

## 根本原因

1. **数据库不一致**：
   - 代码中的模型定义了新字段（`morning_briefing_enabled` 等）
   - PostgreSQL 数据库中的表结构是旧的，缺少这些字段
   - SQLAlchemy 查询时找不到字段导致错误

2. **为什么之前检查时没发现**：
   - 之前检查的是 SQLite 数据库（`health.db`）
   - 但生产环境实际使用的是 PostgreSQL
   - `.env` 文件配置的是 SQLite，但可能有环境变量覆盖

## 迁移内容

### 添加的字段

```sql
ALTER TABLE user_notification_settings 
ADD COLUMN IF NOT EXISTS morning_briefing_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS health_alert_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS ai_advice_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS morning_briefing_time VARCHAR(5) DEFAULT '07:30',
ADD COLUMN IF NOT EXISTS wechat_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS ios_push_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS wechat_openid VARCHAR(100),
ADD COLUMN IF NOT EXISTS wechat_template_ids TEXT,
ADD COLUMN IF NOT EXISTS ios_device_token VARCHAR(200);
```

### 字段说明

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `morning_briefing_enabled` | BOOLEAN | true | 早间简报开关 |
| `reminder_enabled` | BOOLEAN | true | 定时提醒开关 |
| `health_alert_enabled` | BOOLEAN | true | 健康预警开关 |
| `ai_advice_enabled` | BOOLEAN | true | AI 建议开关 |
| `morning_briefing_time` | VARCHAR(5) | '07:30' | 早间简报时间 |
| `wechat_enabled` | BOOLEAN | true | 微信推送开关 |
| `ios_push_enabled` | BOOLEAN | true | iOS 推送开关 |
| `wechat_openid` | VARCHAR(100) | NULL | 微信 OpenID |
| `wechat_template_ids` | TEXT | NULL | 订阅的模板 ID（JSON） |
| `ios_device_token` | VARCHAR(200) | NULL | iOS 设备 Token |

## 执行步骤

### 1. 连接数据库

```bash
ssh root@39.98.206.178
PGPASSWORD='<production-db-secret>' psql -h localhost -U health_user -d health_db
```

### 2. 查看当前表结构

```sql
\d user_notification_settings
```

### 3. 执行迁移

```sql
ALTER TABLE user_notification_settings 
ADD COLUMN IF NOT EXISTS morning_briefing_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS health_alert_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS ai_advice_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS morning_briefing_time VARCHAR(5) DEFAULT '07:30',
ADD COLUMN IF NOT EXISTS wechat_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS ios_push_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS wechat_openid VARCHAR(100),
ADD COLUMN IF NOT EXISTS wechat_template_ids TEXT,
ADD COLUMN IF NOT EXISTS ios_device_token VARCHAR(200);
```

### 4. 验证迁移

```sql
\d user_notification_settings
```

应该看到新添加的字段。

### 5. 重启服务

```bash
systemctl restart health-backend
```

### 6. 验证修复

在小程序中刷新"我的"页面，应该不再有 500 错误。

## 迁移前后对比

### 迁移前（15 个字段）

```
id, user_id, enable_push, enable_email, quiet_hours_start, quiet_hours_end,
reminder_drink_water, reminder_exercise, reminder_sleep, reminder_supplements,
alert_heart_rate, alert_blood_pressure, created_at, updated_at, enabled
```

### 迁移后（25 个字段）

```
上述 15 个字段 +
morning_briefing_enabled, reminder_enabled, health_alert_enabled, ai_advice_enabled,
morning_briefing_time, wechat_enabled, ios_push_enabled, wechat_openid,
wechat_template_ids, ios_device_token
```

## 影响范围

- **受影响功能**：小程序订阅消息设置
- **受影响用户**：所有用户
- **数据影响**：无数据丢失，仅添加新字段
- **向后兼容**：✅ 完全兼容，旧字段保持不变

## 验证结果

- ✅ 表结构更新成功
- ✅ 服务重启成功
- ✅ API 不再报 500 错误
- ⏳ 等待用户确认小程序功能正常

## 经验教训

### 1. 数据库配置混乱

**问题**：
- `.env` 文件配置的是 SQLite
- 实际运行使用的是 PostgreSQL
- 导致排查时走了弯路

**解决**：
- 统一数据库配置
- 确保 `.env` 文件与实际运行环境一致
- 添加数据库连接日志，明确显示使用的数据库

### 2. 缺少数据库迁移工具

**问题**：
- 没有使用 Alembic 等迁移工具
- 表结构变更需要手动执行 SQL
- 容易遗漏或出错

**解决**：
- 配置 Alembic 数据库迁移
- 所有表结构变更通过迁移脚本管理
- 迁移脚本纳入版本控制

### 3. 部署流程不完善

**问题**：
- 部署时没有检查数据库迁移
- 代码和数据库不同步
- 导致运行时错误

**解决**：
- 在部署脚本中添加迁移检查
- 部署前自动执行数据库迁移
- 添加健康检查，确保服务正常

## 后续优化

### 1. 配置 Alembic

```bash
cd /opt/health-app/backend
pip install alembic
alembic init alembic
```

在 `alembic.ini` 中配置数据库连接：

```ini
sqlalchemy.url = postgresql://health_user:<production-db-secret>@localhost/health_db
```

### 2. 生成迁移脚本

```bash
alembic revision --autogenerate -m "Add notification settings fields"
```

### 3. 执行迁移

```bash
alembic upgrade head
```

### 4. 更新部署脚本

```bash
# deploy.sh
cd /opt/health-app/backend
git pull

# 执行数据库迁移
source venv/bin/activate
alembic upgrade head

# 重启服务
systemctl restart health-backend

# 健康检查
sleep 5
if ! curl -f http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "❌ 服务启动失败"
    exit 1
fi

echo "✅ 部署成功"
```

## 相关文档

- [订阅设置 500 错误解决方案](./SUBSCRIBE_500_ERROR_SOLUTION.md)
- [微信订阅设置 500 错误修复](./WECHAT_SUBSCRIBE_SETTINGS_500_FIX.md)
- [小程序订阅提醒设置指南](./MINI_PROGRAM_SUBSCRIBE_GUIDE.md)

---

**迁移执行人**：AI Assistant  
**迁移时间**：2026-01-22 20:15  
**迁移状态**：✅ 成功  
**验证状态**：⏳ 待用户确认
