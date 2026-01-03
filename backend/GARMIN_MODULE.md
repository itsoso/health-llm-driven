# Garmin数据收集和分析模块文档

## 概述

本模块提供了完整的Garmin可穿戴设备数据收集和分析功能，包括：
- 数据同步（API和手动导入）
- 睡眠质量分析
- 心率数据分析
- 身体电量分析
- 活动数据分析
- 综合分析

## API端点

### 数据收集

#### 1. 同步单日Garmin数据
```
POST /api/v1/data-collection/garmin/sync
参数:
  - user_id: int
  - target_date: date (YYYY-MM-DD)
  - access_token: str (可选，Garmin API token)
```

#### 2. 批量同步日期范围数据
```
POST /api/v1/data-collection/garmin/sync-range
参数:
  - user_id: int
  - start_date: date
  - end_date: date
  - access_token: str (可选)
```

#### 3. 检查同步状态
```
GET /api/v1/data-collection/garmin/sync-status/{user_id}?days=30
返回哪些日期有数据，哪些缺失
```

#### 4. 手动导入Garmin数据
```
POST /api/v1/daily-health/garmin
使用GarminDataCreate schema直接创建数据
```

### 数据分析

#### 1. 睡眠质量分析
```
GET /api/v1/garmin-analysis/user/{user_id}/sleep?days=7
返回:
  - 平均睡眠分数
  - 平均睡眠时长
  - 深度睡眠分析
  - 睡眠质量评估
  - 改进建议
```

#### 2. 心率分析
```
GET /api/v1/garmin-analysis/user/{user_id}/heart-rate?days=7
返回:
  - 平均心率
  - 静息心率
  - 心率变异性(HRV)
  - 心率健康评估
```

#### 3. 身体电量分析
```
GET /api/v1/garmin-analysis/user/{user_id}/body-battery?days=7
返回:
  - 平均充电值
  - 平均消耗值
  - 能量水平评估
```

#### 4. 活动分析
```
GET /api/v1/garmin-analysis/user/{user_id}/activity?days=7
返回:
  - 总步数/平均步数
  - 消耗卡路里
  - 活动分钟数
  - 是否符合WHO建议
```

#### 5. 综合分析
```
GET /api/v1/garmin-analysis/user/{user_id}/comprehensive?days=7
返回所有分析的综合报告
```

## 使用示例

### Python示例

```python
import requests
from datetime import date, timedelta

BASE_URL = "http://localhost:8000/api/v1"

# 1. 手动导入Garmin数据
garmin_data = {
    "user_id": 1,
    "record_date": "2024-01-15",
    "sleep_score": 85,
    "total_sleep_duration": 480,  # 分钟
    "deep_sleep_duration": 120,
    "rem_sleep_duration": 90,
    "avg_heart_rate": 65,
    "resting_heart_rate": 58,
    "hrv": 45,
    "body_battery_charged": 85,
    "body_battery_lowest": 45,
    "steps": 12000,
    "calories_burned": 2200,
    "active_minutes": 45
}

response = requests.post(
    f"{BASE_URL}/daily-health/garmin",
    json=garmin_data
)
print(response.json())

# 2. 分析睡眠质量
response = requests.get(
    f"{BASE_URL}/garmin-analysis/user/1/sleep?days=7"
)
print(response.json())

# 3. 获取综合分析
response = requests.get(
    f"{BASE_URL}/garmin-analysis/user/1/comprehensive?days=7"
)
print(response.json())
```

### cURL示例

```bash
# 手动导入数据
curl -X POST "http://localhost:8000/api/v1/daily-health/garmin" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "record_date": "2024-01-15",
    "sleep_score": 85,
    "total_sleep_duration": 480,
    "avg_heart_rate": 65,
    "steps": 12000
  }'

# 分析睡眠
curl "http://localhost:8000/api/v1/garmin-analysis/user/1/sleep?days=7"

# 检查同步状态
curl "http://localhost:8000/api/v1/data-collection/garmin/sync-status/1?days=30"
```

## Garmin API集成说明

### 当前状态

目前Garmin官方API需要：
1. Garmin开发者账号
2. OAuth 1.0a认证流程
3. 应用注册和审核

### 替代方案

1. **手动导入**：从Garmin Connect导出CSV，然后通过API导入
2. **第三方库**：使用`garminconnect`等Python库（需要Garmin账号）
3. **数据导出**：定期从Garmin Connect手动导出数据

### 实现OAuth流程（未来）

如果需要实现完整的OAuth认证：

1. 在Garmin Developer Portal注册应用
2. 获取Consumer Key和Consumer Secret
3. 实现OAuth 1.0a认证流程
4. 获取access_token和access_token_secret
5. 使用token调用Garmin API

## 数据分析功能

### 睡眠质量评估标准

- **优秀**: 睡眠分数 >= 80
- **良好**: 睡眠分数 >= 60
- **一般**: 睡眠分数 >= 40
- **较差**: 睡眠分数 < 40

### 心率健康标准

- **正常静息心率**: 60-100 bpm
- **训练有素**: < 60 bpm（如无不适）
- **偏高**: > 100 bpm（可能表示压力或健康问题）

### 活动建议

- **WHO建议**: 每天至少10000步或150分钟中等强度活动
- **优秀**: >= 10000步 或 >= 150分钟
- **良好**: >= 7500步 或 >= 75分钟
- **一般**: >= 5000步 或 >= 30分钟

## 数据模型

Garmin数据包含以下字段：

- **心率**: avg_heart_rate, resting_heart_rate, hrv
- **睡眠**: sleep_score, total_sleep_duration, deep_sleep_duration, rem_sleep_duration
- **身体电量**: body_battery_charged, body_battery_drained, body_battery_most_charged, body_battery_lowest
- **活动**: steps, calories_burned, active_minutes
- **压力**: stress_level

## 最佳实践

1. **定期同步**: 建议每天同步一次数据
2. **数据分析**: 使用7-30天的数据进行分析，获得更准确的趋势
3. **数据完整性**: 使用sync-status检查数据完整性
4. **异常检测**: 关注睡眠分数、心率等指标的异常变化

## 故障排除

### 问题：无法同步数据

**原因**: 
- 缺少access_token
- Garmin API配置错误
- 网络问题

**解决**:
- 使用手动导入接口
- 检查API配置
- 使用第三方库或导出功能

### 问题：分析结果不准确

**原因**:
- 数据不足（少于7天）
- 数据质量差

**解决**:
- 确保有足够的数据
- 检查数据完整性
- 使用更长的分析周期

