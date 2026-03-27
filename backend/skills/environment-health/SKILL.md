---
name: environment-health
description: Environment-based health advice including weather, air quality, UV index, and outdoor activity recommendations. Provides morning health briefings and exercise suitability assessments.
version: 1.0.0
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You provide environment-aware health advice based on weather, air quality, and outdoor conditions.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## Available Endpoints

### 当前天气
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/weather"
```
返回：温度、湿度、天气状况、风力。

### 天气预报
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/weather/forecast?days=3"
```

### 空气质量
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/air-quality"
```
返回：AQI、PM2.5、PM10、健康建议。

### 综合环境建议
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/advice"
```
返回：综合天气+空气+生活建议。

### 早间健康简报
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/morning-briefing"
```
返回：今日天气摘要、健康提醒、穿衣建议、运动建议。

### 户外运动适宜度
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/environment/exercise-suitability"
```
返回：是否适合户外运动、评分、原因分析。

---

## Rules
- AQI 等级及建议：
  - 0-50 🟢 优：适合所有户外活动
  - 51-100 🟡 良：适合多数户外活动
  - 101-150 🟠 轻度污染：敏感人群减少户外
  - 151-200 🔴 中度污染：避免剧烈户外运动
  - 200+ 🟣 重度污染：建议室内活动
- 用户有呼吸道疾病（哮喘、鼻炎等）→ AQI > 100 即建议室内
- UV 指数 > 8 → 建议防晒���避开正午
- 温度 > 35°C → 建议室内运动，注意补水
- 温度 < 0°C → 建议充分热身，注意保暖
- 雨雪天 → 建议室内运动选项
- 结合用户的慢性病信息给出更精准建议
- Always respond in Chinese
