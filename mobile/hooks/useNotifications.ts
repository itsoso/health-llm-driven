import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { router } from 'expo-router';
import { bindIOSToken } from '../services/notifications';

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
    await bindIOSToken(token.data as string);
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
}

function handleNotificationResponse(response: Notifications.NotificationResponse) {
  const notification = response.notification;
  const actionId = response.actionIdentifier;
  const data = notification.request.content.data as Record<string, any> | undefined;

  // Handle actionable notification buttons (background actions)
  if (actionId === 'TAKEN' || actionId === 'SKIP') {
    handleQuickAction(actionId, data);
    return;
  }
  if (actionId === 'DONE' || actionId === 'SNOOZE_7D' || actionId === 'NOT_INTERESTED') {
    handleOpenLoopAction(actionId, data);
    return;
  }

  // Handle tap-to-open routing
  // Priority: data.deep_link (arbitrary path + query) > data.screen (legacy predefined)
  const deepLink = data?.deep_link as string | undefined;
  if (deepLink) {
    try { router.push(deepLink as any); } catch { router.push('/(tabs)' as any); }
    return;
  }

  const screen = data?.screen as string | undefined;
  switch (screen) {
    case 'alerts':
      router.push('/(tabs)/alerts' as any);
      break;
    case 'record':
      router.push('/(tabs)/record' as any);
      break;
    case 'chat':
      router.push('/(tabs)/chat' as any);
      break;
    case 'diet':
      router.push('/diet' as any);
      break;
    case 'sleep':
      router.push('/sleep' as any);
      break;
    case 'home':
    default:
      router.push('/(tabs)' as any);
      break;
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
