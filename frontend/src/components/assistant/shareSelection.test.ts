import { describe, expect, it } from 'vitest';

import {
  buildSelectedChatShareText,
  durableSelectedMessageIds,
} from './shareSelection';

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

describe('durableSelectedMessageIds', () => {
  it('returns positive durable ids in conversation order', () => {
    expect(durableSelectedMessageIds([
      { id: 11, role: 'user', content: '问题' },
      { id: 12, role: 'assistant', content: '回答' },
    ], new Set([12, 11]))).toEqual([11, 12]);
  });

  it('fails closed for optimistic local message ids', () => {
    expect(() => durableSelectedMessageIds([
      { id: -1, role: 'assistant', content: '仍在生成' },
    ], new Set([-1]))).toThrow('selected_agent_message_not_durable');
  });
});
