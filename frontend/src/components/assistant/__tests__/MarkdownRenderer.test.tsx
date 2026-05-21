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
});
