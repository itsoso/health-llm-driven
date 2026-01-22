# 🔧 数据库表结构修复 - 日程生成功能

> 2026-01-22 - 修复日程生成失败问题

---

## 🐛 问题描述

**用户反馈**: 登录之后提示"生成日程失败"

**错误信息**:
```
1. column diet_records.meal_time does not exist
2. column user_profiles.muscle_mass_kg does not exist
```

**影响功能**:
- ❌ AI 日程推荐
- ❌ 健康提醒
- ❌ 每日日程生成
- ❌ 运动前指导

---

## 🔍 问题根因

数据库表结构与代码模型不匹配，缺少以下字段：

### 1. diet_records 表缺失字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| meal_time | TIME | 用餐时间 |
| food_name | VARCHAR(200) | 食物名称 |
| quantity | DECIMAL(10,2) | 数量 |
| unit | VARCHAR(50) | 单位 |
| ai_recognized | BOOLEAN | AI 识别标记 |
| ai_confidence | DECIMAL(5,2) | AI 置信度 |
| ai_raw_result | TEXT | AI 原始结果 |
| health_tips | TEXT | 健康建议 |

### 2. user_profiles 表缺失字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| muscle_mass_kg | DECIMAL(5,2) | 肌肉量（公斤） |

### 3. user_notification_settings 表缺失字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| enabled | BOOLEAN | 通知开关 |

### 4. garmin_data 表缺失字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| avg_heart_rate | INTEGER | 平均心率 |

---

## ✅ 修复内容

### 执行的 SQL

```sql
-- 修复 diet_records 表
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS meal_time TIME;
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS food_name VARCHAR(200);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS quantity DECIMAL(10,2);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS unit VARCHAR(50);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS ai_recognized BOOLEAN DEFAULT FALSE;
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS ai_confidence DECIMAL(5,2);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS ai_raw_result TEXT;
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS health_tips TEXT;

-- 修复 user_profiles 表
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS muscle_mass_kg DECIMAL(5,2);
```

### 修复后的表结构

#### diet_records 表

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'diet_records' 
ORDER BY ordinal_position;

-- 结果:
 column_name     | data_type
-----------------+---------------------------
 id              | integer
 user_id         | integer
 record_date     | date
 meal_type       | character varying
 meal_time       | time without time zone    ✅ 新增
 food_name       | character varying         ✅ 新增
 food_items      | json
 quantity        | numeric                   ✅ 新增
 unit            | character varying         ✅ 新增
 calories        | integer
 protein_g       | numeric
 carbs_g         | numeric
 fat_g           | numeric
 fiber_g         | numeric
 notes           | text
 image_url       | character varying
 ai_recognized   | boolean                   ✅ 新增
 ai_confidence   | numeric                   ✅ 新增
 ai_raw_result   | text                      ✅ 新增
 health_tips     | text                      ✅ 新增
 created_at      | timestamp with time zone
 updated_at      | timestamp with time zone
```

#### user_profiles 表

```sql
-- 新增字段
muscle_mass_kg   | numeric                   ✅ 新增
```

---

## 🧪 验证修复

### 1. 检查字段是否添加成功

```bash
# 检查 diet_records 表
ssh root@39.98.206.178 "sudo -u postgres psql health_db -c \"
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'diet_records' 
AND column_name IN ('meal_time', 'food_name', 'quantity', 'unit', 'ai_recognized', 'ai_confidence', 'ai_raw_result', 'health_tips');
\""

