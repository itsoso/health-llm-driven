---
name: health-query
description: Query health data from the Health Management System - steps, heart rate, HRV, SpO2, sleep, weight, blood pressure, workouts, diet, and checkin status. Use when the user asks about their health metrics, fitness data, or daily stats.
version: 1.0.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🔍"
---

You have access to a Health Management System API. Use curl to query health data.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`

## Available Endpoints

### 综合健康数据（Garmin）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/comprehensive?days=7"
```
返回：步数、心率、睡眠、压力、Body Battery 综合分析

### 睡眠数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/sleep?days=7"
```

### 心率数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/heart-rate?days=7"
```

### 活动数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/activity?days=7"
```

### HRV心率变异性
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/hrv?days=7"
```
返回：最新HRV、均值、趋势方向、低HRV天数、每日数据

### 血氧SpO2
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/spo2?days=7"
```
返回：最新血氧、均值、最低值、低于95%天数、每日数据

### 体重记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/weight/records/me?limit=7"
```

### 血压记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/blood-pressure/records/me?limit=7"
```

### 今日饮水
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/me/date/$(date +%Y-%m-%d)"
```

### 饮水统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/me/stats?days=7"
```

### 今日打卡
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/records/today"
```

### 打卡统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/stats"
```

### 运动记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/workout/me?days=7"
```

### 健康评分
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health-score/daily/me"
```

## Response Rules
- Always format responses in readable Chinese
- Include units (步, bpm, 分, kg, mmHg, ml)
- Highlight anomalies or notable changes
- Compare with targets when available
- 当HRV状态为low时，主动提醒用户注意休息
- 当SpO2低于95%时，提醒用户关注血氧
