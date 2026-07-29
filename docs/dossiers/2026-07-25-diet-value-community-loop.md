| 字段 | 值 |
|---|---|
| feature | diet-value-community-loop |
| status | shipping |
| current_stage | S7 / G6 pending |
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
| G3 测试 | PASS | 后端 124 项、Mobile 32 项相关回归；TypeScript、迁移、lint、design token、doc drift 通过 |
| G4 安全/隐私 | PASS | owner isolation、严格公开 allowlist、低 BMI/增重目标降级、手动发布和失败隔离均有测试 |
| G5 部署健康 | PASS | backend `e3fa8483` 精确部署、迁移执行、`60/60` 健康分；production OTA 已发布并回读校验 |
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

**裁决**: PASS

验证证据：

- 后端从精确提交 `e3fa84835f6f50817f2753a0c68783bb04d34cad` 部署；
- PostgreSQL 备份、231 张表恢复演练、站外加密归档及 HMAC 校验通过；
- 迁移 `20260725_120000_community_peer_support` 已应用；
- 后端、Celery 和知识库索引重启完成，部署健康分 `60/60`；
- production OTA runtime `1.3.2`，update group `141e813f-3ded-4bc3-9fcd-8113b0e4c437`，iOS update `019f986b-96d6-78bb-960b-bed857ffbd56`；
- OTA 脚本已回读校验 update group、iOS update 和提交锚点。

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

S7 / G6 pending：功能、契约、迁移、隐私、回归、后端部署和 production OTA 已完成。等待真机验证记餐后的目标反馈、主动发布确认、同行反应、删除与举报；在这些操作完成前不宣告 G6 通过。

## Phase 2 Hardening（2026-07-25）

目标：消除不同幂等键造成的同餐重复发布，恢复跨页面发布状态，让支持反应即时可见，并为过期体重提供直接更新入口。

- 实施计划：`docs/plans/2026-07-25-diet-value-community-loop-hardening.md`
- 同一用户、同一来源餐次最多存在一条非删除分享；历史重复由托管迁移保留最新一条。
- Mobile 进入同行圈时先恢复已发布分享，不再短暂展示重复发布器。
- 支持反应先本地更新，服务端失败时回滚并明确提示。
- 体重超过 3 天未更新时提供“更新体重”；新鲜数据及目标安全复核状态不展示该入口。

### Phase 2 Gate Ledger

| Gate | 状态 | 依据 |
|---|---|---|
| G2 可行性+安全 | PASS | 数据库唯一约束为真源；owner-scoped 查询；删除后允许重新发布；目标安全状态不增加体重入口 |
| G3 测试 | PASS | 社区/饮食回执后端完整回归 27 项；迁移语义 1 项；Mobile 页面和服务 12 项；TypeScript、lint、design token 通过 |
| G4 安全/隐私 | PASS | 查询仅返回当前用户来源分享；公开投影未扩大；社区失败不影响私人饮食记录 |
| G5 部署健康 | PASS | 后端 `c127aed7` 精确部署；迁移已应用；生产健康分 `60/60`；production OTA 已发布并回读校验 |
| G6 上线验证 | PENDING | 等待真机验证状态恢复、反应回滚和旧体重入口 |

### Phase 2 G5 部署证据

- 后端从精确提交 `c127aed7999da76948369244f6a866df7e97f28e` 部署；
- PostgreSQL 备份、234 张表恢复演练、站外加密归档及 HMAC 校验通过；
- 迁移 `20260725_180000_community_source_idempotency` 已应用；
- 后端、Celery 和知识库索引重启完成，部署健康分 `60/60`，Skills `22/22`；
- production OTA runtime `1.3.2`，update group `4a82d916-f996-4725-ba08-0a83fbca202b`，iOS update `019f98cf-bb74-750c-abc7-bb373046d1bc`；
- OTA 脚本已回读校验 update group、iOS update 和提交锚点 `c127aed7`。
