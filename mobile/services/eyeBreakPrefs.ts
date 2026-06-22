/**
 * eyeBreakPrefs —— 科学用眼 20-20-20 的本地偏好 + 完成计数（纯客户端）。
 *
 * 用 AsyncStorage 持久化（与 voiceStyle.ts 同一机制；偏好非敏感，无需 SecureStore）。
 * 后端没有对应端点 —— 护眼 P1 完全在客户端闭环，完成计数只是本地激励，不上报。
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  DEFAULT_EYE_BREAK_PREFS,
  EYE_BREAK_INTERVAL_OPTIONS,
  type EyeBreakPrefs,
} from './eyeBreakReminders';

const PREFS_KEY = 'eye_break_prefs_v1';
const COUNTER_KEY = 'eye_break_counter_v1';

function isValidHHMM(raw: unknown): raw is string {
  return typeof raw === 'string' && /^([01]?\d|2[0-3]):[0-5]\d$/.test(raw.trim());
}

/** 把任意读到的对象规整成合法 prefs（非法字段回退到默认值）。导出便于测试。 */
export function sanitizeEyeBreakPrefs(raw: unknown): EyeBreakPrefs {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_EYE_BREAK_PREFS };
  const o = raw as Record<string, unknown>;
  const interval = Number(o.intervalMinutes);
  return {
    enabled: o.enabled === true,
    windowStart: isValidHHMM(o.windowStart) ? (o.windowStart as string) : DEFAULT_EYE_BREAK_PREFS.windowStart,
    windowEnd: isValidHHMM(o.windowEnd) ? (o.windowEnd as string) : DEFAULT_EYE_BREAK_PREFS.windowEnd,
    intervalMinutes: (EYE_BREAK_INTERVAL_OPTIONS as readonly number[]).includes(interval)
      ? interval
      : DEFAULT_EYE_BREAK_PREFS.intervalMinutes,
  };
}

export async function loadEyeBreakPrefs(): Promise<EyeBreakPrefs> {
  try {
    const raw = await AsyncStorage.getItem(PREFS_KEY);
    if (!raw) return { ...DEFAULT_EYE_BREAK_PREFS };
    return sanitizeEyeBreakPrefs(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_EYE_BREAK_PREFS };
  }
}

export async function saveEyeBreakPrefs(prefs: EyeBreakPrefs): Promise<void> {
  try {
    await AsyncStorage.setItem(PREFS_KEY, JSON.stringify(sanitizeEyeBreakPrefs(prefs)));
  } catch (e) {
    if (__DEV__) console.warn('[eyeBreakPrefs] save failed:', e);
  }
}

// ── 本地「今天完成 N 次」计数（仅本地，不上报后端）─────────────────────────

function todayKey(now: Date): string {
  // 本地日期 YYYY-MM-DD，按本地零点滚动。
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

interface CounterState {
  date: string;
  count: number;
}

/** 读今天的完成次数（跨天自动归零）。 */
export async function loadEyeBreakCount(now: Date = new Date()): Promise<number> {
  try {
    const raw = await AsyncStorage.getItem(COUNTER_KEY);
    if (!raw) return 0;
    const state = JSON.parse(raw) as CounterState;
    if (state?.date !== todayKey(now)) return 0; // 不是今天 → 视为 0
    return Number.isInteger(state.count) && state.count >= 0 ? state.count : 0;
  } catch {
    return 0;
  }
}

/** +1 今天的完成次数（用户点「我看完了」），返回新计数。 */
export async function incrementEyeBreakCount(now: Date = new Date()): Promise<number> {
  const current = await loadEyeBreakCount(now);
  const next = current + 1;
  try {
    await AsyncStorage.setItem(COUNTER_KEY, JSON.stringify({ date: todayKey(now), count: next }));
  } catch (e) {
    if (__DEV__) console.warn('[eyeBreakPrefs] counter save failed:', e);
  }
  return next;
}
