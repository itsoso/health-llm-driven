---
name: health-analysis
description: Get AI health analysis, daily recommendations, health trend predictions, and health scores. Use when the user asks for health advice, trend analysis, risk assessment, or wellness recommendations.
version: 1.0.0
metadata:
  agent:
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

## When To Use / When NOT To Use

**使用场景：**
- 用户询问健康状况、体检解读、健康建议
- 用户想了解健康趋势、风险评估
- 用户有 ≥7 天的 Garmin 数据或近期体检报告

**不要使用：**
- 用户只是记录数据（用 health-record skill）
- 用户只查询某个指标数值（用 health-query skill）
- 用户问运动相关问题（用 workout-coach skill）
- 用户问补剂/营养问题（用对应专业 skill）

## Data Contract

**Input（需要的数据）：**
- 基础健康数据（身高、体重、BMI、血压、血脂、血糖）
- Garmin 数据（≥7 天：心率、HRV、睡眠、步数、压力、Body Battery）
- 体检报告（可选，提升分析质量）
- 基因数据（可选，启用精准建议）
- 疾病/用药记录（可选，安全性校验）

**Output（返回格式）：**
- issues[]: 健康问题列表，按严重程度排序
- recommendations[]: 可执行建议列表
- summary: 综合分析文本
- severity_level: 🟢/🟡/🔴

**Quality Checks：**
- 数据不足 7 天 → 标注"数据量有限，建议持续记录"
- 体检数据超过 6 个月 → 提醒复查
- 基因数据缺失 → 跳过基因关联分析，不猜测

## Anti-Patterns

- ❌ 单日数据做趋势判断（需 ≥7 天）
- ❌ 忽略用户时区导致睡眠数据错位
- ❌ 不考虑年龄/性别直接套用统一阈值
- ❌ 用 Garmin 压力指数直接等同于心理压力
- ❌ 对异常值不做离群检测就纳入分析
- ❌ 给出医疗诊断或处方建议（超出范围）

## Evidence & Caveats

- 健康建议基于公共卫生指南，不构成医疗诊断
- 阈值参考：中国高血压防治指南(2024)、中国居民膳食指南(2022)、AHA/WHO 指南
- 基因关联建议为 B 级证据（观察性研究），非 A 级（RCT）
- 可穿戴数据存在设备误差，仅供参考
- 详细阈值和证据来源见 `references/thresholds_and_evidence.md`

## Response Rules
- Present analysis in structured, readable format
- Use severity levels: 🟢 正常, 🟡 注意, 🔴 警告
- Highlight important trends and anomalies
- Provide actionable suggestions
- 如有基因数据，在分析中引用具体基因型
- Always respond in Chinese
