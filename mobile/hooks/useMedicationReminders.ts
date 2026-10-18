import { useEffect, useRef } from 'react';
import {
  scheduleMedicationReminders,
  todayItemsToSources,
} from '../services/medicationReminders';
import type { MedicationTodayItem } from '../services/medications';

/** Dashboard fallback cleanup for retired local reminders; server owns delivery. */
export function useMedicationReminders(
  items: MedicationTodayItem[] | null | undefined,
  enabled: boolean,
) {
  const lastFingerprint = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (!items) return;

    // 指纹只看「会影响排程」的字段: medication_id + reminder_times
    const fingerprint = JSON.stringify(
      items.map((it) => [it.medication_id, it.reminder_times]),
    );
    if (fingerprint === lastFingerprint.current) return;
    lastFingerprint.current = fingerprint;

    scheduleMedicationReminders(todayItemsToSources(items)).catch(() => {
      lastFingerprint.current = null;
      console.warn('[medicationReminders] legacy cleanup failed; retry on refresh');
    });
  }, [items, enabled]);
}
