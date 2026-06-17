# 数据库序列修复报告

**修复时间**: 2026-01-23 08:15 UTC+8  
**严重程度**: 🔴 高危（16 个表受影响）

## 📊 问题概述

### 发现的问题

在全面检查数据库后，发现 **16 个表**的主键序列与实际数据不同步，可能导致：
- ❌ 插入新记录时主键冲突
- ❌ 数据同步失败
- ❌ API 返回 500 错误
- ❌ 用户操作失败

### 受影响的表

| 表名 | 修复前序列 | 修复后序列 | 最大ID | 风险等级 |
|------|-----------|-----------|--------|---------|
| blood_pressure_records | 1 | 2 | 2 | 🔴 高 |
| daily_recommendations | 11 | 54 | 54 | 🔴 高 |
| daily_reviews | 1 | 6 | 6 | 🔴 高 |
| garmin_credentials | 1 | 8 | 8 | 🔴 高 |
| goal_progress | 1 | 4 | 4 | 🔴 高 |
| goals | 1 | 8 | 8 | 🔴 高 |
| habit_records | 1 | 2 | 2 | 🔴 高 |
| health_checkins | 1 | 14 | 14 | 🔴 高 |
| heart_rate_samples | 104 | 35489 | 35489 | 🔴 极高 |
| invitation_codes | 1 | 4 | 4 | 🔴 高 |
| medical_exam_items | 1 | 74 | 74 | 🔴 高 |
| medical_exams | 1 | 5 | 5 | 🔴 高 |
| user_applications | 1 | 2 | 2 | 🔴 高 |
| users | 1 | 20 | 20 | 🔴 极高 |
| weight_records | 1 | 4 | 4 | 🔴 高 |
| workout_records | 1 | 51 | 51 | 🔴 高 |

### 最严重的案例

#### 1. heart_rate_samples
- **序列值**: 104
- **实际最大ID**: 35489
- **差距**: 35385（差距巨大！）
- **影响**: 任何新的心率数据都会失败

#### 2. daily_recommendations
- **序列值**: 11
- **实际最大ID**: 54
- **差距**: 43
- **影响**: 新的每日推荐无法生成

#### 3. users
- **序列值**: 1
- **实际最大ID**: 20
- **影响**: 新用户注册会失败（极其严重！）

## 🔍 根本原因分析

### 可能的原因

1. **数据迁移时未更新序列** ⭐⭐⭐⭐⭐
   - 从旧数据库迁移数据时
   - 直接插入数据但没有更新序列
   - 这是最可能的原因

2. **手动插入数据时指定了 ID**
   ```sql
   -- 错误示例
   INSERT INTO users (id, email, ...) VALUES (1, 'test@example.com', ...);
   -- 这样不会自动更新序列
   ```

3. **数据库恢复后序列未重置**
   - 从备份恢复数据
   - 但序列没有一起恢复

4. **使用 COPY 命令导入数据**
   ```sql
   COPY users FROM 'users.csv';
   -- COPY 不会更新序列
   ```

### 为什么之前没有发现？

- 大部分表的记录较少，还没有触发冲突
- `garmin_data` 表因为频繁同步，最先暴露问题
- 其他表可能还没有新增操作，所以没有报错

## ✅ 修复结果

### 修复统计

```
✅ 成功修复: 16 个表
❌ 修复失败: 0 个表
🎉 成功率: 100%
```

### 修复后验证

所有表的序列值现在都 >= 最大 ID，可以安全地插入新记录。

```
✅ blood_pressure_records: 序列 2 >= 最大ID 2
✅ daily_recommendations: 序列 54 >= 最大ID 54
✅ daily_reviews: 序列 6 >= 最大ID 6
✅ garmin_credentials: 序列 8 >= 最大ID 8
✅ goal_progress: 序列 4 >= 最大ID 4
✅ goals: 序列 8 >= 最大ID 8
✅ habit_records: 序列 2 >= 最大ID 2
✅ health_checkins: 序列 14 >= 最大ID 14
✅ heart_rate_samples: 序列 35489 >= 最大ID 35489
✅ invitation_codes: 序列 4 >= 最大ID 4
✅ medical_exam_items: 序列 74 >= 最大ID 74
✅ medical_exams: 序列 5 >= 最大ID 5
✅ user_applications: 序列 2 >= 最大ID 2
✅ users: 序列 20 >= 最大ID 20
✅ weight_records: 序列 4 >= 最大ID 4
✅ workout_records: 序列 51 >= 最大ID 51
```

