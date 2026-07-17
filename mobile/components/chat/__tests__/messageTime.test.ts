import { buildMessageTimeDividerItems } from '../messageTime';
import type { UIMessage } from '../../../hooks/useChatEngine';

function message(id: string, createdAt: string): UIMessage {
  return {
    id,
    role: id.startsWith('u') ? 'user' : 'assistant',
    content: id,
    streaming: false,
    createdAt,
  };
}

describe('chat message time dividers', () => {
  it('inserts dividers for the first message and gaps over five minutes', () => {
    const items = buildMessageTimeDividerItems([
      message('u1', '2026-07-14T12:30:00'),
      message('a2', '2026-07-14T12:31:00'),
      message('u3', '2026-07-14T12:38:00'),
    ]);

    expect(items.map(item => item.type)).toEqual(['divider', 'message', 'message', 'divider', 'message']);
    expect(items.filter(item => item.type === 'divider')).toHaveLength(2);
  });
});
