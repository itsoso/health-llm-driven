import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ChatView from '../ChatView';

describe('ChatView copy action', () => {
  it('changes the assistant copy action in place after the clipboard write succeeds', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(
      <ChatView
        messages={[{
          id: 7,
          role: 'assistant',
          content: '今天先补水 300ml。',
          created_at: '2026-07-17T12:00:00.000Z',
        }]}
        loading={false}
        doneMessageIds={new Set([7])}
        messageFeedback={{}}
        onFeedback={vi.fn()}
      />,
    );

    const copyButton = screen.getByTitle('复制');
    fireEvent.click(copyButton);

    await waitFor(() => expect(screen.getByTitle('已复制')).toBeInTheDocument());
    expect(writeText).toHaveBeenCalledWith('今天先补水 300ml。');
  });
});
