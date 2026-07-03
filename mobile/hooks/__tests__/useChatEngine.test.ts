import { act, renderHook, waitFor } from '@testing-library/react-native';

const mockStreamChat = jest.fn();
const mockGetConversations = jest.fn();
const mockGetConversationMessages = jest.fn();
const mockDeleteConversation = jest.fn();
const mockRenderServerCards = jest.fn();
let mockAsyncStorage: Record<string, string> = {};

jest.mock('expo-router', () => ({
  useFocusEffect: (cb: any) => {
    const React = require('react');
    React.useEffect(() => cb(), [cb]);
  },
}));

jest.mock('../../services/chat', () => ({
  streamChat: (...args: any[]) => mockStreamChat(...args),
  getConversations: (...args: any[]) => mockGetConversations(...args),
  getConversationMessages: (...args: any[]) => mockGetConversationMessages(...args),
  deleteConversation: (...args: any[]) => mockDeleteConversation(...args),
}));

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (key: string) => mockAsyncStorage[key] ?? null),
  setItem: jest.fn(async (key: string, value: string) => { mockAsyncStorage[key] = value; }),
  removeItem: jest.fn(async (key: string) => { delete mockAsyncStorage[key]; }),
}));

jest.mock('../../components/chat/cards', () => ({
  dispatchCard: jest.fn().mockResolvedValue(null),
  renderServerCards: (...args: any[]) => mockRenderServerCards(...args),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {},
  BASE_URL: 'https://example.test/api/v1',
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: jest.fn(),
}));

import { restoreMessagesFromHistory, useChatEngine } from '../useChatEngine';

let finishStream: (() => void) | undefined;
let failStream: (() => void) | undefined;

async function* streamStartThenWait() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamStartThenTimeout() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    failStream = resolve;
  });
  throw new Error('请求超时');
}

async function* streamStartToolThenWait() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'tool', toolName: 'weather_context', content: '' };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'token', content: '今天户外运动建议先看空气质量。' };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamThoughtsThenWait() {
  yield { type: 'start', conversationId: 777, thought: '正在理解你的问题' };
  yield { type: 'tool', toolName: 'health_query', content: '', thought: '读取健康数据' };
  yield { type: 'tool', toolName: 'health_query', content: '', toolSuccess: true, thought: '已取得健康数据' };
  yield { type: 'token', content: '今晚优先固定睡眠时间。' };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamTokenCardThenWait() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '我先把这顿饭识别为待确认记录。' };
  yield {
    type: 'card',
    anchor: 'after-token-1',
    card: {
      type: 'diet',
      data: { items: ['鸡蛋', '牛奶'] },
      actions: [
        {
          id: 'confirm-diet',
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/12/confirm',
          payload: { write_intent_id: 12 },
          requires_manual_confirm: true,
        },
      ],
    },
  };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// 快路由: 一批 token 紧挨着到达 (worst case for the ~80ms 攒批 throttle).
// 攒批后终态必须是逐 token 顺序拼接, 不丢字、不乱序.
const BURST_TOKENS = ['第一', '段。', '第二', '段。', '第三', '段。', '收尾。'];
async function* streamTokenBurstThenDone() {
  yield { type: 'start', conversationId: 777 };
  for (const t of BURST_TOKENS) {
    yield { type: 'token', content: t };
  }
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// 攒批后走 error 分支: 已接收 token 必须先 flush, 再拼错误尾巴.
async function* streamTokenBurstThenError() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '开头一段' };
  yield { type: 'token', content: '还没说完' };
  yield { type: 'error', content: '请求出错，请稍后再试' };
}

