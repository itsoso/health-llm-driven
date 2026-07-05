jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

import api from '../api';
import {
  buildConversationOpenerReplyContext,
  buildConversationOpenerReplyMessage,
  fetchConversationOpener,
} from '../conversationOpener';

const mockGet = api.get as jest.Mock;

describe('fetchConversationOpener', () => {
  beforeEach(() => jest.clearAllMocks());

  it('returns opener when backend returns one (legacy plain-string quick_replies normalized to {text})', async () => {
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
    // 纯字符串 quick reply → {text} 对象, 无 action。
    expect(out!.quick_replies[0]).toEqual({ text: '做到了 ✅' });
    expect(out!.quick_replies[0].action).toBeUndefined();
  });

  it('parses quick reply action field from the cold-start contract enum', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        opener: {
          text: '欢迎！先从这三件事之一开始吧。',
          source: 'memory_fact',
          source_id: null,
          quick_replies: [
            { text: '拍照记一餐', action: 'photo_meal' },
            { text: '记录体重', action: 'record_weight' },
            { text: '连接设备', action: 'connect_device' },
            { text: '换个话题' },
          ],
          deep_link: null,
          priority: 5,
        },
      },
    });

    const out = await fetchConversationOpener();
    expect(out!.quick_replies).toHaveLength(4);
    expect(out!.quick_replies[0]).toEqual({ text: '拍照记一餐', action: 'photo_meal' });
    expect(out!.quick_replies[1].action).toBe('record_weight');
    expect(out!.quick_replies[2].action).toBe('connect_device');
    // 无 action 的 reply 保持纯文本行为不变。
    expect(out!.quick_replies[3]).toEqual({ text: '换个话题' });
  });

  it('drops an unknown action so the reply degrades to sending its text', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        opener: {
          text: '继续跟进',
          source: 'case_thread',
          source_id: 1,
          quick_replies: [{ text: '打开体检', action: 'open_exam_not_in_enum' }],
          deep_link: null,
          priority: 10,
        },
      },
    });

    const out = await fetchConversationOpener();
    expect(out!.quick_replies[0]).toEqual({ text: '打开体检' });
    expect(out!.quick_replies[0].action).toBeUndefined();
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
      quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }, { text: '调整下计划' }],
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

  it('builds visible quick reply text with the opener target', () => {
    const message = buildConversationOpenerReplyMessage({
      text: '今天就是「AI 预测：7 天体重保持 ≤ 71.3kg」的检验日，做到了吗？',
      source: 'action_card_due',
      source_id: 88,
      quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }],
      priority: 100,
    }, '做到了 ✅');

    expect(message).toContain('AI 预测：7 天体重保持 ≤ 71.3kg');
    expect(message).toContain('做到了 ✅');
  });
});
