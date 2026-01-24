# SQLite 到 PostgreSQL 数据迁移指南

## 📋 概述

本脚本用于将 SQLite 数据库中的数据迁移到 PostgreSQL 数据库。

## 🎯 适用场景

1. **从 SQLite 切换到 PostgreSQL**
   - 开发环境 → 生产环境
   - 单用户 → 多用户

2. **数据备份恢复**
   - 从 SQLite 备份恢复到 PostgreSQL

3. **数据同步**
   - 将测试数据同步到生产环境

## 📦 依赖安装

```bash
cd backend
pip install psycopg2-binary
```

## 🚀 使用方法

### 1. 检查数据量（Dry Run）

在执行迁移前，先检查数据量：

```bash
cd /opt/health-app/backend
python3 scripts/migrate_sqlite_to_postgres.py --dry-run
```

**输出示例**:
```
🔍 Dry Run 模式：仅检查数据量
✅ 数据库连接成功
📊 performance_metrics:
   SQLite: 0 条
   PostgreSQL: 0 条
📊 performance_alerts:
   SQLite: 0 条
   PostgreSQL: 0 条
📊 performance_summaries:
   SQLite: 0 条
   PostgreSQL: 0 条
✅ 数据库连接已关闭
```

### 2. 执行迁移

确认数据量后，执行实际迁移：

```bash
cd /opt/health-app/backend
python3 scripts/migrate_sqlite_to_postgres.py
```

**输出示例**:
```
🚀 开始数据迁移...
📁 SQLite: health.db
🐘 PostgreSQL: localhost:5432/health_db
✅ 数据库连接成功

📊 performance_metrics: SQLite 中有 150 条记录
✅ performance_metrics: 成功迁移 150 条记录
   PostgreSQL 中现有 150 条记录

📊 performance_alerts: SQLite 中有 5 条记录
✅ performance_alerts: 成功迁移 5 条记录
   PostgreSQL 中现有 5 条记录

📊 performance_summaries: SQLite 中有 0 条记录
⏭️  跳过 performance_summaries（无数据）

🎉 数据迁移完成！
✅ 数据库连接已关闭
```

### 3. 指定 SQLite 文件路径

如果 SQLite 文件不在默认位置：

```bash
python3 scripts/migrate_sqlite_to_postgres.py --sqlite-db /path/to/your/health.db
```

## 📊 迁移的表

脚本会迁移以下性能监控相关的表：

1. **performance_metrics** - 性能指标
   - 页面加载时间
   - API 响应时间
   - 渲染性能
   - 交互性能

2. **performance_alerts** - 性能告警
   - 慢页面告警
   - 慢 API 告警
   - 错误率告警

3. **performance_summaries** - 性能汇总
   - 每小时汇总
   - 每日汇总
   - P50/P90/P95/P99 统计

## 🔧 数据转换

脚本会自动处理以下数据转换：

### 1. JSON 字段

SQLite 中的 TEXT 字段会转换为 PostgreSQL 的 JSONB：

```python
# SQLite: TEXT
details = '{"cache_hit": true, "batch": 1}'

# PostgreSQL: JSONB
details = {"cache_hit": true, "batch": 1}
```

### 2. 日期时间

保持 ISO 8601 格式：

```python
# 两者兼容
created_at = '2026-01-24T11:43:14'
```

### 3. ENUM 类型

SQLite 的 CHECK 约束会转换为 PostgreSQL 的 ENUM：

```sql
-- SQLite
platform VARCHAR(20) CHECK(platform IN ('mini_program', 'web', 'h5', 'app'))

-- PostgreSQL
platform platform_type  -- ENUM 类型
```

## ⚠️ 注意事项

### 1. 数据重复

脚本**不会**检查重复数据。如果多次运行，会插入重复记录。

**解决方案**:
- 在迁移前清空 PostgreSQL 表
- 或者修改脚本添加 `ON CONFLICT` 处理

```sql
-- 清空表（谨慎操作！）
TRUNCATE TABLE performance_metrics CASCADE;
TRUNCATE TABLE performance_alerts CASCADE;
TRUNCATE TABLE performance_summaries CASCADE;
```

### 2. 外键约束

如果有外键引用 `users` 表，确保：
- 用户数据已存在于 PostgreSQL
- 或者暂时禁用外键约束

```sql
-- 临时禁用外键约束
SET session_replication_role = 'replica';

-- 执行迁移...

-- 恢复外键约束
SET session_replication_role = 'origin';
```

### 3. 大数据量

如果数据量很大（>10万条），建议：
- 分批迁移
- 使用 `COPY` 命令（更快）
- 临时禁用索引

```python
# 修改脚本中的 page_size
execute_batch(pg_cursor, insert_sql, data_to_insert, page_size=1000)
```