async function* streamQuotaErrorAsToken() {
  yield { type: 'start', conversationId: 777, thought: '正在理解你的问题' };
  yield {
    type: 'token',
    content: "Agent 执行遇到问题: Error code: 429 - {'error': {'message': 'Your token-plan quota has been exhausted.', 'type': 'insufficient_quota', 'code': 'insufficient_quota'}}",
  };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

describe('useChatEngine', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAsyncStorage = {};
    finishStream = undefined;
    failStream = undefined;
    mockGetConversations.mockResolvedValue([]);
    mockGetConversationMessages.mockResolvedValue({ total_messages: 0, messages: [] });
    mockDeleteConversation.mockResolvedValue(true);
    mockRenderServerCards.mockImplementation((cards: any[]) => Array.isArray(cards) ? cards : []);
  });

  it('restores persisted safe thinking steps from assistant history meta', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 42,
        role: 'assistant',
        content: '今天饮食总结如下。',
        created_at: '2026-07-03T12:00:00Z',
        meta: {
          thinking_steps: ['正在理解你的问题', '读取记录信息', '整理回复中'],
          thinking_steps_kind: 'safe_progress_summary',
        },
      },
    ]);

    expect(restored[0]).toEqual(expect.objectContaining({
      role: 'assistant',
      content: '今天饮食总结如下。',
      thinkingSteps: ['正在理解你的问题', '读取记录信息', '整理回复中'],
    }));
  });

  it('restores the last active conversation after the chat page is remounted', async () => {
    mockAsyncStorage['chat:last_conversation_id:v1'] = '321';
    mockGetConversationMessages.mockResolvedValueOnce({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '上一轮问题', created_at: '2026-05-22T10:00:00Z' },
        { id: 2, role: 'assistant', content: '上一轮回答', created_at: '2026-05-22T10:00:10Z' },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.loadLatestConversation();
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(321);
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ role: 'assistant', content: '上一轮回答' }),
        ]),
      );
    });
    expect(mockGetConversationMessages).toHaveBeenCalledWith(321, { days: 7 });
    expect(mockGetConversations).not.toHaveBeenCalledWith('每日健康简报');
  });

  it('can force a context entry to start a new server conversation', async () => {
    mockAsyncStorage['chat:last_conversation_id:v1'] = '321';
    mockGetConversationMessages.mockResolvedValueOnce({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '上一轮问题', created_at: '2026-05-22T10:00:00Z' },
        { id: 2, role: 'assistant', content: '上一轮回答', created_at: '2026-05-22T10:00:10Z' },
      ],
    });
    mockStreamChat.mockImplementation(streamStartThenWait);

    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.loadLatestConversation();
    });
    await waitFor(() => expect(result.current.conversationId).toBe(321));

    act(() => {
      void result.current.sendMessage(
        '请基于我近 7 天睡眠数据分析今晚最该调整的 3 件事。',
        null,
        { extraContext: '{"from":"sleep/7d"}', forceNewConversation: true } as any,
      );
    });

    await waitFor(() => {
      expect(mockStreamChat).toHaveBeenCalledWith(
        '请基于我近 7 天睡眠数据分析今晚最该调整的 3 件事。',
        undefined,
        undefined,
        expect.any(AbortSignal),
        '{"from":"sleep/7d"}',
      );
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('shows a visible thinking assistant bubble immediately after sending', async () => {
    mockStreamChat.mockImplementation(streamStartThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请基于杭州天气调整今天安排');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: true,
            content: '⏳ AI 正在思考中...',
          }),
        ]),
      );
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('keeps the thinking bubble while empty tool events arrive before text tokens', async () => {
    mockStreamChat.mockImplementation(streamStartToolThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请结合天气、空气质量和日程安排户外活动');
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'assistant',
          streaming: true,
          content: '⏳ AI 正在思考中...',
        }),
      ]),
    );

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            content: '今天户外运动建议先看空气质量。',
          }),
        ]),
      );
    });
  });

  it('streams safe thinking steps separately from assistant answer text', async () => {
    mockStreamChat.mockImplementation(streamThoughtsThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('分析我最近 7 天睡眠');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: true,
            content: '今晚优先固定睡眠时间。',
            thinkingSteps: expect.arrayContaining([
              '正在理解你的问题',
              '读取健康数据',
              '已取得健康数据',
            ]),
          }),
        ]),
      );
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('batches bursty tokens without dropping or reordering (攒批终态逐段拼接)', async () => {
    mockStreamChat.mockImplementation(streamTokenBurstThenDone);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('快路由压测');
    });

    // 终态: 逐 token 顺序拼接, 一字不差 (最后一批必 flush).
    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe(BURST_TOKENS.join(''));
      expect(assistant?.streaming).toBe(false);
    });
  });

  it('flushes buffered tokens before an error tail (攒批不吞已接收内容)', async () => {
    mockStreamChat.mockImplementation(streamTokenBurstThenError);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('中途报错');
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      // 已接收的两批 token 都保留 (未被吞), 且顺序不变, 位于错误尾巴 (❌) 之前.
      const content = assistant?.content ?? '';
      expect(content).toContain('开头一段还没说完');
      expect(content).toContain('❌');
      expect(content.indexOf('开头一段还没说完')).toBeLessThan(content.indexOf('❌'));
    });
  });

  it('sanitizes provider quota errors that arrive as legacy token text', async () => {
    mockStreamChat.mockImplementation(streamQuotaErrorAsToken);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('我适合怎样的锻炼');
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toContain('模型额度');
      expect(assistant?.content).toContain('切换模型');
      expect(assistant?.content).not.toContain('insufficient_quota');
      expect(assistant?.content).not.toContain('token-plan quota');
      expect(assistant?.content).not.toContain('Error code: 429');
    });
  });

  it('inserts streamed server cards before the assistant done event', async () => {
    mockStreamChat.mockImplementation(streamTokenCardThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('吃了两个鸡蛋一杯牛奶');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: true,
            content: '我先把这顿饭识别为待确认记录。',
          }),
          expect.objectContaining({
            role: 'assistant',
            content: '',
            cardType: 'diet',
            cardData: { items: ['鸡蛋', '牛奶'] },
            cardActions: [
              expect.objectContaining({
                action: 'write_intent.confirm',
                requires_manual_confirm: true,
              }),
            ],
          }),
        ]),
      );
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('keeps the local streaming assistant bubble when conversation id arrives mid-stream', async () => {
    mockStreamChat.mockImplementation(streamStartThenWait);
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 1,
      messages: [
        {
          id: 1,
          role: 'user',
          content: '请分析这些图片',
          created_at: '2026-05-16T21:19:00Z',
          image_url: '["/uploads/chat/test.jpg"]',
        },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请分析这些图片', [
        { uri: 'file:///lab-report.jpg', base64: 'abc123', type: 'jpeg' },
      ]);
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'assistant',
          streaming: true,
        }),
      ]),
    );
    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'user',
          imageUris: ['file:///lab-report.jpg'],
        }),
      ]),
    );

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('recovers the server answer when a local stream times out after leaving the page', async () => {
    mockStreamChat.mockImplementation(streamStartThenTimeout);
    mockGetConversationMessages.mockResolvedValueOnce({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '继续分析图片记录饮食', created_at: '2026-05-22T23:30:00Z' },
        { id: 2, role: 'assistant', content: '已从服务端恢复的完整回答', created_at: '2026-05-22T23:31:00Z' },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('继续分析图片记录饮食');
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    await act(async () => {
      await Promise.resolve();
      failStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ role: 'assistant', content: '已从服务端恢复的完整回答' }),
        ]),
      );
    });
    expect(result.current.messages).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ content: expect.stringContaining('请求超时') }),
      ]),
    );
    expect(mockGetConversationMessages).toHaveBeenCalledWith(777, { days: 7 });
  });
});
