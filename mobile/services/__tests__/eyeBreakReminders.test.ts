jest.mock('react-native', () => ({ Platform: { OS: 'ios' } }));

jest.mock('expo-notifications', () => ({
  __esModule: true,
  SchedulableTriggerInputTypes: { DATE: 'date', DAILY: 'daily' },
  getPermissionsAsync: jest.fn(),
  getAllScheduledNotificationsAsync: jest.fn(),
  scheduleNotificationAsync: jest.fn(),
  cancelScheduledNotificationAsync: jest.fn(),
}));

import * as Notifications from 'expo-notifications';
import {
  computeEyeBreakSlots,
  buildEyeBreakNotifications,
  scheduleEyeBreakReminders,
  cancelEyeBreakReminders,
  EYE_BREAK_KIND,
  EYE_BREAK_MAX_PENDING,
  DEFAULT_EYE_BREAK_PREFS,
  type EyeBreakPrefs,
} from '../eyeBreakReminders';

const mockNotif = Notifications as unknown as {
  getPermissionsAsync: jest.Mock;
  getAllScheduledNotificationsAsync: jest.Mock;
  scheduleNotificationAsync: jest.Mock;
  cancelScheduledNotificationAsync: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([]);
  mockNotif.scheduleNotificationAsync.mockResolvedValue('id');
  mockNotif.cancelScheduledNotificationAsync.mockResolvedValue(undefined);
});

const prefs = (over: Partial<EyeBreakPrefs> = {}): EyeBreakPrefs => ({
  ...DEFAULT_EYE_BREAK_PREFS,
  enabled: true,
  ...over,
});

// 用固定的本地时间构造日期（避免依赖测试机时区做断言）。
const localDay = (h: number, m = 0) => new Date(2026, 5, 22, h, m, 0, 0); // 2026-06-22

describe('computeEyeBreakSlots', () => {
  const dayStart = new Date(2026, 5, 22, 0, 0, 0, 0);

  it('在时段内按 interval 生成 slot（含 start 和 end）', () => {
    const slots = computeEyeBreakSlots(
      prefs({ windowStart: '09:00', windowEnd: '10:00', intervalMinutes: 20 }),
      dayStart,
      new Date(2026, 5, 22, 0, 0, 0, 0), // after = 当天零点 → 全部保留
    );
    // 09:00 09:20 09:40 10:00 = 4 条
    expect(slots).toHaveLength(4);
    expect(slots[0].getHours()).toBe(9);
    expect(slots[0].getMinutes()).toBe(0);
    expect(slots[3].getHours()).toBe(10);
    expect(slots[3].getMinutes()).toBe(0);
  });

  it('只返回严格晚于 after 的 slot（不排过去的时间）', () => {
    const slots = computeEyeBreakSlots(
      prefs({ windowStart: '09:00', windowEnd: '10:00', intervalMinutes: 20 }),
      dayStart,
      localDay(9, 10), // 09:10 之后 → 09:20 09:40 10:00
    );
    expect(slots.map((s) => `${s.getHours()}:${s.getMinutes()}`)).toEqual(['9:20', '9:40', '10:0']);
  });

  it('尊重自定义 interval（30 分钟）', () => {
    const slots = computeEyeBreakSlots(
      prefs({ windowStart: '09:00', windowEnd: '11:00', intervalMinutes: 30 }),
      dayStart,
      new Date(2026, 5, 22, 0, 0, 0, 0),
    );
    // 09:00 09:30 10:00 10:30 11:00 = 5
    expect(slots).toHaveLength(5);
  });

  it('非法配置（start>=end / interval<=0 / 解析失败）→ []', () => {
    const after = new Date(2026, 5, 22, 0, 0, 0, 0);
    expect(computeEyeBreakSlots(prefs({ windowStart: '21:00', windowEnd: '09:00' }), dayStart, after)).toEqual([]);
    expect(computeEyeBreakSlots(prefs({ intervalMinutes: 0 }), dayStart, after)).toEqual([]);
    expect(computeEyeBreakSlots(prefs({ windowStart: 'bad' }), dayStart, after)).toEqual([]);
  });
});

