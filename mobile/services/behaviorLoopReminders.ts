/**
 * behaviorLoopReminders —— 把「行为闭环」通过可操作本地通知投递到手腕。
 *
 * iOS 本地通知会自动镜像到配对的 Apple Watch（无需 WatchOS App），表上可直接点按钮。
 * 纯 expo-notifications JS API（OTA 可达），不碰 app.json / Info.plist。
 *
 * 两类通知（都按 content.data.kind 标记，重排时只 cancel 自己这几类，
 * 不误删 medication_reminder / open_loop 等其它本地通知）:
 *   1. behavior_loop      —— 「今天最重要一件事」（取现成 daily plan top action）
 *                            按钮: 完成 / 稍后 / 跳过 → 后台调 daily-plan action event API
 *   2. intervention_cycle —— active 干预周期的周期性轻提醒（点开 deep link 到周期屏）
 *   3. intervention_recheck —— 周期 planned recheck 到期提醒（点开 deep link 到周期屏）
 *
 * 克制: 一天最多一条 behavior_loop（DAILY trigger）+ 一条周期提醒 + 必要的复查提醒。
 * 空态（无 plan / 无周期 / 无 top action）不发。
 */
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { pickTopPlanActions, type DailyOperatingPlan, type DailyPlanAction } from './dailyPlan';
import type { InterventionCycle } from './healthOs';
import { deferImmediateLocalNotificationUntilMorningFloor } from './localNotificationQuietHours';

export const BEHAVIOR_LOOP_KIND = 'behavior_loop';
export const INTERVENTION_CYCLE_KIND = 'intervention_cycle';
export const INTERVENTION_RECHECK_KIND = 'intervention_recheck';

/** 我们这个模块排的全部 kind —— 重排前据此过滤 cancel，绝不动他类。 */
const OWNED_KINDS = new Set<string>([
  BEHAVIOR_LOOP_KIND,
  INTERVENTION_CYCLE_KIND,
  INTERVENTION_RECHECK_KIND,
]);

const INTERVENTION_DEEP_LINK = '/intervention-cycle';

/** 「今天最重要一件事」默认推送时间（本地时区 09:00）。 */
const TOP_ACTION_HOUR = 9;
const TOP_ACTION_MINUTE = 0;
/** 干预周期轻提醒推送时间（本地时区 09:30，错开 top action）。 */
const CYCLE_HOUR = 9;
const CYCLE_MINUTE = 30;

interface ScheduledNotificationSpec {
  content: Notifications.NotificationContentInput;
  trigger: Notifications.NotificationTriggerInput;
}

/**
 * 从 daily plan 取「最重要一件事」的可操作通知 spec（纯函数，便于测试）。
 * 复用 pickTopPlanActions —— 读现成数据，不另算优先级。
 * 无可用 top action（空 plan / 无 title）→ 返回 null（不发）。
 */
export function buildTopActionNotification(
  plan: DailyOperatingPlan | null | undefined,
): ScheduledNotificationSpec | null {
  if (!plan) return null;
  const top: DailyPlanAction | undefined = pickTopPlanActions(plan.actions ?? [], 1)[0];
  if (!top || !top.title) return null;
  // 完成/跳过 需要 action_key（后台 event API 按它定位）；没有 key 的行动不发可操作通知。
  if (!top.action_key) return null;

  return {
    content: {
      title: '今天最重要的一件事',
      body: top.title,
      categoryIdentifier: 'BEHAVIOR_LOOP',
      data: {
        kind: BEHAVIOR_LOOP_KIND,
        action_key: top.action_key,
        screen: 'home',
      },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: TOP_ACTION_HOUR,
      minute: TOP_ACTION_MINUTE,
    },
  };
}

function cycleLabel(cycle: InterventionCycle): string {
  const target = cycle.target_metrics?.[0]?.code;
  const upper = target ? target.toUpperCase() : null;
  // 例: 「你的 90 天降 LDL 实验进行中」/ 无 metric 时退化成通用文案
  if (upper && cycle.start_date && cycle.planned_end_date) {
    const days = daysBetween(cycle.start_date, cycle.planned_end_date);
    if (days) return `你的 ${days} 天降 ${upper} 实验进行中`;
  }
  if (upper) return `你的降 ${upper} 干预周期进行中`;
  return '你的干预周期进行中';
}

function daysBetween(startISO: string, endISO: string): number | null {
  const start = Date.parse(startISO);
  const end = Date.parse(endISO);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  const d = Math.round((end - start) / 86400000);
  return d > 0 ? d : null;
}

