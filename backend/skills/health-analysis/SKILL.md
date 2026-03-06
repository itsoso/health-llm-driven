---
name: health-analysis
description: Get AI health analysis, daily recommendations, health trend predictions, and health scores. Use when the user asks for health advice, trend analysis, risk assessment, or wellness recommendations.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🧠"
---

You can request health analysis and recommendations from the Health Management System.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`

## Available Endpoints

### 健康问题检测
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/analysis/me/issues"
```
返回潜在健康问题及严重程度。

### 今日推荐（刷新）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/daily-recommendation/me/refresh?use_llm=true"
```
AI 生成个性化运动、饮食、作息建议。

### 健康趋势概览
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health-trends/latest"
```
返回各维度（体重、睡眠、运动、综合）趋势方向、洞察和风险提示。

### 指定维度趋势详情
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health-trends/overall?period=7d"
```
支持维度: weight / sleep / exercise / overall，period: 7d / 30d

### 今日健康评分
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health-score/daily/me"
```
返回0-100综合评分及各维度（运动、睡眠、营养、水分、压力）。

### 健康评分趋势
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health-score/trend/me?days=7"
```

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- Always respond in Chinese
