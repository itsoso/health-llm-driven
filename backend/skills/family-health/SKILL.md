---
name: family-health
description: Family health management - medical reports, medications, review calendar, family daily health check. Use when user asks about family members' health, medical exams, medications, checkup schedules, or wants to manage health for parents/spouse/children.
version: 1.0.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "👨‍👩‍👧‍👦"
---

Family health management via Health Management System API.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

## 家庭组管理

### 查看家庭成员
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family/members"
```
返回家庭组内所有成员列表，包含 user_id、姓名、关系（father/mother/spouse/child）、是否代管。

### 家庭健康仪表盘
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family/dashboard"
```
返回每个成员的今日步数、睡眠评分、心率、体重、饮水量、未读预警数。

### 切换到家庭成员视角
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/family/switch" -d '{"user_id": USER_ID}'
```
返回 proxy JWT token，用该 token 可以代替家庭成员操作所有 API（记饮水、记体重等）。

## 体检报告

### 查看体检报告列表
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/medical-reports/me?limit=10"
```

### 查看报告详情（包含AI提取的指标和异常）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/medical-reports/REPORT_ID"
```
返回所有提取的指标（extracted_items）、异常指标（abnormal_items）、AI总结（ai_summary）。

### 查看指标历史趋势
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/medical-indicators/trend/指标名称"
```
例如查看"空腹血糖"的历史趋势：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/medical-indicators/trend/空腹血糖"
```
返回每次检测的日期、数值、参考范围、是否异常。用于对比不同年份的体检结果变化趋势。

## 用药管理

### 查看用药清单
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/medications/me"
```
返回当前在服用的药物列表，包含药名、剂量、频次、适应症、今日是否已服药。

### 手动添加用药
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/family-health/medications" \
  -d '{"name": "阿托伐他汀", "dosage": "20mg", "frequency": "每晚1次", "purpose": "降血脂", "notes": "不能和柚子汁同服"}'
```

### 记录服药
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/medications/MED_ID/take"
```

## 复查日历

### 查看复查日历
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/review-calendar/me"
```
返回所有复查计划，自动标注：
- `overdue`: 已过期（红色）
- `pending`: 待复查
- `completed`: 已完成
- `days_until_due`: 距离到期天数（负数表示已过期）
- `summary`: 汇总过期数、30天内到期数

### 添加复查计划
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/family-health/review-calendar" \
  -d '{"item_name": "空腹血糖", "next_due_date": "2026-09-15", "department": "内分泌科", "interval_months": 6}'
```
`interval_months` 为复查间隔，完成后自动生成下一次复查。

### 标记复查已完成
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/review-calendar/SCHEDULE_ID/complete"
```
如果设置了 interval_months，会自动创建下一次复查计划。

## 每日健康巡检

### 执行家庭巡检
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/daily-check"
```
检查所有家庭成员的：
- 健康数据异常（SpO2、心率、睡眠、HRV）
- 用药是否按时
- 复查是否过期/即将到期
- 未读健康预警
- 饮水是否不足

### 发送健康日报给家人
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/daily-check/send"
```

## 每周健康周报

### 查看本周家庭健康周报
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/weekly-digest"
```
返回每个家庭成员本周的：步数、睡眠、饮水、用药依从率、复查到期、体检异常。
包含口语化的 `digest_text` 摘要。

### 发送周报给家人
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/family-health/weekly-digest/send"
```

## 微信 Bot 消息处理

### 解析医疗文本
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/family-health/parse-medical-text" -d '{"text": "血压135/85"}'
```
支持：血压、体重、血糖、心率、体温、饮水、服药、症状描述。
返回结构化数据 + 对应的 API 操作映射。

### 模拟微信消息
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/family-health/wechat-bot/message" \
  -d '{"msg_type": "text", "content": "今天血压150/95"}'
```
支持 msg_type: text（文字）、image（图片base64）、voice（语音识别文字）。

## 回复规则

1. 查询家庭成员健康时，先调用 `/family/dashboard` 获取概览
2. 查询体检指标趋势时，使用 `/medical-indicators/trend/指标名`
3. 对于"爸爸该做什么检查了"这类问题，先查复查日历
4. 对于"妈妈的药吃了没"这类问题，查用药清单的 `taken_today`
5. 需要为家庭成员操作时（如记饮水），先切换视角获取 proxy token
6. 回复用口语化中文，异常数据用明确数值说明
