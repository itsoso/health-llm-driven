jest.mock('../api', () => ({ __esModule: true, default: { post: jest.fn(), get: jest.fn() } }));

import { sortByOriginator, summarize, type PrescriptionDrug } from '../prescriptions';

const drug = (raw: string, hasOrig: boolean): PrescriptionDrug => ({
  raw_name: raw, generic_name: raw, dosage: null, frequency: null,
  originator: hasOrig ? { generic: raw, brand: 'X', manufacturer: 'Y' } : null,
  has_originator: hasOrig,
});

describe('sortByOriginator', () => {
  it('有原研的排前面', () => {
    const out = sortByOriginator([drug('A', false), drug('B', true), drug('C', false)]);
    expect(out[0].raw_name).toBe('B');
  });
  it('空 → []', () => {
    expect(sortByOriginator(null)).toEqual([]);
  });
});

describe('summarize', () => {
  it('N 种药 M 有原研', () => {
    expect(summarize({ items: [drug('A', true), drug('B', false)], matched_originators: 1, note: '' }))
      .toBe('识别 2 种药,其中 1 种找到对应原研药');
  });
  it('空 → 未识别', () => {
    expect(summarize(null)).toBe('未识别到药品');
    expect(summarize({ items: [], matched_originators: 0, note: '' })).toBe('未识别到药品');
  });
});