/** 复查是否到期: planned_end_date <= now（按本地日期比较）。 */
export function isRecheckDue(cycle: InterventionCycle, now: Date): boolean {
  if (cycle.status !== 'active') return false;
  if (!cycle.planned_end_date) return false;
  const end = Date.parse(cycle.planned_end_date);
  if (Number.isNaN(end)) return false;
  return end <= now.getTime();
}

/**
 * 从 active 干预周期生成提醒 spec（纯函数）:
 *   - active 周期 → 一条周期性轻提醒（每日，但文案克制；只在 active 时存在）
 *   - 复查到期 → 一条复查通知（立即提醒）
 * 无周期 / 非 active → 返回 []。
 */
export function buildInterventionCycleNotifications(
  cycle: InterventionCycle | null | undefined,
  now: Date,
): ScheduledNotificationSpec[] {
  if (!cycle || cycle.status !== 'active') return [];
  const specs: ScheduledNotificationSpec[] = [];

  const baseData = {
    cycle_id: cycle.id,
    deep_link: INTERVENTION_DEEP_LINK,
    screen: 'home' as const,
  };

  specs.push({
    content: {
      title: '干预周期进行中',
      body: cycleLabel(cycle),
      categoryIdentifier: 'INTERVENTION_CYCLE',
      data: { ...baseData, kind: INTERVENTION_CYCLE_KIND },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: CYCLE_HOUR,
      minute: CYCLE_MINUTE,
    },
  });

  if (isRecheckDue(cycle, now)) {
    specs.push({
      content: {
        title: '该复查了',
        body: '你的干预周期到了复查时点，点开看看进展',
        categoryIdentifier: 'INTERVENTION_CYCLE',
        data: { ...baseData, kind: INTERVENTION_RECHECK_KIND },
      },
      // 到期提醒若发生在 09:00 前, 延迟到晨间睡眠地板; 白天仍立即投递。
      trigger: deferImmediateLocalNotificationUntilMorningFloor(now),
    });
  }

  return specs;
}

export type BehaviorLoopActionId = 'LOOP_DONE' | 'LOOP_LATER' | 'LOOP_SKIP';

/**
 * 把行为闭环按钮 → daily-plan action event_type（纯函数，便于测试）。
 *   完成 → completed; 跳过 → skipped; 稍后 → null（不记录，行动保持待办）。
 */
export function behaviorLoopActionToEventType(
  actionId: BehaviorLoopActionId,
): 'completed' | 'skipped' | null {
  if (actionId === 'LOOP_DONE') return 'completed';
  if (actionId === 'LOOP_SKIP') return 'skipped';
  return null; // LOOP_LATER
}

/** 取消之前由本模块排的全部行为闭环通知（按 kind 过滤，不误删他类）。 */
export async function cancelBehaviorLoopReminders(): Promise<void> {
  if (Platform.OS !== 'ios') return;
  try {
    const scheduled = await Notifications.getAllScheduledNotificationsAsync();
    const toCancel = scheduled.filter((n) => {
      const kind = (n.content?.data as Record<string, any> | undefined)?.kind;
      return typeof kind === 'string' && OWNED_KINDS.has(kind);
    });
    await Promise.all(
      toCancel.map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)),
    );
  } catch {
    // 无权限 / 模拟器 — 静默跳过，App 内卡片仍在
  }
}

/**
 * 重排行为闭环通知。
 * 先 cancel 旧的（仅本类），再排新的；无权限时静默跳过（返回 0）。
 * @returns 实际排出的通知条数
 */
export async function scheduleBehaviorLoopReminders(input: {
  plan: DailyOperatingPlan | null | undefined;
  cycle: InterventionCycle | null | undefined;
  now?: Date;
}): Promise<number> {
  if (Platform.OS !== 'ios') return 0;

  // 不主动弹权限（复用 useNotifications 的申请流程），只读当前状态
  const { status } = await Notifications.getPermissionsAsync();
  if (status !== 'granted') {
    // 无权限: 顺手清掉残留，但不排新的
    await cancelBehaviorLoopReminders();
    return 0;
  }

  await cancelBehaviorLoopReminders();

  const now = input.now ?? new Date();
  const specs: ScheduledNotificationSpec[] = [];
  const topAction = buildTopActionNotification(input.plan);
  if (topAction) specs.push(topAction);
  specs.push(...buildInterventionCycleNotifications(input.cycle, now));

  let scheduled = 0;
  for (const spec of specs) {
    try {
      await Notifications.scheduleNotificationAsync(spec);
      scheduled += 1;
    } catch {
      // 单条排程失败不阻断其余
    }
  }
  return scheduled;
}
