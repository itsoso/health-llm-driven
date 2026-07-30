import {
  buildSelectedChatShareMessage,
  durableSelectedAgentMessageIds,
  isShareableChatMessage,
} from '../chatShareSelection';

describe('buildSelectedChatShareMessage', () => {
  it('formats selected chat messages in visible order', () => {
    const text = buildSelectedChatShareMessage([
      { id: 'h-10', role: 'user', content: '明天有事我会睡不好' },
      { id: 'h-11', role: 'assistant', content: '今晚把明天事项写成 3 条清单。' },
      { id: 'h-12', role: 'assistant', content: '', cardType: 'daily_plan' },
    ], new Set(['h-11', 'h-10', 'h-12']));

    expect(text).toBe([
      '【我】',
      '明天有事我会睡不好',
      '',
      '【小巴】',
      '今晚把明天事项写成 3 条清单。',
      '',
      '— 小巴对话节选',
    ].join('\n'));
  });

  it('does not share interrupted assistant messages', () => {
    const interrupted = {
      id: 'h-20',
      role: 'assistant' as const,
      content: '## 检查计划\n| 时间 | 行动 |\n| **报',
      completionStatus: 'interrupted' as const,
    };

    expect(isShareableChatMessage(interrupted)).toBe(false);
    expect(buildSelectedChatShareMessage([interrupted], new Set(['h-20']))).toBe('');
  });

  it('returns empty string when no message is selected', () => {
    expect(
      buildSelectedChatShareMessage(
        [{ id: 'h-30', role: 'user', content: '你好' }],
        new Set<string>(),
      ),
    ).toBe('');
  });

  it('returns empty string when all selected messages are blank or unshareable', () => {
    const text = buildSelectedChatShareMessage(
      [
        { id: 'h-40', role: 'user', content: '   ' },
        { id: 'h-41', role: 'assistant', content: '', cardType: 'daily_plan' },
        { id: 'h-42', role: 'assistant', content: '在思考…', streaming: true },
      ],
      new Set(['h-40', 'h-41', 'h-42']),
    );
    expect(text).toBe('');
  });

  it('trims content and only keeps selected ids', () => {
    const text = buildSelectedChatShareMessage(
      [
        { id: 'h-50', role: 'user', content: '  早上好  ' },
        { id: 'h-51', role: 'assistant', content: '今天多喝水。' },
      ],
      new Set(['h-50']),
    );
    expect(text).toBe(['【我】', '早上好', '', '— 小巴对话节选'].join('\n'));
  });

  it('includes selected chat photos as markdown image references', () => {
    const text = buildSelectedChatShareMessage(
      [
        {
          id: 'h-60',
          role: 'user',
          content: '记录这餐',
          imageUris: ['https://health.executor.life/api/v1/upload/files/chat/3/meal.jpg?signature=abc'],
        },
      ],
      new Set(['h-60']),
    );

    expect(text).toBe([
      '【我】',
      '记录这餐',
      '',
      '![对话图片 1](https://health.executor.life/api/v1/upload/files/chat/3/meal.jpg?signature=abc)',
      '',
      '— 小巴对话节选',
    ].join('\n'));
  });

  describe('isShareableChatMessage', () => {
    it('accepts a finished assistant reply with content', () => {
      expect(
        isShareableChatMessage({ id: 'a', role: 'assistant', content: '建议如下' }),
      ).toBe(true);
    });

    it('rejects streaming, card, blank, and length-truncated messages', () => {
      expect(isShareableChatMessage({ id: 'b', role: 'assistant', content: 'x', streaming: true })).toBe(false);
      expect(isShareableChatMessage({ id: 'c', role: 'assistant', content: 'x', cardType: 'daily_plan' })).toBe(false);
      expect(isShareableChatMessage({ id: 'd', role: 'user', content: '   ' })).toBe(false);
      expect(
        isShareableChatMessage({ id: 'e', role: 'assistant', content: '部分内容[回复因长度限制中断]' }),
      ).toBe(false);
    });
  });
});

describe('durableSelectedAgentMessageIds', () => {
  it('returns only server-owned ids in visible conversation order', () => {
    expect(durableSelectedAgentMessageIds([
      { id: 'local-u', role: 'user', content: '问题', sourceMessageId: 41 },
      { id: 'local-a', role: 'assistant', content: '回答', sourceMessageId: 42 },
    ], new Set(['local-a', 'local-u']))).toEqual([41, 42]);
  });

  it.each([
    {
      message: { id: 'local-u', role: 'user' as const, content: '尚未落库' },
      selected: new Set(['local-u']),
    },
    {
      message: {
        id: 'local-a',
        role: 'assistant' as const,
        content: '生成中',
        sourceMessageId: 42,
        streaming: true,
      },
      selected: new Set(['local-a']),
    },
  ])('fails closed when a selected message is not durably shareable', ({ message, selected }) => {
    expect(() => durableSelectedAgentMessageIds([message], selected))
      .toThrow('selected_agent_message_not_durable');
  });

  it('allows a completed durable selection while another message is streaming', () => {
    expect(durableSelectedAgentMessageIds([
      {
        id: 'old-a',
        role: 'assistant',
        content: '已经保存的旧回答',
        sourceMessageId: 42,
      },
      {
        id: 'new-a',
        role: 'assistant',
        content: '正在生成的新回答',
        streaming: true,
      },
    ], new Set(['old-a']))).toEqual([42]);
  });
});
