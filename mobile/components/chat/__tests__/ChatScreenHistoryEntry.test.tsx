/* eslint-disable import/first */
import React from 'react';
import { Text as MockText } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockLoadConversation = jest.fn();
const mockNewChat = jest.fn();
const mockSendMessage = jest.fn();
const mockGetConversations = jest.fn();
const mockDeleteConversation = jest.fn();

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), setParams: jest.fn() },
  useLocalSearchParams: () => ({}),
  useFocusEffect: (cb: () => void | (() => void)) => cb(),
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
  deleteConversation: (...args: any[]) => mockDeleteConversation(...args),
}));

jest.mock('../../../services/conversationOpener', () => ({
  fetchConversationOpener: jest.fn().mockResolvedValue(null),
}));

jest.mock('../../../services/memoryOpener', () => ({
  fetchMemoryOpener: jest.fn().mockResolvedValue([]),
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
    mockGetConversations.mockResolvedValue([
      {
        id: 88,
        title: '恢复能力分析',
        created_at: '2026-05-14T09:00:00Z',
        updated_at: '2026-05-14T09:30:00Z',
      },
    ]);
  });

  it('opens conversation history from the coach header', async () => {
    const { getByLabelText, findByText } = render(<ChatScreen />);

    fireEvent.press(getByLabelText('对话历史'));

    await waitFor(() => expect(mockGetConversations).toHaveBeenCalled());
    expect(await findByText('恢复能力分析')).toBeTruthy();
  });
});
