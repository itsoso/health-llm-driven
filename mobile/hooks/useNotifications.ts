import { useEffect, useRef } from 'react';
import { AppState, Platform } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import { bindIOSToken } from '../services/notifications';
import { emitClientEvent } from '../services/clientEvents';
import { resolveNotificationRoute } from '../services/notificationRoutes';
import { queryClient } from '../applib/queryClient';
import { completeAgendaItem } from '../services/agenda';
import { logMedication } from '../services/medications';
import {
  enqueuePendingMedicationAction,
  listPendingMedicationActions,
  removePendingMedicationAction,
  type PendingMedicationAction,
  type PendingMedicationActionData,
} from '../services/pendingMedicationActions';
import { useToast } from './useToast';

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

let _onForeground: ((n: Notifications.Notification) => void) | null = null;

export function setOnForegroundNotification(
  cb: ((n: Notifications.Notification) => void) | null,
) {
  _onForeground = cb;
}

export function useNotifications(isAuthenticated: boolean) {
  const { show } = useToast();
  const receivedSub = useRef<Notifications.EventSubscription | null>(null);
  const responseSub = useRef<Notifications.EventSubscription | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    void syncGrantedPushRegistration();
    void registerNotificationCategories().catch((error) => {
      console.warn('[useNotifications] failed to register notification categories', error);
    });
    const feedback: NotificationActionFeedback = {
      onMedicationSuccess: (action) => show(action === 'TAKEN' ? '已记录服用' : '已记录跳过', 'success'),
      onMedicationFailure: () => show('服用记录未保存，联网后会自动重试', 'error'),
    };
    const retryPendingAction = () => {
      void (async () => {
        const drained = await drainPendingMedicationActions(feedback);
        if (drained) await consumeLastNotificationResponse(feedback);
      })();
    };
    retryPendingAction();

    receivedSub.current = Notifications.addNotificationReceivedListener(
      (notification) => {
        _onForeground?.(notification);
      },
    );

    responseSub.current = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        void consumeNotificationResponse(response, feedback);
      },
    );

    const unsubscribeNetwork = NetInfo.addEventListener((state) => {
      if (state.isConnected) retryPendingAction();
    });
    const appStateSub = AppState.addEventListener('change', (state) => {
      if (state === 'active') retryPendingAction();
    });

    return () => {
      receivedSub.current?.remove();
      responseSub.current?.remove();
      unsubscribeNetwork();
      appStateSub.remove();
    };
  }, [isAuthenticated, show]);
}

export type PushRegistrationResult = {
  status: string;
  bound: boolean;
};

async function bindCurrentIOSToken(): Promise<PushRegistrationResult> {
  try {
    const token = await Notifications.getDevicePushTokenAsync();
    // 上报当前 bundle (variant 后 dev-client 是 .dev, 正式包 .health),
    // 后端用它做 apns-topic, 否则 APNs 返 DeviceTokenNotForTopic
    const bundleId = Constants.expoConfig?.ios?.bundleIdentifier;
    await bindIOSToken(token.data as string, bundleId || undefined);
    return { status: 'granted', bound: true };
  } catch (error) {
    console.warn('[useNotifications] failed to bind iOS push token', error);
    return { status: 'granted', bound: false };
  }
}

export async function syncGrantedPushRegistration(): Promise<PushRegistrationResult> {
  if (!Device.isDevice || Platform.OS !== 'ios') {
    return { status: 'unavailable', bound: false };
  }
  const { status } = await Notifications.getPermissionsAsync();
  if (status !== 'granted') return { status: 'not_granted', bound: false };
  return bindCurrentIOSToken();
}

export async function requestPushPermissionAndRegister(): Promise<PushRegistrationResult> {
  if (!Device.isDevice || Platform.OS !== 'ios') {
    return { status: 'unavailable', bound: false };
  }
  const current = await Notifications.getPermissionsAsync();
  const status = current.status === 'granted'
    ? 'granted'
    : (await Notifications.requestPermissionsAsync()).status;
  if (status !== 'granted') return { status, bound: false };
  return bindCurrentIOSToken();
}

