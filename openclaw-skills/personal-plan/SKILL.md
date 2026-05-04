---
name: personal-plan
description: 生成并保存个性化健康计划（训练、饮食、恢复、复查等），支持从对话中创建任意时间跨度的计划并固化到首页。当用户要求制定计划、安排时间表、创建方案时使用。
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📅"
---

帮用户创建个性化健康计划，并保存到系统中。

## Authentication
- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## 工作流程

### 第一步：获取用户当前状态（必须先做）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/twin/me"
```
返回用户的 Digital Health Twin（生理/身体/化验/药物/训练负荷/饮食/基因/环境）。**制定计划前必须先读 Twin。**

关键字段：
- `physiological.hrv_latest` / `sleep_score_latest` / `body_battery_current` → 恢复状态
- `body_composition.weight_kg` / `tdee_kcal` → 饮食计划基础
- `behavioral.acute_chronic_ratio` / `workouts_this_week` → 训练负荷
- `medication.active_meds` → 用药注意（GLP-1 延迟胃排空等）
- `genetic.risk_variants` → 基因驱动建议

### 第二步：获取安全告警（必须检查）
```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" "${HEALTH_API_URL}/safety/me"
```
查看是否有安全禁忌（药物相互作用、急性阈值、训练过载等）。**计划不能和安全告警冲突。**

### 第三步：制定计划

基于 Twin + Safety 数据，用你的专业知识制定计划。计划应包含：
- 目标（具体、可衡量）
- 时间跨度（1周/2周/4周/...）
- 每日/每周具体行动（时间、数量、强度）
- 进阶条件（什么时候升级难度）
- 注意事项（结合用户的药物、基因、恢复状态）

### 第四步：保存到首页
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/action-cards/from-message" \
  -d '{
    "content": "你制定的完整计划 markdown 内容",
    "card_type": "plan"
  }'
```

### 第五步（可选）：同时创建周计划
```bash
curl -s -X POST \
  -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HEALTH_API_URL}/smart-plan/generate" \
  -d '{"target_week":"current","user_focus":["俯卧撑","深蹲"],"intensity":"moderate"}'
```

## 计划类型示例

### 训练计划
```markdown
## 俯卧撑 2 周进阶计划

**目标**: 从 M=20 提升到 M=25+
**频率**: 每周4练（周一/三/五/日）

### 第1周
- Day1: 12 × 4组，组休60s
- Day2: 10 × 5组，组休60s
...
```

### 饮食方案
```markdown
## 减脂期饮食方案（4周）

**目标**: 每周减 0.5kg，保持肌肉量
**TDEE**: 2700 kcal → 摄入 2200 kcal（缺口500）

### 每日宏量
- 蛋白: 144g (2g/kg)
- 碳水: 220g
- 脂肪: 73g
...
```

### 复查提醒
```markdown
## 肝功能复查计划

**原因**: ALT 54 / AST 67 / GGT 72（1.8× ULN）
**时间**: 4-6周后（约2026年5月下旬）

### 复查项目
- 肝功能全套（ALT/AST/GGT/ALP/TBIL）
- 腹部超声（排查脂肪肝）
...
```

## 行为规则

1. 制定计划前**必须**先调 `/twin/me` 和 `/safety/me`
2. 计划内容不能和安全告警冲突（如 ACWR 过载时不能安排高强度训练）
3. 涉及药物/剂量调整的计划，明确标注"需和医生确认"
4. 计划写好后**自动**调 `from-message` 保存到首页
5. 回复用户时确认"已保存到首页"