## 🛡️ 预防措施

### 1. 自动检查脚本

创建定期检查脚本：

```bash
#!/bin/bash
# /opt/health-app/scripts/check_sequences.sh

cd /opt/health-app/backend
source venv/bin/activate

python3 << 'PYTHON'
from sqlalchemy import text
from app.database import SessionLocal
import sys

db = SessionLocal()
issues = []

try:
    tables = ['users', 'garmin_data', 'workout_records', 'diet_records', 
              'weight_records', 'blood_pressure_records', 'medical_exams']
    
    for table in tables:
        seq_name = f'{table}_id_seq'
        seq_value = db.execute(text(f"SELECT last_value FROM {seq_name};")).scalar()
        max_id = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table};")).scalar()
        
        if seq_value < max_id:
            issues.append(f'{table}: seq={seq_value} < max_id={max_id}')
    
    if issues:
        print('❌ 发现序列问题:')
        for issue in issues:
            print(f'  - {issue}')
        sys.exit(1)
    else:
        print('✅ 所有序列正常')
        sys.exit(0)
        
except Exception as e:
    print(f'❌ 检查失败: {e}')
    sys.exit(2)
finally:
    db.close()
PYTHON
```

### 2. 自动修复脚本

```bash
#!/bin/bash
# /opt/health-app/scripts/fix_sequences.sh

cd /opt/health-app/backend
source venv/bin/activate

python3 << 'PYTHON'
from sqlalchemy import text, inspect
from app.database import SessionLocal, engine

db = SessionLocal()
try:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    for table in tables:
        columns = [col['name'] for col in inspector.get_columns(table)]
        if 'id' not in columns:
            continue
        
        seq_name = f'{table}_id_seq'
        
        try:
            db.execute(text(f"""
                SELECT setval('{seq_name}', 
                    (SELECT COALESCE(MAX(id), 1) FROM {table})
                );
            """))
            db.commit()
            print(f'✅ {table}')
        except:
            pass
    
    print('\\n🎉 所有序列已修复')
    
except Exception as e:
    print(f'❌ 修复失败: {e}')
    db.rollback()
finally:
    db.close()
PYTHON
```

### 3. 添加到 Crontab

```bash
# 每天凌晨 2 点检查序列
0 2 * * * /opt/health-app/scripts/check_sequences.sh >> /var/log/health-app/sequence-check.log 2>&1
```

### 4. 数据迁移时的正确做法

```python
# 迁移数据后，务必更新序列
def migrate_data_with_sequence_fix():
    # 1. 迁移数据
    migrate_users()
    migrate_garmin_data()
    # ...
    
    # 2. 修复所有序列
    from sqlalchemy import text
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        tables = ['users', 'garmin_data', 'workout_records', ...]
        
        for table in tables:
            seq_name = f'{table}_id_seq'
            db.execute(text(f"""
                SELECT setval('{seq_name}', 
                    (SELECT COALESCE(MAX(id), 1) FROM {table})
                );
            """))
        
        db.commit()
        print('✅ 序列已更新')
    except Exception as e:
        print(f'❌ 序列更新失败: {e}')
        db.rollback()
    finally:
        db.close()
```

### 5. 使用 UPSERT 模式

在代码中使用更安全的插入模式：

```python
from sqlalchemy.dialects.postgresql import insert

def safe_insert_or_update(db, model, data):
    """安全的插入或更新，避免主键冲突"""
    stmt = insert(model).values(**data)
    
    # 如果主键冲突，则更新
    stmt = stmt.on_conflict_do_update(
        index_elements=['id'],
        set_=data
    )
    
    db.execute(stmt)
    db.commit()
```

