# Feature Spec: 复杂回答时延与恢复数据安全升档

> Status: approved
> Owner: Codex
> Updated: 2026-08-31
> Related PRD/PDD: `docs/dossiers/2026-08-31-complex-latency-recovery-safety-routing.md`
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/llm/task_routing.py`, `backend/app/services/wearable_router.py`

## 1. Decision

为 staged response 的均衡档设置用途匹配的最终回答预算；当恢复/运动建议所依赖的数据缺失、过期、冲突、读取失败或明显不可信时，确定性地升到高风险答案模型，并限制为保守运动建议。

## 2. Problem

复杂健康问题虽已先发送承接语，但最终生成仍可使用 8000 token，长尾没有按“均衡分析”用途收口。另一方面，恢复问题在读取睡眠/HRV 后才可能发现数据不可用，而当前模型分档只看用户输入；普通查询工具暴露数据问题不会二次升档，也没有确定性的运动强度上限。

若不处理，用户仍会长时间等待完整答案；更严重的是，系统可能在恢复证据不足时给出看似确定的积极训练建议。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 降低复杂回答完整耗时，并在恢复数据质量不足时自动升档和收紧运动建议
  classification: existing_core_loop_performance_and_safety_behavior
  first_user_fit: yes
  core_loop_step: wearable facts -> data quality -> safety -> advice -> action
  first_class_objects: [HealthTwin, SafetyGuardian, LeverageAction]
  target_surface: Backend Agent consumed by Mobile
  source_of_truth: owner-scoped wearable router snapshot plus actual tool result
  safety_level: medical_boundary
  prescription_or_causal_verdict: no
  autonomy_tier: none
  evidence_provenance: wearable source freshness/conflict and tool result status
  claim_hedging: degraded recovery data must be stated explicitly
  verification_window: same turn
  success_metric: balanced P95 budget <= 30s; degraded recovery always high_stakes and conservative
  added_user_burden: none
  burden_justification: not_applicable
  non_goals: [diagnosis, medication advice changes, new data writes, raw reasoning exposure]
  smallest_end_to_end_slice: recovery question -> read -> quality guard -> escalation -> bounded conservative answer
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- 不把用户可见医疗正文降到 fast 模型。
- 不关闭均衡/高风险分析思考，不以牺牲正确性换 TTFT。
- 不修改 SafetyGuardian、恢复评分算法、设备来源优先级或健康数据。
- 不新增数据库、API、客户端 schema、自动写入或后台同步。
- 不承诺缺失数据时用户一定可以锻炼；急性症状仍优先走既有红线。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | 不改存储；继续提供恢复事实，质量判定复用 owner-scoped wearable snapshot。 |
| `SafetyGuardian` | 增加 Agent 合成前的确定性恢复数据安全边界，不替代既有急性红线。 |
| `LeverageAction` | 数据降级时训练动作最多为低强度恢复活动或休息，不生成高强度行动。 |

## 6. User Flow

```text
用户询问睡眠/恢复与今天训练
  -> 立即收到确定性承接语
  -> 内部快模型只决定只读工具
  -> owner-scoped 恢复数据被读取并检查完整性、新鲜度、冲突和 plausibility
  -> 正常数据：均衡模型在有界答案预算内综合
  -> 降级数据：答案模型升至 high_stakes，合成收到保守运动硬约束
  -> 用户看到完整结论、数据缺口和安全下一步
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 展示既有阶段响应和最终回答 | 不新增协议；旧客户端兼容。 |
| Backend | 分档、质量判定、升档、保守合成和内容无关元数据 | 不扩大工具或写权限。 |

## 8. Data Contract

```yaml
apis: unchanged
events: existing accepted/tool/synthesis/done
models: none
fields:
  - done.meta.recovery_data_guard.status
  - done.meta.recovery_data_guard.reason_codes
  - done.meta.recovery_data_guard.model_escalated
enums:
  - status: ok | degraded
  - reason_codes: missing_core_signal | stale_signal | conflicting_signal | implausible_signal | read_failed | guard_unavailable
backward_compatibility: additive optional metadata only
migration: none
```

元数据不得包含健康数值、用户文本、来源原始载荷或错误堆栈。

## 9. Safety, Privacy, And Medical Boundary

- 判定只读取当前认证用户的 wearable snapshot；不跨用户、不写数据。
- 恢复数据降级时不得输出冲刺、间歇、VO2max、大重量或其他高强度训练许可。
- 在没有急性症状的前提下，最多建议轻松步行、拉伸、活动度练习；有明显不适时优先休息，并沿用既有就医红线。
- 系统必须明确数据缺失/异常，不得把通用知识填成个人恢复结论。
- guard 自身异常按 fail-closed 降级，日志只记原因码和耗时，不记录完整健康载荷。

## 10. AI Behavior

- LLM 可解释已验证的恢复事实并给出非处方化行动。
- LLM 不决定数据是否可信；该判定来自确定性 guard。
- 降级指令作为 system-owned tool context 进入最终合成，要求声明不确定性并限制运动强度。
- 模型路由在工具结果后可从 balanced 提升为 high_stakes；不能降档。
- flag off 时保留原行为，便于回滚。

## 11. Acceptance Criteria

```gherkin
Given staged response 为 on 且问题属于 balanced
When 最终答案模型生成正文
Then max_tokens 使用均衡档预算而不是全局 8000
And 高风险档与 flag off 保留既有质量预算

Given 用户询问昨晚恢复是否适合锻炼
When owner-scoped 恢复数据缺少睡眠或 HRV/readiness 核心信号
Then recovery_data_guard=degraded
And 答案模型提升为 high_stakes
And 最终合成明确数据不足且禁止高强度训练许可

Given 恢复数据过期、跨设备冲突、读取失败或含 plausibility warning
When 工具结果进入合成
Then 使用同一 fail-closed 升档与保守边界

Given 用户只是查询步数或记录饮食
When 工具正常执行
Then 不触发恢复数据 guard 或模型升档

Given 简单、均衡、高风险三档合成 fixtures
When 在 iOS Simulator 运行验收
Then 都先显示阶段反馈并完成；均衡档满足完整耗时预算；高风险/降级恢复档展示保守边界且不泄露思考过程
```

## 12. Verification Plan

```bash
python3.12 -m pytest backend/tests/test_agent_recovery_data_guard.py
python3.12 -m pytest backend/tests/test_agent_executor_progress_events.py
python3.12 -m pytest backend/tests/test_task_routing_power_on.py
python3.12 scripts/harness_llm_change_gate.py --path backend/app/services/agent_executor.py
python3.12 scripts/harness_llm_regression_gate.py --include-live-llm --json
./scripts/system-map-check.sh
git diff --check
```

最后在 iOS Simulator 使用不含真实健康数据的简单、均衡、高风险 fixture 验收阶段顺序、完成态、模型档位元数据与保守文案。

## 13. Rollout And Rollback

- 行为继续受 `STAGED_RESPONSE_MODE` 控制；off 回到旧路由和旧回答预算。
- 无迁移、无数据回填；回滚只改变后续回答。
- 生产放量、commit、push、deploy、OTA 需要独立授权，本切片不自动执行。

