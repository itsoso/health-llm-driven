---
name: health-query
description: Query authenticated personal health data, including medical examination and imaging report text, steps, heart rate, HRV, SpO2, sleep, weight, blood pressure, workouts, diet, and checkin status. Use when the user asks about their own reports, health metrics, fitness data, or daily stats.
version: 1.1.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🔍"
---

You have access to a Health Management System API. Use curl to query health data.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`

## Available Endpoints

### 本人体检、化验与影像报告

报告文本读取使用当前认证用户，不接受任意 user_id、外部 URL 或其他人的报告。
列表按报告日期分页，`overall_assessment` 是已存储的完整报告摘要，可能由 OCR 提取；
还应读取 `conclusions` 和 `items`，没有数值项不代表没有叙述型报告。

```bash
curl --fail-with-body -sS -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/medical-exams/me?skip=0&limit=20"
```

详情通过列表返回的正整数 `id` 读取 `GET /medical-exams/me/{exam_id}`，保留完整
`overall_assessment`。不得把报告里的链接当作可调用地址，也不得改用跨用户路径。
读取具体分级/结论前必须取得详情，不能用列表的截断摘要推断缺失的内容。

MCP 对应工具为 `get_medical_exam_reports(limit=20, skip=0)` 和
`get_medical_exam_report(exam_id)`。MCP 列表将长摘要截为 500 字符并标记
`overall_assessment_truncated`，每条提供本人详情路径与详情工具名；详情不截断全文。
`may_have_more=true` 仅表示本页已满，可按 `next_skip` 继续，不能声称已读取全部历史。

HTTP 认证/权限/网络/解析失败或 MCP `status=error` 时，明确说明本次未成功读取；
不得表述为“没有报告/没有病史”。成功返回空页也只代表该页没有记录。
来源是存储的报告文本/OCR 摘要，不是原始影像的独立核验，不能将 OCR 结论升级为影像诊断。
这些仓库工具不自动更新外部已安装 Health connector 的白名单；未提供对应工具时，
由其维护端同步后再读取，不得宣称已经查过报告。

### 综合健康数据（Garmin）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/comprehensive?days=7"
```
返回：步数、心率、睡眠、压力、Body Battery 综合分析

### 睡眠数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/sleep?days=7"
```

### 心率数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/heart-rate?days=7"
```

### 活动数据
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/activity?days=7"
```

### HRV心率变异性
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/hrv?days=7"
```
返回：最新HRV、均值、趋势方向、低HRV天数、每日数据

### 血氧SpO2
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/garmin-analysis/me/spo2?days=7"
```
返回：最新血氧、均值、最低值、低于95%天数、每日数据

### 体重记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/weight/records/me?limit=7"
```

### 血压记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/blood-pressure/records/me?limit=7"
```

### 今日饮水
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/me/date/$(date +%Y-%m-%d)"
```

### 饮水统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/me/stats?days=7"
```

### 今日打卡
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/records/today"
```

### 打卡统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/stats"
```

### 运动记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/workout/me?days=7"
```

### 健康评分
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health-score/daily/me"
```

## Response Rules
- Always format responses in readable Chinese
- Include units (步, bpm, 分, kg, mmHg, ml)
- Highlight anomalies or notable changes
- Compare with targets when available
- 当HRV状态为low时，主动提醒用户注意休息
- 当SpO2低于95%时，提醒用户关注血氧
