# Feature Spec: Agent 批量健康记录删除

> Status: accepted
> Owner: Reva Backend
> Updated: 2026-08-27
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md`
> Related code: `backend/app/services/write_intent_scope.py`, `backend/app/services/agent_kernel/goal_spec.py`, `backend/app/services/agent_kernel/capability_policy.py`, `backend/app/services/agent_executor.py`

## 1. Decision

允许用户在一个明确的当前回合中删除最多 5 条饮食记录；服务端必须从用户原文编译完整 ID 集，先验证所有目标都属于当前用户，再生成不可由模型删减或扩大的删除计划。其他健康类型继续只支持单条精确删除。

## 2. Problem

Mobile Agent 目前只承认单个“记录类型 + ID”的整条删除语法。用户要求删除饮食记录 977 和 979 时，模型虽然连续提出两个删除工具调用，安全策略仍把两次调用都判为缺少单目标证据，导致回合长时间等待且没有删除任何记录。后续“确认删除”也无法补齐当前回合所需的精确类型和 ID 证据。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复 Mobile Agent 无法删除两条明确错误餐食记录并发布
  classification: bugfix
  first_user_fit: 使用 Mobile Agent 修正错误健康记录的核心用户
  core_loop_step: correction -> WriteIntent -> verified ExecutionEvent -> HealthTwin
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: [Mobile, Backend]
  source_of_truth: owner-scoped PostgreSQL health records and verified write receipts
  safety_level: privacy_sensitive_destructive_write
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: exact current-turn typed IDs plus owner-scoped server lookup
  claim_hedging: n/a
  verification_window: same turn and post-deploy read-only smoke
  success_metric: a valid two-ID request produces two verified receipts; unsafe variants produce zero writes
  added_user_burden: explicit record type and IDs in the delete message
  burden_justification: required to disambiguate IDs that may exist in different health tables
  non_goals: batch delete for non-diet types, delete by ordinal/latest/all/range, mixed record types, transactional batch endpoint, automatic deletion after a prior vague confirmation
  smallest_end_to_end_slice: one typed diet delete request -> owner lookup -> exact two-call plan -> two verified receipts
  stale_surface_to_remove_or_archive: unsupported guidance that suggests a generic confirmation can authorize deletion
  spec_required: yes
```

## 4. Non-Goals

- 不根据“刚才两餐”“全部”“上一条”或范围猜测目标。
- 不支持非饮食类型批量删除或混合记录类型，也不跨回合继承模糊确认。
- 不新增数据库迁移或批量删除 API；已有逐条 owner-scoped 删除与回执仍是执行真源。
- 不在发布验证中删除 977/979 或其他真实用户数据。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | 从当前用户原文固定饮食类型、去重、有限数量的完整目标 ID 集。 |
| `ExecutionEvent` | 每个目标仍需独立 verified receipt；部分失败必须诚实暴露并可按既有恢复机制续跑。 |

## 6. User Flow

```text
用户说“删除饮食记录 977 和 979”
  -> 服务端闭合语法编译 diet + [977, 979]
  -> owner-scoped list 一次性校验全部目标
  -> 服务端生成两条确定性删除调用并持久化完整预期写计划
  -> 逐条执行并收集 verified receipts
  -> 只有两条都验证后才确认全部完成
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 发送用户原文并展示服务端终态 | 无原生或 OTA 代码变更；不得把等待/失败显示为已删除。 |
| Backend | 编译授权、owner 校验、固定计划、执行与回执 | 模型不能增加、删减或替换目标；任一目标未找到时零删除。 |

## 8. Data Contract

```yaml
apis: existing Agent SSE and health_manage endpoints
events: existing planned writes and verified write receipts
models: no change
fields: no change
enums: no change
backward_compatibility: existing exact single-record delete remains supported
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- 删除属于不可逆健康数据写操作，授权只来自当前回合的闭合语法，不来自模型输出或历史泛化确认。
- 批量类型必须明确为饮食，ID 必须为正整数、去重后 2 至 5 个；范围、选项、混合类型、字段删除、否定和撤销均 fail closed。其他健康类型继续沿用单条精确删除。
- 执行前必须证明所有目标都存在于同一 owner-scoped lookup；只找到一部分时禁止删除任何一条。
- 日志只记录类型、数量、策略原因和回执状态，不新增健康内容日志。

## 10. AI Behavior

LLM 可以理解用户意图和生成回复，但不能决定删除目标。服务端在查询前把任何模型写调用改写为唯一 owner lookup；查询后忽略模型给出的删除子集或额外 ID，按编译后的完整目标集生成确定性调用。解析、查询或任一回执失败时不得声称全部完成。

## 11. Acceptance Criteria

```gherkin
Given the user says to delete diet records 977 and 979
When both IDs are returned by the owner-scoped diet lookup
Then exactly those two delete calls are planned and each requires a verified receipt

Given only one requested ID is returned by the owner-scoped lookup
When the mutation phase is reached
Then no delete call is authorized or executed

Given the user omits the record type, uses a range/all/field-removal expression, mixes types, or requests more than five records
When the turn is compiled
Then no batch delete goal is created and zero records are deleted

Given an existing exact single-record delete request
When its owner lookup succeeds
Then its behavior remains compatible
```

## 12. Verification Plan

```bash
cd backend
pytest tests/test_write_intent_scope.py tests/test_agent_goal_spec.py tests/test_agent_kernel_capability_policy.py tests/test_health_manage_date_normalize.py

python3 scripts/harness_llm_change_gate.py
python3 scripts/check_dossier_consistency.py
./scripts/system-map-check.sh
git diff --check
```

部署前执行独立 G4 安全评审；部署后只验证生产 revision、服务健康和闭合策略，不触碰真实健康记录。

## 13. Rollout And Rollback

仅发布 Backend，无 Mobile OTA 或数据库迁移。使用根目录 `deploy.sh` 发布；失败或生产策略异常时回滚到部署前 SHA。真实 977/979 的删除需用户在新版本上线后重新发起明确的带类型请求。

## 14. Open Questions

无首版阻断问题。未来如需要跨类型或事务型批量删除，应另建带预览和二次确认的一等产品对象，不在本次扩权。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-27 | Accepted bounded typed batch delete | Production Mobile request exposed a single-target authorization dead end. |
| 2026-08-27 | Narrowed batch support to diet records | Only the diet owner lookup honors the bounded 100-row preflight needed for the reported case; other types retain safe single-record behavior. |
