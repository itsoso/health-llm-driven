import React from 'react';
import { render } from '@testing-library/react-native';
import { MetricTableCardView, MetricTableCardSpec } from '../MetricTableCard';
import { renderCard } from '../registry';
import { extractRevaUiBlocks } from '../../../../utils/revaUiBlocks';
import type { MetricTableData } from '../../../../utils/metricTable';

const fixture: MetricTableData = {
  title: '近三次血压',
  columns: [
    { key: 'date', label: '日期' },
    { key: 'sys', label: '收缩压' },
    { key: 'dia', label: '舒张压' },
  ],
  rows: [
    { date: '07-11', sys: '128', dia: '82' },
    { date: '07-12', sys: '124', dia: '79' },
    { date: '07-13', sys: '121', dia: '77' },
  ],
  footnote: '仅供健康管理参考',
};

describe('MetricTableCardView', () => {
  it('renders title, column headers, cell values and footnote', () => {
    const { getByText } = render(<MetricTableCardView {...fixture} />);
    expect(getByText('近三次血压')).toBeTruthy();
    expect(getByText('收缩压')).toBeTruthy();
    expect(getByText('舒张压')).toBeTruthy();
    expect(getByText('07-12')).toBeTruthy();
    expect(getByText('124')).toBeTruthy();
    expect(getByText('79')).toBeTruthy();
    expect(getByText('仅供健康管理参考')).toBeTruthy();
  });

  it('renders empty cells as an em-dash and does not crash', () => {
    const { getByText } = render(
      <MetricTableCardView
        columns={[
          { key: 'a', label: 'A' },
          { key: 'b', label: 'B' },
        ]}
        rows={[{ a: '1', b: '' }]}
      />,
    );
    expect(getByText('—')).toBeTruthy();
  });

  it('renders nothing (empty view, no crash) for malformed data', () => {
    // @ts-expect-error intentionally malformed to exercise the defensive branch
    const tree = render(<MetricTableCardView columns={'nope'} rows={undefined} />);
    expect(tree.toJSON()).toBeTruthy();
    expect(tree.queryByText('日期')).toBeNull();
  });

  it('matches snapshot for the fixture rows', () => {
    const { toJSON } = render(<MetricTableCardView {...fixture} />);
    expect(toJSON()).toMatchSnapshot();
  });
});

describe('MetricTableCardSpec', () => {
  it('is server-only (never locally matched or built)', () => {
    const ctx = {
      query: '给我一个表格',
      query_lower: '给我一个表格',
      toolsUsed: new Set<string>(),
      data: {},
      api: {},
    };
    expect(MetricTableCardSpec.type).toBe('metric_table');
    expect(MetricTableCardSpec.match(ctx)).toBeNull();
    expect(MetricTableCardSpec.build(ctx)).toBeNull();
  });
});

describe('metric_table end-to-end wiring (fence → parser → registry → card)', () => {
  const fenced = [
    '近三次血压如下:',
    '',
    '```reva-ui',
    '{"type":"metric_table","v":1,"title":"近三次血压","columns":[{"key":"date","label":"日期"},{"key":"sys","label":"收缩压"},{"key":"dia","label":"舒张压"}],"rows":[{"date":"07-11","sys":"128","dia":"82"},{"date":"07-12","sys":"124","dia":"79"}],"footnote":"仅供健康管理参考"}',
    '```',
  ].join('\n');

  it('strips the fence from prose and renders through the card registry', () => {
    const { text, cards } = extractRevaUiBlocks(fenced);

    // fence never leaks into prose
    expect(text).toBe('近三次血压如下:');
    expect(text).not.toContain('reva-ui');
    expect(text).not.toContain('metric_table');
    expect(cards).toHaveLength(1);
    expect(cards[0].type).toBe('metric_table');

    const element = renderCard(cards[0]);
    expect(element).not.toBeNull();
    const { getByText } = render(element!);
    expect(getByText('近三次血压')).toBeTruthy();
    expect(getByText('收缩压')).toBeTruthy();
    expect(getByText('124')).toBeTruthy();
    expect(getByText('仅供健康管理参考')).toBeTruthy();
  });
});
