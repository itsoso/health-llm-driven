import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import type { ChatMessage } from '@/services/api/ai';
import ChatView from '../ChatView';
import { projectServerCards } from '../inlineCards/serverCardProjection';

// Synthetic content only: exercise the real markdown, card and transparency renderers.
const content = `本周睡眠列表：

| 日期 | 睡眠时长 |
| --- | --- |
| 测试日 | 8 小时 |

血氧：本例没有可用数据，不作推断。

建议：先保持规律作息。`;
const sleep = { type: 'sleep', data: { score: 80, duration_h: 8 } };
const base: ChatMessage = {
  id: 7, role: 'assistant', content, created_at: '2026-09-23T15:40:00Z',
  elapsed_ms: 1000, completion_status: 'complete',
};
const props = { loading: false, messageFeedback: {}, onFeedback: vi.fn() };

function withCards(cards: unknown[]): ChatMessage {
  const projected = projectServerCards(cards);
  return {
    ...base,
    ...(projected ? {
      card_type: projected.type, card_data: projected.data, card_actions: projected.actions,
    } : {}),
  };
}

function expectFullAnswer() {
  expect(screen.getByRole('table')).toHaveTextContent('测试日');
  expect(screen.getByText('血氧：本例没有可用数据，不作推断。')).toBeVisible();
  expect(screen.getByText('建议：先保持规律作息。')).toBeVisible();
  expect(screen.getByText('睡眠分析')).toBeVisible();
  expect(screen.getByTitle('复制')).toBeInTheDocument();
  expect(screen.getByText(/透视/)).toBeInTheDocument();
}

describe('ChatView cards supplement the complete answer', () => {
  it('keeps streamed table and narrative when done attaches a server sleep card', () => {
    const view = render(<ChatView {...props} messages={[base]} doneMessageIds={new Set()} />);
    expect(screen.getByRole('table')).toHaveTextContent('测试日');
    view.rerender(<ChatView {...props} messages={[withCards([
      { type: 'system_knowledge_evidence', data: { private_internal: 'not UI text' } },
      { type: 'runtime_agenda', data: {} }, sleep,
    ])]} doneMessageIds={new Set([7])} />);
    expectFullAnswer();
    expect(screen.queryByText('not UI text')).not.toBeInTheDocument();
  });

  it('restores history with all known cards and copies the full narrative', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    render(<ChatView {...props} messages={[withCards([
      sleep, { type: 'vitals', data: { sleep: 'synthetic-vitals' } },
    ])]} doneMessageIds={new Set([7])} />);
    expectFullAnswer();
    expect(screen.getByText('synthetic-vitals')).toBeVisible();
    fireEvent.click(screen.getByTitle('复制'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(content));
  });

  it('still renders a card-only historical message with its timestamp', () => {
    render(<ChatView {...props} messages={[{ ...withCards([sleep]), content: '' }]}
      doneMessageIds={new Set([7])} />);
    expect(screen.getByText('睡眠分析')).toBeVisible();
    expect(screen.getByTestId('message-hover-time')).toBeInTheDocument();
    expect(screen.queryByTitle('复制')).not.toBeInTheDocument();
  });

  it('preserves narrative when an unknown historical card cannot render', () => {
    render(<ChatView {...props} messages={[{ ...base, card_type: 'unknown', card_data: {} }]}
      doneMessageIds={new Set([7])} />);
    expect(screen.getByRole('table')).toHaveTextContent('测试日');
    expect(screen.getByTitle('复制')).toBeInTheDocument();
  });
});
