import { act, renderHook, waitFor } from '@testing-library/react-native';

const mockStreamChat = jest.fn();
const mockGetConversations = jest.fn();
const mockGetConversationMessages = jest.fn();
const mockDeleteConversation = jest.fn();

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

jest.mock('../../components/chat/cards', () => ({
  dispatchCard: jest.fn().mockResolvedValue(null),
  renderServerCards: jest.fn().mockReturnValue([]),
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

async function* streamStartThenWait() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

describe('useChatEngine', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    finishStream = undefined;
    mockGetConversations.mockResolvedValue([]);
    mockDeleteConversation.mockResolvedValue(true);
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
});