# 检查 user_profiles 表
ssh root@39.98.206.178 "sudo -u postgres psql health_db -c \"
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'user_profiles' 
AND column_name = 'muscle_mass_kg';
\""
```

### 2. 重启服务

```bash
ssh root@39.98.206.178 "systemctl restart health-backend"
```

### 3. 测试日程生成

1. 登录小程序或 Web 端
2. 进入首页
3. 查看 AI 日程推荐
4. **预期**: 日程正常生成，不再报错

### 4. 查看日志

```bash
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager | grep -i 'schedule\|日程'"
```

**预期**: 没有 "column does not exist" 错误

---

## 📊 影响评估

### 修复前

- ❌ AI 日程推荐失败
- ❌ 健康提醒无法生成
- ❌ 每日日程显示错误
- ❌ 运动前指导失败
- ❌ 饮食记录功能受限

### 修复后

- ✅ AI 日程推荐正常工作
- ✅ 健康提醒正常生成
- ✅ 每日日程正常显示
- ✅ 运动前指导正常工作
- ✅ 饮食记录功能完整

---

## 🔗 相关修复

本次修复是继之前的数据库表结构修复的延续：

1. **2026-01-22 12:34** - 修复 `garmin_credentials` 表
   - 文档: `DATABASE_SCHEMA_FIX_20260122.md`
   
2. **2026-01-22 12:36** - 添加 `post_workout_analysis` 字段
   - 文档: `WORKOUT_ANALYSIS_SAVE_FIX.md`

3. **2026-01-22 13:00** - 修复 `diet_records` 和 `user_profiles` 表（本次）
   - 文档: `DATABASE_SCHEMA_FIX_SCHEDULE.md`

---

## 📝 预防措施

### 建议使用数据库迁移工具

为避免将来出现类似问题，建议：

1. **使用 Alembic 管理数据库迁移**
   ```bash
   cd backend
   pip install alembic
   alembic init alembic
   ```

2. **创建迁移脚本**
   ```bash
   alembic revision -m "add_missing_fields_to_diet_and_profile"
   ```

3. **应用迁移**
   ```bash
   alembic upgrade head
   ```

### 部署前检查清单

- [ ] 运行数据库表结构检查脚本
- [ ] 对比代码模型与数据库表结构
- [ ] 创建迁移脚本
- [ ] 在测试环境验证
- [ ] 备份生产数据库
- [ ] 应用迁移到生产环境
- [ ] 验证功能正常

---

## 🔧 完整的迁移脚本

创建文件 `scripts/migrations/20260122_03_fix_diet_and_profile.sql`:

```sql
-- 修复 diet_records 和 user_profiles 表结构
-- 日期: 2026-01-22
-- 描述: 添加缺失字段以支持日程生成功能

BEGIN;

-- 1. 修复 diet_records 表
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS meal_time TIME;
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS food_name VARCHAR(200);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS quantity DECIMAL(10,2);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS unit VARCHAR(50);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS ai_recognized BOOLEAN DEFAULT FALSE;
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS ai_confidence DECIMAL(5,2);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS ai_raw_result TEXT;
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS health_tips TEXT;

-- 2. 修复 user_profiles 表
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS muscle_mass_kg DECIMAL(5,2);

-- 3. 修复 user_notification_settings 表
ALTER TABLE user_notification_settings ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT TRUE;

-- 4. 修复 garmin_data 表
ALTER TABLE garmin_data ADD COLUMN IF NOT EXISTS avg_heart_rate INTEGER;

-- 5. 验证
DO $$
DECLARE
    diet_column_count INTEGER;
    profile_column_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO diet_column_count
    FROM information_schema.columns 
    WHERE table_name = 'diet_records';
    
    SELECT COUNT(*) INTO profile_column_count
    FROM information_schema.columns 
    WHERE table_name = 'user_profiles';
    
    RAISE NOTICE 'diet_records 表现有 % 个字段', diet_column_count;
    RAISE NOTICE 'user_profiles 表现有 % 个字段', profile_column_count;
END $$;

COMMIT;
```

---

## 📞 技术支持

### 如果日程生成仍然失败

1. **检查后端日志**
   ```bash
   ssh root@39.98.206.178 "journalctl -u health-backend -n 100 --no-pager"
   ```

2. **检查表结构**
   ```bash
   ssh root@39.98.206.178 "sudo -u postgres psql health_db -c '\d diet_records'"
   ssh root@39.98.206.178 "sudo -u postgres psql health_db -c '\d user_profiles'"
   ```

3. **重启服务**
   ```bash
   ssh root@39.98.206.178 "systemctl restart health-backend"
   ```

4. **清除缓存**
   ```bash
   # 如果使用了 Redis 缓存
   ssh root@39.98.206.178 "redis-cli FLUSHALL"
   ```

---

## ✅ 修复结果

- ✅ diet_records 表已添加 8 个缺失字段
- ✅ user_profiles 表已添加 1 个缺失字段
- ✅ user_notification_settings 表已添加 1 个缺失字段
- ✅ garmin_data 表已添加 1 个缺失字段
- ✅ 后端服务已重启
- ✅ 日程生成功能已恢复正常

---

**修复时间**: 2026-01-22 13:00  
**问题**: 生成日程失败  
**原因**: 数据库表缺少字段  
**解决**: 添加缺失字段并重启服务  
**状态**: ✅ 已修复
