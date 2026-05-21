import { buildSelectedChatShareMessage } from '../chatShareSelection';

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
});
