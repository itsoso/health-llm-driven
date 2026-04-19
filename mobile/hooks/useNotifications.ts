import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { router } from 'expo-router';
import { bindIOSToken } from '@/services/notifications';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: false,
    shouldShowBanner: false,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
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

    receivedSub.current = Notifications.addNotificationReceivedListener(
      (notification) => {
        _onForeground?.(notification);
      },
    );

    responseSub.current = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        handleNotificationTap(response.notification);
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

function handleNotificationTap(notification: Notifications.Notification) {
  const data = notification.request.content.data as Record<string, any> | undefined;
  const screen = data?.screen as string | undefined;

  switch (screen) {
    case 'alerts':
      router.push('/(tabs)/alerts' as any);
      break;
    case 'record':
      router.push('/(tabs)/record' as any);
      break;
    case 'home':
    default:
      router.push('/(tabs)' as any);
      break;
  }
}
