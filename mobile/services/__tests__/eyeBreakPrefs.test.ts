import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  sanitizeEyeBreakPrefs,
  loadEyeBreakPrefs,
  saveEyeBreakPrefs,
  loadEyeBreakCount,
  incrementEyeBreakCount,
} from '../eyeBreakPrefs';
import { DEFAULT_EYE_BREAK_PREFS } from '../eyeBreakReminders';

beforeEach(async () => {
  await AsyncStorage.clear();
});

describe('sanitizeEyeBreakPrefs', () => {
  it('合法对象原样保留', () => {
    expect(
      sanitizeEyeBreakPrefs({ enabled: true, windowStart: '08:00', windowEnd: '20:00', intervalMinutes: 30 }),
    ).toEqual({ enabled: true, windowStart: '08:00', windowEnd: '20:00', intervalMinutes: 30 });
  });

  it('非法字段回退到默认值', () => {
    const got = sanitizeEyeBreakPrefs({ enabled: 'yes', windowStart: '99:99', windowEnd: 5, intervalMinutes: 7 });
    expect(got.enabled).toBe(false); // 非严格 true → false
    expect(got.windowStart).toBe(DEFAULT_EYE_BREAK_PREFS.windowStart);
    expect(got.windowEnd).toBe(DEFAULT_EYE_BREAK_PREFS.windowEnd);
    expect(got.intervalMinutes).toBe(DEFAULT_EYE_BREAK_PREFS.intervalMinutes); // 7 不在选项 → 默认 20
  });

  it('null / 非对象 → 全默认', () => {
    expect(sanitizeEyeBreakPrefs(null)).toEqual(DEFAULT_EYE_BREAK_PREFS);
    expect(sanitizeEyeBreakPrefs('x')).toEqual(DEFAULT_EYE_BREAK_PREFS);
  });
});

describe('load/save prefs', () => {
  it('空存储 → 默认', async () => {
    expect(await loadEyeBreakPrefs()).toEqual(DEFAULT_EYE_BREAK_PREFS);
  });

  it('save 后 load 回读一致（经 sanitize 落盘）', async () => {
    await saveEyeBreakPrefs({ enabled: true, windowStart: '10:00', windowEnd: '22:00', intervalMinutes: 45 });
    expect(await loadEyeBreakPrefs()).toEqual({
      enabled: true, windowStart: '10:00', windowEnd: '22:00', intervalMinutes: 45,
    });
  });

  it('损坏 JSON → 回退默认（不抛）', async () => {
    await AsyncStorage.setItem('eye_break_prefs_v1', '{not json');
    expect(await loadEyeBreakPrefs()).toEqual(DEFAULT_EYE_BREAK_PREFS);
  });
});

describe('today counter', () => {
  const today = new Date(2026, 5, 22, 10, 0, 0);

  it('空 → 0；increment 累加', async () => {
    expect(await loadEyeBreakCount(today)).toBe(0);
    expect(await incrementEyeBreakCount(today)).toBe(1);
    expect(await incrementEyeBreakCount(today)).toBe(2);
    expect(await loadEyeBreakCount(today)).toBe(2);
  });

  it('跨天自动归零', async () => {
    await incrementEyeBreakCount(today);
    const tomorrow = new Date(2026, 5, 23, 9, 0, 0);
    expect(await loadEyeBreakCount(tomorrow)).toBe(0);
  });
});
