import { useEffect, useRef } from 'react';
import {
  scheduleMedicationReminders,
  todayItemsToSources,
} from '../services/medicationReminders';
import type { MedicationTodayItem } from '../services/medications';

/**
 * 按今日在服药品的 reminder_times 调度每日本地通知。
 * - items 变化 (药品列表 / 提醒时间增删) 时重排; 先 cancel 旧的再排新的。
 * - 用 reminder_times 的指纹去抖, 避免 dashboard 每次刷新(taken_count 变)都重排。
 * - 无通知权限时 scheduleMedicationReminders 内部静默跳过。
 */
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
      // 排程失败不影响 UI
    });
  }, [items, enabled]);
}
