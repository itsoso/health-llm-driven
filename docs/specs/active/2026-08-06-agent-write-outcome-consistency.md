# Feature Spec: Agent 健康写入终态一致性

> Status: accepted
> Owner: Codex + release owner
> Updated: 2026-08-06
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` R5/R11/R12
> Related code: `backend/app/services/agent_executor.py`, `backend/app/api/agent.py`, `backend/app/services/inline_cards.py`, `backend/app/services/medication_intake_batch.py`, `backend/app/services/contextual_meal_photo_service.py`, `frontend/src/components/assistant/inlineCards/cards.tsx`, `mobile/components/chat/cards/`

## 1. Decision

把健康写入的正文、卡片和持久化结果收口到服务端执行事实：没有回执不得显示“已记录”，没有真实确认计划不得显示“待确认”，失败的图片原子保存不得退化为无图片饮食写入。

## 2. Problem

两个生产故障暴露了同一类缺陷：

- 餐食图片已经完成识别，但图片资产与饮食草稿的 PostgreSQL 原子保存失败；对话仍继续调用通用饮食写工具，最终同时出现“已记录”和“未保存”。
- 常见的“数量在药名前”用药表达未进入确定性用药确认路径，被 Agent 主分类器误判成饮食；校验失败后，旧卡片仍显示成不可操作的“待确认”，最终正文又声称缺少信息。

现有正文、服务端 `WriteIntent`、工具回执和 query 派生卡片使用了不同真源。继续按句式打补丁会留下同类矛盾，并直接影响正式版可信度和 App Store 真机验收。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复早餐图片保存和用药记录中的同类写入状态矛盾
  classification: bugfix
  first_user_fit: 需要低摩擦记录饮食、用药和补剂的核心用户
  core_loop_step: Mobile/Web execution -> ExecutionEvent -> Health Twin
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: [Backend, Mobile, Web]
  source_of_truth: verified write receipts and durable server-owned WriteIntent state
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: deterministic parser, tool execution facts, database receipts
  claim_hedging: n/a
  verification_window: same turn plus post-deploy production smoke
  success_metric: zero contradictory write-state presentations in the regression matrix
  added_user_burden: none
  burden_justification: n/a
  non_goals: dose advice, medication changes, nutrition-estimation redesign, schema migration
  smallest_end_to_end_slice: two production sentences plus shared failed/pending/verified card gate
  stale_surface_to_remove_or_archive: route-only medication/supplement cards masquerading as pending confirmations
  spec_required: yes
```

## 4. Non-Goals

- 不诊断、不开方、不调整药物剂量或频次。
- 不扩展药名识别到任意未知字符串；确定性批次仅使用现有药物和受控别名字典。
- 不重写 Agent 全部状态机，不新增数据库表或迁移。
- 不改变营养估算模型或图片识别算法。
- 不把本修复视为 App Store 已通过；正式版本仍需独立 G5/G6 和真机证据。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | 常见的单药“服量在药名前”表达进入真实服务端待确认计划；路由建议不冒充待确认。 |
| `ExecutionEvent` | 用户可见“已记录”只由验证回执支撑；失败或待确认不得被通用兜底覆盖。 |

## 6. User Flow

```text
用户明确记录饮食/用药/补剂
  -> 确定性分类与解析
  -> 图片草稿 / WriteIntent / 工具写入
  -> 服务端根据执行事实得到 verified | confirmation_required | failed
  -> 同一终态投影到正文与卡片
  -> 用户确认后才产生可验证写入回执
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | 唯一执行真源 | `write_receipts` 表示已写入；服务端 pending plan 表示待确认；失败终态压制 query 派生摄入卡。 |
| Mobile | 主执行面 | 只有真实 pending plan 显示“待确认”；route-only 草稿显示“待核对/去记录”。 |
| Web | 次级执行面 | 与 Mobile 使用相同的 pending/suggestion/terminal 语义。 |

## 8. Data Contract

```yaml
apis: existing Agent SSE done/card descriptors; no endpoint change
events: existing turn_outcome, write_receipts, pending_write_intent_ids/kinds
models: no schema change
fields:
  presentation_state: optional card presentation hint; suggestion for route-only legacy drafts
enums:
  presentation_state: suggestion
