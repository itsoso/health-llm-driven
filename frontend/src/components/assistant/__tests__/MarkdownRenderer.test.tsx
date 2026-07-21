// @vitest-environment jsdom

import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import MarkdownRenderer, { splitRevaUiSegments } from '../MarkdownRenderer';

const METRIC_TABLE_JSON = JSON.stringify({
  type: 'metric_table',
  v: 1,
  title: '近3天关键指标',
  columns: [
    { key: 'metric', label: '指标' },
    { key: 'value', label: '数值' },
    { key: 'status', label: '状态' },
  ],
  rows: [
    { metric: '睡眠', value: '7.5h', status: '良好' },
    { metric: '静息心率', value: '52 bpm', status: '偏优' },
  ],
  footnote: '仅供健康管理参考，不替代诊断。',
});

describe('MarkdownRenderer', () => {
  it('never renders raw executable HTML from assistant content', () => {
    const { container } = render(
      <MarkdownRenderer
        variant="light"
        content={'<img src=x onerror="alert(1)"><script>alert(2)</script>\n[bad](javascript:alert(3))'}
      />,
    );

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a')?.getAttribute('href') || '').not.toMatch(/^javascript:/i);
  });

  it('renders GFM tables for shared assistant messages', () => {
    render(
      <MarkdownRenderer
        variant="light"
        content={[
          '5月21日 健康简报',
          '',
          '| 指标 | 数值 | 状态 |',
          '| --- | --- | --- |',
          '| 睡眠 | 95分 | ✅ 优秀 |',
          '| 饮水 | 0ml/2000ml | ⚠️ 未达标 |',
        ].join('\n')}
      />,
    );

    const table = screen.getByRole('table');
    expect(within(table).getByRole('columnheader', { name: '指标' })).toBeInTheDocument();
    expect(within(table).getByRole('cell', { name: '0ml/2000ml' })).toBeInTheDocument();
  });

  it('renders reva-ui chart blocks as cards instead of leaking JSON code', () => {
    render(
      <MarkdownRenderer
        variant="light"
        content={[
          '最近一周睡眠时长趋势如下:',
          '',
          '```reva-ui',
          '{"v":1,"schema":"reva.metric_line_chart.v1","component":"metric_line_chart","metric":"sleep","range":"7d","title":"睡眠时长趋势","unit":"h","x":["06-24","06-25","06-26"],"series":[{"name":"每日值","points":[5.8,13.7,8.3]}],"annotations":[{"x":"06-25","label":"最高 13.7h","kind":"warn"}],"source":"garmin","data_note":"基于 3 天真实数据"}',
          '```',
        ].join('\n')}
      />,
    );

    expect(screen.getByText('睡眠时长趋势')).toBeInTheDocument();
    expect(screen.getByText('基于 3 天真实数据')).toBeInTheDocument();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
    expect(screen.queryByText(/"component":"metric_line_chart"/)).toBeNull();
  });

  it('renders reva-ui metric empty-state cards instead of leaking JSON code', () => {
    render(
      <MarkdownRenderer
        variant="light"
        content={[
          '最近一周血糖暂无足够数据:',
          '',
          '```reva-ui',
          '{"v":1,"schema":"reva.metric_empty_state.v1","component":"metric_empty_state","metric":"blood_glucose","range":"7d","title":"血糖数据不足","message":"暂无足够数据，至少需要 3 天真实记录后才能生成趋势图。","suggestions":["同步 HealthKit 或可穿戴设备数据","补录最近几天的关键指标"],"boundary":"仅用于健康管理参考，不替代诊断或治疗。"}',
          '```',
        ].join('\n')}
      />,
    );

    expect(screen.getByText('血糖数据不足')).toBeInTheDocument();
    expect(screen.getByText(/至少需要 3 天真实记录/)).toBeInTheDocument();
    expect(screen.getByText('同步 HealthKit 或可穿戴设备数据')).toBeInTheDocument();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
    expect(screen.queryByText(/"component":"metric_empty_state"/)).toBeNull();
  });

  it('renders reva-ui metric_table blocks as a card instead of leaking JSON code', () => {
    render(
      <MarkdownRenderer
        variant="warm"
        content={['近三天概览:', '', '```reva-ui', METRIC_TABLE_JSON, '```'].join('\n')}
      />,
    );

    const card = screen.getByTestId('reva-ui-metric-table-card');
    expect(within(card).getByText('近3天关键指标')).toBeInTheDocument();
    expect(within(card).getByRole('columnheader', { name: '状态' })).toBeInTheDocument();
    expect(within(card).getByRole('cell', { name: '52 bpm' })).toBeInTheDocument();
    expect(within(card).getByText('仅供健康管理参考，不替代诊断。')).toBeInTheDocument();
    // 叙事正文保留, 原始围栏/JSON 不外泄
    expect(screen.getByText('近三天概览:')).toBeInTheDocument();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
    expect(screen.queryByText(/"type":"metric_table"/)).toBeNull();
  });

  it('strips a malformed metric_table fence silently (no raw JSON in prose)', () => {
    render(
      <MarkdownRenderer
        variant="warm"
        content={['概览:', '', '```reva-ui', '{"type":"metric_table","v":1,"columns":[bad json', '```'].join('\n')}
      />,
    );
    expect(screen.getByText('概览:')).toBeInTheDocument();
    expect(screen.queryByTestId('reva-ui-metric-table-card')).toBeNull();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
    expect(screen.queryByText(/bad json/)).toBeNull();
  });

  it('strips an unknown reva-ui component silently', () => {
    render(
      <MarkdownRenderer
        variant="warm"
        content={['概览:', '', '```reva-ui', '{"v":1,"type":"pie_chart","slices":[1,2,3]}', '```'].join('\n')}
      />,
    );
    expect(screen.getByText('概览:')).toBeInTheDocument();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
    expect(screen.queryByText(/pie_chart/)).toBeNull();
  });

  it('does not leak a partial (unclosed) metric_table fence mid-stream', () => {
    // 流式中途: fence 还没收尾, 半截 JSON 不能以代码块/裸文本闪现
    render(
      <MarkdownRenderer
        variant="warm"
        content={['近三天概览:', '', '```reva-ui', '{"type":"metric_table","v":1,"title":"近3天关'].join('\n')}
      />,
    );
    expect(screen.getByText('近三天概览:')).toBeInTheDocument();
    expect(screen.queryByTestId('reva-ui-metric-table-card')).toBeNull();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
    expect(screen.queryByText(/metric_table/)).toBeNull();
  });
});

