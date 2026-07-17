---
name: reminder-setter
description: 设置健康提醒 — 服药提醒、复查提醒、运动提醒、饮水提醒等。当用户要求设置提醒、定时通知、到时间提醒做某事时使用。
version: 1.0.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "⏰"
---

帮用户设置健康相关的定时提醒。

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`
- Content-Type: `application/json`

## 使用场景

| 用户说 | 你应该做 |
|---|---|
| "提醒我下午3点喝水" | 创建一次性提醒 |
| "每天晚上9点提醒吃莫米松" | 创建每日重复提醒 |
| "周一三五提醒我跑步" | 创建按星期重复的提醒 |
| "4周后提醒复查肝功能" | 计算日期并创建一次性提醒 |
| "我有哪些提醒" | 查询提醒列表 |
| "取消那个吃药提醒" | 删除提醒 |

## API 端点

### 创建提醒
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/reminders/me" \
  -d '{
    "title": "喝水",
    "message": "下午3点该喝300ml水了",
    "remind_at": "2026-04-12T15:00:00+08:00",
    "priority": "normal",
    "recurrence": null
  }'
```

**字段说明**：
- **title** (必填): 提醒标题，简短（如"喝水"、"服药"、"跑步"）
- **message** (可选): 详细提醒内容
- **remind_at** (必填): ISO 8601 格式时间，**必须带时区 +08:00**（中国时区）
- **priority**: `low` / `normal` / `high` / `urgent`
- **recurrence** (可选): 重复规则
  - `null` — 一次性
  - `"daily"` — 每天
  - `"weekdays"` — 工作日
  - `"weekly:1,3,5"` — 每周一三五（1=周一，7=周日）

### 查询我的提醒
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/reminders/me?status=pending"
```
status: `pending`（待执行）/ `triggered`（已触发）/ `all`

### 取消提醒
```bash
curl -s -X DELETE \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/reminders/{reminder_id}"
```

## 时间计算规则

用户说的时间需要你转成 ISO 8601 格式：
- "下午3点" → 今天的 `T15:00:00+08:00`
- "明天早上8点" → 明天的 `T08:00:00+08:00`
- "4周后" → 当前日期 + 28 天的 `T09:00:00+08:00`（默认上午9点）
- "每天晚上9点" → 今天的 `T21:00:00+08:00` + `recurrence: "daily"`

## 常见提醒模板

### 服药提醒
```json
{"title": "莫米松鼻喷", "message": "洗澡后使用，每侧2喷", "remind_at": "2026-04-12T21:00:00+08:00", "priority": "high", "recurrence": "daily"}
```

### 复查提醒
```json
{"title": "复查肝功能", "message": "去医院复查 ALT/AST/GGT + 腹部超声", "remind_at": "2026-05-24T09:00:00+08:00", "priority": "high", "recurrence": null}
```

### 饮水提醒
```json
{"title": "喝水", "message": "喝300ml水", "remind_at": "2026-04-12T15:00:00+08:00", "priority": "normal", "recurrence": "weekdays"}
```

## 行为规则

1. 时间**必须**带 `+08:00` 时区
2. 一次性提醒的 remind_at **必须**是未来时间
3. 重复提醒的首次 remind_at 可以是今天
4. 创建成功后回复用户确认（标题 + 时间 + 是否重复）
5. 如果接口返回 `delivery_status.agent_claim = "created_not_device_delivered"`，只能说提醒已创建、手机到点会尝试提醒、手表刷新今日摘要后可执行；**不得**说“已发送到手表 / 已同步到手表 / 已送达到手表”，除非 `delivery_status.watch.delivery_confirmed = true`
6. 如果用户说的时间模糊（"过几天"），主动确认具体日期
