# Feature Spec: 复杂回答时延与恢复数据安全升档

> Status: implementing
> Owner: Codex
> Updated: 2026-08-31
> Related PRD/PDD: `docs/dossiers/2026-08-31-complex-latency-recovery-safety-routing.md`
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/llm/task_routing.py`, `backend/app/services/wearable_router.py`

## 1. Decision

为 staged response 的均衡档设置用途匹配的最终回答预算；当恢复/运动建议所依赖的数据缺失、过期、冲突、读取失败或明显不可信时，确定性地升到高风险答案模型，并限制为保守运动建议。

### 1.1 2026-08-31 TTFT correction

本轮继续优化不把“已接收”状态当成正文 TTFT，也不再使用从健康证据编译之后才起钟的局部指标冒充端到端时延：

- 保留 `llm_ttft_ms` / `total_ms` 兼容字段，新增从 `run_stream` 入口起算的 `end_to_end_ttft_ms` / `end_to_end_total_ms`、`turn_setup_ms`、`health_compile_ms` 与 `first_evidence_ms`。
- staged `balanced` 在已探针验证支持的模型上使用 512 thinking token；`high_stakes` 与调用过 `health_analysis` 的回合不封顶。
- Health Evidence 正文继续完整缓冲并经过确定性验证，但最终可见回答预算收口到 1200 token，避免“必须生成完才能首字”的无界长尾；不限制模型思考。
- 在 `request_persisted` 后、正文 token 前发送与最终 `done.answer_evidence` 相同的有界依据投影。它只来自本轮 owner-scoped Health Evidence packet，不包含 prompt、原始嵌套载荷或模型草稿。
- `BALANCED_SYNTHESIS_THINKING_BUDGET=0`、`HEALTH_EVIDENCE_ANSWER_MAX_TOKENS=8000`、`ANSWER_EVIDENCE_STREAMING_ENABLED=false` 可分别回退三个策略，不需要关闭健康安全运行时。

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
- 不关闭均衡/高风险分析思考；均衡档只做已验证参数的有界思考，高风险与深分析保持完整思考。
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
| Mobile | 在流式 assistant 气泡中先展示有界回答依据，再展示最终验证正文 | 未识别 `answer_evidence` 的旧客户端忽略该加法事件。 |
| Backend | 分档、质量判定、升档、保守合成、依据投影和端到端计时 | 不扩大工具、数据范围或写权限。 |

## 8. Data Contract

```yaml
apis: unchanged
events: existing accepted/request_persisted/tool/synthesis/done plus additive answer_evidence
models: none
fields:
  - done.meta.recovery_data_guard.status
  - done.meta.recovery_data_guard.reason_codes
  - done.meta.recovery_data_guard.model_escalated
  - done.perf.end_to_end_ttft_ms
  - done.perf.end_to_end_total_ms
  - done.perf.turn_setup_ms
  - done.perf.health_compile_ms
  - done.perf.first_evidence_ms
enums:
  - status: ok | degraded
  - reason_codes: missing_core_signal | stale_signal | conflicting_signal | implausible_signal | read_failed | guard_unavailable
backward_compatibility: additive optional metadata only
migration: none
```

元数据不得包含健康数值、用户文本、来源原始载荷或错误堆栈。

`answer_evidence` 是用户可见 L3 健康数据投影，不属于上述内容无关元数据；它必须在当前已认证 SSE 连接中、且只在 `request_persisted` 后发送。其 schema 与最终持久化的 `answer-evidence.v1` 相同，最多 4 条依据和 3 条限制。

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

Given staged balanced 使用支持 thinking budget 的答案模型
When 进入无工具合成轮
Then thinking_budget=512
And high_stakes 或 health_analysis 回合不注入 thinking_budget

Given Health Evidence 回合需要在最终验证后才释放正文
When 生成答案
Then max_tokens=1200 且验证器仍在正文前执行
And 将配置设回 8000 可单独回退该限制

Given Health Evidence packet 已编译且用户消息已持久化
When Mobile 等待最终验证正文
Then 先收到 answer_evidence.v1，再收到 token/done
And early projection 与 done/persisted projection 一致
And 流式阶段立即显示依据但不开放复制或分享
And interrupted/error 终态保留依据时明确标注回复未完整结束
And 关闭 streaming kill switch 时不发送早期事件但不丢失 done/历史依据

Given 同一批真实或可复现 fixture 请求
When 比较改动前后
Then 以 end_to_end_ttft_ms 的 P50/P90/P99 和 first_evidence_ms 验收
And 不以 accepted/status 延迟代替正文 TTFT
And 在安全/质量不回退前不宣称“已经变快”
```

## 12. Verification Plan

```bash
python3.12 -m pytest backend/tests/test_agent_recovery_data_guard.py
python3.12 -m pytest backend/tests/test_agent_executor_progress_events.py
python3.12 -m pytest backend/tests/test_task_routing_power_on.py
uv run --project backend python -m pytest backend/tests/test_agent_executor_thinking_budget.py backend/tests/test_agent_executor_health_evidence_runtime.py backend/tests/test_agent_send_observability.py
cd mobile && npm test -- --runInBand services/__tests__/chatStream.test.ts hooks/__tests__/useChatEngine.test.ts utils/__tests__/chatTransparency.test.ts
python3.12 scripts/harness_llm_change_gate.py --path backend/app/services/agent_executor.py
python3.12 scripts/harness_llm_regression_gate.py --include-live-llm --json
./scripts/system-map-check.sh
git diff --check
```

最后在 iOS Simulator 使用不含真实健康数据的简单、均衡、高风险 fixture 验收阶段顺序、完成态、模型档位元数据与保守文案。

## 13. Rollout And Rollback

- 行为继续受 `STAGED_RESPONSE_MODE` 控制；off 回到旧路由和旧回答预算。
- balanced thinking、Health Evidence 输出预算和早期依据事件分别有独立配置回退；端到端计时字段只增不删。
- 无迁移、无数据回填；回滚只改变后续回答。
- 生产放量、commit、push、deploy、OTA 需要独立授权，本切片不自动执行。

## 14. Changelog

- 2026-08-31：补充 TTFT 口径修正、balanced thinking 预算、Health Evidence 输出上限、早期依据事件及独立回退条件。
