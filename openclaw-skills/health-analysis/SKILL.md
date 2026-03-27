---
name: health-analysis
description: AI health analysis, daily recommendations, sleep/activity/heart insights, health trend predictions, recovery status, and health scores.
version: 2.0.0
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can request health analysis and recommendations from the Health Management System.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## Available Endpoints

### 健康问题检测
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/analysis/me/issues"
```
返回潜在健康问题及严重程度。

### 今日推荐（刷新）
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me/refresh?use_llm=true"
```
AI 生成个性化运动、饮食、作息建议。

### 今日推荐（缓存）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me"
```
获取缓存的今日建议，若无缓存则自动生成。

---

## 深度洞察

### 睡眠洞察
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me/sleep-insights"
```
返回：睡眠质量评估、深睡/REM/浅睡分布、趋势对比。

### 活动洞察
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me/activity-insights"
```
返回：步数、活动时间、消耗分析。

### 心率洞察
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me/heart-insights"
```
返回：静息心率、HRV、最大/最小心率分��。

### 恢复状态
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/daily-recommendation/me/recovery-status"
```
返回：压力水平、Body Battery 充放电、恢复建议。

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
dimension: weight / sleep / exercise / overall
period: 7d / 30d

### 趋势历史
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trends/history?days=30"
```

### 健康趋势预测
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trend/me/prediction?days=30"
```

### 健康风险因素
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-trend/me/risk-factors"
```

---

## 健康评分

### 今日健康评分
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-score/daily/me"
```
返回0-100综合评分及各维度（运动、睡眠、营养、水分、压力）。

### 健康评分趋势
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/health-score/trend/me?days=7"
```

---

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- 睡眠评分 < 60 → 🔴 重点关注
- HRV 持续 low → 建议休息
- 恢复状态差 → 不建议高强度运动
- Always respond in Chinese
