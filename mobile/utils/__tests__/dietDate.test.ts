import { formatLocalDate, offsetDate, todayStr } from '../dietDate';

// 数据完整性回归: prod 上一次午餐被记到 2 天前 (record_date=2026-06-29 而非 2026-07-01)。
// 根因是旧 offsetDate 用 `new Date("YYYY-MM-DD")` (UTC 午夜解析), 在负 UTC 时区里
// getDate() 已是前一天 → 单次 "-1" 跳 2 个日历日。这些测试钉死修复后的语义。

describe('offsetDate', () => {
  it('±1 moves exactly one local calendar day (prod regression: single tap must not jump 2 days)', () => {
    expect(offsetDate('2026-07-01', -1)).toBe('2026-06-30');
    expect(offsetDate('2026-07-01', 0)).toBe('2026-07-01');
    expect(offsetDate('2026-07-01', 1)).toBe('2026-07-02');
  });

  it('rolls across month boundary', () => {
    expect(offsetDate('2026-07-01', -1)).toBe('2026-06-30');
    expect(offsetDate('2026-06-30', 1)).toBe('2026-07-01');
  });

  it('rolls across year boundary', () => {
    expect(offsetDate('2026-01-01', -1)).toBe('2025-12-31');
    expect(offsetDate('2025-12-31', 1)).toBe('2026-01-01');
  });

  it('is offset-additive (n taps == single n)', () => {
    let d = '2026-07-01';
    for (let i = 0; i < 3; i++) d = offsetDate(d, -1);
    expect(d).toBe('2026-06-28');
    expect(offsetDate('2026-07-01', -3)).toBe('2026-06-28');
  });

  // 时区无关性: 通过重设 process.env.TZ 并重新 require 模块, 在负/正 UTC 极端时区下
  // 断言同一结果。旧实现在 America/Los_Angeles 会返回 2026-06-29 (双跳 bug)。
  describe.each([
    'America/Los_Angeles', // UTC-8/-7 — 触发原 bug
    'Pacific/Pago_Pago',   // UTC-11 — 最负
    'UTC',
    'Asia/Shanghai',       // 本 App 时区 UTC+8
    'Pacific/Kiritimati',  // UTC+14 — 最正
  ])('under TZ=%s', (tz) => {
    const origTZ = process.env.TZ;
    beforeAll(() => { process.env.TZ = tz; jest.resetModules(); });
    afterAll(() => { process.env.TZ = origTZ; jest.resetModules(); });

    it('offsetDate(2026-07-01, -1) === 2026-06-30 (no 2-day jump)', () => {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { offsetDate: od } = require('../dietDate');
      expect(od('2026-07-01', -1)).toBe('2026-06-30');
      expect(od('2026-07-01', 0)).toBe('2026-07-01');
      expect(od('2026-07-01', 1)).toBe('2026-07-02');
    });
  });
});

describe('todayStr', () => {
  it('returns a local YYYY-MM-DD string', () => {
    expect(todayStr()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('matches the local calendar date (not UTC-derived)', () => {
    const now = new Date();
    const expected = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    expect(todayStr()).toBe(expected);
  });
});

describe('formatLocalDate', () => {
  it('formats the supplied local calendar components instead of the UTC date', () => {
    const localLateEvening = new Date(2026, 6, 25, 23, 30, 0);
    expect(formatLocalDate(localLateEvening)).toBe('2026-07-25');
  });
});
