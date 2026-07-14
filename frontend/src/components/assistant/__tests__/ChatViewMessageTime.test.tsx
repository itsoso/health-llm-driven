import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import ChatView from '../ChatView';
import type { ChatMessage } from '@/services/api/ai';

vi.mock('../MarkdownRenderer', () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));

function renderChat(messages: ChatMessage[]) {
  return render(
    <ChatView
      messages={messages}
      loading={false}
      doneMessageIds={new Set(messages.map(message => message.id))}
      messageFeedback={{}}
      onFeedback={vi.fn()}
    />,
  );
}

describe('ChatView message time', () => {
  it('adds stable hover and accessibility time metadata to each message row', () => {
    renderChat([
      {
        id: 1,
        role: 'user',
        content: '飞机准备起飞 记录下来',
        created_at: '2026-07-14T04:30:00.000Z',
      },
      {
        id: 2,
        role: 'assistant',
        content: '已记录。',
        created_at: '2026-07-14T04:31:00.000Z',
      },
    ]);

    expect(screen.getByLabelText(/你发送于/)).toHaveAttribute('title', expect.stringContaining('2026'));
    expect(screen.getByLabelText(/小巴回复于/)).toHaveAttribute('title', expect.stringContaining('2026'));
    expect(screen.getAllByTestId('message-hover-time')).toHaveLength(2);
  });
});
