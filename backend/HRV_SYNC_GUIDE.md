# HRV 数据同步指南

## 概述

心率变异性（HRV）数据现在已集成到 Garmin 数据同步中。HRV 数据从 Garmin Connect 的睡眠数据中提取（`avgOvernightHrv` 字段）。

## 当前状态

- ✅ HRV 数据提取逻辑已实现
- ✅ 新同步的数据会自动包含 HRV
- ⚠️ 历史数据需要批量更新

## 检查 HRV 数据状态

### 查看数据库中的 HRV 数据统计

```bash
cd backend
source venv/bin/activate
sqlite3 health.db "SELECT COUNT(*) as total, COUNT(hrv) as with_hrv, COUNT(*) - COUNT(hrv) as missing_hrv FROM garmin_data WHERE user_id=1;"
```

### 查看最近几天的 HRV 数据

```bash
sqlite3 health.db "SELECT record_date, sleep_score, hrv, avg_heart_rate FROM garmin_data WHERE user_id=1 AND record_date >= date('now', '-7 days') ORDER BY record_date DESC;"
```

## 批量更新历史 HRV 数据

### 使用更新脚本

已创建专门的脚本 `scripts/update_hrv_data.py` 用于批量更新历史数据的 HRV 值。

#### 基本用法

```bash
cd backend
source venv/bin/activate
python scripts/update_hrv_data.py <email> <password> <user_id>
```

#### 限制更新范围（推荐）

为了避免一次性同步过多数据导致 API 限制，建议分批更新：

```bash
# 更新最近 30 天的数据
python scripts/update_hrv_data.py itsoso@126.com Sisi1124 1 --days 30

# 更新最近 90 天的数据
python scripts/update_hrv_data.py itsoso@126.com Sisi1124 1 --days 90

# 更新最近 180 天的数据
python scripts/update_hrv_data.py itsoso@126.com Sisi1124 1 --days 180
```

#### 更新所有历史数据

```bash
# 更新所有缺少 HRV 的记录（可能需要较长时间）
python scripts/update_hrv_data.py itsoso@126.com Sisi1124 1
```

### 脚本功能

- ✅ 自动查找所有缺少 HRV 数据的记录
- ✅ 从 Garmin Connect 重新获取这些日期的数据
- ✅ 只更新 HRV 字段，不影响其他数据
- ✅ 显示详细的进度和结果统计
- ✅ 支持限制更新范围（`--days` 参数）
- ✅ 每 10 条记录自动提交，避免数据库锁定

### 注意事项

1. **API 限制**：Garmin Connect API 可能有请求频率限制，建议分批更新
2. **数据可用性**：某些旧日期可能没有 HRV 数据（设备不支持或未佩戴）
3. **执行时间**：更新大量数据可能需要较长时间（每条记录约 1-2 秒）

## 技术细节

### HRV 数据来源

HRV 数据从 Garmin Connect 的 `get_sleep_data()` API 返回的 `avgOvernightHrv` 字段中提取。

### 数据解析逻辑

1. 优先从睡眠数据（`sleep_data`）中获取 `avgOvernightHrv`
2. 如果睡眠数据中没有，尝试从用户摘要（`summary`）中获取
3. 如果都没有，HRV 值设为 `None`

### 代码位置

- **数据提取**：`backend/app/services/data_collection/garmin_connect.py`
  - `parse_to_garmin_data_create()` 方法中的 HRV 提取逻辑
- **批量更新脚本**：`backend/scripts/update_hrv_data.py`

## 验证更新结果

更新完成后，可以运行以下命令验证：

```bash
# 检查更新后的统计
sqlite3 health.db "SELECT COUNT(*) as total, COUNT(hrv) as with_hrv, COUNT(*) - COUNT(hrv) as missing_hrv FROM garmin_data WHERE user_id=1;"

# 查看最近更新的记录
sqlite3 health.db "SELECT record_date, sleep_score, hrv FROM garmin_data WHERE user_id=1 AND hrv IS NOT NULL ORDER BY record_date DESC LIMIT 10;"
```

## 前端显示

HRV 数据已在前端页面中显示：

- **数据表格**：`http://localhost:3000/garmin` 的详细数据列表中
- **趋势图表**：HRV 趋势图和主趋势图中
- **心率分析**：心率分析标签页中的平均 HRV 值

## 故障排除

### 问题：更新脚本报错 "Garmin 登录失败"

**解决方案**：
- 检查邮箱和密码是否正确
- 确认网络连接正常
- 检查 Garmin Connect 账号是否正常

### 问题：某些日期的 HRV 仍然为空

**可能原因**：
- 该日期设备未佩戴或未记录 HRV 数据
- Garmin Connect 中没有该日期的 HRV 数据
- 设备不支持 HRV 测量

**解决方案**：
- 这是正常情况，不是所有日期都有 HRV 数据
- 可以手动检查 Garmin Connect 应用确认该日期是否有 HRV 数据

### 问题：更新速度很慢

**解决方案**：
- 这是正常的，每条记录需要调用 Garmin API
- 建议使用 `--days` 参数分批更新
- 可以在非高峰时段运行更新