### 4. 数据验证

迁移后务必验证数据：

```sql
-- 检查记录数
SELECT COUNT(*) FROM performance_metrics;

-- 检查数据完整性
SELECT 
    platform,
    metric_type,
    COUNT(*) as count,
    MIN(created_at) as earliest,
    MAX(created_at) as latest
FROM performance_metrics
GROUP BY platform, metric_type;

-- 检查 JSON 字段
SELECT details, meta_data 
FROM performance_metrics 
WHERE details IS NOT NULL 
LIMIT 5;
```

## 🔍 故障排查

### 问题 1: 连接失败

**错误**:
```
psycopg2.OperationalError: could not connect to server
```

**解决**:
```bash
# 检查 PostgreSQL 配置
cat .env | grep POSTGRES

# 测试连接
PGPASSWORD=your_password psql -h localhost -U health_user -d health_db -c '\l'
```

### 问题 2: 权限错误

**错误**:
```
psycopg2.errors.InsufficientPrivilege: permission denied for table
```

**解决**:
```sql
-- 授予权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO health_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO health_user;
```

### 问题 3: JSON 解析错误

**错误**:
```
json.decoder.JSONDecodeError: Expecting value
```

**解决**:
- 检查 SQLite 中的 JSON 字段格式
- 修改脚本添加错误处理

```python
try:
    details = json.loads(row['details']) if row['details'] else None
except json.JSONDecodeError:
    print(f"⚠️  警告: 无效的 JSON 数据: {row['details']}")
    details = None
```

## 📈 性能优化

### 1. 批量插入

使用 `execute_batch` 而不是逐条插入：

```python
# 慢 ❌
for row in rows:
    cursor.execute(insert_sql, row)

# 快 ✅
execute_batch(cursor, insert_sql, rows, page_size=100)
```

### 2. 临时禁用索引

对于大数据量迁移：

```sql
-- 删除索引
DROP INDEX IF EXISTS idx_perf_created_at;
DROP INDEX IF EXISTS idx_perf_platform_metric_created;

-- 执行迁移...

-- 重建索引
CREATE INDEX idx_perf_created_at ON performance_metrics(created_at);
CREATE INDEX idx_perf_platform_metric_created ON performance_metrics(platform, metric_type, created_at);
```

### 3. 使用 COPY 命令

对于超大数据量（>100万条）：

```python
import io

# 生成 CSV 数据
csv_buffer = io.StringIO()
for row in rows:
    csv_buffer.write(f"{row['id']},{row['name']}\n")
csv_buffer.seek(0)

# 使用 COPY
cursor.copy_from(csv_buffer, 'table_name', sep=',', columns=['id', 'name'])
```

## 🎯 最佳实践

### 1. 迁移前

- ✅ 备份 SQLite 数据库
- ✅ 备份 PostgreSQL 数据库
- ✅ 执行 Dry Run 检查数据量
- ✅ 在测试环境先测试

### 2. 迁移中

- ✅ 监控迁移进度
- ✅ 记录迁移日志
- ✅ 准备回滚方案

### 3. 迁移后

- ✅ 验证数据完整性
- ✅ 验证数据一致性
- ✅ 更新应用配置
- ✅ 测试应用功能

## 📝 迁移检查清单

```
迁移前:
□ 备份 SQLite 数据库
□ 备份 PostgreSQL 数据库
□ 检查磁盘空间
□ 执行 Dry Run
□ 确认数据量

迁移中:
□ 停止应用服务（可选）
□ 执行迁移脚本
□ 监控迁移进度
□ 记录错误信息

迁移后:
□ 验证记录数
□ 验证数据完整性
□ 测试查询性能
□ 更新应用配置
□ 重启应用服务
□ 功能测试
□ 性能测试

清理:
□ 备份 SQLite 文件
□ 删除或归档 SQLite 文件
□ 更新文档
```

## 🆘 获取帮助

```bash
# 查看帮助信息
python3 scripts/migrate_sqlite_to_postgres.py --help

# 输出:
# usage: migrate_sqlite_to_postgres.py [-h] [--sqlite-db SQLITE_DB] [--dry-run]
# 
# SQLite 到 PostgreSQL 数据迁移
# 
# optional arguments:
#   -h, --help            show this help message and exit
#   --sqlite-db SQLITE_DB
#                         SQLite 数据库文件路径（默认: health.db）
#   --dry-run             仅检查数据量，不执行迁移
```

## 📚 相关文档

- `POSTGRESQL_MIGRATION.md` - PostgreSQL 迁移记录
- `DATABASE_MIGRATION_SUMMARY.md` - 数据库迁移总结
- `backend/migrations/` - 数据库迁移脚本

---

**最后更新**: 2026-01-24  
**维护者**: AI Agent
