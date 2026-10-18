# Feature Spec: 主动开启的当天 GPS 行程

> Status: accepted for implementation
> Owner: Reva
> Updated: 2026-10-18
> Related PRD: ../prd/2026-10-18-daily-gps-journey.md

## Decision and admission

用户主动开启当天采集，提供路线、停留和移动时间复盘，解释出行对日常行动时间安排的影响；不从位置推断健康、宗教、职业或就诊事实。

```yaml
RequirementAdmission:
  request: 实时获取本人 GPS，记录和分析一天的行程；用户确认按建议方案实现
  classification: new_product_behavior
  first_user_fit: 减少日常行为记录负担，复盘通勤与行动时间安排
  core_loop_step: execution evidence -> review -> next plan
  first_class_objects: [ExecutionEvent, HealthTwin]
  target_surface: Mobile
  source_of_truth: authenticated backend sessions and device GPS observations
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: device GPS with timestamp and accuracy; user corrections separate
  claim_hedging: hedged
  verification_window: one local day
  success_metric: explicit start through end and owned review; visible gaps; verified deletion
  added_user_burden: start once per day and optional corrections
  burden_justification: sensitive collection requires bounded explicit permission
  non_goals: covert tracking, medical inference, location sharing, autonomous health writes
  smallest_end_to_end_slice: start -> collect -> pause/resume/end -> owned daily review -> delete
  stale_surface_to_remove_or_archive: preserve existing city-annotation journey; link to daily GPS
  spec_required: yes
```

## User flow and surface contract

Mobile 的“这一路”增加“记录今天行程”入口，开启前显示精确位置用途、后台定位、私有云保存和保留期限。默认关闭；保留期限可选 1 或 7 天，默认 7 天。用户点开启后请求系统权限并创建当天 session，显示采集中/暂停/未同步/中断状态。暂停和结束先本地停采集，再同步状态；离线操作不得显示云端已确认。跨天不自动开启新 session。查看本人日期列表、路线分段、停留及统计，允许修改停留名称或移动方式；删除清除原始点、修正和派生信息。

Backend 是 session 状态、所有权和删除的真源，所有 endpoint 要认证；GPS 不进入 LLM，不进入公共分享，不触发既有健康执行写入。首版复盘为确定性观测汇总，交通方式只标估计/用户确认。Watch/Web 不新增采集。

## State and privacy contract

- Session active -> paused -> active / ended；ended 不可恢复。默认截止启动时区的当天午夜，最长 24 小时，时区变化不延长。
- 每用户最多一条未结束 session，绑定启动设备 client_id。停止/删除可以从其他本人设备发起，采集批次只接受绑定设备且合法采集区间。
- GPS payload 与用户修正字段必须严格加密，解密失败不返回明文；日志、错误、审计只记录 opaque session ID/计数/状态。
- 客户端账号切换/登出/删除账号同步停止采集并隔离清除本地队列；延迟响应和批次不得借用新的账号 token。
- 本地离线队列采用系统安全存储，条目有界，保留期限与 session 一致。容量不足或无法持久化必须停止/显示中断，不能标成功。
- 所有客户端字段重新验证，禁止 NaN/Inf、非法坐标、未来时间、超出 session/day 或暂停区间的时间、过大批次。重复上传幂等，重复 ID 内容不同拒绝。
- 1/7 天到期后读取不可见；定时物理清理有执行证据，删除后不能因重试/排队复活。
- 地图不把跨暂停、定位缺口或低精度点连成一条路线。停留须有连续足够观测，末尾点不自动外推到当前时间。
- 里程为有效 GPS 相邻段估算；不据速度断言具体交通方式，不把静止当睡眠/久坐，不把地点推断成到访某机构。
- iOS 后台交付非连续保证；权限撤销、强退、系统限制、离线或队列溢出均可缺失，界面诚实展示。

## API contract (v1, /daily-journeys)

All IDs opaque UUID strings; authenticated user supplied exclusively by auth dependency. Timestamps RFC3339 timezone-aware UTC; finite numeric coordinates. Responses no-store.

