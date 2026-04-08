---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, diet entries, supplements, illness episodes, excretion, mood, and reminders.
version: 2.0.0
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

### 记录饮食（文字）
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/diet/records" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","meal_type":"LUNCH","food_items":"鸡胸肉沙拉","calories":400,"protein":35,"carbs":20,"fat":10}'
```
meal_type: BREAKFAST / LUNCH / DINNER / EXTRA
自动推断规则（按当前时间）：6-10点=BREAKFAST, 10-14点=LUNCH, 14-17点=EXTRA, 17-21点=DINNER, 其他=EXTRA

### 饮食图片识别并保存
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/diet/recognize-and-save" \
  -d '{"image_base64":"<base64>","meal_type":"LUNCH"}'
```

### 估算营养（不保存）
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/diet/estimate-nutrition" \
  -d '{"food_description":"一碗牛肉面加一个鸡蛋"}'
```

---

## 病症管理

### 创建病症
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/illness/episodes" \
  -d '{"name":"感冒","severity":5,"status":"active","notes":"嗓子疼，流鼻涕"}'
```
severity: 0-10 (0=无症状, 10=极严重), status: active/improving/resolved

### 更新病症
```bash
curl -s -X PATCH -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/illness/episodes/{episode_id}" \
  -d '{"status":"improving","severity":3}'
```

### 添加病症进展
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/illness/episodes/{episode_id}/updates" \
  -d '{"status":"improving","severity":3,"notes":"好多了，不流鼻涕了"}'
```

---

## 排泄记录

### 记录排泄
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/excretion/records" \
  -d '{"type":"bowel","record_date":"'$(date +%Y-%m-%d)'","stool_type":4,"notes":"正常"}'
```
type: bowel（大便）/ urine（小便）
stool_type: 1-7（Bristol 大便分类，4=正常）
可选: has_blood, color, urgency

---

## 情绪记录

### 记录情绪
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/mood/records" \
  -d '{"mood_score":7,"energy_level":6,"journal":"今天心情不错，工作顺利"}'
```
mood_score: 1-10, energy_level: 1-10（可选）, journal: 文字记录（可选）

---

## 提醒管理

### 创建提醒
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/reminders/me" \
  -d '{"title":"吃药","message":"饭后服用维生素D","remind_at":"2026-03-28T09:00:00+08:00","priority":"normal"}'
```
priority: low / normal / high / urgent
recurrence（可选）: daily / weekdays / weekly:1,3,5

### 取消提醒
```bash
curl -s -X DELETE -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/reminders/{reminder_id}"
```

---

## 异常预警确认

### 确认单条预警
```bash
curl -s -X PATCH -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/anomaly-alerts/{alert_id}/acknowledge"
```

### 确认所有预警
```bash
curl -s -X PATCH -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/anomaly-alerts/acknowledge-all?days=7"
```

---

## 补剂打卡

### 批量补剂打卡
先查询今日状态：
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/supplements/me/date/$(date +%Y-%m-%d)"
```
然后批量打卡：
```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/supplements/records/batch" \
  -d '{"record_date":"'$(date +%Y-%m-%d)'","checkins":[{"supplement_id":1,"taken":true},{"supplement_id":2,"taken":true}]}'
```

---

## Garmin 同步

当用户说"同步Garmin"、"同步Garmin数据"、"同步数据"、"更新运动数据"、"拉取最新数据"、"sync garmin"时，**必须立即调用此 API**，不要让用户手动操作：

```bash
curl -s -X POST -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/data-collection/garmin/me/sync?days=1"
```
- `days`: 同步最近N天数据，通过 URL query 参数传递
- 404: 未绑定 Garmin，提示去设置页绑定
- 成功后告知同步结果
- **重要**：必须直接调用 API，不要回复"请手动操作"

---

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Parse natural language:
  - "喝了一杯水" → 250ml, "喝了两杯" → 500ml, "喝了一大杯" → 500ml
  - "体重72公斤" → 72.0, "72.5kg" → 72.5
  - "血压120/80" → systolic=120, diastolic=80
  - "感冒了" → 创建病症 name=感冒
  - "提醒我明天8点吃药" → 创建提醒
  - "今天情绪不错" → mood_score=7-8
- meal_type 按当前时间自动推断（6-10=早餐, 10-14=午餐, 14-17=加餐, 17-21=晚餐）
- Always respond in Chinese
