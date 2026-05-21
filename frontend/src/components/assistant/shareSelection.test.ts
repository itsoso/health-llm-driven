import { describe, expect, it } from 'vitest';

import { buildSelectedChatShareText } from './shareSelection';

describe('buildSelectedChatShareText', () => {
  it('keeps selected messages in conversation order with roles', () => {
    const text = buildSelectedChatShareText([
      { id: 1, role: 'user', content: '我昨晚没睡好', created_at: '2026-05-21T08:00:00Z' },
      { id: 2, role: 'assistant', content: '先别堆高强度训练。', created_at: '2026-05-21T08:01:00Z' },
      { id: 3, role: 'assistant', content: '  ', created_at: '2026-05-21T08:02:00Z' },
    ], new Set([2, 1, 3]));

    expect(text).toBe([
      '【我】',
      '我昨晚没睡好',
      '',
      '【健康 Agent】',
      '先别堆高强度训练。',
      '',
      '— 健康 Agent 对话节选',
    ].join('\n'));
  });
});
