/* eslint-disable import/first */
import React from 'react';
import { Text as MockText } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import type { AgentTurnState } from '../../../utils/agentTurnState';
import type { UIMessage } from '../../../hooks/useChatEngine';

const mockLoadConversation = jest.fn();
const mockNewChat = jest.fn();
const mockSendMessage = jest.fn();
const mockGetConversations = jest.fn();
const mockGetConversationsPage = jest.fn();
const mockDeleteConversation = jest.fn();
const mockChatState = {
  messages: [] as UIMessage[],
  isStreaming: false,
  activeTurn: { phase: 'idle', recoverable: false } as AgentTurnState,
};

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), navigate: jest.fn(), setParams: jest.fn() },
  useLocalSearchParams: () => ({}),
  useFocusEffect: (cb: () => void | (() => void)) => cb(),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: undefined, isLoading: false, isSuccess: false }),
}));

// 今日焦点走 React Query-backed hooks;测试无 QueryClientProvider,mock 掉。
jest.mock('../../../hooks/useTodayTimeline', () => ({
  useTodayTimeline: () => ({ data: undefined }),
}));

jest.mock('@react-navigation/bottom-tabs', () => ({
  useBottomTabBarHeight: () => 83,
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    ...mockChatState,
    conversationId: undefined,
    sendMessage: mockSendMessage,
    newChat: mockNewChat,
    loadLatestConversation: jest.fn(),
    loadConversation: mockLoadConversation,
    loadMoreHistory: jest.fn(),
    hasMoreHistory: false,
    deleteCurrentConversation: jest.fn(),
    setMessages: jest.fn(),
  }),
}));

jest.mock('../../../services/chat', () => ({
  getConversations: (...args: any[]) => mockGetConversations(...args),
  getConversationsPage: (...args: any[]) => mockGetConversationsPage(...args),
  deleteConversation: (...args: any[]) => mockDeleteConversation(...args),
  updateConversationTitle: jest.fn(),
}));

jest.mock('../../../services/conversationOpener', () => ({
  fetchConversationOpener: jest.fn().mockResolvedValue(null),
  fetchConversationStarters: jest.fn().mockResolvedValue({ opener: null, suggestions: [], onboarding: false }),
}));

jest.mock('../../../services/memoryOpener', () => ({
  fetchMemoryOpener: jest.fn().mockResolvedValue([]),
}));

jest.mock('../../../services/llmPreference', () => ({
  getLlmPreference: jest.fn().mockResolvedValue({ model_id: null, options: [] }),
  updateLlmPreference: jest.fn(),
}));

jest.mock('../../../services/actionCards', () => ({
  recordCardAdherence: jest.fn().mockResolvedValue({}),
}));

jest.mock('../ChatInputBar', () => {
  const MockChatInputBar = () => <MockText>ChatInputBar</MockText>;
  MockChatInputBar.displayName = 'MockChatInputBar';
  return MockChatInputBar;
});
jest.mock('../BrandCircle', () => {
  const MockBrandCircle = ({ children }: any) => <MockText>{children}</MockText>;
  MockBrandCircle.displayName = 'MockBrandCircle';
  return MockBrandCircle;
});
jest.mock('../ChatBubble', () => {
  const MockChatBubble = () => <MockText>ChatBubble</MockText>;
  MockChatBubble.displayName = 'MockChatBubble';
  return MockChatBubble;
});
jest.mock('../OpenerCard', () => {
  const MockOpenerCard = () => <MockText>OpenerCard</MockText>;
  MockOpenerCard.displayName = 'MockOpenerCard';
  return MockOpenerCard;
});

import ChatScreen from '../../../app/(tabs)/chat';

describe('ChatScreen history entry', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockChatState.messages = [];
    mockChatState.isStreaming = false;
    mockChatState.activeTurn = { version: 1, phase: 'idle', turnId: null, recoverable: false, hadWrite: false };
    // 历史列表现在走分页接口 getConversationsPage (返回 { items, total })
    mockGetConversationsPage.mockResolvedValue({
      items: [
        {
          id: 88,
          title: '恢复能力分析',
          created_at: '2026-05-14T09:00:00Z',
          updated_at: '2026-05-14T09:30:00Z',
        },
      ],
      total: 1,
    });
  });

  it('opens conversation history from the coach header', async () => {
    const { getByLabelText, findByText } = render(<ChatScreen />);

    await act(async () => {
      fireEvent.press(getByLabelText('对话历史'));
    });

    await waitFor(() => expect(mockGetConversationsPage).toHaveBeenCalled());
    expect(await findByText('恢复能力分析')).toBeTruthy();
  });

  it('starts a new chat directly from the visible header entry', async () => {
    const { getByLabelText } = render(<ChatScreen />);

    expect(getByLabelText('新建对话')).toBeTruthy();
    await act(async () => {
      fireEvent.press(getByLabelText('新建对话'));
    });

    expect(mockNewChat).toHaveBeenCalledTimes(1);
  });

  it('keeps processing progress in the assistant turn without a duplicate top strip', async () => {
    mockChatState.isStreaming = true;
    mockChatState.activeTurn = { ...mockChatState.activeTurn, phase: 'running', label: '正在理解你的问题' };
    mockChatState.messages = [{ id: 'active-ui-preview', role: 'assistant', content: '', streaming: true }];
    const { queryByTestId, getByText } = render(<ChatScreen />);
    await act(async () => {});
    expect(getByText('ChatBubble')).toBeTruthy();
    expect(queryByTestId('chat-today-focus-card')).toBeNull();
  });

  it.each([
    ['partial', '部分完成，请查看未完成的事项'],
    ['waiting_for_user', '等待你确认或补充信息'],
    ['failed', '上一轮未完成，内容已保留'],
  ] as const)('retains the %s outcome strip after processing', async (phase, label) => {
    mockChatState.isStreaming = true; // A late stream cleanup must not hide a terminal warning.
    mockChatState.activeTurn = { ...mockChatState.activeTurn, phase };
    const { getByText } = render(<ChatScreen />);
    await act(async () => {});
    expect(getByText(label)).toBeTruthy();
  });
});
