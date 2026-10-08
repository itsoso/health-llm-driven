import { render, screen } from '@testing-library/react';
import MarkdownRenderer from '../MarkdownRenderer';

const table = '| 项目 | 说明 |\n| --- | --- |\n| 示例 | 可横向阅读的表格 |';
const prefix = `[查看资料](https://example.com)\n\n${table}\n\n`;
const card = '```reva-ui\n' + JSON.stringify({
  v: 1, component: 'metric_empty_state', title: '示例卡片', message: '暂无数据',
}) + '\n```';

describe('streaming Markdown reading continuity', () => {
  it.each(['light', 'dark', 'warm'] as const)('preserves focus and table scroll as %s content grows', variant => {
    const view = render(<MarkdownRenderer variant={variant} content={`${prefix}正在生成`} />);
    const link = screen.getByRole('link');
    const initialTable = screen.getByRole('table');
    const scroller = initialTable.parentElement!;
    link.focus();
    scroller.scrollLeft = 120;

    view.rerender(<MarkdownRenderer variant={variant} content={`${prefix}正在生成后续文字`} />);

    expect(screen.getByRole('link')).toBe(link);
    expect(link).toHaveFocus();
    expect(screen.getByRole('table')).toBe(initialTable);
    expect(scroller.scrollLeft).toBe(120);
    expect(screen.getByText('正在生成后续文字')).toBeVisible();
  });

  it('preserves the existing prose when a streamed card completes', () => {
    const view = render(<MarkdownRenderer variant="warm" content={prefix + '\n\n```reva-ui\n{'} />);
    const link = screen.getByRole('link');
    link.focus();

    view.rerender(<MarkdownRenderer variant="warm" content={`${prefix}${card}`} />);

    expect(screen.getByRole('link')).toBe(link);
    expect(link).toHaveFocus();
    expect(screen.getByText('示例卡片')).toBeVisible();
    expect(screen.queryByText(/```reva-ui/)).toBeNull();
  });

  it('updates the theme and URL when props change', () => {
    const view = render(<MarkdownRenderer variant="light" content="[资料](https://example.com/old)" />);
    view.rerender(<MarkdownRenderer variant="warm" content="[新资料](https://example.com/new)" />);
    expect(screen.getByRole('link', { name: '新资料' })).toHaveAttribute('href', 'https://example.com/new');
    expect(screen.getByRole('link')).toHaveClass('text-[#C96442]');
  });
});

// Opt-in replay through the real renderer; synthetic text, no API or personal data.
describe.runIf(process.env.REVA_MARKDOWN_BENCH === '1')('Markdown render replay', () => {
  it('reports stream update latency and DOM churn', () => {
    const samples: Record<string, unknown>[] = [];
    for (const segmented of [false, true]) {
      const longPrefix = Array.from({ length: 12 }, (_, i) => `## 示例 ${i}\n\n${prefix}`).join('\n\n');
      const content = segmented ? `${longPrefix}${card}\n\n` : longPrefix;
      const view = render(<MarkdownRenderer variant="warm" content={content} />);
      const observer = new MutationObserver(() => {});
      observer.observe(view.container, { childList: true, subtree: true });
      const durations: number[] = [];
      let removedElements = 0;
      for (let i = 0; i < 100; i++) {
        const started = performance.now();
        view.rerender(<MarkdownRenderer variant="warm" content={`${content}${'后续文字'.repeat(i + 1)}`} />);
        durations.push(performance.now() - started);
        for (const record of observer.takeRecords()) {
          removedElements += Array.from(record.removedNodes).filter(node => node.nodeType === 1).length;
        }
      }
      observer.disconnect();
      view.unmount();
      durations.sort((a, b) => a - b);
      samples.push({ segmented, updates: durations.length, removedElements,
        p50: durations[49], p95: durations[94], p99: durations[98] });
    }
    console.info('MARKDOWN_REPLAY', JSON.stringify(samples));
  });
});
