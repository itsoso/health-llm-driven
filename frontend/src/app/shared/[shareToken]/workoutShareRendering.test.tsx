import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MarkdownRenderer from '@/components/assistant/MarkdownRenderer';
import { normalizeSharedAgentContent } from './contentNormalizer';

const legacy = '跑步摘要\n本次跑步。 | 指标 | 本次数据 | 评价 ||---|---|---|| 距离 | 2km | 增加 | | 时长 | 18分钟 | 放缓 | | 平均心率 | 130 bpm | 合理强度。\n— 小巴健康';

describe('shared workout report rendering', () => {
  it('renders a flattened legacy workout table including its unclosed last row', () => {
    const content = normalizeSharedAgentContent(legacy);
    render(<MarkdownRenderer content={content} variant="light" />);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getAllByRole('columnheader').map(x => x.textContent)).toEqual(['指标', '本次数据', '评价']);
    expect(screen.getAllByRole('row')).toHaveLength(4);
    expect(screen.getByText('130 bpm')).toBeTruthy();
    expect(screen.getByText('— 小巴健康')).toBeTruthy();
    expect(normalizeSharedAgentContent(content)).toBe(content);
  });

  it('keeps a flattened signature outside the table and preserves incomplete fragments', () => {
    const repaired = normalizeSharedAgentContent(legacy.replace(/\n/g, ' '));
    expect(repaired).toContain('合理强度。 |\n\n— 小巴健康');
    const incomplete = '| 指标 | 本次数据 | 评价 ||---|---|---|| 距离 |';
    expect(normalizeSharedAgentContent(incomplete)).toBe(incomplete);
  });

  it('preserves valid Markdown, ordinary pipes, and fenced code', () => {
    for (const text of ['选择 A | B', '| 指标 | 本次数据 | 评价 |\n| --- | --- | --- |\n| 距离 | 2km | 稳定 |', '```text\n' + legacy + '\n```']) {
      expect(normalizeSharedAgentContent(text)).toBe(text);
    }
  });

  it('does not enable HTML execution while repairing a legacy table', () => {
    const { container } = render(<MarkdownRenderer content={normalizeSharedAgentContent(legacy.replace('增加', '<img src=x onerror=alert(1)>'))} variant="light" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
  });
});
