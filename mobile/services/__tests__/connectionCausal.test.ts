import { ucla3Total, effectArrow, type InterventionEffect } from '../chronicHealth';

describe('ucla3Total', () => {
  it('sums three items into the 3-9 range', () => {
    expect(ucla3Total(1, 1, 1)).toBe(3);
    expect(ucla3Total(2, 3, 2)).toBe(7);
    expect(ucla3Total(3, 3, 3)).toBe(9);
  });

  it('clamps out-of-range sums to the legal 3-9 band', () => {
    expect(ucla3Total(0, 0, 0)).toBe(3); // floor
    expect(ucla3Total(5, 5, 5)).toBe(9); // ceiling
  });
});

describe('effectArrow', () => {
  const base: InterventionEffect = {
    medication: '阿托伐他汀',
    metric_label: 'LDL',
    before_mean: 3.5,
    after_mean: 2.4,
    delta: -1.1,
    pct: -31.4,
    n_before: 2,
    n_after: 3,
  };

  it('points down when the metric dropped', () => {
    expect(effectArrow(base)).toBe('↓');
  });

  it('points up when the metric rose', () => {
    expect(effectArrow({ ...base, delta: 0.8 })).toBe('↑');
  });

  it('is flat when there is no change', () => {
    expect(effectArrow({ ...base, delta: 0 })).toBe('→');
  });
});
