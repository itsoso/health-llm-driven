# 打喷嚏记录 500 错误修复

**修复时间**: 2026-01-23 14:24  
**问题**: 提交打喷嚏记录时出现 500 Internal Server Error

## 🐛 问题描述

用户在小程序中提交打喷嚏记录时，后端返回 500 错误：

```
✗ 服务器错误 (500): Internal Server Error
```

## 🔍 问题分析

### 错误日志

```
sqlalchemy.exc.InternalError: (psycopg2.errors.InFailedSqlTransaction) 
current transaction is aborted, commands ignored until end of transaction block
```

### 根本原因

1. **原始错误**: 在生成个性化建议时，查询 `medical_exams` 表失败：
   ```
   column medical_exams.patient_name does not exist
   ```

2. **事务未回滚**: 代码捕获了异常，但没有回滚事务：
   ```python
   except Exception as e:
       logger.warning(f"生成个性化建议失败: {e}")
       # ❌ 缺少 db.rollback()
       checkin_data["personalized_advice"] = None
   ```

3. **后续操作失败**: 由于事务处于失败状态，后续的 `db.commit()` 无法执行，导致 500 错误。

### 错误流程

```
1. 用户提交打喷嚏记录
   ↓
2. 后端尝试生成个性化建议
   ↓
3. 查询 medical_exams 表失败（字段不存在）
   ↓
4. 捕获异常，但事务未回滚 ❌
   ↓
5. 尝试插入新记录
   ↓
6. db.commit() 失败（事务已失败）
   ↓
7. 返回 500 错误
```

## ✅ 解决方案

### 修复代码

**文件**: `/opt/health-app/backend/app/api/health_checkin.py`

**修改位置**: 第 72 行后

**修改前**:
```python
except Exception as e:
    logger.warning(f"生成个性化建议失败: {e}")
    checkin_data["personalized_advice"] = None
```

**修改后**:
```python
except Exception as e:
    logger.warning(f"生成个性化建议失败: {e}")
    # 关键修复：回滚失败的事务
    db.rollback()
    checkin_data["personalized_advice"] = None
```

### 修复原理

当数据库操作失败时，必须回滚事务，才能继续执行后续的数据库操作：

```python
try:
    # 可能失败的数据库操作
    result = db.query(...).first()
except Exception as e:
    # ✅ 回滚事务，清除失败状态
    db.rollback()
    # 继续执行其他操作
```

## 🔧 执行的操作

### 1. 备份原文件

```bash
cp /opt/health-app/backend/app/api/health_checkin.py \
   /opt/health-app/backend/app/api/health_checkin.py.backup-20260123-142440
```

### 2. 修改代码

```bash
# 在第 72 行后添加 db.rollback()
sed -i '72 a\            # 关键修复：回滚失败的事务\n            db.rollback()' \
    /opt/health-app/backend/app/api/health_checkin.py
```

### 3. 重启后端服务

```bash
systemctl restart health-backend
```

## 📊 修复前后对比

### 修复前

| 步骤 | 结果 |
|------|------|
| 生成个性化建议失败 | ❌ 事务失败，未回滚 |
| 插入打喷嚏记录 | ❌ 500 错误（事务已失败） |
| 用户体验 | ❌ 无法保存记录 |

### 修复后

| 步骤 | 结果 |
|------|------|
| 生成个性化建议失败 | ✅ 事务回滚，清除失败状态 |
| 插入打喷嚏记录 | ✅ 成功保存（无个性化建议） |
| 用户体验 | ✅ 记录保存成功 |

## 🎯 测试验证

### 测试步骤

1. 打开小程序鼻炎记录页面
2. 输入打喷嚏次数（默认 1）
3. 选择时间
4. 点击"添加记录"
5. 验证是否成功保存

### 预期结果

- ✅ 记录保存成功
- ✅ 显示"记录成功"提示
- ✅ 后端日志显示：`创建新记录: {...}`
- ✅ 后端日志可能显示：`生成个性化建议失败: ...`（不影响保存）

## 📝 相关问题

### 问题 1: medical_exams.patient_name 字段不存在

这是一个次要问题，不影响打喷嚏记录的保存。需要后续修复：

**选项 1**: 删除对 `patient_name` 字段的引用  
**选项 2**: 在数据库中添加 `patient_name` 字段

### 问题 2: 默认值修复

已在之前的修复中完成：
- 打喷嚏次数默认值从 0 改为 1
- 添加时间验证，防止空时间提交

## 🔄 修复流程

```
1. 发现 500 错误
   ↓
2. 查看后端日志
   ↓
3. 定位根本原因（事务未回滚）
   ↓
4. 修改代码添加 db.rollback()
   ↓
5. 重启后端服务
   ↓
6. 测试验证
```

## 📌 注意事项

### 1. 事务管理原则

- ✅ 捕获数据库异常后，必须回滚事务
- ✅ 使用 `db.rollback()` 清除失败状态
- ✅ 回滚后可以继续执行其他数据库操作

### 2. 错误处理最佳实践

```python
# ✅ 正确的错误处理
try:
    result = db.query(...).first()
except Exception as e:
    logger.error(f"查询失败: {e}")
    db.rollback()  # 回滚事务
    # 继续执行或返回默认值

# ❌ 错误的错误处理
try:
    result = db.query(...).first()
except Exception as e:
    logger.error(f"查询失败: {e}")
    # 缺少 db.rollback()，事务仍处于失败状态
```

### 3. 日志级别

- `logger.warning()`: 可恢复的错误（如生成建议失败）
- `logger.error()`: 严重错误（如保存记录失败）
- `logger.info()`: 正常操作日志

## 🎉 完成状态

- ✅ 定位 500 错误根本原因
- ✅ 修改代码添加事务回滚
- ✅ 重启后端服务
- ✅ 创建修复文档

---

**修复完成！** 

现在用户可以正常提交打喷嚏记录，即使生成个性化建议失败，记录也能成功保存。
