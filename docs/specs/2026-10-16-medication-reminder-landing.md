# Feature Spec: 用药提醒落地页

> Status: defining
> Owner: unified publishing session
> Updated: 2026-10-16

## Decision / Problem

通知点击进入独立的「本次用药提醒」，保留目标药品、日期、时间和已记录状态；当前全量用药管理列表无法处理对应剂次，且停用按钮占据主操作。仅复用本人用药档案与确定性日志，不调用模型。

## Requirement Admission

```yaml
RequirementAdmission:
  request: 重新设计用药提醒的landing页面
  classification: product_change
  first_user_fit: 使用用药提醒的本人用户
  core_loop_step: 提醒到执行记录再核对
  first_class_objects: [HealthAgendaItem, ExecutionEvent, WriteIntent]
  target_surface: Mobile
  source_of_truth: authenticated backend Medication and MedicationLog
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 当前本人药品及精确剂次日志
  claim_hedging: n/a
  verification_window: 本次发布前合成用例及模拟器
  success_metric: 通知进入对应剂次且重复打开不重复记录
  added_user_burden: 已服用需本人点击确认；无日期旧通知需选择日期语义
  burden_justification: 打开提醒不等于服用，旧重复通知无法证明发生日
  non_goals: [调整处方或剂量, 停药建议, 删除历史异常条目, 新通知出口, 原生能力]
  smallest_end_to_end_slice: 通知定位到单药单剂次，读取状态，手动记录，凭回执更新
  stale_surface_to_remove_or_archive: 通知默认落到全量用药管理列表
  spec_required: yes
```

## Flow and visual design

Generic private notification → route with medication identifier and occurrence fields → authenticated exact-slot read → warm-paper page with back/header, green time hero, single white medication card, dosage/frequency and existing safety alerts → explicit 已服用 or 本次未服 → exact receipt → completed state. Management is a quiet bottom link; no pause/delete action in landing. Layout max-width 640, scrollable for large fonts/narrow screens. Missing identity/time shows useful unavailable state and management link, never all medications as a guessed dose.

Local repeating notifications lack date. Show 「提醒日期待确认」 and explicit 「查看今天这次提醒」 with account date/timezone; no write before confirmation. Dated historical reminders retain date and read exact historical status. Future slots, timezone mismatch, inactive/changed schedule, blank/clearly instruction-like names block quick check-in and offer review. No automatic deletion or reclassification of stored data. Payload names/doses are never the displayed source of truth.

## Contracts / safety

New read-only occurrence endpoint under medication API returns authenticated owner, account timezone/today, target date/time, medication details, exact slot log and actionable state/reason. Dedicated POST /medication/medications/{id}/reminder/log reuses the existing slot-idempotent log service. It accepts confirmed date/time/account timezone and an expected medication revision returned by GET, locks the owned medication row, and validates current active/schedule/name/dose/future/timezone/revision before writing. Generic manual-log semantics stay unchanged. Exact receipt must match id/date/time/status before success. Read-before-write additionally rechecks current context; server enforcement is authoritative. Local notification taken_time is the original dose slot; scheduled_time may only be delivery time and must not replace it. Remote uses scheduled_time and scheduled_timezone. Date-absent GET resolves account today but returns requires_date_confirmation and non-actionable; explicit date selection is necessary. Account/token changes invalidate pending reads and writes. Unknown POST outcome reconciles via one GET, no automatic retry. Double taps share a busy guard. Taken slot cannot be demoted by skip; agenda writeback must follow the persisted receipt, not conflicting request. Server owner isolation remains mandatory. Lock-screen strings stay generic.

## Implementation plan

T1 Backend: typed owner-scoped occurrence read, validation/status reasons and authoritative log writeback; failing tests first, SQLite plus PostgreSQL safety evidence.
T2 Mobile: safe notification param normalization, service with session guards/read-before-write/receipt reconciliation, dedicated responsive page and management reentry, failing tests first.
T3 Integration: routing, historical/undated/account switch/duplicate/error tests, visual synthetic preview and simulator where available; types, full mobile tests, System Map and dossier checks; independent G4.
T4 Release: unified clean candidate, CI-mode and exact main CI, backend then trusted OTA validate/publish; publisher handoff is still required before any external write. No backups. Record all receipts separately; no claim of device uptake.

## Acceptance

A1 Old local/remote notifications land on the new page; explicit edit links remain unchanged. A2 No write on open, wrong owner, unknown date/time, stale/changed med, or expired session. A3 Exact date/slot read and receipt-based state; repeat clicks/reopen do not duplicate. A4 Failed or uncertain requests never show success; retry only re-reads until reconciliation. A5 Long names/large text scroll, all controls at least 44px; manage as secondary, no stop control. A6 Generic notification privacy preserved. A7 Native camera/push delivery on device unverified; synthetic rendering is not device acceptance.
