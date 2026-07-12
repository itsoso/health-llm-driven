import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import type { MedicationTodayItem } from './medications';

/** scheduler 接受的最小药品形状 — Medication 与 MedicationTodayItem 都满足 */
export interface ReminderSource {
  id: number;
  name: string;
  dosage: string | null;
  reminder_times: string[] | null;
}

/** 把 dashboard 的 today-items 归一成 scheduler 输入 (medication_id → id) */
export function todayItemsToSources(items: MedicationTodayItem[]): ReminderSource[] {
  return items.map((it) => ({
    id: it.medication_id,
    name: it.name,
    dosage: it.dosage,
    reminder_times: it.reminder_times,
  }));
}

// 用 content.data.kind 标记我们排的吃药通知, 重排前据此只 cancel 自己的,
// 不误删其它本地通知 (open-loop / 别的 reminder)。
const MED_REMINDER_KIND = 'medication_reminder';

interface ParsedReminder {
  medicationId: number;
  name: string;
  dosage: string | null;
  time: string; // "HH:MM"
  hour: number;
  minute: number;
}

/** 把在服药品列表 → 扁平的「每药×每时段」提醒条目。纯函数, 便于测试。 */
export function buildReminderEntries(meds: ReminderSource[]): ParsedReminder[] {
  const entries: ParsedReminder[] = [];
  for (const med of meds) {
    const times = med.reminder_times;
    if (!Array.isArray(times) || times.length === 0) continue;
    for (const raw of times) {
      const parsed = parseHHMM(raw);
      if (!parsed) continue;
      entries.push({
        medicationId: med.id,
        name: med.name,
        dosage: med.dosage,
        time: raw,
        hour: parsed.hour,
        minute: parsed.minute,
      });
    }
  }
  return entries;
}

function parseHHMM(raw: string): { hour: number; minute: number } | null {
  if (typeof raw !== 'string') return null;
  const m = raw.trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const hour = Number(m[1]);
  const minute = Number(m[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

/** 取消之前由本模块排的全部吃药通知 (避免重复堆积)。 */
export async function cancelMedicationReminders(): Promise<void> {
  if (Platform.OS !== 'ios') return;
  try {
    const scheduled = await Notifications.getAllScheduledNotificationsAsync();
    const toCancel = scheduled.filter(
      (n) => (n.content?.data as Record<string, any> | undefined)?.kind === MED_REMINDER_KIND,
    );
    await Promise.all(
      toCancel.map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)),
    );
  } catch {
    // 无权限 / 模拟器 — 静默跳过, 卡片仍可用
  }
}

/**
 * 按在服药品的 reminder_times 重排每日本地通知。
 * 先 cancel 旧的吃药通知再排新的; 无权限时静默跳过 (返回 0)。
 * @returns 实际排出的通知条数
 */
export async function scheduleMedicationReminders(meds: ReminderSource[]): Promise<number> {
  if (Platform.OS !== 'ios') return 0;

  // 不主动弹权限 (复用 useNotifications 的申请流程), 只读当前状态
  const { status } = await Notifications.getPermissionsAsync();
  if (status !== 'granted') {
    // 无权限: 顺手清掉残留, 但不排新的
    await cancelMedicationReminders();
    return 0;
  }

  await cancelMedicationReminders();

  const entries = buildReminderEntries(meds);
  let scheduled = 0;
  for (const e of entries) {
    try {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: '吃药提醒',
          // §5 推送隐私 (AGENTS.md §5.6): 锁屏可见的 body 不带药名/剂量 ——
          // 药名可反推诊断 (二甲双胍→糖尿病)。名称/剂量只进 data, 解锁后应用内渲染。
          body: `有一次用药到点了（${e.time}），点开查看`,
          categoryIdentifier: 'MEDICATION_REMINDER',
          data: {
            kind: MED_REMINDER_KIND,
            reminder_type: 'medication',
            medication_id: e.medicationId,
            medication_name: e.name,
            dosage: e.dosage,
            taken_time: e.time,
            screen: 'home',
          },
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DAILY,
          hour: e.hour,
          minute: e.minute,
        },
      });
      scheduled += 1;
    } catch {
      // 单条排程失败不阻断其余
    }
  }
  return scheduled;
}
