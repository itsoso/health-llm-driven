/**
 * timelineLayout 纯函数单测 —— 分钟数学 + 重叠泳道。
 * 这是时间轴定位的正确性闸:start/end 解析错或泳道分配错 → 块错位/互相遮盖。
 */
import {
  assignLanes, clampDayMinute, DAY_MINUTES, hhmmToMinutes, isoToMinutesOfDay,
  type TimelineBlock,
} from '../timelineLayout';

describe('hhmmToMinutes', () => {
  it('parses HH:MM to minutes-of-day', () => {
    expect(hhmmToMinutes('00:00')).toBe(0);
    expect(hhmmToMinutes('08:30')).toBe(510);
    expect(hhmmToMinutes('23:59')).toBe(1439);
    expect(hhmmToMinutes('9:05')).toBe(545); // single-digit hour ok
  });
  it('returns null for malformed / out-of-range', () => {
    expect(hhmmToMinutes('24:00')).toBeNull();
    expect(hhmmToMinutes('08:60')).toBeNull();
    expect(hhmmToMinutes('abc')).toBeNull();
    expect(hhmmToMinutes('')).toBeNull();
  });
});

describe('isoToMinutesOfDay', () => {
  it('extracts local H*60+M from a datetime', () => {
    const d = new Date(2026, 5, 18, 14, 15); // local 14:15
    expect(isoToMinutesOfDay(d.toISOString())).toBe(14 * 60 + 15);
  });
  it('returns null for null/invalid', () => {
    expect(isoToMinutesOfDay(null)).toBeNull();
    expect(isoToMinutesOfDay('not-a-date')).toBeNull();
  });
});

describe('clampDayMinute', () => {
  it('clamps to [0, 1440]', () => {
    expect(clampDayMinute(-30)).toBe(0);
    expect(clampDayMinute(700)).toBe(700);
    expect(clampDayMinute(2000)).toBe(DAY_MINUTES);
  });
});

describe('assignLanes', () => {
  const blk = (key: string, startMin: number, endMin: number): TimelineBlock => ({ key, startMin, endMin });

  it('puts non-overlapping blocks all in lane 0 of 1', () => {
    const out = assignLanes([blk('a', 0, 60), blk('b', 60, 120), blk('c', 200, 260)]);
    out.forEach((p) => {
      expect(p.lane).toBe(0);
      expect(p.lanes).toBe(1);
    });
  });

  it('splits two overlapping blocks into 2 lanes', () => {
    const out = assignLanes([blk('a', 540, 600), blk('b', 570, 630)]);
    const byKey = Object.fromEntries(out.map((p) => [p.block.key, p]));
    expect(byKey.a.lanes).toBe(2);
    expect(byKey.b.lanes).toBe(2);
    expect(byKey.a.lane).not.toBe(byKey.b.lane);
  });

  it('reuses a freed lane after a block ends (3 staggered → max 2 lanes)', () => {
    // a:9-10, b:9:30-10:30 (overlaps a → lane1), c:10:15-11 (a done, overlaps b → reuse lane0)
    const out = assignLanes([blk('a', 540, 600), blk('b', 570, 630), blk('c', 615, 660)]);
    const byKey = Object.fromEntries(out.map((p) => [p.block.key, p]));
    // a,b,c are one transitive cluster (b bridges a and c) → all share lanes count
    expect(byKey.a.lanes).toBe(2);
    expect(byKey.c.lane).toBe(byKey.a.lane); // c reuses a's freed lane
  });

  it('touching blocks (end == next start) do NOT overlap', () => {
    const out = assignLanes([blk('a', 540, 600), blk('b', 600, 660)]);
    expect(out.every((p) => p.lanes === 1)).toBe(true);
  });

  it('three mutually-overlapping blocks → 3 lanes, distinct', () => {
    const out = assignLanes([blk('a', 540, 660), blk('b', 555, 660), blk('c', 570, 660)]);
    const lanes = out.map((p) => p.lane).sort();
    expect(out.every((p) => p.lanes === 3)).toBe(true);
    expect(lanes).toEqual([0, 1, 2]);
  });

  it('does not mutate input order / array', () => {
    const input = [blk('b', 100, 200), blk('a', 0, 50)];
    const snapshot = input.map((b) => b.key);
    assignLanes(input);
    expect(input.map((b) => b.key)).toEqual(snapshot);
  });
});
