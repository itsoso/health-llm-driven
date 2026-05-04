---
name: action-card-manager
description: 管理首页行动卡片 — 创建、查询、完成、归档。当用户想把某条建议固化到首页、查看当前行动计划、标记完成，使用这个 skill。
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📌"
---

管理智能助理首页的行动卡片（ActionCard）。行动卡片是对话中产出的有价值建议的持久化形式。

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`
- Content-Type: `application/json`

## 使用场景

| 用户说 | 你应该做 |
|---|---|
| "把这个计划保存到首页" | 调用创建卡片接口 |
| "固化到首页" | 调用创建卡片接口 |
| "我有哪些行动计划" | 调用查询卡片接口 |
| "这个计划完成了" | 调用更新状态接口 |
| "删掉那个卡片" | 调用归档接口 |

## API 端点

### 从对话内容创建卡片（最常用）
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/action-cards/from-message" \
  -d '{
    "content": "## 俯卧撑2周计划\n\n每周4练...\n\n### 第1周\n- Day1: 12×4组\n...",
    "card_type": "plan",
    "source_id": "conversation_123"
  }'
```
- **content** (必填): AI 回答的完整 markdown 内容。系统会自动从中提取标题。
- **card_type** (可选): `plan`（训练/行动计划）、`insight`（健康洞察）、`recommendation`（饮食/补剂建议）、`note`（备忘）。默认 `plan`。
- **source_id** (可选): 消息来源 ID，用于溯源。

**关键规则**：content 字段放你完整的回答内容（markdown），不要只放标题。系统会自动提取标题。

### 手动创建卡片
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/action-cards" \
  -d '{
    "title": "每周复查肝功能",
    "content": "4-6周后复查 ALT/AST/GGT，期间避免酒精和肝毒性补剂。",
    "card_type": "recommendation",
    "priority": 10
  }'
```
- **title** (必填): 卡片标题
- **content** (必填): markdown 正文
- **card_type**: plan / insight / recommendation / note
- **priority**: 数字越大越靠前（默认0，from-message 创建的默认10）

### 查询我的行动卡片
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/action-cards/me?status=active&limit=10"
```
- **status**: `active`（进行中）、`completed`（已完成）、`archived`（已归档）、`all`（全部）
- **limit**: 最多返回数量（默认20）

返回 JSON 数组，每个元素包含 `id`, `title`, `content`, `card_type`, `status`, `priority`, `created_at`。

### 更新卡片状态
```bash
curl -s -X PATCH \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/action-cards/{card_id}" \
  -d '{"status": "completed"}'
```
可更新字段：
- **status**: `active` → `completed` → `archived`
- **title**: 修改标题
- **priority**: 调整排序
- **is_visible**: `false` 隐藏

### 归档（删除）卡片
```bash
curl -s -X DELETE \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/action-cards/{card_id}"
```

## 行为规则

1. 当用户说"保存到首页"/"固化"/"钉住"时，把**你完整的回答内容**作为 content 传给 `from-message` 接口
2. 不要只传标题 — 系统会自动提取标题
3. card_type 选择：训练计划/周计划→`plan`、化验解读/趋势分析→`insight`、饮食/补剂建议→`recommendation`、其他→`note`
4. 创建成功后告诉用户"已保存到首页"
5. 查询卡片时按优先级和时间排序展示
