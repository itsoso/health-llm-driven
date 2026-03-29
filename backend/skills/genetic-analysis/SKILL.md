---
name: genetic-analysis
description: Query and analyze user genetic test data. Cross-reference genetics with medical reports and current health status for personalized nutrition, exercise, drug, and sleep advice.
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🧬"
---

You can query and analyze user's genetic test data.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`

## Available Actions

### 查询基因汇总
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/summary/me"
```
返回按类别(nutrition/exercise/drug_sensitivity/disease_risk/sleep)分组的基因位点汇总。

### 按类别查询
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/variants/me?category=nutrition"
```
可选 category: nutrition, exercise, drug_sensitivity, disease_risk, sleep

### 基因+健康交叉分析
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/genetic/cross-analysis/me"
```
AI 综合分析基因风险与当前健康数据的关联，返回运动/饮食/睡眠/药物建议。

## Rules
- 药物敏感基因(CYP2C19/CYP2D6等)必须对照用户当前用药，发现冲突立即提醒
- 营养代谢基因(MTHFR/LCT/ALDH2等)直接指导饮食建议
- 运动基因(ACTN3/ACE等)指导运动类型和强度建议
- 疾病风险基因(APOE/FTO等)结合体检指标给出预防建议
- 睡眠基因(CLOCK/PER2等)结合实际睡眠数据给出作息建议
- 始终使用中文回复，引用具体基因型
