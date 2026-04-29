---
name: health-query
description: Query health data from the Health Management System - steps, heart rate, sleep, weight, blood pressure, workouts, diet, checkin status, environment, illness, plans, anomalies, supplements, mood, and more.
version: 2.0.0
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You have access to a Health Management System API. Use curl to query health data.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## Available Endpoints

### 综合健康数据（Garmin）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/comprehensive?days=7"
```
返回：步数、心率、睡眠、压力、Body Battery 综合分析

### 睡眠数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/sleep?days=7"
```

### 心率数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/heart-rate?days=7"
```

### 活动数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/activity?days=7"
```

### HRV 数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/hrv?days=7"
```

### 血氧数据
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/garmin-analysis/me/spo2?days=7"
```

### 体重记录
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/weight/records/me?limit=7"
```

### 血压记录
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/blood-pressure/records/me?limit=7"
```

### 今日饮水
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/water/records/me/date/$(date +%Y-%m-%d)"
```

### 饮水统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/water/records/me/stats?days=7"
```

### 今日打卡
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/checkin/records/today"
```

### 打卡统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/checkin/stats"
```

### 运动记录
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/workout/me?days=7"
```

### 运动详情
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/workout/me/{workout_id}"
```
替换 {workout_id} 为具体运动ID。

### 运动统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/workout/me/stats"
```

### 健康评分
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-score/daily/me"
```

---

## 环境与天气

### 当前天气
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/weather"
```

### 空气质量
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/air-quality"
```

### 户外运动适宜度
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/exercise-suitability"
```

---

## 饮食记录

### 最近饮食
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/diet/records/me?days=3"
```

---

## 病症追踪

### 活跃病症
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/illness/episodes?status=active"
```
status 可选: active / improving / resolved / all（不传默认 active）

### 病症详情
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/illness/episodes/{episode_id}"
```

---

## 排泄记录

### 最近排泄
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/excretion/records/me?limit=14"
```

### 排泄统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/excretion/stats/me"
```

### 排泄模式分析
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/excretion/patterns/me"
```

---

## 智能计划

### 当前周计划
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/smart-plan/current?week=current"
```

### 今日计划
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/smart-plan/today"
```

### 活跃目标
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/smart-plan/goals/active"
```

---

## 异常预警

### 我的预警
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/anomaly-alerts/me?days=7&acknowledged=false"
```
参数: days (查询天数, 默认7), acknowledged (true/false/不传=全部), severity (info/warning/critical)

---

## 情绪记录

### 今日情绪
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/mood/records/me/today"
```

---

## 补剂

### 我的补剂列表
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/supplements/me/definitions"
```

### 今日补剂状态
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/supplements/me/date/$(date +%Y-%m-%d)"
```

### 补剂统计
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/supplements/me/stats"
```

---

## 提醒

### 待处理提醒
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/reminders/me?status=pending"
```

---

## 用户画像

### 我的资料
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/profile/me"
```
返回：身高、体重目标、慢性病、过敏、用药等

---

## 健康趋势

### 趋势总览
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trends/latest"
```

### 维度趋势
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trends/{dimension}?period=30d"
```
dimension 可选: weight / sleep / exercise / overall

---

## 交叉分析

### 恢复就绪度 + 能量平衡
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-context/me/cross-analysis"
```
返回: recovery_readiness（恢复就绪度）、sleep_exercise_correlation（睡眠运动关联）、energy_balance（能量平衡）、hydration（饮水充足度）

---

## Response Rules
- Always format responses in readable Chinese
- Include units (步, bpm, 分, kg, mmHg, ml)
- Highlight anomalies or notable changes
- Compare with targets when available
- HRV 标注状态（balanced/low/unbalanced），low 时建议休息
- SpO2 < 95% 时提醒关注
- 异常预警按严重度排序，critical 优先提醒