backward_compatibility: missing presentation_state keeps existing server-owned medication pending behavior
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- 用药记录永久保持 `manual_confirm`；解析结果只是本次已服事实草稿，不是剂量建议。
- 确定性解析和 LLM 兼容入口都只接受受控药名/别名或该用户已有的药物定义；未知“药名样式”必须在创建 `WriteIntent` 前 fail closed。
- 只接受明确肯定、当前时点、带数量的表达；疑问、否定、更正、缺量继续 fail closed。
- 不把用户原始健康文本写入新增日志；终态 telemetry 只记录无内容的 category/reason。
- 所有 `WriteIntent`、记录和回执继续由现有 owner/user_id 隔离与确认服务执行。
- 图片原子保存失败必须显式失败且零饮食写入，不允许静默降级。

## 10. AI Behavior

- LLM 可解释或请求缺失信息，但不是“已记录/待确认”的授权真源。
- 确定性解析器可从受控药名词典解析单个药物及本次实际服量。
- 回合完成前使用执行事实压制与终态冲突的 query 派生卡片。
- 失败不由模型改写成成功；待确认不由模型改写成通用缺参。

## 11. Acceptance Criteria

```gherkin
Given 用户发送“记录我吃了两粒阿奇霉素”
When Agent 处理本轮
Then 不调用 LLM 猜写入，不创建 MedicationLog，并返回一个真实可确认的 medication_intake_batch WriteIntent

Given 该 WriteIntent 已向用户展示
When 用户确认一次或重复确认
Then 只产生一条验证过的 MedicationLog 回执且保持幂等

Given 用户发送带数量的未知“药名样式”且模型把它提议为 medication
When 服务端校验模型工具参数
Then 在创建 WriteIntent 前拒绝提案，且产生零 MedicationLog；用户已有药物定义仍可进入手动确认

Given query 派生的用药或补剂卡只有页面跳转动作
When Web 或 Mobile 渲染卡片
Then 标题不得是“待确认”，并明确当前尚未写入

Given Agent 写入终态是 action_not_executed/tool_failed/tool_blocked/write_reconciliation_required
When API 组合 done.cards
Then 不附加 query 派生的饮食、用药或补剂写入卡

Given 餐食图片草稿包含受外键约束的图片资产
When PostgreSQL 刷新事务
Then 先持久化父草稿再持久化资产并一次提交

Given 图片草稿保存失败或仍待确认
When 模型随后尝试通用饮食写入
Then 健康写工具被确定性阻止且本轮产生零 DietRecord 回执
```

## 12. Verification Plan

```bash
cd backend
pytest tests/test_medication_intake_batch.py tests/test_agent_medication_batch_flow.py
pytest tests/test_utterance_intent_classifier.py tests/test_agent_conversations_api.py
pytest tests/test_contextual_meal_photo_service.py tests/test_agent_executor_food_vision.py

cd frontend
npm test -- src/components/assistant/inlineCards/__tests__/MedicationDraftCard.test.tsx

cd mobile
npm test -- --runInBand components/chat/cards/__tests__/MedicationDraftCard.test.tsx components/chat/cards/__tests__/registry.test.tsx
npx tsc --noEmit

python3 backend/scripts/check_dossier_consistency.py
python3 scripts/check_doc_drift.py
git diff --check
```

部署前再运行项目集成闸、G4 独立安全评审和主干 CI 检查；部署后使用合成 QA 账号验证，不记录真实健康内容。

## 13. Rollout And Rollback

- 先部署 Backend，使解析、外键顺序和卡片组合闸生效。
- Web 随正常前端部署；Mobile 仅 JS/TS 展示语义变化，可走 production OTA，但 App Store 1.3.3 候选构建开始后必须遵守 production OTA freeze。
- 回滚到部署前 commit；无数据库迁移和不可逆数据变更。
- 若 G5/G6 失败，停止 iOS 1.3.3 构建/提交并回到 S5。

## 14. Open Questions

无阻断问题。完整统一所有健康写状态机留作后续架构切片，本次只增加终态一致性闸与两个已证实生产根因修复。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-06 | Accepted initial spec | 用户确认按系统性、可控的 B 方案实施。 |
| 2026-08-06 | Hardened model-proposed medication identity boundary | G4 发现宽泛药名后缀可能绕过确定性解析进入 durable WriteIntent。 |
