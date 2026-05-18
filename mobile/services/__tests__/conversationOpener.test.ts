jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

import api from '../api';
import { buildConversationOpenerReplyContext, fetchConversationOpener } from '../conversationOpener';

const mockGet = api.get as jest.Mock;

describe('fetchConversationOpener', () => {
  beforeEach(() => jest.clearAllMocks());

  it('returns opener when backend returns one', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        opener: {
          text: '明天就到「提前晚餐」的检验日，目前情况怎么样？',
          source: 'action_card_due',
          source_id: 12,
          quick_replies: ['做到了 ✅', '没做 ❌', '调整下计划'],
          deep_link: '/action-cards/12',
          priority: 100,
        },
      },
    });

    const out = await fetchConversationOpener();
    expect(mockGet).toHaveBeenCalledWith('/agent/conversation-opener');
    expect(out).not.toBeNull();
    expect(out!.text).toContain('提前晚餐');
    expect(out!.source).toBe('action_card_due');
    expect(out!.quick_replies).toHaveLength(3);
  });

  it('returns null when backend says no signals', async () => {
    mockGet.mockResolvedValueOnce({ data: { opener: null } });
    expect(await fetchConversationOpener()).toBeNull();
  });

  it('returns null when backend errors out — chat 启动不该被这个挂', async () => {
    mockGet.mockRejectedValueOnce(new Error('500'));
    expect(await fetchConversationOpener()).toBeNull();
  });

  it('returns null when response shape is unexpected', async () => {
    mockGet.mockResolvedValueOnce({ data: undefined });
    expect(await fetchConversationOpener()).toBeNull();
  });

  it('returns null when data.opener field missing', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    expect(await fetchConversationOpener()).toBeNull();
  });

  it('builds quick reply context for action-card verification replies', () => {
    const context = buildConversationOpenerReplyContext({
      text: '今天就是「AI 预测：7 天体重保持 ≤ 71.3kg」的检验日，做到了吗？',
      source: 'action_card_due',
      source_id: 88,
      quick_replies: ['做到了 ✅', '没做 ❌', '调整下计划'],
      deep_link: '/action-cards/88',
      priority: 100,
    }, '做到了 ✅');

    expect(JSON.parse(context)).toMatchObject({
      entry: 'conversation_opener_quick_reply',
      user_reply: '做到了 ✅',
      opener_text: expect.stringContaining('7 天体重保持 ≤ 71.3kg'),
      source: 'action_card_due',
      source_id: 88,
      action_card_id: 88,
    });
  });
});