export async function registerNotificationCategories() {
  if (Platform.OS !== 'ios') return;
  await Notifications.setNotificationCategoryAsync('SUPPLEMENT_REMINDER', [
    { identifier: 'TAKEN', buttonTitle: '已服用', options: { opensAppToForeground: false } },
    { identifier: 'SKIP', buttonTitle: '跳过', options: { opensAppToForeground: false } },
  ]);
  await Notifications.setNotificationCategoryAsync('MEDICATION_REMINDER', [
    // iOS 上 false 会在 App 被终止时直接丢失 response listener。服用是医疗级
    // 依从事实,必须唤醒进程并由冷启动补偿消费;Watch 镜像同一 category/action。
    { identifier: 'TAKEN', buttonTitle: '服用', options: { opensAppToForeground: true } },
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

const processedNotificationResponses = new Set<string>();
const inFlightNotificationResponses = new Map<string, Promise<boolean>>();
const MAX_PROCESSED_NOTIFICATION_RESPONSES = 128;

function markNotificationResponseProcessed(key: string) {
  processedNotificationResponses.add(key);
  if (processedNotificationResponses.size <= MAX_PROCESSED_NOTIFICATION_RESPONSES) return;
  const oldest = processedNotificationResponses.values().next().value;
  if (oldest) processedNotificationResponses.delete(oldest);
}

function notificationResponseKey(response: Notifications.NotificationResponse): string {
  const data = response.notification.request.content.data as Record<string, any> | undefined;
  if (data?.reminder_type === 'medication' && typeof data.rule_id === 'string') {
    return `${data.rule_id}:${response.actionIdentifier}`;
  }
  return `${response.notification.request.identifier}:${response.actionIdentifier}`;
}

interface NotificationActionFeedback {
  onMedicationSuccess?: (action: 'TAKEN' | 'SKIP') => void;
  onMedicationFailure?: () => void;
}

interface ConsumeNotificationResponseOptions {
  clearNativeResponse?: boolean;
}

function isMedicationActionResponse(response: Notifications.NotificationResponse): boolean {
  const data = response.notification.request.content.data as Record<string, any> | undefined;
  return data?.reminder_type === 'medication'
    && (response.actionIdentifier === 'TAKEN' || response.actionIdentifier === 'SKIP');
}

function pendingMedicationActionFromResponse(
  response: Notifications.NotificationResponse,
): Pick<PendingMedicationAction, 'action' | 'data'> | null {
  if (!isMedicationActionResponse(response)) return null;
  const source = response.notification.request.content.data as Record<string, any> | undefined;
  const medicationId = normalizeAgendaActionObjectId(source?.medication_id);
  const scheduledDate = normalizeMedicationReminderDate(source?.scheduled_date);
  const scheduledTime = normalizeMedicationReminderTime(source?.scheduled_time);
  const action = response.actionIdentifier as 'TAKEN' | 'SKIP';
  if (
    medicationId == null
    || !scheduledDate
    || !scheduledTime
    || source?.scheduled_timezone !== 'Asia/Shanghai'
    || source?.rule_id !== `medication_reminder.${medicationId}.${scheduledDate}.${scheduledTime}`
  ) return null;
  const data: PendingMedicationActionData = {
    reminder_type: 'medication',
    medication_id: medicationId,
    scheduled_date: scheduledDate,
    scheduled_time: scheduledTime,
    scheduled_timezone: 'Asia/Shanghai',
    rule_id: source.rule_id,
  };
  return { action, data };
}

function medicationFailureNotificationId(data?: Record<string, any>): string | null {
  if (typeof data?.rule_id !== 'string' || !data.rule_id.trim()) return null;
  return `watch-medication-action-failed-${data.rule_id}`;
}

async function dismissMedicationFailureNotification(data?: Record<string, any>) {
  const identifier = medicationFailureNotificationId(data);
  if (!identifier) return;
  try {
    await Notifications.dismissNotificationAsync(identifier);
  } catch (error) {
    console.warn('[useNotifications] failed to dismiss medication retry notice', error);
  }
}

async function showMedicationFailureNotification(data?: Record<string, any>) {
  const identifier = medicationFailureNotificationId(data);
  if (!identifier) return;
  try {
    await Notifications.scheduleNotificationAsync({
      identifier,
      content: {
        title: '用药打卡未保存',
        body: '网络恢复后会自动重试，请勿重复操作。',
        data: { kind: 'medication_action_retry' },
      },
      trigger: null,
    });
  } catch (error) {
    console.warn('[useNotifications] failed to show medication retry notice', error);
  }
}

async function processNotificationResponse(
  response: Notifications.NotificationResponse,
): Promise<boolean> {
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
    await handleAgendaAction(actionId === 'COMPLETE' ? 'done' : 'skipped', data);
    return true;
  }

  // Handle actionable notification buttons (background actions)
  if (actionId === 'TAKEN' || actionId === 'SKIP') {
    if (data?.reminder_type === 'medication') {
      return handleMedicationReminderAction(actionId, data);
    }
    await handleQuickAction(actionId, data);
    return true;
  }
  if (actionId === 'DONE' || actionId === 'SNOOZE_7D' || actionId === 'NOT_INTERESTED') {
    await handleOpenLoopAction(actionId, data);
    return true;
  }
  if (actionId === 'LOOP_DONE' || actionId === 'LOOP_LATER' || actionId === 'LOOP_SKIP') {
    await handleBehaviorLoopAction(actionId, data);
    return true;
  }
  if (actionId === 'VIEW_PROGRESS') {
    const link = resolveNotificationRoute(data) ?? '/intervention-cycle';
    try { router.push(link as any); } catch { router.push('/(tabs)' as any); }
    return true;
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
  return true;
}

export async function handleNotificationResponse(
  response: Notifications.NotificationResponse,
): Promise<boolean> {
  const key = notificationResponseKey(response);
  if (processedNotificationResponses.has(key)) return true;
  const existing = inFlightNotificationResponses.get(key);
  if (existing) return existing;

  const task = processNotificationResponse(response);
  inFlightNotificationResponses.set(key, task);
  try {
    const handled = await task;
    if (handled) markNotificationResponseProcessed(key);
    return handled;
  } finally {
    inFlightNotificationResponses.delete(key);
  }
}

export async function consumeNotificationResponse(
  response: Notifications.NotificationResponse,
  feedback?: NotificationActionFeedback,
  options: ConsumeNotificationResponseOptions = {},
): Promise<boolean> {
  const medicationAction = isMedicationActionResponse(response);
  const data = response.notification.request.content.data as Record<string, any> | undefined;
  const pendingInput = pendingMedicationActionFromResponse(response);
  let pendingKey: string | null = null;
  if (pendingInput) {
    try {
      pendingKey = (await enqueuePendingMedicationAction(pendingInput)).key;
    } catch (error) {
      console.warn('[useNotifications] failed to persist medication action', error);
      await emitClientEvent('watch_action_failed', {
        reason: 'retry_queue_failed',
        kind: 'medication',
        action: response.actionIdentifier,
        rule_id: pendingInput.data.rule_id,
      });
    }
  }
  try {
    const handled = await handleNotificationResponse(response);
    if (handled) {
      if (pendingKey) {
        try {
          await removePendingMedicationAction(pendingKey);
        } catch (error) {
          console.warn('[useNotifications] failed to clear persisted medication action', error);
        }
      }
      if (options.clearNativeResponse !== false) {
        await Notifications.clearLastNotificationResponseAsync();
      }
      if (medicationAction) {
        await dismissMedicationFailureNotification(data);
        feedback?.onMedicationSuccess?.(response.actionIdentifier as 'TAKEN' | 'SKIP');
      }
      return true;
    }
    if (medicationAction) feedback?.onMedicationFailure?.();
    return false;
  } catch (error) {
    console.warn('[useNotifications] notification action failed', error);
    if (medicationAction) feedback?.onMedicationFailure?.();
    return false;
  }
}

export async function consumeLastNotificationResponse(
  feedback?: NotificationActionFeedback,
): Promise<boolean | null> {
  try {
    const response = await Notifications.getLastNotificationResponseAsync();
    if (!response) return null;
    return consumeNotificationResponse(response, feedback);
  } catch (error) {
    console.warn('[useNotifications] cold-start notification action failed', error);
    return false;
  }
}

export async function drainPendingMedicationActions(
  feedback?: NotificationActionFeedback,
): Promise<boolean> {
  let pending: PendingMedicationAction[];
  try {
    pending = await listPendingMedicationActions();
  } catch (error) {
    console.warn('[useNotifications] failed to load persisted medication actions', error);
    return false;
  }
  for (const item of pending) {
    const response = {
      actionIdentifier: item.action,
      notification: {
        date: Date.parse(`${item.data.scheduled_date}T${item.data.scheduled_time}:00+08:00`),
        request: {
          identifier: item.key,
          content: { data: item.data },
        },
      },
    } as unknown as Notifications.NotificationResponse;
    const handled = await consumeNotificationResponse(response, feedback, {
      clearNativeResponse: false,
    });
    if (!handled) return false;
  }
  return true;
}

// 统一议程闭环: AGENDA_ACTION 通知的「完成 / 跳过」后台动作。
// 读 data.complete_ref ({object_type, object_id}) → POST /agenda/complete(显式录依从,
// 唯一一次写;不 deep-link 进任何自动写屏)→ invalidate 首页两个 query key,让该项「熄灭」。
// 失败在 LISTENER 边界吞掉(fire-and-forget 通知动作的正确姿势),但会先 log,
// 与既有后台 handler 一致(用户可回 app 再操作)。
function normalizeAgendaActionObjectId(raw: number | string): number | null {
  if (typeof raw === 'number' && Number.isInteger(raw)) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return Number(raw);
  return null;
}

export async function handleAgendaAction(
  status: 'done' | 'skipped',
  data?: Record<string, any>,
) {
  const ref = data?.complete_ref as
    | { object_type?: string; object_id?: number | string; slot?: string }
    | undefined;
  if (!ref?.object_type || ref.object_id == null) return;
  const objectId = normalizeAgendaActionObjectId(ref.object_id);
  if (objectId == null) {
    console.warn('[useNotifications] invalid agenda object_id', ref);
    await emitClientEvent('agenda_action_failed', {
      reason: 'invalid_object_id',
      object_type: ref.object_type,
      object_id: ref.object_id,
      status,
    });
    return;
  }

  try {
    await completeAgendaItem(
      // F5b:push complete_ref 带 slot 时(真多剂提醒)透传 → 该剂各自闭环;单剂省略。
      { object_type: ref.object_type, object_id: objectId, slot: ref.slot },
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
    await emitClientEvent('agenda_action_failed', {
      reason: 'request_failed',
      object_type: ref.object_type,
      object_id: objectId,
      status,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

async function handleQuickAction(action: string, data?: Record<string, any>) {
  if (!data) return;
  try {
    const { default: api } = await import('../services/api');
    if (data.reminder_type === 'supplement' && data.supplement_id) {
      await api.post('/supplements/me/checkin', {
        supplement_id: data.supplement_id,
        action: action === 'TAKEN' ? 'take' : 'skip',
      });
    }
  } catch {
    // Background action failed silently — user can check in the app later
  }
}

function normalizeMedicationReminderTime(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const match = raw.trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function normalizeMedicationReminderDate(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const match = raw.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) return null;
  return `${match[1]}-${match[2]}-${match[3]}`;
}

export async function handleMedicationReminderAction(
  action: 'TAKEN' | 'SKIP',
  data?: Record<string, any>,
): Promise<boolean> {
  const medicationId = normalizeAgendaActionObjectId(data?.medication_id);
  if (medicationId == null) {
    await emitClientEvent('watch_action_failed', {
      reason: 'invalid_medication_id',
      kind: 'medication',
      medication_id: data?.medication_id ?? null,
      action,
    });
    return false;
  }
  const takenDate = normalizeMedicationReminderDate(data?.scheduled_date);
  const takenTime = normalizeMedicationReminderTime(data?.scheduled_time);
  const timezone = data?.scheduled_timezone;
  const expectedRuleId = takenDate && takenTime
    ? `medication_reminder.${medicationId}.${takenDate}.${takenTime}`
    : null;
  if (
    !takenDate
    || !takenTime
    || timezone !== 'Asia/Shanghai'
    || data?.rule_id !== expectedRuleId
  ) {
    await emitClientEvent('watch_action_failed', {
      reason: 'invalid_medication_occurrence',
      kind: 'medication',
      medication_id: medicationId,
      action,
      scheduled_date: data?.scheduled_date ?? null,
      scheduled_time: data?.scheduled_time ?? null,
      scheduled_timezone: timezone ?? null,
    });
    return false;
  }
  const status = action === 'TAKEN' ? 'taken' : 'skipped';

  try {
    const result = await logMedication({
      medication_id: medicationId,
      taken_date: takenDate,
      taken_time: takenTime,
      status,
    });
    if (
      result.status !== status
      || result.medication_id !== medicationId
      || result.taken_date !== takenDate
      || result.taken_time !== takenTime
    ) {
      await emitClientEvent('watch_action_failed', {
        reason: 'response_mismatch',
        kind: 'medication',
        medication_id: medicationId,
        action,
        scheduled_date: takenDate,
        scheduled_time: takenTime,
        response_status: result.status,
      });
      await showMedicationFailureNotification(data);
      return false;
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['medications'] }),
      queryClient.invalidateQueries({ queryKey: ['medicationToday'] }),
      queryClient.invalidateQueries({ queryKey: ['timeline', 'today'] }),
      queryClient.invalidateQueries({ queryKey: ['agenda', 'today'] }),
    ]);
    await emitClientEvent('quick_record_logged', {
      kind: 'medication',
      status,
      scheduled_date: takenDate,
      scheduled_time: takenTime,
      source: 'watch_notification',
    });
    return true;
  } catch (error) {
    console.warn('[useNotifications] medication reminder action failed', error);
    await emitClientEvent('watch_action_failed', {
      reason: 'request_failed',
      action_id: `medication-${medicationId}-${takenTime}`,
      kind: 'medication',
      action,
      scheduled_date: takenDate,
      scheduled_time: takenTime,
      error: error instanceof Error ? error.message : String(error),
    });
    await showMedicationFailureNotification(data);
    return false;
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
