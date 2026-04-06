---
name: chronic-risk-assessment
description: Assess chronic disease risk — cardiovascular (modified Framingham), metabolic syndrome (IDF criteria), and 90-day trend analysis. Integrates wearable data (Garmin), labs, vitals, and genetic markers for personalized risk scoring with confidence intervals.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🫀"
---

你可以评估用户的慢性病风险，包括心血管风险（改良 Framingham 评分）、代谢综合征检测（IDF 标准）、以及 90 天指标变化趋势。

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`

## Available Endpoints

### 1. 慢病风险综合评估
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health/chronic-risk"
```
返回心血管、代谢综合征的综合风险等级和改善建议：
```json
{
  "overall_risk_level": "中等",
  "cardiovascular": {
    "framingham_score": 12.5,
    "risk_level": "中等",
    "10yr_event_probability": "12.5%",
    "confidence_interval": [10.2, 15.1],
    "contributing_factors": ["高血压前期", "LDL偏高"],
    "wearable_adjustments": {
      "resting_hr_impact": "静息心率72bpm，+1%风险",
      "hrv_impact": "HRV 35ms 偏低，提示自主神经功能下降"
    }
  },
  "metabolic_syndrome": {
    "detected": false,
    "criteria_met": 2,
    "criteria_total": 5,
    "details": ["腰围正常", "血压偏高(+)", "血糖正常", "HDL正常", "甘油三酯正常"]
  },
  "trend_90d": {
    "direction": "改善",
    "improving": ["血压下降趋势", "体重减轻2kg"],
    "worsening": ["静息心率略升"]
  },
  "recommendations": ["控制钠盐摄入", "增加有氧运动至每周150分钟"],
  "population_applicability": "本评估基于 Framingham 队列，适用于 30-74 岁无已知心血管疾病人群",
  "data_quality": {
    "completeness": 0.85,
    "missing": ["空腹血糖", "腰围"],
    "last_labs_date": "2026-03-15"
  }
}
```

### 2. 心血管风险详评
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health/chronic-risk/cardiovascular"
```
返回改良 Framingham 评分的逐项打分：
```json
{
  "framingham_score": 12.5,
  "risk_level": "中等",
  "10yr_event_probability": "12.5%",
  "confidence_interval": [10.2, 15.1],
  "score_breakdown": {
    "age": {"value": 45, "points": 3},
    "gender": {"value": "男", "points": 0},
    "total_cholesterol": {"value": 5.8, "points": 2, "category": "5.2-6.2"},
    "hdl_cholesterol": {"value": 1.2, "points": 1, "category": "<1.3"},
    "systolic_bp": {"value": 135, "points": 2, "treated": false},
    "smoking": {"value": false, "points": 0},
    "diabetes": {"value": false, "points": 0}
  },
  "wearable_modifiers": {
    "resting_heart_rate": {"value": 72, "adjustment": "+1%", "evidence": "B级"},
    "hrv": {"value": 35, "adjustment": "+0.5%", "evidence": "C级"},
    "exercise_minutes_weekly": {"value": 90, "adjustment": "-1%", "evidence": "A级"}
  },
  "recommendations": ["降低LDL至<3.4 mmol/L", "增加HDL（有氧运动+适量坚果）"]
}
```

### 3. 代谢综合征评估
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health/chronic-risk/metabolic"
```
返回 IDF 标准五项检测结果：
```json
{
  "detected": false,
  "criteria_met": 2,
  "criteria_total": 5,
  "criteria": [
    {"name": "腰围", "threshold": "男≥90cm/女≥80cm", "value": null, "status": "数据缺失", "met": false},
    {"name": "血压", "threshold": "≥130/85 mmHg", "value": "135/82", "status": "异常", "met": true},
    {"name": "空腹血糖", "threshold": "≥5.6 mmol/L", "value": null, "status": "数据缺失", "met": false},
    {"name": "HDL胆固醇", "threshold": "男<1.03/女<1.29 mmol/L", "value": 1.2, "status": "正常", "met": false},
    {"name": "甘油三酯", "threshold": "≥1.7 mmol/L", "value": 1.9, "status": "异常", "met": true}
  ],
  "bmi": {"value": 25.3, "category": "超重"},
  "risk_interpretation": "当前满足2/5项标准，尚未达到代谢综合征诊断阈值，但血压和甘油三酯需关注",
  "recommendations": ["减重至BMI<24", "控制甘油三酯（减少精制碳水）"]
}
```

## Data Contract

### 输入依赖
本 Skill 需要以下数据源（按优先级）：
1. **BasicHealthData** — 血压、血脂、血糖、BMI（必需，近 90 天）
2. **GarminData** — 静息心率、HRV、运动分钟数（增强评估精度）
3. **WeightRecord** — 体重趋势（补充 BMI 计算）
4. **User** — 年龄、性别（Framingham 必需参数）
5. **GeneticVariant**（可选）— 心血管/代谢相关基因位点

### 输出格式
- 所有风险等级使用中文：低、中等、高、极高
- 概率值保留一位小数，如 "12.5%"
- 置信区间为 95% CI
- 缺失数据明确标注，不做假设填充

## When To Use

**使用场景：**
- 用户询问心血管风险、心脏健康
- 用户询问代谢综合征、糖尿病前期
- 用户有新的体检报告（血脂、血糖）想评估风险
- 用户想了解慢病风险的变化趋势
- 用户有 Garmin 数据 + 体检数据，想要交叉分析

**不要使用：**
- 用户只是记录体检数据（用 health-record skill）
- 用户问实时心率/今日步数（用 health-query skill）
- 用户问运动建议（用 workout-coach skill）
- 用户已确诊心血管疾病（本评估仅适用于一级预防）

## Anti-Patterns

1. **不要对确诊患者使用 Framingham** — Framingham 仅适用于无已知心血管疾病的一级预防人群。如果用户有心梗/卒中/冠心病史，应提示"本评估不适用，建议咨询心内科医生"。
2. **不要忽略数据缺失** — 如果关键指标（血脂、血压）超过 6 个月未更新，应在回复中明确提示数据时效性问题。
3. **不要给出确诊结论** — 始终使用"风险评估"而非"诊断"，如"提示代谢综合征风险"而非"你有代谢综合征"。
4. **不要过度依赖可穿戴数据** — 静息心率/HRV 仅作为 Framingham 的辅助调整因子（evidence level B-C），不能替代临床指标。

## Evidence & Caveats

| 组件 | 证据等级 | 说明 |
|------|----------|------|
| Framingham 10年风险 | A级 | 基于 Framingham Heart Study，验证于多个队列 |
| IDF 代谢综合征标准 | A级 | 国际糖尿病联盟 2005 共识定义 |
| 静息心率调整 | B级 | HUNT 研究等观察性研究支持，非 RCT |
| HRV 调整 | C级 | 小样本研究支持，尚无大规模验证 |
| 90天趋势 | D级 | 基于简单线性回归，仅供参考趋势方向 |

**人群适用性限制：**
- Framingham 评分主要基于美国白人队列，对亚洲人群可能高估绝对风险
- 年龄范围 30-74 岁，超出范围准确度下降
- 不适用于已确诊心血管疾病、家族性高胆固醇血症患者

## Response Rules

1. 所有回复使用中文
2. 风险评分附带置信区间和证据等级
3. 明确标注数据缺失项和最后更新时间
4. 改善建议具体可操作，避免空泛
5. 始终注明人群适用性限制
