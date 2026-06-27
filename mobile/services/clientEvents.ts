import api from './api';

export type ClientEventName =
  // 上一季 ship 的 3 个事件 (2026-05-01)
  | 'reasoning_sheet_opened'
  | 'journal_timeline_entered'
  | 'specialist_scorecard_entered'
  // Phase 0.4 (2026-05-04) — 5 种核心事件让看板看得见用户操作
  | 'home_chip_clicked'           // 首页 chip 点击 (TrustHero / SpecialistChipRow)
  | 'action_card_executed'        // ActionCard 执行/完成按钮
  | 'push_notification_opened'    // 从推送进 app (deep_link 路由后 emit)
  | 'chat_message_sent'           // 用户发送对话 (chat / voice 入口)
  | 'chat_runtime_skill_completed' // Chat 内确定性 runtime skill 完成
  | 'quick_record_logged'         // 快速记录 (BP / 体重 / 用药 / 喝水) 提交
  // Phase 4 (2026-05-29) — cold start 观测
  | 'home_cold_start_perf'        // 首页 critical query 全部就绪的耗时分布
  // Phase 5 (2026-05-29) — starter chip CTR (调权从拍脑袋变成有据)
  | 'starter_chips_shown'         // 新对话空状态 chips 曝光 (CTR 分母)
  | 'starter_chip_clicked'        // 新对话 chip 点击 (CTR 分子)
  // Watch leverage-action loop (2026-06-16)
  | 'watch_action_shown'
  | 'watch_action_completed'
  | 'watch_action_snoozed'
  | 'watch_action_skipped'
  | 'watch_action_failed'
  | 'agenda_action_failed'
  // N-of-1 闭环北极星 (2026-06-17) — 已验证闭环数
  | 'verified_loop'               // meta: { cycle_id, verdict_count, total } 复查产出 ≥1 非 pending 裁决
  // Reva Daily Artifact (2026-06-27) — 首页健康运行时闭环
  | 'daily_artifact_impression'
  | 'daily_artifact_accepted'
  | 'daily_artifact_completed'
  | 'daily_artifact_skipped'
  // Phase 1C — first-run demo path, must stay isolated from real PHI writes.
  | 'demo_on_ramp_opened';

/**
 * 发一条 UI 埋点事件. 失败静默 — 埋点不该影响用户流程.
 * 后端 /client-events 把事件写入 client_events 表, 观察期看板用来算行为率.
 *
 * meta 约定 (各事件):
 * - home_chip_clicked: { chip: 'trust_hero' | 'specialist', target?: string }
 * - action_card_executed: { card_id: number, action: 'execute' | 'complete' | 'reminder' }
 * - push_notification_opened: { kind?: string, deep_link?: string }
 * - chat_message_sent: { source: 'chat' | 'voice' | 'siri', has_image: boolean }
 * - chat_runtime_skill_completed: { skill_id: string, card_type: string }
 * - quick_record_logged: { kind: 'bp' | 'weight' | 'water' | 'medication' | 'supplement' | 'mood' | ... }
 * - starter_chips_shown: { keys: string[], source: 'chat' }
 * - starter_chip_clicked: { key: string, priority: number, position: number, source: 'chat' }
 * - watch_action_*: { action_id: string, kind: string, priority_tier?: 'P0'|'P1'|'P2'|'P3'|'P4', reason?: string }
 * - agenda_action_failed: { reason: string, object_type?: string, object_id?: unknown, status?: string }
 * - daily_artifact_*: { artifact_id, week_index, top_action_source, top_action_title, skip_reason? }
 * - demo_on_ramp_opened: { mode: 'demo', estimated_minutes: number }
 */
export async function emitClientEvent(
  name: ClientEventName,
  meta?: Record<string, unknown>,
): Promise<void> {
  try {
    await api.post('/client-events', { event_name: name, meta });
  } catch {
    // swallow — 埋点不该影响 UI
  }
}
