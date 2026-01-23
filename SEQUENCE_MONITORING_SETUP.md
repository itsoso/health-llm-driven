# 数据库序列监控设置指南

**创建时间**: 2026-01-23 08:20 UTC+8

## 📋 概述

为了防止数据库主键序列不同步导致的插入失败问题，我们建立了完整的监控和自动修复机制。

## 🎯 已完成的工作

### 1. 发现并修复了 16 个表的序列问题

详见：`DATABASE_SEQUENCE_FIX_REPORT.md`

受影响的表：
- users (极高风险)
- heart_rate_samples (极高风险)
- garmin_credentials
- workout_records
- weight_records
- blood_pressure_records
- medical_exams
- medical_exam_items
- 等共 16 个表

### 2. 创建了自动化脚本

#### 检查脚本
**路径**: `backend/scripts/check_sequences.py`

**功能**:
- 检查所有表的序列状态
- 识别异常、临界和正常状态
- 生成详细报告

**使用方法**:
```bash
cd /opt/health-app/backend
source venv/bin/activate
python3 scripts/check_sequences.py
```

**返回值**:
- 0: 所有序列正常
- 1: 发现序列问题
- 2: 检查失败

#### 修复脚本
**路径**: `backend/scripts/fix_sequences.py`

**功能**:
- 自动修复所有异常的序列
- 支持模拟模式（--dry-run）
- 支持单表修复（--table）

**使用方法**:
```bash
# 修复所有表
cd /opt/health-app/backend
source venv/bin/activate
python3 scripts/fix_sequences.py

# 模拟模式（只检查不修复）
python3 scripts/fix_sequences.py --dry-run

# 只修复特定表
python3 scripts/fix_sequences.py --table users
```

#### 部署脚本
**路径**: `scripts/setup_sequence_monitoring.sh`

**功能**:
- 一键设置监控环境
- 配置定时任务
- 测试脚本运行

**使用方法**:
```bash
ssh root@39.98.206.178
cd /opt/health-app
bash scripts/setup_sequence_monitoring.sh
```

### 3. 已部署到生产服务器

所有脚本已上传到服务器：
- ✅ `/opt/health-app/backend/scripts/check_sequences.py`
- ✅ `/opt/health-app/backend/scripts/fix_sequences.py`
- ✅ `/opt/health-app/scripts/setup_sequence_monitoring.sh`
- ✅ 脚本权限已设置为可执行

## 🚀 下一步操作

### 立即执行（需要在服务器上）

```bash
# 1. SSH 到服务器
ssh root@39.98.206.178

# 2. 运行部署脚本
cd /opt/health-app
bash scripts/setup_sequence_monitoring.sh
```

这个脚本会：
1. ✅ 验证脚本权限
2. ✅ 测试检查脚本
3. ✅ 如果发现问题，询问是否修复
4. ✅ 添加定时任务（每天凌晨 2 点检查）
5. ✅ 创建日志目录

### 验证部署

```bash
# 1. 手动运行检查
cd /opt/health-app/backend
source venv/bin/activate
python3 scripts/check_sequences.py

# 2. 查看 crontab
crontab -l | grep check_sequences

# 3. 查看日志目录
ls -la /var/log/health-app/
```

## 📊 监控机制

### 自动检查

**频率**: 每天凌晨 2 点

**Crontab 配置**:
```bash
0 2 * * * cd /opt/health-app/backend && source venv/bin/activate && python3 scripts/check_sequences.py >> /var/log/health-app/sequence-check.log 2>&1
```

**日志位置**: `/var/log/health-app/sequence-check.log`

### 手动检查

随时可以手动运行检查：

```bash
cd /opt/health-app/backend
source venv/bin/activate
python3 scripts/check_sequences.py
```

### 查看日志

```bash
# 查看最新日志
tail -f /var/log/health-app/sequence-check.log

# 查看历史日志
cat /var/log/health-app/sequence-check.log

# 查看最近 50 行
tail -50 /var/log/health-app/sequence-check.log
```

## 🔧 使用场景

### 场景 1: 定期检查

**自动执行**: 每天凌晨 2 点

**无需人工干预**

### 场景 2: 数据迁移后

```bash
# 迁移数据后立即检查
cd /opt/health-app/backend
source venv/bin/activate
python3 scripts/check_sequences.py

# 如果发现问题，立即修复
python3 scripts/fix_sequences.py
```

### 场景 3: 发现插入失败

如果遇到类似错误：
```
duplicate key value violates unique constraint "xxx_pkey"
```

**立即执行**:
```bash
cd /opt/health-app/backend
source venv/bin/activate

# 检查问题
python3 scripts/check_sequences.py

# 修复问题
python3 scripts/fix_sequences.py
```

### 场景 4: 新表添加后

```bash
# 检查新表的序列
python3 scripts/check_sequences.py

# 如果新表有问题，修复
python3 scripts/fix_sequences.py --table new_table_name
```

## 📈 监控指标

### 序列状态分类