describe('splitRevaUiSegments (reva-ui parser)', () => {
  it('extracts a valid metric_table into a table segment', () => {
    const segments = splitRevaUiSegments(['前言', '', '```reva-ui', METRIC_TABLE_JSON, '```'].join('\n'));
    const table = segments.find(s => s.kind === 'table');
    expect(table).toBeDefined();
    expect(table && table.kind === 'table' && table.data.columns).toHaveLength(3);
    expect(table && table.kind === 'table' && table.data.rows).toHaveLength(2);
  });

  it('drops malformed JSON (no table segment)', () => {
    const segments = splitRevaUiSegments(['x', '```reva-ui', '{not json', '```'].join('\n'));
    expect(segments.some(s => s.kind === 'table')).toBe(false);
    expect(segments.every(s => s.kind !== 'markdown' || !s.text.includes('reva-ui'))).toBe(true);
  });

  it('drops an unknown component type (no non-markdown segment)', () => {
    const segments = splitRevaUiSegments(['```reva-ui', '{"v":1,"type":"pie_chart"}', '```'].join('\n'));
    expect(segments.every(s => s.kind === 'markdown')).toBe(true);
  });

  it('strips an unclosed partial fence and never surfaces its bytes', () => {
    const segments = splitRevaUiSegments(['keep', '', '```reva-ui', '{"type":"metric_table","v":1,"tit'].join('\n'));
    expect(segments.some(s => s.kind === 'table')).toBe(false);
    const markdown = segments.filter(s => s.kind === 'markdown').map(s => (s as { text: string }).text).join('');
    expect(markdown).toContain('keep');
    expect(markdown).not.toContain('reva-ui');
    expect(markdown).not.toContain('metric_table');
  });

  it('coerces a table missing rows into a dropped block', () => {
    const segments = splitRevaUiSegments(
      ['```reva-ui', '{"type":"metric_table","v":1,"columns":[{"key":"a"}],"rows":[]}', '```'].join('\n'),
    );
    expect(segments.some(s => s.kind === 'table')).toBe(false);
  });
});
