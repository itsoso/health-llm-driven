import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import { bindIOSToken } from '../services/notifications';
import { emitClientEvent } from '../services/clientEvents';
import { resolveNotificationRoute } from '../services/notificationRoutes';
import { queryClient } from '../applib/queryClient';
import { completeAgendaItem } from '../services/agenda';

const SILENT_SCREENS = new Set(['home']);

Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const data = notification.request.content.data as Record<string, any> | undefined;
    const screen = data?.screen as string | undefined;
    const isSilent = SILENT_SCREENS.has(screen ?? 'home');
    return {
      shouldShowAlert: !isSilent,
      shouldShowBanner: !isSilent,
      shouldShowList: true,
      shouldPlaySound: !isSilent,
      shouldSetBadge: true,
    };
  },
});

type NotificationTapCallback = (
  notification: Notifications.Notification,
) => void;

let _onForeground: ((n: Notifications.Notification) => void) | null = null;

export function setOnForegroundNotification(
  cb: ((n: Notifications.Notification) => void) | null,
) {
  _onForeground = cb;
}

export function useNotifications(isAuthenticated: boolean) {
  const receivedSub = useRef<Notifications.EventSubscription | null>(null);
  const responseSub = useRef<Notifications.EventSubscription | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    registerForPush();
    registerNotificationCategories();

    receivedSub.current = Notifications.addNotificationReceivedListener(
      (notification) => {
        _onForeground?.(notification);
      },
    );

    responseSub.current = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        handleNotificationResponse(response);
      },
    );

    return () => {
      receivedSub.current?.remove();
      responseSub.current?.remove();
    };
  }, [isAuthenticated]);
}

async function registerForPush() {
  if (!Device.isDevice) return;
  if (Platform.OS !== 'ios') return;

  const { status: existing } = await Notifications.getPermissionsAsync();
  let finalStatus = existing;

  if (existing !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== 'granted') return;

  try {
    const token = await Notifications.getDevicePushTokenAsync();
    // 上报当前 bundle (variant 后 dev-client 是 .dev, 正式包 .health),
    // 后端用它做 apns-topic, 否则 APNs 返 DeviceTokenNotForTopic
    const bundleId = Constants.expoConfig?.ios?.bundleIdentifier;
    await bindIOSToken(token.data as string, bundleId || undefined);
  } catch {
    // simulator or token error — silently ignore
  }
}

async function registerNotificationCategories() {
  if (Platform.OS !== 'ios') return;
  await Notifications.setNotificationCategoryAsync('SUPPLEMENT_REMINDER', [
    { identifier: 'TAKEN', buttonTitle: '已服用', options: { opensAppToForeground: false } },
    { identifier: 'SKIP', buttonTitle: '跳过', options: { opensAppToForeground: false } },
  ]);
  await Notifications.setNotificationCategoryAsync('MEDICATION_REMINDER', [
    { identifier: 'TAKEN', buttonTitle: '已服用', options: { opensAppToForeground: false } },
    { identifier: 'SKIP', buttonTitle: '跳过', options: { opensAppToForeground: false } },
  ]);
  // Open-Loop Manager (主动循环推送): 3 actions 无需打开 app
  await Notifications.setNotificationCategoryAsync('OPEN_LOOP', [
    { identifier: 'DONE', buttonTitle: '已处理', options: { opensAppToForeground: false } },
    { identifier: 'SNOOZE_7D', buttonTitle: '暂停 7 天', options: { opensAppToForeground: false } },
    { identifier: 'NOT_INTERESTED', buttonTitle: '不感兴趣', options: { opensAppToForeground: false, isDestructive: true } },
  ]);
  // 行为闭环「今天最重要一件事」: 完成 / 稍后 / 跳过, 后台处理无需开 app.
  // 这条通知会自动镜像到 Apple Watch, 表上直接点按钮。
  await Notifications.setNotificationCategoryAsync('BEHAVIOR_LOOP', [
    { identifier: 'LOOP_DONE', buttonTitle: '完成', options: { opensAppToForeground: false } },
    { identifier: 'LOOP_LATER', buttonTitle: '稍后', options: { opensAppToForeground: false } },
    { identifier: 'LOOP_SKIP', buttonTitle: '跳过', options: { opensAppToForeground: false } },
  ]);
  // 干预周期提醒: 唯一动作「查看进展」(deep link 到周期屏, 需打开 app)。
  await Notifications.setNotificationCategoryAsync('INTERVENTION_CYCLE', [
    { identifier: 'VIEW_PROGRESS', buttonTitle: '查看进展', options: { opensAppToForeground: true } },
  ]);
  // 统一议程提醒(用药/补剂/协议到点): 完成 / 跳过, 后台经 /agenda/complete 写依从事实,
  // 无需打开 app。默认点按通知体仍走 deep_link(resolveNotificationRoute)。
  await Notifications.setNotificationCategoryAsync('AGENDA_ACTION', [
    { identifier: 'COMPLETE', buttonTitle: '完成', options: { opensAppToForeground: false } },
    { identifier: 'SKIP', buttonTitle: '跳过', options: { opensAppToForeground: false } },
  ]);
}

