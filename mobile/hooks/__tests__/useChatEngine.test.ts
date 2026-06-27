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

import { useChatEngine } from '../useChatEngine';

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

async function* streamCardBeforeDone() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '今天先降低强度。' };
  yield {
    type: 'card',
    card: {
      type: 'workout',
      data: { title: '低强度恢复跑' },
      actions: [{ action: 'confirm_write_intent', payload: { id: 9 } }],
    },
    anchor: 'after_current_token',
  };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
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
    mockRenderServerCards.mockReturnValue([]);
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

  it('inserts a server card while the assistant stream is still running', async () => {
    mockStreamChat.mockImplementation(streamCardBeforeDone);
    mockRenderServerCards.mockImplementation((cards: any[]) => cards.map((card, index) => ({
      type: card.type,
      data: card.data,
      actions: card.actions,
      key: `card-${index}`,
    })));

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('今天怎么练');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            content: '今天先降低强度。',
            streaming: true,
          }),
          expect.objectContaining({
            role: 'assistant',
            content: '',
            cardType: 'workout',
            cardData: { title: '低强度恢复跑' },
            cardActions: [{ action: 'confirm_write_intent', payload: { id: 9 } }],
          }),
        ]),
      );
    });

    expect(result.current.isStreaming).toBe(true);

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages.filter(m => m.cardType === 'workout')).toHaveLength(1);
      expect(result.current.isStreaming).toBe(false);
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
