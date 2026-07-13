import * as Notifications from 'expo-notifications';

export const LOCAL_NOTIFICATION_MORNING_FLOOR_HOUR = 9;
export const LOCAL_NOTIFICATION_MORNING_FLOOR_MINUTE = 0;

export function applyLocalMorningFloorToDailyTime(
  hour: number,
  minute: number,
): { hour: number; minute: number; shifted: boolean } {
  const current = hour * 60 + minute;
  const floor = LOCAL_NOTIFICATION_MORNING_FLOOR_HOUR * 60
    + LOCAL_NOTIFICATION_MORNING_FLOOR_MINUTE;
  if (current >= floor) return { hour, minute, shifted: false };
  return {
    hour: LOCAL_NOTIFICATION_MORNING_FLOOR_HOUR,
    minute: LOCAL_NOTIFICATION_MORNING_FLOOR_MINUTE,
    shifted: true,
  };
}

export function formatHHMM(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

export function deferImmediateLocalNotificationUntilMorningFloor(
  now: Date,
): Notifications.NotificationTriggerInput {
  const floor = new Date(now);
  floor.setHours(
    LOCAL_NOTIFICATION_MORNING_FLOOR_HOUR,
    LOCAL_NOTIFICATION_MORNING_FLOOR_MINUTE,
    0,
    0,
  );
  if (now < floor) {
    return {
      type: Notifications.SchedulableTriggerInputTypes.DATE,
      date: floor,
    };
  }
  return null;
}
