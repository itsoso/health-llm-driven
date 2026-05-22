import { buildSelectedChatShareMessage, isShareableChatMessage } from '../chatShareSelection';

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
      '【健康 Agent】',
      '今晚把明天事项写成 3 条清单。',
      '',
      '— 健康 Agent 对话节选',
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
});
