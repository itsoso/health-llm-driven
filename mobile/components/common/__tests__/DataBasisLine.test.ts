/**
 * DataBasisLine 内部 helper 单测 (formatAge / ageTone).
 * UI rendering 测试嫌重 — 这两个纯函数足够保 schema 不退化.
 */
import { ageTone, formatAge } from '../dataBasisHelpers';

const tone = ageTone;

describe('formatAge', () => {
  it('handles "1h ago"', () => {
    const r = formatAge('1h ago');
    expect(r.hours).toBe(1);
    expect(r.pretty).toBe('1 小时前');
  });

  it('handles "30 min ago" → 0 hours, but pretty shows minutes', () => {
    const r = formatAge('30 min ago');
    expect(r.hours).toBe(0);
    expect(r.pretty).toBe('30 分钟前');
  });

  it('handles 中文 今日 / 今天', () => {
    expect(formatAge('今日').hours).toBe(0);
    expect(formatAge('今日').pretty).toBe('今日');
    expect(formatAge('今天').hours).toBe(0);
  });

  it('handles 昨日', () => {
    const r = formatAge('昨日');
    expect(r.hours).toBe(24);
    expect(r.pretty).toBe('昨日');
  });

  it('handles "3 天前"', () => {
    const r = formatAge('3 天前');
    expect(r.hours).toBe(72);
    expect(r.pretty).toBe('3 天前');
  });

  it('handles "6 个月前" → roughly 180 天', () => {
    const r = formatAge('6 个月前');
    expect(r.hours).toBe(180 * 24);
    expect(r.pretty).toBe('6 月前');
  });

  it('null / 空字符串', () => {
    expect(formatAge(null)).toEqual({ hours: null, pretty: '未录入' });
    expect(formatAge(undefined)).toEqual({ hours: null, pretty: '未录入' });
    // 空字符串走 trim, 然后没 match → freshnessAgeDays 返回 null → pretty 是空 slice
    const r = formatAge('');
    expect(r.hours).toBeNull();
  });

  it('未识别格式 不抛, hours=null', () => {
    const r = formatAge('weird-format-xyz');
    expect(r.hours).toBeNull();
  });
});

describe('tone', () => {
  it('<=12h → fresh', () => {
    expect(tone(0)).toBe('fresh');
    expect(tone(1)).toBe('fresh');
    expect(tone(12)).toBe('fresh');
  });

  it('12-72h → stale', () => {
    expect(tone(13)).toBe('stale');
    expect(tone(48)).toBe('stale');
    expect(tone(72)).toBe('stale');
  });

  it('>72h → missing (太旧别信)', () => {
    expect(tone(73)).toBe('missing');
    expect(tone(720)).toBe('missing');
  });

  it('null → missing', () => {
    expect(tone(null)).toBe('missing');
  });
});
