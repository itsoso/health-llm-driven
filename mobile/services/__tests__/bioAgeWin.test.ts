jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

import { pickBioAgeWin } from '../myProgress';

function card(over: any) {
  return {
    id: 1, title: '', status: 'completed', user_decision: 'accepted',
    outcome: 'improved', effect_size: 0.06, accuracy_score: 80,
    metric_key: 'phenotypic_age', baseline_value: '47', actual_value: '44',
    evidence_level: 'high', created_at: null, completed_at: null,
    graded_at: '2026-06-01T00:00:00Z', ...over,
  };
}

function dash(closed: any[]) {
  return { window: { since: '', until: '', days: 30 }, stats: {} as any, closed_cards: closed, verifying_cards: [] } as any;
}

describe('pickBioAgeWin', () => {
  it('挑出 improved 的生物年龄卡, 算出年轻几岁', () => {
    const w = pickBioAgeWin(dash([card({})]));
    expect(w).not.toBeNull();
    expect(w!.baseline).toBe(47);
    expect(w!.actual).toBe(44);
    expect(w!.deltaYears).toBe(3);
  });

  it('认 biological_age 别名', () => {
    const w = pickBioAgeWin(dash([card({ metric_key: 'biological_age' })]));
    expect(w?.deltaYears).toBe(3);
  });

  it('不把 worsened/unchanged 粉饰成 win', () => {
    expect(pickBioAgeWin(dash([card({ outcome: 'worsened', actual_value: '50' })]))).toBeNull();
    expect(pickBioAgeWin(dash([card({ outcome: 'unchanged', actual_value: '47' })]))).toBeNull();
  });

  it('忽略非生物年龄指标卡', () => {
    expect(pickBioAgeWin(dash([card({ metric_key: 'weight', actual_value: '70' })]))).toBeNull();
  });

  it('多张取最近 graded', () => {
    const older = card({ baseline_value: '50', actual_value: '48', graded_at: '2026-01-01T00:00:00Z' });
    const newer = card({ baseline_value: '47', actual_value: '44', graded_at: '2026-06-01T00:00:00Z' });
    const w = pickBioAgeWin(dash([older, newer]));
    expect(w!.actual).toBe(44);
  });

  it('空/缺值健壮', () => {
    expect(pickBioAgeWin(undefined)).toBeNull();
    expect(pickBioAgeWin(dash([]))).toBeNull();
    expect(pickBioAgeWin(dash([card({ actual_value: null })]))).toBeNull();
  });
});
