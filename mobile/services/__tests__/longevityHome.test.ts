jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

import { topNextData, pickCausalHighlight } from '../longevityHome';

describe('topNextData', () => {
  it('取 priority 最高的建议', () => {
    const r = {
      suggestions: [
        { item: 'A', unlocks: 'x', priority: 30 },
        { item: 'B', unlocks: 'y', priority: 60 },
        { item: 'C', unlocks: 'z', priority: 40 },
      ],
    };
    expect(topNextData(r)!.item).toBe('B');
  });
  it('空/undefined → null', () => {
    expect(topNextData({ suggestions: [] })).toBeNull();
    expect(topNextData(undefined)).toBeNull();
  });
});

describe('pickCausalHighlight', () => {
  const note = (direction: string, text = 't') => ({
    metric: 'hrv', before: 40, after: 48, pct: 0.2, direction, text,
  });
  it('优先取"改善"那条', () => {
    const r = { notes: [note('走低', '坏'), note('改善', '好')] };
    expect(pickCausalHighlight(r)!.text).toBe('好');
  });
  it('无改善则取第一条', () => {
    const r = { notes: [note('走低', '只有这条')] };
    expect(pickCausalHighlight(r)!.text).toBe('只有这条');
  });
  it('空 → null', () => {
    expect(pickCausalHighlight({ notes: [] })).toBeNull();
    expect(pickCausalHighlight(null)).toBeNull();
  });
});
