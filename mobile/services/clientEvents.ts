import api from './api';

export type ClientEventName =
  | 'reasoning_sheet_opened'
  | 'journal_timeline_entered'
  | 'specialist_scorecard_entered';

/**
 * 发一条 UI 埋点事件. 失败静默 — 埋点不该影响用户流程.
 * 后端 (Task 9) 会把事件写入 client_events 表, 观察期看板用来算行为率.
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