describe('buildEyeBreakNotifications', () => {
  it('未开启 → []', () => {
    expect(buildEyeBreakNotifications(prefs({ enabled: false }), localDay(8))).toEqual([]);
  });

  it('开启 → 全部用 DATE trigger + eye_break tag + 不带 screen（前台不被抑制）', () => {
    const specs = buildEyeBreakNotifications(
      prefs({ windowStart: '09:00', windowEnd: '09:40', intervalMinutes: 20 }),
      localDay(8), // 08:00, 当天 09:00/09:20/09:40 都在 now 之后
    );
    expect(specs.length).toBeGreaterThanOrEqual(3);
    for (const s of specs) {
      expect((s.trigger as any).type).toBe('date');
      expect(s.content.data).toMatchObject({ kind: EYE_BREAK_KIND });
      // 关键: 不带 screen:'home' → 不会被 useNotifications 的 SILENT_SCREENS 抑制
      expect((s.content.data as any).screen).toBeUndefined();
      expect(String(s.content.body)).toContain('20 英尺');
    }
  });

  it('总条数不超过 EYE_BREAK_MAX_PENDING（64-cap 防护）', () => {
    // 06:00–23:00 / 20min ≈ 52 条/天 × 2 天 = 100+，必须截断到上限。
    const specs = buildEyeBreakNotifications(
      prefs({ windowStart: '06:00', windowEnd: '23:00', intervalMinutes: 20 }),
      localDay(5), // 05:00，当天整段都在 now 之后
    );
    expect(specs.length).toBeLessThanOrEqual(EYE_BREAK_MAX_PENDING);
    expect(EYE_BREAK_MAX_PENDING).toBeLessThan(64);
  });
});

describe('scheduleEyeBreakReminders', () => {
  it('有权限 + 开启: 先 cancel 本类旧通知（不动他类）再排新的', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([
      { identifier: 'eye_old', content: { data: { kind: EYE_BREAK_KIND } } },
      { identifier: 'med', content: { data: { kind: 'medication_reminder' } } },
      { identifier: 'loop', content: { data: { kind: 'behavior_loop' } } },
    ]);

    const n = await scheduleEyeBreakReminders(
      prefs({ windowStart: '09:00', windowEnd: '09:40', intervalMinutes: 20 }),
      localDay(8),
    );

    expect(n).toBeGreaterThanOrEqual(3);
    // 只 cancel 自己那一条，不动 medication / behavior_loop
    const cancelled = mockNotif.cancelScheduledNotificationAsync.mock.calls.map((c) => c[0]);
    expect(cancelled).toEqual(['eye_old']);
    expect(mockNotif.scheduleNotificationAsync).toHaveBeenCalledTimes(n);
  });

  it('关闭: 只清残留不排新的 → 0', async () => {
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([
      { identifier: 'eye_old', content: { data: { kind: EYE_BREAK_KIND } } },
    ]);
    const n = await scheduleEyeBreakReminders(prefs({ enabled: false }), localDay(8));
    expect(n).toBe(0);
    // 关闭路径不读权限（直接清），也不排新的
    expect(mockNotif.getPermissionsAsync).not.toHaveBeenCalled();
    expect(mockNotif.cancelScheduledNotificationAsync).toHaveBeenCalledWith('eye_old');
    expect(mockNotif.scheduleNotificationAsync).not.toHaveBeenCalled();
  });

  it('无权限: 不排新的 → 0', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'denied' });
    const n = await scheduleEyeBreakReminders(prefs(), localDay(8));
    expect(n).toBe(0);
    expect(mockNotif.scheduleNotificationAsync).not.toHaveBeenCalled();
  });

  it('排出的条数不超过 64-cap 上限', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    const n = await scheduleEyeBreakReminders(
      prefs({ windowStart: '06:00', windowEnd: '23:00', intervalMinutes: 20 }),
      localDay(5),
    );
    expect(n).toBeLessThanOrEqual(EYE_BREAK_MAX_PENDING);
  });
});

describe('cancelEyeBreakReminders', () => {
  it('只 cancel eye_break 这一类 kind', async () => {
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([
      { identifier: 'a', content: { data: { kind: EYE_BREAK_KIND } } },
      { identifier: 'b', content: { data: { kind: 'medication_reminder' } } },
      { identifier: 'c', content: { data: {} } },
      { identifier: 'd', content: { data: { kind: EYE_BREAK_KIND } } },
    ]);
    await cancelEyeBreakReminders();
    const cancelled = mockNotif.cancelScheduledNotificationAsync.mock.calls.map((c) => c[0]);
    expect(cancelled.sort()).toEqual(['a', 'd']);
  });
});