- POST /sessions: {request_id, client_id, timezone, retention_days:1|7, consent:true}. Idempotent request_id per owner; local date and expires_at derived server-side. Returns Session.
- GET /sessions?date=YYYY-MM-DD: {items:Session[]} only owner/nonexpired.
- GET /sessions/{id}: Session. Session fields id, client_id, local_date, timezone, status(active|paused|ended), version, segment, started_at, deadline_at, ended_at|null, expires_at, retention_days, point_count.
- POST /sessions/{id}/state: {action:pause|resume|end, expected_version, client_id}. CAS; resume requires bound client; paused/ended with no concurrent state change idempotent. Server transitions anchor sample windows; local pause/end immediately stop capture, retain valid encrypted offline samples and preserve pending deletion over day-boundary transitions. Resume/new start must first finish prior pending synchronization.
- POST /sessions/{id}/points: {client_id, segment, points:[{id, recorded_at, latitude, longitude, accuracy_m, speed_mps:null|number}]}. Max 100 per batch, max 10000 per session. Returns {accepted, duplicate, session:Session}. Current segment only; late delivery of observations captured before server-owned pause/end/deadline is accepted until retention expiry, even when paused/ended. Immutable duplicate content comparison. Samples outside current segment or more than 120 seconds future rejected; expired rows never revived.
- GET /sessions/{id}/review: {session:Session, points:[...], segments:[...], stops:[...], gaps:[...], summary:{...}}. Coordinates only in authenticated review; display strings use canonical format_display_number. Exact response schema completed by backend before UI integration.
- PATCH /sessions/{id}/annotations: {expected_version, annotations:[{target_id,label?,mode?:unknown|walking|cycling|vehicle}]} bound to deterministic review target IDs; encrypted; user corrections separate from estimates.
- DELETE /sessions/{id}: idempotent 204 for owner/missing. Remove all points/annotations; delayed uploads cannot recreate session. Existing session lookup for start idempotency cannot recreate deleted request_id (retain only opaque owner/request/session tombstones until account deletion, without location, dates or device metadata).

## Acceptance and verification

RED before implementation; SQLite API/state tests plus real PostgreSQL migration, uniqueness, concurrent CAS, duplicate samples, deletion, ciphertext and retention tests. Mobile permission denied, background registration failure, force-stop lifecycle, account switch during await, offline queue limit, cross-day, state conflicts, coordinate rendering/segment boundaries tests. Verify generated native plist and native runtime identity, tsc/jest, full exact-SHA CI, independent G4 review. Simulator can validate UI and synthetic locations only; real GPS accuracy, background duration, energy and system behavior remain explicitly unverified without device acceptance.

## Rollout

Additive managed PostgreSQL migration plus SQLite mirror; old city annotations unchanged. Backend before new signed iOS package. Native permission changes require new runtime identity/build and cannot be OTA into previous binary. Default no collection, user enables in app. No backups or automatic rollback under current policy; failed deployment retains locks/receipts and follows governed forward repair. No new store publication without its release gates. No final shipped claim until G5/G6 evidence.

## G2 feasibility constraints
午夜为数据采集截止（有效旧点可在保留期限内补传）；系统休眠时不能承诺硬件定位任务恰好午夜停机，下一次回调/前台必须停任务。系统钥匙串分块使用可锁屏访问的设备专属等级，账号切换和安装身份变更使旧任务失效。当前 App Store 原生权限闸必须用明确候选能力允许规则评审，不删除其他背景能力限制。实际硬件/电量验收未完成时不宣称 G6 或商店送审通过。

开启后台定位时，仅针对当前已登录凭证，在同一认证存储串行队列中验证账号与退出屏障并开启设备首次解锁后的本机访问；结束/删除及待同步队列完成后恢复仅解锁可读。默认登录存储等级不变，失效操作不能扩大凭证访问。


## Deterministic review estimates
Only continuous valid route groups contribute distance or transport estimation; gaps are never bridged. Estimates require at least 5 observations, 120 seconds, 100 metres, all accuracy at most 50 metres and at least 80% moving adjacent legs. Walking is a coarse estimate only when median speed is 0.5–1.8 m/s and every leg is at most 2.5 m/s. Vehicle is a coarse estimate when median speed is at least 12 m/s, lower-quartile speed at least 8 m/s and every leg at most 60 m/s. These are heuristic assumptions, not identified transport facts. Short, stationary, poor-accuracy or ambiguous groups remain unknown; running/cycling overlap is not guessed. Users can correct any segment to unknown/walking/cycling/vehicle; corrections retain user provenance. Stops require at least three continuous observations within 60 metres of the first and at least five observed minutes; no end-point extrapolation. Leading/trailing unobserved intervals remain visible, including a session with no GPS points.
