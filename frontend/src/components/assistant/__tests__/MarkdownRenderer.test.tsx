// @vitest-environment jsdom

import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import MarkdownRenderer from '../MarkdownRenderer';

describe('MarkdownRenderer', () => {
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
});
