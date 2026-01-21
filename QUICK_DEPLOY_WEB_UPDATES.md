# Web端更新快速部署指南

## 更新内容

1. ✅ Web端添加计圈功能（与小程序一致）
2. ✅ 科学分析结果缓存（避免重复生成）

## 部署步骤

### 1. 运行数据库迁移

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 添加lap_data字段（如果之前已运行，可跳过）
sqlite3 health.db < ../scripts/migrations/20260121_01_add_lap_data_to_workout.sql

# 添加post_workout_analysis字段（新增）
sqlite3 health.db < ../scripts/migrations/20260121_02_add_post_workout_analysis.sql
```

验证迁移：
```bash
sqlite3 health.db "PRAGMA table_info(workout_records);" | grep -E "lap_data|post_workout_analysis"
```

应该看到：
```
22|lap_data|TEXT|0||0
23|post_workout_analysis|TEXT|0||0
```

### 2. 重启后端服务

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 停止现有服务
pkill -f "python.*main.py"

# 启动服务
./start.sh
```

### 3. 重新构建并部署前端

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/frontend

# 安装依赖（如有更新）
npm install

# 构建生产版本
npm run build

# 启动服务（或使用PM2）
npm start

# 或使用PM2
pm2 restart health-frontend
```

### 4. 测试功能

#### 测试计圈功能

1. 访问 https://health.westwetlandtech.com/workout
2. 选择一条Garmin同步的运动记录
3. 查看详情区域的Tab按钮（统计信息、计圈、区间用时）
4. 点击"计圈"Tab
5. 应该看到每圈的详细数据（或空状态提示）

#### 测试科学分析缓存

1. 选择一条运动记录
2. 点击"📊 科学分析"按钮
3. 首次会显示"分析中..."，完成后显示"✓ 科学分析完成"
4. 关闭分析弹窗，再次点击"📊 科学分析"
5. 应该立即显示结果，提示"✓ 已加载分析结果"
6. 应该看到"🔄 重新生成"按钮
7. 点击"🔄 重新生成"，会重新分析并更新缓存

### 5. 验证日志

```bash
# 查看后端日志
tail -f backend/backend.log | grep -E "lap|post_workout_analysis|科学分析"
```

应该看到类似日志：
```
INFO - 用户 1 使用缓存的运动后分析 (workout_id=123)
INFO - [运动后分析] 分析完成并已保存
```

### 6. 检查数据库

```bash
cd backend

# 检查计圈数据
sqlite3 health.db "SELECT id, workout_name, lap_data IS NOT NULL as has_laps FROM workout_records WHERE source='garmin' LIMIT 5;"

# 检查科学分析缓存
sqlite3 health.db "SELECT id, workout_name, post_workout_analysis IS NOT NULL as has_analysis FROM workout_records LIMIT 5;"
```

## 常见问题

### Q1: 前端Tab不显示

**解决**:
1. 清除浏览器缓存（Ctrl+Shift+R 或 Cmd+Shift+R）
2. 确认前端已重新构建：`cd frontend && npm run build`
3. 检查浏览器控制台是否有错误

### Q2: 科学分析每次都重新生成

**可能原因**:
- 数据库迁移未成功
- 后端代码未更新

**解决**:
1. 检查数据库字段：`sqlite3 health.db "PRAGMA table_info(workout_records);" | grep post_workout_analysis`
2. 检查后端日志是否有保存成功的日志
3. 重启后端服务

### Q3: 计圈数据为空

**可能原因**:
- 该运动是室内运动，Garmin未记录分段
- 需要手动刷新数据

**解决**:
1. 在运动详情页点击"刷新"按钮
2. 或调用 `/refresh-laps` API
3. 或重新同步Garmin数据

### Q4: 迁移失败

**解决**:
```bash
# 检查数据库文件
ls -la backend/health.db

# 如果字段已存在，可以忽略错误
# SQLite的 "IF NOT EXISTS" 会自动跳过已存在的字段
```

## 回滚（如果需要）

### 回滚数据库

```bash
cd backend

# 回滚lap_data字段
sqlite3 health.db "ALTER TABLE workout_records DROP COLUMN lap_data;"

# 回滚post_workout_analysis字段
sqlite3 health.db "ALTER TABLE workout_records DROP COLUMN post_workout_analysis;"
```

### 回滚代码

```bash
# 使用git回滚到之前的版本
git log --oneline | head -10
git checkout <commit-hash>
```

## 性能影响

### 数据库
- 新增2个TEXT字段，存储JSON数据
- 对查询性能影响极小
- 建议定期清理过期的分析缓存（可选）

### API响应时间
- **首次科学分析**: 5-15秒（取决于数据量和AI响应）
- **缓存加载**: <100ms（直接从数据库读取）
- **性能提升**: 约50-150倍

### 存储空间
- 每条运动记录的计圈数据：约1-5KB
- 每条运动记录的科学分析：约2-10KB
- 1000条记录估计增加：3-15MB

## 监控建议

### 1. 缓存命中率

```bash
# 查看缓存使用情况
sqlite3 health.db "
SELECT 
  COUNT(*) as total_workouts,
  SUM(CASE WHEN post_workout_analysis IS NOT NULL THEN 1 ELSE 0 END) as cached_analysis,
  ROUND(100.0 * SUM(CASE WHEN post_workout_analysis IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as cache_rate
FROM workout_records;
"
```

### 2. 日志监控

```bash
# 监控缓存使用
tail -f backend/backend.log | grep "使用缓存的运动后分析"

# 监控新生成
tail -f backend/backend.log | grep "分析完成并已保存"
```

## 完成！

现在你的Web端应该已经支持：
- ✅ 计圈数据展示（统计信息、计圈、区间用时三个Tab）
- ✅ 科学分析结果缓存（快速加载，支持重新生成）

查看完整文档: 
- `WEB_LAP_AND_ANALYSIS_CACHE.md` - 详细实现文档
- `LAP_DATA_IMPLEMENTATION.md` - 小程序计圈功能文档
