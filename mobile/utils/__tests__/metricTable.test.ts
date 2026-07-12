import { parseMetricTable } from '../metricTable';

describe('parseMetricTable', () => {
  const validBlock = {
    type: 'metric_table',
    v: 1,
    title: '近三次血压',
    columns: [
      { key: 'date', label: '日期' },
      { key: 'sys', label: '收缩压' },
      { key: 'dia', label: '舒张压' },
    ],
    rows: [
      { date: '07-11', sys: '128', dia: '82' },
      { date: '07-12', sys: '124', dia: '79' },
    ],
    footnote: '仅供健康管理参考',
  };

  it('parses a well-formed metric_table', () => {
    const data = parseMetricTable(validBlock);
    expect(data).not.toBeNull();
    expect(data!.title).toBe('近三次血压');
    expect(data!.columns).toEqual([
      { key: 'date', label: '日期' },
      { key: 'sys', label: '收缩压' },
      { key: 'dia', label: '舒张压' },
    ]);
    expect(data!.rows).toEqual([
      { date: '07-11', sys: '128', dia: '82' },
      { date: '07-12', sys: '124', dia: '79' },
    ]);
    expect(data!.footnote).toBe('仅供健康管理参考');
  });

  it('coerces finite numeric cells to strings and trims text', () => {
    const data = parseMetricTable({
      columns: [
        { key: 'k', label: '指标' },
        { key: 'v', label: '值' },
      ],
      rows: [{ k: '  空腹血糖  ', v: 5.6 }],
    });
    expect(data!.rows).toEqual([{ k: '空腹血糖', v: '5.6' }]);
  });

  it('title/footnote are optional', () => {
    const data = parseMetricTable({
      columns: [
        { key: 'a', label: 'A' },
        { key: 'b', label: 'B' },
      ],
      rows: [{ a: '1', b: '2' }],
    });
    expect(data).not.toBeNull();
    expect(data!.title).toBeUndefined();
    expect(data!.footnote).toBeUndefined();
  });

  it('rejects fewer than 2 valid columns → null', () => {
    expect(
      parseMetricTable({
        columns: [{ key: 'only', label: '唯一列' }],
        rows: [{ only: '1' }],
      }),
    ).toBeNull();
  });

  it('rejects columns missing key or label', () => {
    expect(
      parseMetricTable({
        columns: [
          { key: 'a', label: 'A' },
          { key: '', label: 'B' }, // invalid → dropped, leaves 1 valid col
        ],
        rows: [{ a: '1' }],
      }),
    ).toBeNull();
  });

  it('drops all-empty rows and rejects when no rows survive', () => {
    expect(
      parseMetricTable({
        columns: [
          { key: 'a', label: 'A' },
          { key: 'b', label: 'B' },
        ],
        rows: [{ a: '', b: '' }, { x: 'unrelated' }],
      }),
    ).toBeNull();
  });

  it('caps columns at 4 and rows at 12', () => {
    const cols = Array.from({ length: 6 }, (_, i) => ({ key: `c${i}`, label: `L${i}` }));
    const rows = Array.from({ length: 20 }, (_, i) => ({ c0: String(i), c1: 'x' }));
    const data = parseMetricTable({ columns: cols, rows });
    expect(data!.columns).toHaveLength(4);
    expect(data!.rows).toHaveLength(12);
  });

  it('de-duplicates columns by key', () => {
    const data = parseMetricTable({
      columns: [
        { key: 'a', label: 'A' },
        { key: 'a', label: 'A-dup' },
        { key: 'b', label: 'B' },
      ],
      rows: [{ a: '1', b: '2' }],
    });
    expect(data!.columns).toEqual([
      { key: 'a', label: 'A' },
      { key: 'b', label: 'B' },
    ]);
  });

  it('missing cells become empty strings (rendered as em-dash downstream)', () => {
    const data = parseMetricTable({
      columns: [
        { key: 'a', label: 'A' },
        { key: 'b', label: 'B' },
      ],
      rows: [{ a: '1' }], // b missing
    });
    expect(data!.rows).toEqual([{ a: '1', b: '' }]);
  });

  it('rejects non-object / malformed input → null', () => {
    expect(parseMetricTable(null)).toBeNull();
    expect(parseMetricTable('nope')).toBeNull();
    expect(parseMetricTable([1, 2, 3])).toBeNull();
    expect(parseMetricTable({ columns: 'x', rows: 'y' })).toBeNull();
    expect(parseMetricTable({})).toBeNull();
  });
});
