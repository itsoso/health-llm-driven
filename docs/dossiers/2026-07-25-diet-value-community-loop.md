| 字段 | 值 |
|---|---|
| feature | diet-value-community-loop |
| status | building |
| current_stage | S5 |
| date | 2026-07-25 |

# Dossier: 饮食价值回执与同行支持

## 用户原话

> 要具备社区 点赞 激励 距离自己减肥目标 还有多少 实时的价值反馈 基于饮食记录打卡之后 思考如何进行产品设计

> 按照规划执行

## 目标用户与当前绕路

有明确减脂目标、持续记餐和称重的用户。目前写入后能看到营养与下一餐建议，但需要离开对话才能理解目标进度，也只能分享到外部平台，不能获得产品内同行支持。

## Discovery

- 已有确定性记录后反馈：`backend/app/services/post_record_quality.py`
- 已有原生卡：`mobile/components/chat/cards/RecordQualityCard.tsx`
- 已有目标体重：`UserProfile.target_weight_kg`
- 已有长期容器：`HealthProgram`
- 已有体重记录：`WeightRecord`
- 已有外部图片分享，但没有产品内社区模型或 API
- 无同域开放 PR；社区能力需要新跨端契约与迁移

## 产出物

- Spec: `docs/specs/active/2026-07-25-diet-value-community-loop.md`
- PRD: `docs/prd/2026-07-25-diet-value-community-loop.md`
- Plan: `docs/plans/2026-07-25-diet-value-community-loop.md`

## Gate Ledger

| Gate | 状态 | 依据 |
|---|---|---|
| G1 准入 | PASS after reframe | 映射 HealthProgram/ExecutionEvent/LeverageAction/InterventionCycle；拒绝排行榜和自动发布 |
| G2 可行性+安全 | PASS | 复用现有记录卡；服务端隐私投影；用户已明确要求执行 |
| G3 测试 | PASS | 后端 123 项、Mobile 32 项相关回归；TypeScript、迁移、lint、design token、doc drift 通过 |
| G4 安全/隐私 | PASS | owner isolation、严格公开 allowlist、低 BMI/增重目标降级、手动发布和失败隔离均有测试 |
| G5 部署健康 | PENDING | backend deploy + production OTA |
| G6 上线验证 | PENDING | 真机记餐、目标进度、发布与反应 |

## G1 准入

**裁决**: PASS

映射 HealthProgram/ExecutionEvent/LeverageAction/InterventionCycle；拒绝排行榜和自动发布。

## G2 可行性与风险

**裁决**: PASS

复用现有记录卡；服务端隐私投影；用户已明确要求执行。

## G3 测试

**裁决**: PASS

验证证据：

- 社区、目标进度、迁移：24 项通过；
- 既有饮食幂等、卡片去重、快速回执和穿戴上下文：99 项通过；
- 目标进度增重边界：18 项全文件回归通过；
- Mobile 社区服务/页面/记录卡：21 项通过；
- Mobile `useChatEngine` 饮食卡权威快照和去重：11 项通过；
- Mobile TypeScript、目标文件 lint、design token、API 类型同步通过；
- system map、Mobile nav graph 已重新生成，doc drift 与 dossier consistency 通过。

## G4 安全与隐私

**裁决**: PASS

服务端只公开餐次、日期、食物和宏量营养；原图、体重、病史、药物、位置、备注和原始 AI 上下文均不进入公开快照。发布必须主动确认，附言明确提示不填写敏感信息；跨用户记录返回 404。低 BMI 目标不展示进度鼓励，增重目标不误标为减重，单餐不获得体重变化因果归因。

## G5 部署健康

**裁决**: PENDING

等待 backend deploy 和 production OTA。

## G6 上线验证

**裁决**: PENDING

等待真机记餐、目标进度、发布与反应验证。

## 安全不变量

- 单餐不获得体重变化因果归因。
- 低 BMI 目标不被鼓励。
- 社区发布必须手动确认。
- 公开快照不含体重、病史、药物、位置、备注和原图。
- 社区故障不回滚或重复写入饮食记录。
- 反应计数不进入 Agent 医疗或行动排序。

## 当前检查点

S5 building：功能、契约、迁移、隐私与回归已通过，等待精确提交、后端部署和 production OTA。
