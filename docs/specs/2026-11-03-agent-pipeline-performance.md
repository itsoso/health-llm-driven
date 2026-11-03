# Agent 请求处理链路性能优化

Status: first batch released at `b9904bd198615e811b4c6df3d586e537431d53e6`; remaining stages and production SLO unverified. Baseline `3c438e8362e3ce3dc11e845b80d22c98a506be0b`.
Controller / evidence: [既有延迟 Dossier](../dossiers/2026-11-02-explicit-model-latency.md).

## Decision and admission

在原鉴权、同意、运行账本、Pi/Gateway 和结果核验内，减少不必要的串行调用；以有效结果而非进度动画衡量三秒目标。

```yaml
RequirementAdmission:
  request: 按整体代码链路性能规划执行
  classification: existing-flow-performance
  first_user_fit: 减少记录与查询的等待和注意力成本
  core_loop_step: execution-and-verification
  first_class_objects: [ExecutionEvent, WriteIntent]
  target_surface: [backend-agent, mobile-chat]
  source_of_truth: owner-bound persistence and verified receipts
  safety_level: health-data-sensitive
  prescription_or_causal_verdict: none added
  autonomy_tier: existing current-turn authorization
  evidence_provenance: seven-day production aggregate and paired synthetic replay
  claim_hedging: production and native-paint SLO unproven until measured
  verification_window: before candidate release and post-release observation
  success_metric: fewer serial calls with no quality regression; common effective-result P95 target 3s
  added_user_burden: none
  burden_justification: none
  non_goals: no lowered clinical floors or new write authority
  smallest_end_to_end_slice: closed read bypasses advisory route; known meal receipt completes without model prose
  stale_surface_to_remove_or_archive: progress-only first_useful accounting
  spec_required: yes
```

## Execution and surface contract

Common entry remains authenticated consent / dedupe / owner-bound runtime admission.
Closed read scope may omit the optional decision service; existing-conversation history and model planning remain required.
Unknown/chat tool intent retains the answer provider and the existing tool set instead of first generating disposable text on a fast tool provider.
Closed current-turn meal record may finish after canonical receipt, owner, source message and attached photo proofs agree. Pending/failed/mixed/advice/correction turns retain their existing paths.
All terminal output goes through existing outcome classification, persistence, receipt validation and stream finalization.

Mobile measures progress separately from useful text/card/verified receipt. Corrected metric version is separated from historical v2; it does not claim onLayout proves viewport visibility.
No DB schema or native dependency change. Existing event versions remain readable; no per-owner cache or new notification surface is introduced.

## Sequencing and acceptance

1. Remove proven unnecessary waits and duplicate generation; establish RED/GREEN on actual executor/client paths.
2. Make closed meal completion receipt-driven; preserve photo identity, calibration, idempotency and clarification.
3. Correct and version timing semantics across producer/ingestion/aggregation/export.
4. Evaluate context preparation, vision and deep-analysis continuation against paired evidence before expanding their behavior. Reuse existing scopes and lifecycle; do not promote a new timeout, provider, cache or background runner without quality and recovery evidence.

Baseline window 2026-10-27 01:44:39 UTC through 2026-11-03 01:44:39 UTC: 156 run-linked requests, 150 with performance; 39/116 advisory routes timed out around 5s; 19 discarded direct fast answers. These are historical aggregate observations, not a causal sum or candidate acceptance.
Paired replay uses fixed synthetic prompts with disposable owner data and genuine providers where needed. Preserve every timeout/failure; report P50/P95/P99 with sample limitations, model calls, prompt size and observed token usage. Do not replay raw production health content into tests.
Negative tests cover owner/source mismatch, missing/unverified receipts, extra goals, negation, clinical floors, historical correction and stream interruption. PG CI validates production database semantics before release.
Stop rollout on false success, changed write scope, quality decline, unexpected model/cost increase or worse tail latency. Keep the current healthy deployment and repair candidate; no backup, restore drill or automatic old-configuration recovery.

## Delivery

Run focused suites, CI-mode integration, System Map, independent safety review and exact-candidate live LLM gate. Then exact-SHA full CI, governed backend deployment, OTA validate and publish. Server/OTA proof and App visible-result acceptance remain separate.