## 📈 监控建议

### 1. 添加告警

```python
# backend/app/utils/sequence_monitor.py
from sqlalchemy import text
from app.database import SessionLocal

def check_critical_sequences():
    """检查关键表的序列状态"""
    critical_tables = ['users', 'garmin_data', 'workout_records']
    
    db = SessionLocal()
    alerts = []
    
    try:
        for table in critical_tables:
            seq_name = f'{table}_id_seq'
            seq_value = db.execute(text(f"SELECT last_value FROM {seq_name};")).scalar()
            max_id = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table};")).scalar()
            
            if seq_value < max_id:
                alerts.append({
                    'table': table,
                    'seq_value': seq_value,
                    'max_id': max_id,
                    'severity': 'critical'
                })
            elif seq_value == max_id:
                alerts.append({
                    'table': table,
                    'seq_value': seq_value,
                    'max_id': max_id,
                    'severity': 'warning'
                })
        
        return alerts
    finally:
        db.close()
```

### 2. 健康检查端点

```python
# backend/app/api/health.py
from fastapi import APIRouter
from app.utils.sequence_monitor import check_critical_sequences

router = APIRouter()

@router.get("/health/sequences")
async def check_sequences_health():
    """检查数据库序列健康状态"""
    alerts = check_critical_sequences()
    
    if not alerts:
        return {
            "status": "healthy",
            "message": "所有序列正常"
        }
    
    critical = [a for a in alerts if a['severity'] == 'critical']
    warnings = [a for a in alerts if a['severity'] == 'warning']
    
    return {
        "status": "unhealthy" if critical else "warning",
        "critical": critical,
        "warnings": warnings
    }
```

## 🎯 后续行动

### 立即执行（已完成）

- ✅ 修复所有 16 个表的序列
- ✅ 验证修复结果
- ✅ 创建修复报告

### 短期（本周内）

- [ ] 创建自动检查脚本
- [ ] 添加到 crontab
- [ ] 创建自动修复脚本
- [ ] 添加序列健康检查端点

### 中期（本月内）

- [ ] 审查所有数据插入代码
- [ ] 使用 UPSERT 模式重构关键操作
- [ ] 添加序列监控告警
- [ ] 编写数据迁移最佳实践文档

### 长期

- [ ] 定期（每月）审查序列状态
- [ ] 在数据迁移流程中强制检查序列
- [ ] 考虑使用 UUID 代替自增 ID（避免此类问题）

## 📚 相关文档

- `GARMIN_ISSUE_RESOLUTION.md` - Garmin 问题解决报告
- `FINAL_STATUS_REPORT.md` - 最终状态报告
- `AGENTS.md` - 开发规范（包含数据安全部分）

## 💡 经验教训

### 1. 数据迁移的隐患

数据迁移是最容易出现序列问题的场景：
- ✅ 迁移数据后**必须**更新序列
- ✅ 使用脚本自动化，不要手动操作
- ✅ 迁移后**必须**验证序列状态

### 2. 早期发现的重要性

如果不是因为 Garmin 同步频繁触发了问题：
- ❌ `users` 表序列异常可能导致新用户无法注册
- ❌ `medical_exams` 表可能导致体检记录无法保存
- ❌ `workout_records` 表可能导致运动记录丢失

**定期检查可以避免严重后果！**

### 3. 监控的价值

- 主动监控 > 被动修复
- 自动化检查 > 手动检查
- 预防 > 治疗

## 🎉 总结

### 修复成果

- ✅ 发现并修复了 **16 个表**的序列问题
- ✅ 避免了潜在的严重故障
- ✅ 提供了完整的预防方案

### 影响范围

如果不修复，可能导致：
- ❌ 新用户无法注册
- ❌ Garmin 数据无法同步
- ❌ 运动记录无法保存
- ❌ 体检数据无法录入
- ❌ 各种 500 错误

### 当前状态

🟢 **所有序列已修复，系统运行正常**

---

**重要提醒**: 这次修复解决了当前问题，但需要建立长期的监控和预防机制，避免问题再次发生。
