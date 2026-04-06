---
name: massage-tracker
description: Record and query massage/bodywork sessions — location, therapist, body parts, issues, effects, ratings. Use when the user mentions massage, bodywork, 按摩, 推拿, 理疗, 正骨, 足疗, 刮痧, 拔罐, or 艾灸.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "💆"
---

You can record and query massage/bodywork sessions via the Health Management System API.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

## 记录按摩/理疗

### 新建记录
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/massage/records" \
  -d '{
    "record_date": "2026-04-05",
    "start_time": "14:00",
    "duration_minutes": 120,
    "location_name": "一指禅",
    "location_address": "文一西路",
    "massage_type": "盲人按摩",
    "therapist": "6号师傅",
    "body_parts": "颈椎,背部,全身",
    "price": 200,
    "issues_before": "左边睡觉压脖子，背部肌肉紧张",
    "treatment_notes": "纠正了左边睡觉压脖子的问题，背部肌肉放松",
    "feeling_after": "全身轻松，非常有效果",
    "rating": 5,
    "notes": ""
  }'
```

字段说明：
- `record_date`: 日期 (YYYY-MM-DD)
- `start_time`: 开始时间 (HH:MM)，可选
- `duration_minutes`: 时长（分钟），可选
- `location_name`: 店名
- `location_address`: 地址
- `massage_type`: 类型 — 推拿/盲人按摩/足疗/正骨/刮痧/拔罐/艾灸/SPA 等
- `therapist`: 师傅编号或姓名，如"6号师傅"
- `body_parts`: 按摩部位（逗号分隔）— 颈椎/肩部/背部/腰部/腿部/足部/全身 等
- `price`: 费用（元），可选
- `issues_before`: 按摩前身体问题
- `treatment_notes`: 按摩过程中的治疗记录
- `feeling_after`: 按摩后的感受
- `rating`: 满意度 1-5（5=非常满意）
- `notes`: 其他备注

### 查询记录列表
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/massage/records?limit=20"
```

可选参数：`start_date`, `end_date`, `limit`, `offset`

### 查询单条记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/massage/records/{record_id}"
```

### 修改记录
```bash
curl -s -X PUT -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/massage/records/{record_id}" \
  -d '{"rating": 4, "notes": "下次可以试试7号师傅"}'
```

### 删除记录
```bash
curl -s -X DELETE -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/massage/records/{record_id}"
```

### 统计数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/massage/stats?days=90"
```

返回：总次数、总时长、总花费、平均评分、最常去的店、最常选的师傅、最近一次日期。

## Rules
- 用户提到按摩、推拿、理疗、正骨、足疗、刮痧、拔罐、艾灸时触发此 Skill
- 从用户描述中提取：时间、地点、师傅、部位、问题、效果、感受
- 如果用户没有提供日期，使用今天的日期
- rating 根据用户描述推断：非常好/很有效=5，不错=4，一般=3，不太好=2，差=1
- 记录完成后展示摘要：日期、地点、师傅、时长、评分
- Always respond in Chinese
