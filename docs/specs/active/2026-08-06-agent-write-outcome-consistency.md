# Feature Spec: Agent 健康写入终态一致性

> Status: accepted
> Owner: Codex + release owner
> Updated: 2026-08-06
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` R5/R11/R12
> Related code: `backend/app/services/agent_executor.py`, `backend/app/api/agent.py`, `backend/app/services/inline_cards.py`, `backend/app/services/medication_intake_batch.py`, `backend/app/services/contextual_meal_photo_service.py`, `frontend/src/components/assistant/inlineCards/cards.tsx`, `mobile/components/chat/cards/`
>
> **Current release override (2026-08-12):** all repo-contained automatic remote/vendor release
> entrypoints, local signing/install/automatic-provisioning entrypoints and every OTA/rollback
> channel are frozen. EAS preview/development cannot prove isolation because channel→branch mapping may
> drift or be shared. Only local tests/Metro/iOS Simulator, offline evidence and public
> unauthenticated HTTPS are allowed; release plan/validate and production network observation are
> frozen, and no allowed evidence forms G5/G6;
> `npm run ios` uses the Simulator wrapper, callers may not append npm/Expo `--device`, and the
> wrapper pins an exact available Simulator UDID; physical iOS repo CLI is frozen;
> archive/export/signing/provisioning is frozen. The release
> Gate is BLOCK/STOP pending a new external trust-root dossier and independent G4.

## 1. Decision

把健康写入的正文、卡片和持久化结果收口到服务端执行事实：没有回执不得显示“已记录”，没有真实确认计划不得显示“待确认”，失败的图片原子保存不得退化为无图片饮食写入；带餐次的图片记录请求必须进入饮食链路，不能被通用图片词误路由到媒体创作或用药。

## 2. Problem

两个生产故障暴露了同一类缺陷：

- 餐食图片已经完成识别，但图片资产与饮食草稿的 PostgreSQL 原子保存失败；对话仍继续调用通用饮食写工具，最终同时出现“已记录”和“未保存”。
- 常见的“数量在药名前”用药表达未进入确定性用药确认路径，被 Agent 主分类器误判成饮食；校验失败后，旧卡片仍显示成不可操作的“待确认”，最终正文又声称缺少信息。

部署后的生产烟测进一步发现第三个同类入口问题：`记录这张早餐图片` 因通用 `图片` 先于具体健康域匹配而进入 AIGC 草稿；首次收窄后，`图片` 中的裸子串 `片` 又被误判为用药。该问题发生在写入前的确定性路由层，必须和终态一致性一起 fail closed。

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
- 不把本修复视为 App Store 已通过；正式版本仍需独立 G5/G6，以及解冻后由仓库外获权
  人工流程生成的同包真机证据。当前物理 iOS Gate 保持 BLOCK。

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
apis: existing Agent SSE done/card descriptors; AIGC confirmation GET adds exact outbound_prompt/review_token and confirm POST requires the token
events: existing turn_outcome, write_receipts, pending_write_intent_ids/kinds
models: no schema change
fields:
  presentation_state: optional card presentation hint; suggestion for route-only legacy drafts
  outbound_prompt/review_token/review_expires_at: owner-scoped runtime confirmation projection; never persisted in cards
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
- 通用附件名词不能单独授权 AIGC 或用药；只有显式媒体生成请求可进入 AIGC 草稿，已知药物与剂量单位仍由确定性用药解析器识别。
- 已完成/已保存等既成事实以及不要/禁止/取消/停止/未授权等否定表达不构成媒体生成授权；工具裁剪还必须核验显式生成 reason，不能只信领域与操作枚举。
- provider 确认只接受闭合语法且所有取消/撤销/本地-only 限制 deny-first；完整实际外发 prompt 必须先由 owner 审阅，确认 token 短时绑定 owner/confirmation/provider/model/prompt-version，Mobile/Web 加载失败时按钮保持禁用，通用 action dispatcher 不得绕过专用审阅卡。

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

Given 用户发送“记录这张早餐图片，仅用于发布验证”并附带图片
When Agent 选择领域与最小权限工具集
Then 领域为 diet 且不得把工具集收窄为仅 `draft_aigc_media`

Given 用户明确要求“把这张早餐图片做成短视频”
When Agent 选择领域与最小权限工具集
Then 仍进入 AIGC 手动确认草稿，不创建饮食或用药记录

Given 用户只说“记录这张图片”或陈述“图片已记录”
When Agent 选择领域与最小权限工具集
Then 不得进入 AIGC 草稿，且保留完整工具集等待视觉结果确定真实健康域

Given 用户说“不要生成图片”“禁止生成图片”或“未授权生成图片”
When Agent 处理显式生成动作
Then 不创建 AIGC 草稿，也不强制或收窄到媒体创作工具

Given 用户发出带当前源图片的复杂创作要求
When 语句不满足闭合的简单强制语法
Then 保持 general toolset 由模型选择草稿；若同时包含取消上传或仅限本地约束，capability gateway 必须在 provider 前阻断

Given 用户打开 AIGC 确认卡
When 完整外发 prompt 或 review token 未能从 owner-scoped GET 加载
Then Mobile/Web 不允许确认；加载成功后显示的完整纯文本必须与实际 provider prompt 逐字节一致
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

- 本地验证 Backend 解析、外键顺序、卡片组合闸，以及 Web/Mobile 展示；不得部署任一端。
- 所有 OTA/rollback channel 与 production native writer/observation 均冻结；existing
  candidate 仅可从 already-downloaded IPA/已有本地 metadata 对账，人工发布 Gate 保持
  BLOCK。
- 无数据库迁移和不可逆数据变更；本地失败回 S5。G5/G6 因无获准部署保持 BLOCK。

## 14. Open Questions

无阻断问题。完整统一所有健康写状态机留作后续架构切片，本次只增加终态一致性闸与两个已证实生产根因修复。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-06 | Accepted initial spec | 用户确认按系统性、可控的 B 方案实施。 |
| 2026-08-06 | Hardened model-proposed medication identity boundary | G4 发现宽泛药名后缀可能绕过确定性解析进入 durable WriteIntent。 |
| 2026-08-06 | Added attached meal-photo routing boundary | 部署后生产烟测发现通用“图片”和裸“片”子串会先后误入 AIGC 与用药域。 |
| 2026-08-06 | Closed generic/factual/negated AIGC authorization bypasses | 独立 G4 对抗复评发现媒体域仍可被普通记录、既成事实和否定生成表达误授权。 |
| 2026-08-06 | Made media denial association clause-aware | G4 二次复评证明字符邻近法既漏判口语/后置否定，也误伤跨分句的新授权。 |
| 2026-08-06 | Replaced media keyword authorization with explicit command frames | 连续对抗证明否定词表无法区分事实提及、撤销旧动作、重新授权和内容约束；外发草稿必须 fail-closed。 |
| 2026-08-06 | Made attribution and provider consent stateful across clauses | 独立复评证明跨标点转述、确认后的事实限定和无 provider 名称的上传 veto 仍会误授权；授权现在只由完整当前用户命令建立，并由非命令后继或隐私 veto 失效。 |
| 2026-08-06 | Replaced media synonym boundaries with fail-closed grammar | 后续复评证明 reporting/出站/动作名词扩表仍会漂移；控制面现忽略引号 payload、拒绝未知前导和非对象型裸动作，并把明确 create 到最终输出之间整体当作内容。 |
| 2026-08-06 | Closed external-provider review and capability gates | provider 授权改为 classifier/force 共用闭集并拒绝空白注入；完整 prompt、短时绑定 token、客户端初始禁用和 capability 本地/驻留/外发 veto 通过最终独立 G4。 |
