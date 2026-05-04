---
name: health-data-summary
description: 综合查询健康数据 — Digital Health Twin 快照、Safety 告警、长期趋势、Orchestrator 多专家分析。当用户想了解自己的整体健康状况、趋势变化、安全风险时使用。
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📊"
---

综合查询用户的健康数据和 AI 分析结果。整合了 Digital Health Twin、Safety Guardian、Orchestrator 多专家系统。

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## 使用场景

| 用户说 | 你应该调用的接口 |
|---|---|
| "我的健康状况怎么样" | Twin + Safety + Orchestrator |
| "我有什么安全风险" | Safety |
| "我过去半年的变化" | Personal Outcome |
| "分析我的 HRV 趋势" | Orchestrator |
| "我该注意什么" | Safety + Orchestrator |

## API 端点

### 1. Digital Health Twin（统一健康快照）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/twin/me"
```
返回用户当前的完整健康状态（13 个维度）：
- `physiological`: HRV, 心率, 睡眠, 压力, 电量, 步数, SpO2
- `body_composition`: 体重, BMI, 体脂, TDEE, BMR
- `labs`: 血压, 胆固醇, 血糖, 化验异常项
- `cgm`: CGM 血糖读数, TIR, 变异系数
- `medication`: 在服药物, 依从率
- `supplement`: 补剂打卡状态
- `genetic`: 基因变异（药物敏感/风险/保护）
- `environment`: 天气, AQI, PM2.5
- `behavioral`: 饮食, 饮水, 训练负荷, ACWR
- `mental`: 情绪, 精力, 压力 7 日均值
- `chronic`: 鼻炎今日状态
- `goals`: 当前目标
- `freshness`: 各数据源的新鲜度

**典型用法**：先调 Twin 了解全貌，再根据具体问题深入分析。

### 2. Safety Guardian 安全告警
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/safety/me"
```
返回基于 47 条确定性规则的安全告警：
- 药物-药物相互作用 (DDI)
- 药物-补剂相互作用 (DSI)
- 药物基因组学 (PGx: CYP2D6/MTHFR/ALDH2...)
- 急性阈值 (BP/HR/SpO2)
- 化验异常升级 (肝酶/LDL/HbA1c)
- 训练负荷 (ACWR 过载/欠训练)
- CGM 血糖异常

每条告警包含 `severity`（info/low/medium/high/critical）、`action`（建议动作）、`data_citation`（数据溯源）。

### 3. Orchestrator 多专家综合分析
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/orchestrator/chat" \
  -d '{"query": "综合分析我的健康状态并给出今日建议"}'
```
调度最多 10 个专家协作分析：
- SafetyGuardian, RecoveryCoach, FuelStrategist, MovementCoach
- MentalHealthCompanion, HypertensionSpecialist, MetabolicSpecialist
- RhinitisSpecialist, KnowledgeLibrarian, LongitudinalAnalyst

返回每个专家的结构化 finding + LLM 合成的自然语言回答。

### 4. 长期趋势（Personal Outcome）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/personal-outcome/me/timeline?range=6m&granularity=month"
```
- **range**: `6m` / `1y` / `2y`
- **granularity**: `week` / `month`

返回：
- `points[]`: 每月/每周的 HRV, 静息心率, 睡眠, 体重, 血压均值
- `events[]`: 干预事件（开始补剂/体检/里程碑）
- `summary.metrics`: 每个指标的 first→last 变化和趋势方向

### 5. 安全告警解读
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/safety/explain" \
  -d '{
    "rule_id": "labs.liver_enzyme_pattern",
    "data_citation": {"alt": {"value": 54}, "ast": {"value": 67}},
    "message": "肝酶组合升高"
  }'
```
对单条安全告警请求 LLM 个性化解读，结合用户真实健康数据给出具体建议。

### 6. 已注册的安全规则列表
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/safety/rules"
```
返回全部 47 条规则的名称列表（透明度用）。

### 7. Agent 审计日志
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/safety/audit?limit=10"
```
查看最近的 agent 决策历史（谁做了什么分析、多少告警、用了多少毫秒）。

## 推荐查询组合

### "我的健康状况怎么样"
1. 调 `/twin/me` → 获取全貌
2. 调 `/safety/me` → 获取安全风险
3. 用两者数据回答用户

### "过去半年我进步了吗"
1. 调 `/personal-outcome/me/timeline?range=6m` → 获取趋势
2. 提取 summary.metrics 的 delta 和方向
3. 找出改善和恶化的指标

### "我今天能高强度训练吗"
1. 调 `/orchestrator/chat` query="我今天能高强度训练吗"
2. 直接用返回的 synthesis 回答用户

## 行为规则

1. 回答健康问题时**优先调 Twin + Safety**，确保答案基于真实数据
2. 不要猜测用户的数据 — 调 API 获取真实值
3. 安全告警**必须**提及，即使用户没有问（这是安全义务）
4. 涉及药物/基因的问题，引用 Safety Guardian 的确定性规则结果
5. 长期趋势问题调 personal-outcome，不要凭记忆回答
