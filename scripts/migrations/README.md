# 数据库迁移脚本

本目录包含数据库架构的增量更新脚本。

## 迁移说明

- **首次部署**：使用 `scripts/init_database.sql` 创建完整的数据库结构
- **升级部署**：按版本顺序执行 `migrations/` 目录下的迁移脚本

## 迁移文件命名规范

```
YYYYMMDD_NN_description.sql
```

例如：
- `20260101_01_add_garmin_credentials_fields.sql`
- `20260107_01_add_garmin_extended_fields.sql`

## 执行迁移

```bash
# 单个迁移
sqlite3 /opt/health-app/backend/health.db < scripts/migrations/20260107_01_xxx.sql

# 按顺序执行所有迁移（从某个版本开始）
for f in scripts/migrations/202601*.sql; do
    echo "执行: $f"
    sqlite3 /opt/health-app/backend/health.db < "$f"
done
```

## 迁移历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-01-01 | 01 | 添加 Garmin 凭证扩展字段 (is_cn, credentials_valid, etc.) |
| 2026-01-06 | 01 | 添加心率采样表 heart_rate_samples |
| 2026-01-07 | 01 | 添加 Garmin 扩展字段 (HRV, SpO2, 呼吸等) |
| 2026-01-07 | 02 | 创建运动训练表 workout_records |

## 注意事项

1. **备份数据库**：执行迁移前务必备份
   ```bash
   cp /opt/health-app/backend/health.db /opt/health-app/backend/health.db.bak
   ```

2. **SQLite 限制**：
   - 不支持一次 ALTER TABLE 添加多列
   - 不支持删除列（需要重建表）
   - 列已存在时 ALTER TABLE ADD COLUMN 会报错（可忽略继续）

3. **检查迁移状态**：
   ```bash
   # 查看表结构
   sqlite3 /opt/health-app/backend/health.db ".schema garmin_data"
   
   # 查看所有表
   sqlite3 /opt/health-app/backend/health.db ".tables"
   ```

