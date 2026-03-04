---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, and diet entries.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can record health data via the Health Management System API.

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`
- Content-Type: `application/json`

## Available Actions

### 记录饮水（快速）
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/water/records/quick?amount=250"
```
默认250ml，可修改 amount 参数。

### 记录体重
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/weight/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","weight":72.5}'
```

### 记录血压
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/blood-pressure/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","systolic":120,"diastolic":80,"pulse":72}'
```

### 快速打卡
先查询可用模板：
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/checkin/templates"
```
然后打卡（用模板ID）：
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/checkin/records/quick" \
  -d '{"template_id":1,"value":30}'
```

### 记录饮食
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/diet/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","meal_type":"LUNCH","food_items":"鸡胸肉沙拉","calories":400}'
```
meal_type: BREAKFAST / LUNCH / DINNER / EXTRA

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Parse natural language: "喝了一杯水" → 250ml, "喝了两杯" → 500ml
- Parse weight: "体重72公斤" → 72.0, "72.5kg" → 72.5
- Parse blood pressure: "血压120/80" → systolic=120, diastolic=80
- Always respond in Chinese
