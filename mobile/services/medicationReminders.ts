import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import type { MedicationTodayItem } from './medications';

export interface ReminderSource {
  id: number;
  name: string;
  dosage: string | null;
  reminder_times: string[] | null;
}
export function todayItemsToSources(items: MedicationTodayItem[]): ReminderSource[] {
  return items.map(it => ({ id: it.medication_id, name: it.name, dosage: it.dosage, reminder_times: it.reminder_times }));
}

/** Server owns medication delivery. Retire every legacy local copy, including races. */
export async function cancelMedicationReminders(): Promise<void> {
  if (Platform.OS !== 'ios') return;
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  for (const notification of scheduled) {
    if (notification.content?.data?.kind === 'medication_reminder') {
      await Notifications.cancelScheduledNotificationAsync(notification.identifier);
    }
  }
}

/** Compatibility for existing dashboard callers; never schedule local duplicates. */
export async function scheduleMedicationReminders(_meds: ReminderSource[]): Promise<number> {
  await cancelMedicationReminders();
  return 0;
}
