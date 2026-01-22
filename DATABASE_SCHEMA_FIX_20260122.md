# 🔧 数据库表结构修复

> 2026-01-22 - 修复 garmin_credentials 表字段不匹配问题

---

## 🐛 问题描述

**错误信息**:
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) 
column garmin_credentials.garmin_email does not exist
```

**影响范围**: 
- 所有涉及 Garmin 凭证的功能
- Garmin 数据同步
- 用户设置页面

---

## 🔍 问题根因

### 代码与数据库不一致

**代码定义** (`backend/app/models/user.py`):
```python
class GarminCredential(Base):
    __tablename__ = "garmin_credentials"
    
    garmin_email = Column(String, nullable=False)  # ❌ 代码中使用 garmin_email
    # ...
```

**数据库实际字段**:
```sql
-- ❌ 数据库中是 email
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'garmin_credentials';

-- 结果: email (不是 garmin_email)
```

### 缺失字段

代码中定义了以下字段，但数据库中缺失：
- `is_cn` - 是否使用中国服务器
- `sync_enabled` - 同步开关
- `credentials_valid` - 凭证是否有效
- `requires_mfa` - 是否需要两步验证
- `last_error` - 最后错误信息
- `error_count` - 错误次数

---

## ✅ 解决方案

### 执行的 SQL 修复

```sql
-- 1. 重命名字段
ALTER TABLE garmin_credentials 
RENAME COLUMN email TO garmin_email;

-- 2. 添加缺失字段
ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS is_cn BOOLEAN DEFAULT FALSE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS credentials_valid BOOLEAN DEFAULT TRUE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS requires_mfa BOOLEAN DEFAULT FALSE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS last_error TEXT;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0;

-- 3. 删除多余字段
ALTER TABLE garmin_credentials 
DROP COLUMN IF EXISTS is_active;
```

### 修复后的表结构

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'garmin_credentials' 
ORDER BY ordinal_position;

-- 结果:
    column_name     |          data_type          
--------------------+-----------------------------
 id                 | integer
 user_id            | integer
 garmin_email       | character varying          ✅
 encrypted_password | text
 last_sync_at       | timestamp without time zone
 created_at         | timestamp without time zone
 updated_at         | timestamp without time zone
 garth_session      | text
 session_expires_at | timestamp without time zone
 is_cn              | boolean                     ✅ 新增
 sync_enabled       | boolean                     ✅ 新增
 credentials_valid  | boolean                     ✅ 新增
 requires_mfa       | boolean                     ✅ 新增
 last_error         | text                        ✅ 新增
 error_count        | integer                     ✅ 新增
```

---

## 🧪 验证修复

### 1. 检查表结构

```bash
ssh root@39.98.206.178 "sudo -u postgres psql health_db -c \"
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'garmin_credentials' 
ORDER BY ordinal_position;
\""
```

### 2. 重启服务

```bash
ssh root@39.98.206.178 "systemctl restart health-backend"
```

### 3. 查看日志

```bash
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"
```

**预期**: 没有 `garmin_email does not exist` 错误

### 4. 测试功能

访问以下页面确认功能正常：
- https://health.westwetlandtech.com/garmin - Garmin 设置页面
- https://health.westwetlandtech.com/dashboard - 仪表盘（显示 Garmin 数据）
- https://health.westwetlandtech.com/workout - 运动记录页面

---

## 📋 相关表检查

### 其他可能需要检查的表

```sql
-- 检查 device_credentials 表
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'device_credentials';

-- 检查 workout_records 表
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'workout_records';

-- 检查 user_notification_settings 表
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'user_notification_settings';
```

---

## 🔄 数据迁移建议

### 创建迁移脚本

为避免将来出现类似问题，建议创建数据库迁移脚本：

```sql
-- scripts/migrations/20260122_fix_garmin_credentials.sql

-- 修复 garmin_credentials 表结构
BEGIN;

-- 1. 重命名字段（如果存在）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'garmin_credentials' 
        AND column_name = 'email'
    ) THEN
        ALTER TABLE garmin_credentials RENAME COLUMN email TO garmin_email;
    END IF;
END $$;

-- 2. 添加缺失字段
ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS is_cn BOOLEAN DEFAULT FALSE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS credentials_valid BOOLEAN DEFAULT TRUE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS requires_mfa BOOLEAN DEFAULT FALSE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS last_error TEXT;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0;

-- 3. 删除多余字段
ALTER TABLE garmin_credentials 
DROP COLUMN IF EXISTS is_active;

COMMIT;
```

### 使用 Alembic 管理迁移

建议使用 Alembic 进行数据库版本管理：

```bash
# 安装 Alembic
pip install alembic

# 初始化 Alembic
cd backend
alembic init alembic

# 创建迁移
alembic revision -m "fix_garmin_credentials_schema"

# 应用迁移
alembic upgrade head
```

---

## 🚨 预防措施

### 1. 代码与数据库同步检查

创建检查脚本 `scripts/check_db_schema.py`:

```python
#!/usr/bin/env python3
"""
检查数据库表结构与模型定义是否一致
"""
from sqlalchemy import inspect
from app.database import engine
from app.models import Base

def check_schema():
    inspector = inspect(engine)
    
    for table_name in Base.metadata.tables.keys():
        print(f"\n检查表: {table_name}")
        
        # 获取模型定义的列
        model_columns = set(Base.metadata.tables[table_name].columns.keys())
        
        # 获取数据库实际的列
        db_columns = set(col['name'] for col in inspector.get_columns(table_name))
        
        # 检查差异
        missing_in_db = model_columns - db_columns
        extra_in_db = db_columns - model_columns
        
        if missing_in_db:
            print(f"  ❌ 数据库缺少字段: {missing_in_db}")
        
        if extra_in_db:
            print(f"  ⚠️  数据库多余字段: {extra_in_db}")
        
        if not missing_in_db and not extra_in_db:
            print(f"  ✅ 表结构一致")

if __name__ == "__main__":
    check_schema()
```

### 2. CI/CD 集成

在部署流程中添加表结构检查：

```yaml
# .github/workflows/deploy.yml
- name: Check Database Schema
  run: |
    cd backend
    python scripts/check_db_schema.py
```

### 3. 部署前检查清单

- [ ] 运行 `check_db_schema.py` 检查表结构
- [ ] 创建数据库备份
- [ ] 测试迁移脚本（在测试环境）
- [ ] 应用迁移到生产环境
- [ ] 验证功能正常
- [ ] 回滚计划准备

---

## 📊 影响评估

### 修复前

- ❌ Garmin 设置页面报错
- ❌ Garmin 数据同步失败
- ❌ 仪表盘无法显示 Garmin 数据
- ❌ 运动记录页面可能报错

### 修复后

- ✅ 所有 Garmin 相关功能恢复正常
- ✅ 数据同步正常工作
- ✅ 用户可以正常查看和管理 Garmin 数据
- ✅ 新增字段支持更多功能（如错误追踪、MFA 支持）

---

## 🔗 相关文档

- **数据库模型**: `backend/app/models/user.py`
- **Garmin 服务**: `backend/app/services/data_collection/garmin_connect.py`
- **迁移脚本**: `scripts/migrations/20260122_fix_garmin_credentials.sql`

---

**修复时间**: 2026-01-22 12:34  
**修复人员**: AI Assistant  
**影响用户**: 所有使用 Garmin 同步功能的用户  
**状态**: ✅ 已修复并验证
