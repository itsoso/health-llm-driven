---
name: rhinitis-tracker
description: Track rhinitis symptoms (sneezing, nasal congestion, runny nose), record episodes, query history and environment alerts. Use when the user mentions sneezing, nasal symptoms, rhinitis, or nose-related health issues.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "👃"
---

You can track rhinitis symptoms and episodes via the Health Management System API.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

## 鼻炎症状记录（急性发作）

### 新建发作记录
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/illness/episodes" \
  -d '{"illness_name":"打喷嚏","severity":5,"notes":"连续打了好几个喷嚏","start_date":"'$(date +%Y-%m-%d)'"}'
```
severity: 1-10 (1=轻微 10=严重)

### 查看当前活跃发作
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/illness/episodes"
```

### 查看所有历史发作（含已痊愈）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/illness/episodes/all"
```

### 更新发作状态
```bash
curl -s -X PATCH -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/illness/episodes/{episode_id}" \
  -d '{"status":"improving","severity":3}'
```
status: active / improving / resolved

### 添加每日进展
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/illness/episodes/{episode_id}/updates" \
  -d '{"severity":4,"notes":"今天喷嚏减少，但仍有鼻塞","medications":"氯雷他定"}'
```

## 慢性鼻炎档案管理

### 记录鼻炎症状（慢性追踪）
先查询用户鼻炎档案ID：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/disease/profiles"
```
然后记录症状：
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/disease/profiles/{profile_id}/symptoms" \
  -d '{"symptoms":[{"name":"打喷嚏","severity":6},{"name":"鼻塞","severity":4},{"name":"流涕","severity":5}],"triggers":["冷空气","尘螨"],"medications":[{"name":"氯雷他定","dosage":"10mg"}],"notes":"早起症状明显"}'
```

### 查看症状统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/disease/profiles/{profile_id}/stats?days=30"
```

## Rules
- 当用户说"打喷嚏"、"鼻塞"、"流鼻涕"时，用 illness/episodes 记录急性发作
- severity 解析："轻微"→2, "有点"→3, "比较严重"→6, "很严重"→8
- 常见 illness_name: "打喷嚏", "鼻塞", "流涕", "鼻炎发作"
- 常见 triggers: "冷空气", "尘螨", "花粉", "油烟", "香水"
- 记录后告知用户已记录，并提醒洗鼻等缓解措施
- Always respond in Chinese
