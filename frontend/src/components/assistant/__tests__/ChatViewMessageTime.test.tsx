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

  it('keeps hover time out of normal flex layout so it cannot force message wrapping', () => {
    renderChat([
      {
        id: 1,
        role: 'user',
        content: '这是一条比较长的用户消息，时间不应该占据 flex 宽度把正文挤换行',
        created_at: '2026-07-14T04:30:00.000Z',
      },
      {
        id: 2,
        role: 'assistant',
        content: '已记录。',
        created_at: '2026-07-14T04:31:00.000Z',
      },
    ]);

    for (const row of [
      screen.getByLabelText(/你发送于/),
      screen.getByLabelText(/小巴回复于/),
    ]) {
      expect(row).toHaveClass('relative');
    }
    for (const pill of screen.getAllByTestId('message-hover-time')) {
      expect(pill).toHaveClass('absolute');
      expect(pill).not.toHaveClass('shrink-0');
    }
  });

  it('renders sparse centered time dividers only for the first message and larger gaps', () => {
    renderChat([
      {
        id: 1,
        role: 'user',
        content: '第一条',
        created_at: '2026-07-14T12:30:00',
      },
      {
        id: 2,
        role: 'assistant',
        content: '一分钟内回复',
        created_at: '2026-07-14T12:31:00',
      },
      {
        id: 3,
        role: 'user',
        content: '七分钟后继续',
        created_at: '2026-07-14T12:38:00',
      },
    ]);

    expect(screen.getAllByTestId('message-time-divider')).toHaveLength(2);
  });
});
