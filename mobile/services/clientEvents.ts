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
  | 'quick_record_logged'         // 快速记录 (BP / 体重 / 用药 / 喝水) 提交
  // Phase 4 (2026-05-29) — cold start 观测
  | 'home_cold_start_perf'        // 首页 critical query 全部就绪的耗时分布
  // Phase 5 (2026-05-29) — starter chip CTR (调权从拍脑袋变成有据)
  | 'starter_chips_shown'         // 新对话空状态 chips 曝光 (CTR 分母)
  | 'starter_chip_clicked';       // 新对话 chip 点击 (CTR 分子)

/**
 * 发一条 UI 埋点事件. 失败静默 — 埋点不该影响用户流程.
 * 后端 /client-events 把事件写入 client_events 表, 观察期看板用来算行为率.
 *
 * meta 约定 (各事件):
 * - home_chip_clicked: { chip: 'trust_hero' | 'specialist', target?: string }
 * - action_card_executed: { card_id: number, action: 'execute' | 'complete' | 'reminder' }
 * - push_notification_opened: { kind?: string, deep_link?: string }
 * - chat_message_sent: { source: 'chat' | 'voice' | 'siri', has_image: boolean }
 * - quick_record_logged: { kind: 'bp' | 'weight' | 'water' | 'medication' | 'supplement' | 'mood' | ... }
 * - starter_chips_shown: { keys: string[], source: 'chat' }
 * - starter_chip_clicked: { key: string, priority: number, position: number, source: 'chat' }
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
