import { dietShareLocationLine, normalizeDietShareLocation, withDietShareLocation } from '../dietShareLocation';

describe('explicit public share location', () => {
  it('defaults to omission and never adds an empty line', () => {
    expect(dietShareLocationLine()).toBe('');
    expect(dietShareLocationLine(' \n\t ')).toBe('');
    expect(withDietShareLocation('正文', '')).toBe('正文');
  });
  it('normalizes whitespace, hidden controls and length consistently', () => {
    const raw = ' 杭州\n  示例\u202e餐厅\u0000 ';
    expect(normalizeDietShareLocation(raw)).toBe('杭州 示例 餐厅');
    expect(withDietShareLocation('正文', raw)).toBe(`正文\n\n${dietShareLocationLine(raw)}`);
    expect(Array.from(normalizeDietShareLocation('杭'.repeat(60)))).toHaveLength(40);
    expect(Array.from(normalizeDietShareLocation('🍜'.repeat(60)))).toHaveLength(40);
  });
});
