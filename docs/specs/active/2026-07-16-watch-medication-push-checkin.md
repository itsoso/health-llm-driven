# Feature Spec: Watch 用药提醒一键打卡

> Status: implemented, pending production verification
> Owner: Codex
> Updated: 2026-07-16
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` R4, R15
> Related code: `backend/app/tasks/notifications.py`, `mobile/hooks/useNotifications.ts`

## 1. Decision

Apple Watch 镜像的用药推送提供“服用”动作；用户明确点击后，系统按该提醒的药物和时间槽写入一条可验证、可幂等的 `MedicationLog`，不再要求进入 App 二次打卡。

## 2. Problem

目标用户每天可能有多个药物和多个服用时点。提醒只负责唤醒、打卡仍需打开手机，会增加遗漏和时间回忆误差。既有 `MEDICATION_REMINDER` 虽显示动作，但 App 被系统终止时 Expo 的 JS response listener 可能收不到后台动作，造成用户以为已打卡、数据库却没有记录。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 手表用药 push 点击服用后直接打卡到系统
  classification: product_change
  first_user_fit: 多药多时点且以 Apple Watch 执行日常健康行动的锚点用户
  core_loop_step: Agenda reminder -> Watch explicit action -> ExecutionEvent/MedicationLog -> review
  first_class_objects: [HealthAgendaItem, ExecutionEvent]
  target_surface: [Watch, Mobile, Backend]
  source_of_truth: PostgreSQL MedicationLog via POST /medication/logs
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 用户明确点击 + notification medication_id + scheduled_time
  claim_hedging: n/a
  verification_window: 点击后立即写入并刷新今日用药和议程状态
  success_metric: 成功点击一次对应同时间槽一条 taken 记录，失败不显示成功且可重试
  added_user_burden: 一次腕上点击
  burden_justification: 取代打开手机后的二次手工打卡
  non_goals: 不判断是否实际吞咽，不修改处方/剂量/时间，不自动代替用户确认
  smallest_end_to_end_slice: 远程用药提醒 -> Watch 镜像服用动作 -> Mobile 冷启动补偿 -> MedicationLog
  stale_surface_to_remove_or_archive: 旧的无时间槽 medication quick-action 写路径
  spec_required: yes
```

## 4. Product And Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | 提醒与持久化真源 | 可见文案不含药名/剂量；data 带 `medication_id`、`scheduled_date`、`scheduled_time`、`scheduled_timezone`、`rule_id`；`/medication/logs` 校验用户归属并按日+时点幂等 |
| Watch | 最短执行面 | 显示 iOS 镜像的“服用”动作，只表达用户确认，不作医疗判断 |
| Mobile | 可靠动作桥接 | 注册 category；动作唤醒或恢复后写入；成功才清 cold-start response；刷新今日用药、时间线和议程 |

## 5. User Flow

```text
到点用药提醒
  -> Apple Watch 显示“服用”
  -> 用户明确点击
  -> iOS/Expo 交付 notification response
  -> 严格校验 occurrence identity(date/time/timezone/rule_id)
  -> POST /medication/logs(medication_id, scheduled_date, scheduled_time, taken)
  -> PostgreSQL MedicationLog 幂等写入 + agenda writeback
  -> Mobile 今日用药/时间线/议程刷新
```

## 6. Safety And Privacy

- 点击“服用”只记录依从事实，不代表系统证明用户已吞咽，也不改变药名、剂量、频次或处方。
- 锁屏可见 title/content 只到“用药提醒”类别和时机，不暴露药名、剂量或诊断线索。
- `medication_id` 由认证用户的后端接口再次校验归属；客户端不能指定其他用户。
- 发生日期、时间、时区和 `rule_id` 缺一或不一致时 fail closed，不以手机点击时刻猜测服用槽。
- 网络或鉴权失败时不得清理冷启动动作、不得伪报已打卡；应用内显示失败、保留 response，并在联网恢复或 App 回前台时重试。
- 每日重复的本地通知没有稳定 occurrence date，不提供“服用”直写动作；只有后端远程推送可承载腕上打卡。
- 服务端用 `(user_id, medication_id, taken_date, taken_time)` 语义幂等，防止 Watch/iPhone 重复回调产生双记录。

## 7. Acceptance Criteria

```gherkin
Given 用药提醒已镜像到 Apple Watch
When 用户点击“服用”
Then 系统以提醒的 medication_id 和 scheduled_time 写入 taken MedicationLog

Given 用户跨午夜或旅行后点击旧提醒
When 客户端处理“服用”
Then 系统按 payload 的 scheduled_date/time/timezone 写入原发生日，且不误完成今天议程

Given 同一通知 response 被重复交付
When 客户端再次消费
Then 客户端去重且服务端同时间槽幂等，不产生第二条依从事实

Given App 在点击前已被系统终止
When 动作唤醒 App 并进入认证态
Then 客户端消费最后一条 response，写入成功后才清除 response

Given 写入失败
When 冷启动动作处理结束
Then response 保留、失败事件可观测，界面提示未保存，并在联网恢复或回前台时自动重试
```

## 8. Verification And Rollout

```bash
pnpm --dir mobile exec jest --runTestsByPath hooks/__tests__/agendaNotificationAction.test.ts services/__tests__/medications.test.ts --runInBand
pnpm --dir mobile exec tsc --noEmit
backend/venv/bin/python -m pytest backend/tests/test_push_privacy.py backend/tests/test_medication_log_agenda_writeback.py backend/tests/test_agenda_bid_multidose.py -q --no-cov
git diff --check
```

- Backend 文案随标准 backend deploy 发布；Mobile TS 通过 production OTA 发布，不需要新增原生模块。
- 最终 G6 必须使用真实 iPhone + Apple Watch：锁屏提醒出现、腕上点击“服用”、数据库/今日用药显示同一时间槽已服。
- OTA 回滚可恢复旧客户端行为；服务端幂等写入和手机内手工打卡始终保留。

## 9. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-16 | Initial implementation | 让腕上明确确认直接形成系统依从事实，并补足 terminated-app 可靠性 |
| 2026-07-16 | Safety hardening | occurrence identity fail-closed、失败反馈与重试、跨用户隔离、本地重复通知取消直写动作 |