function handleNotificationResponse(response: Notifications.NotificationResponse) {
  const notification = response.notification;
  const actionId = response.actionIdentifier;
  const data = notification.request.content.data as Record<string, any> | undefined;

  // AGENDA_ACTION 的两颗按钮 COMPLETE / SKIP → 统一议程闭环完成/跳过。
  // 注意 'SKIP' 与 supplement/medication 旧 quick-action 共用同一 identifier,
  // 所以这里按 data.category / complete_ref 区分(AGENDA_ACTION 才有 complete_ref),
  // 不能只看 actionId, 否则会偷走旧 quick-action 的 SKIP。
  if (
    (actionId === 'COMPLETE' || actionId === 'SKIP') &&
    (data?.category === 'AGENDA_ACTION' || data?.complete_ref)
  ) {
    handleAgendaAction(actionId === 'COMPLETE' ? 'done' : 'skipped', data);
    return;
  }

  // Handle actionable notification buttons (background actions)
  if (actionId === 'TAKEN' || actionId === 'SKIP') {
    handleQuickAction(actionId, data);
    return;
  }
  if (actionId === 'DONE' || actionId === 'SNOOZE_7D' || actionId === 'NOT_INTERESTED') {
    handleOpenLoopAction(actionId, data);
    return;
  }
  if (actionId === 'LOOP_DONE' || actionId === 'LOOP_LATER' || actionId === 'LOOP_SKIP') {
    handleBehaviorLoopAction(actionId, data);
    return;
  }
  if (actionId === 'VIEW_PROGRESS') {
    const link = resolveNotificationRoute(data) ?? '/intervention-cycle';
    try { router.push(link as any); } catch { router.push('/(tabs)' as any); }
    return;
  }

  // Phase 0.4: 用户从推送进 app (default tap action) — emit 看板能算 push CTR.
  // Background actions 不算 (那是按钮回调, 没进 app).
  emitClientEvent('push_notification_opened', {
    kind: data?.kind ?? data?.type ?? 'unknown',
    deep_link: data?.deep_link ?? data?.deeplink ?? null,
  });

  // Handle tap-to-open routing.
  // resolveNotificationRoute centralises both forms (plain expo-router path + custom-scheme URL)
  // and the legacy data.screen enum; same helper backs the history feed (notification-history.tsx).
  // Always fall back to home on any miss / bad link — never crash on a user tap.
  const route = resolveNotificationRoute(data);
  try {
    router.push((route ?? '/(tabs)') as any);
  } catch {
    router.push('/(tabs)' as any);
  }
}

