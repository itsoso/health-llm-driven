// @vitest-environment jsdom

import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import MetricTableCard, { coerceMetricTable, type RevaUiMetricTableData } from '../MetricTableCard';

const fixture: RevaUiMetricTableData = {
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
};

describe('MetricTableCard', () => {
  it('renders title, column headers, cell values and footnote', () => {
    render(<MetricTableCard data={fixture} variant="warm" />);
    const card = screen.getByTestId('reva-ui-metric-table-card');
    expect(within(card).getByText('近3天关键指标')).toBeInTheDocument();
    ['指标', '数值', '状态'].forEach(h =>
      expect(within(card).getByRole('columnheader', { name: h })).toBeInTheDocument(),
    );
    expect(within(card).getByRole('cell', { name: '睡眠' })).toBeInTheDocument();
    expect(within(card).getByRole('cell', { name: '7.5h' })).toBeInTheDocument();
    expect(within(card).getByRole('cell', { name: '偏优' })).toBeInTheDocument();
    expect(within(card).getByText('仅供健康管理参考，不替代诊断。')).toBeInTheDocument();
  });

  it('falls back to column key when a label is missing', () => {
    render(
      <MetricTableCard
        data={{ ...fixture, title: undefined, footnote: undefined, columns: [{ key: 'raw_key' }, { key: 'v', label: '值' }] }}
        variant="light"
      />,
    );
    expect(screen.getByRole('columnheader', { name: 'raw_key' })).toBeInTheDocument();
  });

  it('renders nothing when there are no valid columns or rows', () => {
    const { container } = render(
      <MetricTableCard data={{ type: 'metric_table', v: 1, columns: [], rows: [] }} variant="warm" />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe('coerceMetricTable', () => {
  it('accepts a well-formed table (type discriminant)', () => {
    expect(coerceMetricTable(fixture)).not.toBeNull();
  });

  it('accepts component === metric_table as a fallback discriminant', () => {
    const { type: _drop, ...rest } = fixture;
    expect(coerceMetricTable({ ...rest, component: 'metric_table' })).not.toBeNull();
  });

  it('rejects non-table blocks', () => {
    expect(coerceMetricTable({ component: 'metric_line_chart', v: 1 } as RevaUiMetricTableData)).toBeNull();
  });

  it('rejects a table with no rows', () => {
    expect(coerceMetricTable({ ...fixture, rows: [] })).toBeNull();
  });

  it('rejects a table whose columns lack string keys', () => {
    expect(
      coerceMetricTable({ ...fixture, columns: [{ label: 'no key' } as { key?: string; label?: string }] }),
    ).toBeNull();
  });
});
