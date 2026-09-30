import api from './api';
import { behaviorLoopActionToEventType } from './behaviorLoopReminders';
import { emitClientEvent } from './clientEvents';
import { recordDailyPlanActionEvent } from './dailyPlan';

/**
 * OPEN_LOOP / BEHAVIOR_LOOP 通知的后台按钮动作(手表镜像可点)。
 *
 * 失败在 listener 边界记录(console.warn + watch_action_failed),不抛;
 * 日志只记 error.message(axios error 对象带含 action_key 的 URL),
 * 遥测不回显 action_key —— 它可能回退为 `{domain}.{行动标题}` 原文。
 */

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const OPEN_LOOP_ACTIONS = {
  DONE: 'done',
  SNOOZE_7D: 'snooze_7d',
  NOT_INTERESTED: 'not_interested',
} as const;

// Open-Loop Manager 的 3 个 action → POST /open-loop/{history_id}/feedback
// history_id 由后端预写 OpenLoopHistory 时生成, 塞进 APNs data.
export async function recordOpenLoopFeedback(
  actionId: keyof typeof OPEN_LOOP_ACTIONS,
  data?: Record<string, any>,
): Promise<void> {
  const historyId = Number(data?.history_id);
  if (!Number.isInteger(historyId) || historyId <= 0) {
    console.warn('[notificationLoopActions] invalid history_id in open-loop payload');
    await emitClientEvent('watch_action_failed', {
      reason: 'invalid_history_id',
      kind: 'open_loop',
      action: actionId,
    });
    return;
  }
  try {
    await api.post(`/open-loop/${historyId}/feedback`, { action: OPEN_LOOP_ACTIONS[actionId] });
  } catch (error) {
    console.warn('[notificationLoopActions] open-loop feedback failed', errorMessage(error));
    await emitClientEvent('watch_action_failed', {
      reason: 'request_failed',
      kind: 'open_loop',
      action: actionId,
      history_id: historyId,
      error: errorMessage(error),
    });
  }
}

// 行为闭环「今天最重要一件事」的 3 个 action.
// 完成 → completed event; 跳过 → skipped event; 稍后 → 不记录(行动保持待办, 下次再提醒)。
// 走现成 POST /daily-plan/actions/{action_key}/events (同 HomeCommandCard 的完成路径)。
export async function recordBehaviorLoopAction(
  actionId: 'LOOP_DONE' | 'LOOP_LATER' | 'LOOP_SKIP',
  data?: Record<string, any>,
): Promise<void> {
  const eventType = behaviorLoopActionToEventType(actionId);
  if (!eventType) return; // 稍后: 不打卡, 不改状态

  const actionKey = data?.action_key;
  if (typeof actionKey !== 'string' || !actionKey) {
    console.warn('[notificationLoopActions] missing action_key in behavior-loop payload');
    await emitClientEvent('watch_action_failed', {
      reason: 'invalid_action_key',
      kind: 'behavior_loop',
      action: actionId,
    });
    return;
  }
  try {
    await recordDailyPlanActionEvent(actionKey, {
      event_type: eventType,
      payload: { source: 'wrist_notification' },
    });
  } catch (error) {
    console.warn('[notificationLoopActions] behavior-loop action failed', errorMessage(error));
    await emitClientEvent('watch_action_failed', {
      reason: 'request_failed',
      kind: 'behavior_loop',
      action: actionId,
      error: errorMessage(error),
    });
  }
}
