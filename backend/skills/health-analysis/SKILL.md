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

## 基因数据关联

进行健康分析时，可调用基因数据辅助判断：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/summary/me"
```
如用户有基因数据，应结合基因风险等级解读体检指标和健康趋势。例如：
- FTO 肥胖基因 + BMI 偏高 → 加强饮食控制建议
- MTHFR TT + 同型半胱氨酸偏高 → 建议补充活性叶酸
- CYP2C19 慢代谢 + 正在服用氯吡格雷 → 警告需换药

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- 如有基因数据，在分析中引用具体基因型
- Always respond in Chinese
