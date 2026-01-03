# 修复数据同步问题指南

## 问题描述

如果同步后的数据中缺少：
- 睡眠分数 (sleep_score)
- 睡眠时长 (total_sleep_duration)
- 平均心率 (avg_heart_rate)

## 解决方案

### 方法1：重新同步数据（推荐）

使用改进后的同步脚本重新同步数据：

```bash
cd backend
source venv/bin/activate

# 同步最近30天的数据
python scripts/sync_garmin.py <your_email> <your_password> <user_id> 30
```

改进后的解析逻辑会：
1. ✅ 尝试多种字段名变体
2. ✅ 从多个数据源提取（summary、sleep、heart_rate）
3. ✅ 添加调试日志帮助定位问题

### 方法2：调试数据获取

如果重新同步后仍然缺少数据，使用调试脚本查看实际返回的数据结构：

```bash
cd backend
source venv/bin/activate

# 调试昨天的数据
python scripts/debug_garmin_data.py <your_email> <your_password>

# 调试指定日期的数据
python scripts/debug_garmin_data.py <your_email> <your_password> 2024-01-15
```

调试脚本会显示：
- ✅ 每个API返回的实际数据结构
- ✅ 可用的字段名
- ✅ 数据提取建议

### 方法3：检查日志

同步时查看后端日志，会显示：
- 从哪些数据源获取了数据
- 解析出的关键字段值
- 数据提取的详细信息

```bash
# 启动后端时查看日志
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 改进内容

### 1. 睡眠数据解析改进

现在会尝试从以下字段获取睡眠分数：
- `sleepScore`
- `overallSleepScore`
- `sleepQualityScore`
- `overall`
- `sleepScores.overall`

睡眠时长会尝试：
- `sleepTimeSeconds`
- `duration`
- `sleepTimeMillis` (自动转换为秒)
- `totalSleepTimeSeconds`
- `sleepDurationSeconds`

### 2. 心率数据解析改进

现在会尝试从以下字段获取平均心率：
- `averageHeartRate`
- `avgHeartRate`
- `avg`
- `average`
- `heartRateAverage`

会从以下数据源提取：
- `get_heart_rates()` API返回的数据
- `get_user_summary()` API返回的数据

### 3. 调试功能

添加了详细的调试日志：
- 显示原始数据结构（前2000字符）
- 显示解析结果
- 显示数据来源

## 常见问题

### Q: 为什么有些日期没有数据？

A: 可能的原因：
1. Garmin设备当天没有佩戴
2. 设备没有同步到Garmin Connect
3. 数据还在处理中（通常需要几小时）

### Q: 如何确认数据已正确同步？

A: 
1. 查看数据库：
```bash
# 使用SQLite查看（开发环境）
sqlite3 health.db "SELECT record_date, sleep_score, total_sleep_duration, avg_heart_rate FROM garmin_data WHERE user_id=1 ORDER BY record_date DESC LIMIT 10;"
```

2. 使用API查看：
```bash
curl "http://localhost:8000/api/v1/daily-health/garmin/user/1?start_date=2024-01-01&end_date=2024-12-31" | jq '.data[0]'
```

3. 查看前端页面：
访问 http://localhost:3000/garmin

### Q: 数据同步后仍然缺少某些字段？

A: 
1. 运行调试脚本查看Garmin API实际返回的数据
2. 检查日志中的解析结果
3. 如果字段确实不存在，可能需要：
   - 检查Garmin设备是否支持该功能
   - 检查Garmin Connect中是否有该数据
   - 联系Garmin支持

## 下一步

1. **重新同步数据**：使用改进后的脚本
2. **验证数据**：检查数据库或前端页面
3. **查看分析**：使用 `/garmin-analysis` API获取分析结果

## 相关文档

- **Garmin集成文档**: `GARMIN_CONNECT_INTEGRATION.md`
- **数据查看指南**: `../VIEW_DATA.md`
- **运行指南**: `../RUN.md`

