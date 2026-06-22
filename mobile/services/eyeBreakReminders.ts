/**
 * eyeBreakReminders —— 科学用眼 20-20-20 本地提醒（P1 时间近似版）。
 *
 * 产品定位（spec §1.5.2 决策 #3）：用户主动开启后，在可配置的活跃时段内，
 * 每隔 ~20 分钟提醒「看 20 英尺(6 米)外 20 秒，放松睫状肌」。
 *
 * ⚠️ 这是**时间驱动的 P1 近似**，不是真正的「连续看屏 20 分钟才提醒」。
 *    真·屏幕注视累积信号（accumulated screen-focus）需要 Mac / Rokid 的
 *    DeviceObservation，留到 P2/P3。**本模块不检测、也不声称检测屏幕注视。**
 *
 * R4：纯人体工学/护眼提示，**不含任何医疗主张/诊断**。
 *
 * 纯 expo-notifications JS API（OTA 可达），不碰 app.json / Info.plist / native。
 *
 * ── iOS 64 条 pending 上限的处理 ───────────────────────────────────────────
 * iOS 单 App 最多 64 条 pending 本地通知。一天 12 小时 / 20 分钟 = 36 条，
 * 多排几天就会撞顶并把别的提醒（吃药/行为闭环）挤掉。
 *
 * 本模块用「滚动当日重排（rolling daily re-schedule）」策略：
 *   - 每次重排只排 **从 now 到当日时段结束** 的剩余 slot（一次性 DATE trigger，
 *     不用 repeating trigger —— repeating 无法限制在活跃时段内，会半夜响）。
 *   - 再向前多排 1 天兜底（防用户当天不再打开 App），且对总条数做硬上限
 *     EYE_BREAK_MAX_PENDING（远小于 64，给吃药/行为闭环留足额度）。
 *   - App 进前台时（useEyeBreakReminders hook）重排，把消耗掉的 slot 补回，
 *     因此稳态下永远只占个位数～二十几条，绝不接近 64。
 * 重排前只 cancel 自己这一类（按 content.data.kind 过滤），不误删他类通知。
 */
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';

/** 标记本模块排的提醒；重排/取消时只动这一类。 */
export const EYE_BREAK_KIND = 'eye_break';

/** 一次重排排出的硬上限（远小于 iOS 的 64，给其它本地通知留额度）。 */
export const EYE_BREAK_MAX_PENDING = 40;

/** 向前多排几天兜底（防用户当天不再开 App）。1 = 今天 + 明天。 */
const LOOKAHEAD_DAYS = 1;

export interface EyeBreakPrefs {
  enabled: boolean;
  /** 活跃时段开始 "HH:MM"（含）。 */
  windowStart: string;
  /** 活跃时段结束 "HH:MM"（含，提醒不会晚于此时刻）。 */
  windowEnd: string;
  /** 提醒间隔（分钟）。 */
  intervalMinutes: number;
}

export const DEFAULT_EYE_BREAK_PREFS: EyeBreakPrefs = {
  enabled: false,
  windowStart: '09:00',
  windowEnd: '21:00',
  intervalMinutes: 20,
};

/** 间隔可选项（分钟）—— 设置屏与校验共用。 */
export const EYE_BREAK_INTERVAL_OPTIONS = [20, 30, 45, 60] as const;

const EYE_BREAK_TITLE = '科学用眼 · 该远眺了 👀';
const EYE_BREAK_BODY = '看 20 英尺(6 米)外 20 秒，放松睫状肌。';

