/* eslint-disable import/first */
import React from 'react';
import { Text as MockText } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockLoadConversation = jest.fn();
const mockNewChat = jest.fn();
const mockSendMessage = jest.fn();
const mockGetConversations = jest.fn();
const mockGetConversationsPage = jest.fn();
const mockDeleteConversation = jest.fn();

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), navigate: jest.fn(), setParams: jest.fn() },
  useLocalSearchParams: () => ({}),
  useFocusEffect: (cb: () => void | (() => void)) => cb(),
}));

// 今日简报条走 React Query 的 useTodayTimeline;测试无 QueryClientProvider,mock 掉。
jest.mock('../../../hooks/useTodayTimeline', () => ({
  useTodayTimeline: () => ({ data: undefined }),
}));

jest.mock('@react-navigation/bottom-tabs', () => ({
  useBottomTabBarHeight: () => 83,
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    messages: [],
    isStreaming: false,
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
  fetchConversationStarters: jest.fn().mockResolvedValue({ opener: null, suggestions: [] }),
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
// BriefingStrip 依赖 React Query provider, 本 suite 无 provider → mock 掉。
jest.mock('../BriefingStrip', () => {
  const MockBriefingStrip = () => <MockText>BriefingStrip</MockText>;
  MockBriefingStrip.displayName = 'MockBriefingStrip';
  return MockBriefingStrip;
});

import ChatScreen from '../../../app/(tabs)/chat';

describe('ChatScreen history entry', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
});