| 状态 | 说明 | 风险等级 | 处理方式 |
|------|------|---------|---------|
| ✅ 正常 | 序列值 > 最大ID | 无风险 | 无需处理 |
| ⚠️ 临界 | 序列值 = 最大ID | 低风险 | 建议修复 |
| ❌ 异常 | 序列值 < 最大ID | 高风险 | 立即修复 |

### 关键表监控

以下表的序列问题会导致严重后果，需要特别关注：

| 表名 | 影响 | 优先级 |
|------|------|--------|
| users | 新用户无法注册 | 🔴 极高 |
| garmin_data | Garmin 数据无法同步 | 🔴 极高 |
| workout_records | 运动记录无法保存 | 🔴 高 |
| medical_exams | 体检数据无法录入 | 🔴 高 |
| diet_records | 饮食记录无法保存 | 🟡 中 |
| weight_records | 体重记录无法保存 | 🟡 中 |

## 🛡️ 预防措施

### 1. 数据迁移规范

```python
# 迁移数据后必须执行
def migrate_data():
    # 1. 迁移数据
    import_users()
    import_garmin_data()
    # ...
    
    # 2. 修复序列（必须！）
    import subprocess
    subprocess.run([
        'python3', 
        'scripts/fix_sequences.py'
    ], cwd='/opt/health-app/backend')
```

### 2. 手动插入数据规范

```sql
-- ❌ 错误：指定 ID
INSERT INTO users (id, email, ...) VALUES (1, 'test@example.com', ...);

-- ✅ 正确：让数据库自动分配 ID
INSERT INTO users (email, ...) VALUES ('test@example.com', ...);
```

### 3. 使用 UPSERT 模式

```python
from sqlalchemy.dialects.postgresql import insert

def safe_insert(db, model, data):
    stmt = insert(model).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=['id'],
        set_=data
    )
    db.execute(stmt)
    db.commit()
```

## 📞 故障排查

### 问题 1: 检查脚本运行失败

**症状**: `python3 scripts/check_sequences.py` 返回错误

**排查步骤**:
1. 检查是否在正确的目录
   ```bash
   pwd  # 应该在 /opt/health-app/backend
   ```

2. 检查虚拟环境是否激活
   ```bash
   which python3  # 应该显示 venv 路径
   ```

3. 检查数据库连接
   ```bash
   python3 -c "from app.database import SessionLocal; db = SessionLocal(); print('OK')"
   ```

### 问题 2: 修复后仍然失败

**症状**: 运行修复脚本后，插入仍然失败

**排查步骤**:
1. 再次运行检查脚本
   ```bash
   python3 scripts/check_sequences.py
   ```

2. 查看具体错误信息
   ```bash
   journalctl -u health-backend -n 100 | grep -i "unique\|duplicate"
   ```

3. 手动检查序列
   ```sql
   SELECT last_value FROM table_name_id_seq;
   SELECT MAX(id) FROM table_name;
   ```

### 问题 3: Crontab 未执行

**症状**: 日志文件没有更新

**排查步骤**:
1. 检查 crontab 配置
   ```bash
   crontab -l | grep check_sequences
   ```

2. 检查 cron 服务状态
   ```bash
   systemctl status cron
   ```

3. 手动测试命令
   ```bash
   cd /opt/health-app/backend && source venv/bin/activate && python3 scripts/check_sequences.py
   ```

## 📚 相关文档

- `DATABASE_SEQUENCE_FIX_REPORT.md` - 详细的修复报告
- `GARMIN_ISSUE_RESOLUTION.md` - Garmin 问题解决报告
- `FINAL_STATUS_REPORT.md` - 系统最终状态报告
- `AGENTS.md` - 开发规范

## ✅ 检查清单

### 部署前检查

- [ ] 脚本已上传到服务器
- [ ] 脚本权限已设置为可执行
- [ ] 日志目录已创建

### 部署后检查

- [ ] 手动运行检查脚本成功
- [ ] Crontab 已配置
- [ ] 日志文件可写入
- [ ] 所有序列状态正常

### 定期检查（每周）

- [ ] 查看自动检查日志
- [ ] 验证序列状态
- [ ] 检查是否有新的异常

### 数据迁移后检查

- [ ] 运行检查脚本
- [ ] 修复发现的问题
- [ ] 验证修复结果
- [ ] 测试插入操作

## 🎉 总结

### 已实现的功能

1. ✅ 自动检查所有表的序列状态
2. ✅ 自动修复异常的序列
3. ✅ 定时任务每天自动检查
4. ✅ 详细的日志记录
5. ✅ 完整的使用文档

### 预期效果

- 🛡️ 防止主键冲突错误
- 🔍 及时发现序列问题
- 🔧 快速修复序列问题
- 📊 持续监控数据库健康

### 维护建议

- **每周**: 查看自动检查日志
- **每月**: 手动运行一次检查
- **迁移后**: 立即检查和修复
- **发现问题**: 及时修复并记录

---

**重要提醒**: 数据库序列问题可能导致严重的系统故障，建议定期检查和维护。