interface ScheduledNotificationSpec {
  content: Notifications.NotificationContentInput;
  trigger: Notifications.NotificationTriggerInput;
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

/** 把 "HH:MM" 落到给定日期的「当天第几分钟」（0..1439），解析失败返回 null。 */
function minutesOfDay(raw: string): number | null {
  const p = parseHHMM(raw);
  if (!p) return null;
  return p.hour * 60 + p.minute;
}

/**
 * 计算一天内（给定 dayStart 当地零点）落在活跃时段、且严格晚于 after 的所有提醒时刻。
 * 纯函数，便于测试。
 *
 * 规则：
 *   - 第一个 slot 在 windowStart（含），之后每 intervalMinutes 一个，直到 windowEnd（含）。
 *   - 只返回 > after 的时刻（after 通常是 now，避免排过去的时间）。
 *   - 配置非法（解析失败 / start>=end / interval<=0）→ 返回 []，调用方据此「不发」。
 */
export function computeEyeBreakSlots(
  prefs: EyeBreakPrefs,
  dayStart: Date,
  after: Date,
): Date[] {
  const startMin = minutesOfDay(prefs.windowStart);
  const endMin = minutesOfDay(prefs.windowEnd);
  const interval = prefs.intervalMinutes;
  if (startMin == null || endMin == null) return [];
  if (!Number.isFinite(interval) || interval <= 0) return [];
  if (startMin >= endMin) return []; // 不支持跨午夜时段（护眼场景无意义）

  const slots: Date[] = [];
  const baseMs = dayStart.getTime();
  for (let m = startMin; m <= endMin; m += interval) {
    const at = new Date(baseMs + m * 60_000);
    if (at.getTime() > after.getTime()) slots.push(at);
    // 防御：极小 interval 也不会无限循环（endMin 上限 1439）
  }
  return slots;
}

/** 当地零点（剥掉时分秒）。 */
function localMidnight(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
}

/**
 * 生成今天 + 未来 LOOKAHEAD_DAYS 天、活跃时段内的全部提醒 spec（纯函数，便于测试）。
 * 总条数硬上限 EYE_BREAK_MAX_PENDING（超出截断，远离 iOS 64 上限）。
 * 未开启 / 配置非法 → 返回 []。
 */
export function buildEyeBreakNotifications(
  prefs: EyeBreakPrefs,
  now: Date,
): ScheduledNotificationSpec[] {
  if (!prefs.enabled) return [];

  const all: Date[] = [];
  for (let dayOffset = 0; dayOffset <= LOOKAHEAD_DAYS; dayOffset += 1) {
    const day = localMidnight(now);
    day.setDate(day.getDate() + dayOffset);
    // 第 0 天只排 now 之后的 slot；后续天排整段。
    const after = dayOffset === 0 ? now : new Date(day.getTime() - 1);
    all.push(...computeEyeBreakSlots(prefs, day, after));
    if (all.length >= EYE_BREAK_MAX_PENDING) break;
  }

  const capped = all.slice(0, EYE_BREAK_MAX_PENDING);
  return capped.map((at) => ({
    content: {
      title: EYE_BREAK_TITLE,
      body: EYE_BREAK_BODY,
      // 自己的 data tag —— 不带 screen:'home'，所以不会被 useNotifications 的
      // SILENT_SCREENS 抑制；前台也会正常显示横幅。
      data: { kind: EYE_BREAK_KIND },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DATE,
      date: at,
    },
  }));
}

/** 取消之前由本模块排的全部护眼提醒（按 kind 过滤，绝不动他类本地通知）。 */
export async function cancelEyeBreakReminders(): Promise<void> {
  if (Platform.OS !== 'ios') return;
  try {
    const scheduled = await Notifications.getAllScheduledNotificationsAsync();
    const toCancel = scheduled.filter(
      (n) => (n.content?.data as Record<string, any> | undefined)?.kind === EYE_BREAK_KIND,
    );
    await Promise.all(
      toCancel.map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)),
    );
  } catch {
    // 无权限 / 模拟器 — 静默跳过
  }
}

/**
 * 重排护眼提醒（滚动当日重排）。
 * 先 cancel 本类旧通知，再排新的；无权限 / 关闭时只清不排（返回 0）。
 * @returns 实际排出的通知条数
 */
export async function scheduleEyeBreakReminders(
  prefs: EyeBreakPrefs,
  now: Date = new Date(),
): Promise<number> {
  if (Platform.OS !== 'ios') return 0;

  // 关闭 → 清掉残留，不排新的（toggle off 的取消路径走这里）。
  if (!prefs.enabled) {
    await cancelEyeBreakReminders();
    return 0;
  }

  // 不主动弹权限（复用 useNotifications 的申请流程），只读当前状态。
  const { status } = await Notifications.getPermissionsAsync();
  if (status !== 'granted') {
    await cancelEyeBreakReminders();
    return 0;
  }

  await cancelEyeBreakReminders();

  const specs = buildEyeBreakNotifications(prefs, now);
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
