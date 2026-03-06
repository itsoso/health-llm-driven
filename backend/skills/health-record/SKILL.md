---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, diet entries, and supplements. Use when the user wants to log drinking water, weight, blood pressure, checkins, meals, or supplement intake (vitamins, minerals, etc).
version: 1.1.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📝"
---

You can record health data via the Health Management System API.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

## Available Actions

### 记录饮水（快速）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/quick?amount=250"
```
默认250ml，可修改 amount 参数。

### 记录体重
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/weight/records" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","weight":72.5}'
```

### 记录血压
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/blood-pressure/records" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","systolic":120,"diastolic":80,"pulse":72}'
```

### 快速打卡
先查询可用模板：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/templates"
```
然后打卡（用模板ID）：
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/checkin/records/quick" \
  -d '{"template_id":1,"value":30}'
```

### 记录饮食
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/records" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","meal_type":"LUNCH","food_items":"鸡胸肉沙拉","calories":400}'
```
meal_type: BREAKFAST / LUNCH / DINNER / EXTRA

### 补剂记录

#### 1. 查询用户补剂列表（含今日打卡状态）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/supplements/me/records?record_date=$(date +%Y-%m-%d)"
```

#### 2. 创建新补剂定义（如果用户要记录的补剂不在列表中）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/definitions" \
  -d '{"name":"甘氨酸锌","dosage":"30mg","timing":"morning","category":"矿物质"}'
```
- timing: morning / noon / evening / bedtime
- category: 维生素 / 矿物质 / 氨基酸 / 抗氧化 / 益生菌 / 中药 / 其他

#### 3. 补剂打卡（单个）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/records" \
  -d '{"supplement_id":1,"user_id":1,"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","taken":true,"notes":"早餐后服用"}'
```

#### 4. 补剂批量打卡
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/records/batch" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","checkins":[{"supplement_id":1,"taken":true},{"supplement_id":2,"taken":true}]}'
```

#### 5. 查看补剂统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/supplements/me/stats?days=30"
```

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Parse natural language: "喝了一杯水" → 250ml, "喝了两杯" → 500ml
- Parse weight: "体重72公斤" → 72.0, "72.5kg" → 72.5
- Parse blood pressure: "血压120/80" → systolic=120, diastolic=80
- Always respond in Chinese

### 补剂特殊规则
- 记录补剂前，先查询用户补剂列表确认 supplement_id
- 如果用户提到的补剂不在列表中，先自动创建补剂定义，再打卡
- 多个补剂同时记录时，优先用批量打卡接口
- "吃了NAC两粒" → 找到NAC的supplement_id，记录taken=true
- "吃了甘氨酸锌" → 先查列表，不存在则创建定义，然后打卡