// 统一议程闭环: AGENDA_ACTION 通知的「完成 / 跳过」后台动作。
// 读 data.complete_ref ({object_type, object_id}) → POST /agenda/complete(显式录依从,
// 唯一一次写;不 deep-link 进任何自动写屏)→ invalidate 首页两个 query key,让该项「熄灭」。
// 失败在 LISTENER 边界吞掉(fire-and-forget 通知动作的正确姿势),但会先 log,
// 与既有后台 handler 一致(用户可回 app 再操作)。
export async function handleAgendaAction(
  status: 'done' | 'skipped',
  data?: Record<string, any>,
) {
  const ref = data?.complete_ref as
    | { object_type?: string; object_id?: number | string }
    | undefined;
  if (!ref?.object_type || ref.object_id == null) return;

  try {
    await completeAgendaItem(
      { object_type: ref.object_type, object_id: ref.object_id },
      'protocol',
      undefined,
      { status },
    );
    // 首页时间线 + 议程缓存失效 → 已完成/已跳过的项从列表里消失。
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['timeline', 'today'] }),
      queryClient.invalidateQueries({ queryKey: ['agenda', 'today'] }),
    ]);
  } catch (err) {
    // Background action failed — log at the listener boundary, user can complete in-app later.
    console.warn('[useNotifications] agenda action failed', err);
  }
}

async function handleQuickAction(action: string, data?: Record<string, any>) {
  if (!data) return;
  try {
    const { default: api } = await import('../services/api');
    const type = data.reminder_type; // 'supplement' | 'medication'
    if (type === 'supplement' && data.supplement_id) {
      await api.post('/supplements/me/checkin', {
        supplement_id: data.supplement_id,
        action: action === 'TAKEN' ? 'take' : 'skip',
      });
    } else if (type === 'medication' && data.medication_id) {
      await api.post('/medication/logs', {
        medication_id: data.medication_id,
        status: action === 'TAKEN' ? 'taken' : 'skipped',
      });
    }
  } catch {
    // Background action failed silently — user can check in the app later
  }
}

// Open-Loop Manager 的 3 个 action → POST /open-loop/{history_id}/feedback
// history_id 由后端预写 OpenLoopHistory 时生成, 塞进 APNs data.
async function handleOpenLoopAction(
  actionId: 'DONE' | 'SNOOZE_7D' | 'NOT_INTERESTED',
  data?: Record<string, any>,
) {
  if (!data?.history_id) return;
  const historyId = Number(data.history_id);
  if (!historyId || isNaN(historyId)) return;

  const actionMap: Record<string, string> = {
    DONE: 'done',
    SNOOZE_7D: 'snooze_7d',
    NOT_INTERESTED: 'not_interested',
  };
  const action = actionMap[actionId];
  if (!action) return;

  try {
    const { default: api } = await import('../services/api');
    await api.post(`/open-loop/${historyId}/feedback`, { action });
  } catch {
    // Background feedback failed silently — server-side dedup still applies
  }
}

// 行为闭环「今天最重要一件事」的 3 个 action.
// 完成 → completed event; 跳过 → skipped event; 稍后 → 不记录(行动保持待办, 下次再提醒)。
// 走现成 POST /daily-plan/actions/{action_key}/events (同 HomeCommandCard 的完成路径)。
async function handleBehaviorLoopAction(
  actionId: 'LOOP_DONE' | 'LOOP_LATER' | 'LOOP_SKIP',
  data?: Record<string, any>,
) {
  const actionKey = data?.action_key as string | undefined;
  if (!actionKey) return;

  const { behaviorLoopActionToEventType } = await import('../services/behaviorLoopReminders');
  const eventType = behaviorLoopActionToEventType(actionId);
  if (!eventType) return; // 稍后: 不打卡, 不改状态

  try {
    const { recordDailyPlanActionEvent } = await import('../services/dailyPlan');
    await recordDailyPlanActionEvent(actionKey, {
      event_type: eventType,
      payload: { source: 'wrist_notification' },
    });
  } catch {
    // Background action failed silently — user can complete in the app later
  }
}
