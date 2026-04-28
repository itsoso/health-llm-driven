jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import { freshnessAgeDays } from '../twin';

describe('freshnessAgeDays', () => {
  const now = new Date('2026-04-28T10:00:00Z');

  it('returns 0 for "今日"', () => {
    expect(freshnessAgeDays('今日', now)).toBe(0);
    expect(freshnessAgeDays('今天', now)).toBe(0);
  });

  it('returns 0 for recent hour/minute strings', () => {
    expect(freshnessAgeDays('1h ago', now)).toBe(0);
    expect(freshnessAgeDays('30 min ago', now)).toBe(0);
    expect(freshnessAgeDays('刚刚', now)).toBe(0);
  });

  it('parses "3 天前" / "3 days ago"', () => {
    expect(freshnessAgeDays('3 天前', now)).toBe(3);
    expect(freshnessAgeDays('3 days ago', now)).toBe(3);
    expect(freshnessAgeDays('3d ago', now)).toBe(3);
  });

  it('parses explicit dates YYYY-MM-DD', () => {
    expect(freshnessAgeDays('2026-04-25', now)).toBe(3);
    expect(freshnessAgeDays('2026-04-28', now)).toBe(0);
    expect(freshnessAgeDays('2026-01-28', now)).toBeGreaterThan(80);
  });

  it('parses months', () => {
    expect(freshnessAgeDays('2 个月前', now)).toBe(60);
    expect(freshnessAgeDays('6 months ago', now)).toBe(180);
  });

  it('returns null for null/empty/unparseable', () => {
    expect(freshnessAgeDays(null)).toBeNull();
    expect(freshnessAgeDays(undefined)).toBeNull();
    expect(freshnessAgeDays('')).toBeNull();
    expect(freshnessAgeDays('absolutely unparseable garbage')).toBeNull();
  });
});
