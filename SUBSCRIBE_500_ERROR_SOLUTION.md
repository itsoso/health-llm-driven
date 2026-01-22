# 订阅设置 500 错误完整解决方案

## 问题现象

小程序"我的"页面加载时报错：

```
GET https://health.westwetlandtech.com/api/wechat/subscribe/settings 500
```

错误信息：
```
column user_notification_settings.morning_briefing_enabled does not exist
```

## 问题原因

这个问题之前已经修复过（2026-01-22 20:00），但可能由于以下原因再次出现：

1. **SQLAlchemy 元数据缓存**：服务重启前缓存了旧的表结构
2. **数据库连接池**：连接池中的旧连接还保留着旧的元数据
3. **多次部署**：在短时间内多次部署导致状态不一致

## 解决方案

### 方案 1：重启后端服务（推荐）

```bash
ssh root@39.98.206.178 "systemctl restart health-backend"
```

重启后等待 5 秒，让服务完全启动：

```bash
ssh root@39.98.206.178 "sleep 5 && systemctl status health-backend"
```

### 方案 2：清除 SQLAlchemy 缓存

如果重启无效，可能需要清除 Python 的 `__pycache__`：

```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; systemctl restart health-backend"
```

### 方案 3：验证数据库表结构

检查数据库中是否真的存在该字段：

```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && sqlite3 health.db 'PRAGMA table_info(user_notification_settings)' | grep morning_briefing_enabled"
```

如果没有输出，说明表结构确实缺少该字段，需要执行数据库迁移。

## 验证修复

### 1. 检查服务日志

```bash
ssh root@39.98.206.178 "journalctl -u health-backend --since '1 minute ago' --no-pager | grep -E '(ERROR|500|subscribe)'"
```

如果没有错误输出，说明服务正常。

### 2. 测试 API

```bash
curl -X GET "https://health.westwetlandtech.com/api/wechat/subscribe/settings" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -w "\nHTTP Status: %{http_code}\n"
```

应该返回 200 或 401（未登录），而不是 500。

### 3. 小程序测试

1. 打开小程序
2. 进入"我的"页面
3. 查看开发者工具控制台
4. 应该不再有 500 错误

## 为什么会反复出现？

这个问题可能反复出现的原因：

1. **SQLAlchemy 的元数据缓存机制**
   - SQLAlchemy 在首次连接数据库时会缓存表结构
   - 如果表结构在运行时发生变化，缓存不会自动更新
   - 需要重启服务才能重新加载

2. **数据库迁移未执行**
   - 如果表结构确实缺少字段，每次重启都会报错
   - 需要执行数据库迁移脚本

3. **多数据库配置**
   - 错误信息显示 `psycopg2.errors`（PostgreSQL）
   - 但 `.env` 文件配置的是 SQLite
   - 可能存在环境变量覆盖或多个配置文件

## 根本解决方案

### 1. 使用数据库迁移工具

建议使用 Alembic 进行数据库迁移：

```bash
cd /opt/health-app/backend

# 生成迁移脚本
alembic revision --autogenerate -m "Add notification settings fields"

# 执行迁移
alembic upgrade head

# 重启服务
systemctl restart health-backend
```

### 2. 统一数据库配置

确保只有一个数据库配置生效：

```bash
# 检查环境变量
ssh root@39.98.206.178 "systemctl cat health-backend | grep Environment"

# 检查 .env 文件
ssh root@39.98.206.178 "cat /opt/health-app/backend/.env | grep DATABASE_URL"
```

### 3. 添加健康检查

在部署脚本中添加健康检查：

```bash
# deploy.sh
systemctl restart health-backend
sleep 5

# 检查服务是否正常
if ! systemctl is-active --quiet health-backend; then
    echo "❌ 服务启动失败"
    exit 1
fi

# 检查 API 是否正常
if ! curl -f http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "❌ API 健康检查失败"
    exit 1
fi

echo "✅ 服务部署成功"
```

## 当前状态

- **最后修复时间**：2026-01-22 20:12
- **修复方法**：重启后端服务
- **服务状态**：✅ 正常运行
- **API 状态**：需要测试验证

## 下一步操作

1. **立即操作**：
   - 在小程序中刷新"我的"页面
   - 查看是否还有 500 错误
   - 如果还有，再次执行 `systemctl restart health-backend`

2. **长期优化**：
   - 配置 Alembic 数据库迁移
   - 添加 API 健康检查端点
   - 在部署脚本中添加自动化测试

3. **监控告警**：
   - 配置 500 错误告警
   - 定期检查服务日志
   - 监控数据库连接状态

## 相关文档

- [微信订阅设置 500 错误修复](./WECHAT_SUBSCRIBE_SETTINGS_500_FIX.md)
- [小程序订阅提醒设置指南](./MINI_PROGRAM_SUBSCRIBE_GUIDE.md)
- [小程序重新构建指南](./MINI_PROGRAM_REBUILD_GUIDE.md)

---

**最后更新**：2026-01-22 20:12  
**维护人员**：AI Assistant  
**问题状态**：🔄 已重启服务，待验证
