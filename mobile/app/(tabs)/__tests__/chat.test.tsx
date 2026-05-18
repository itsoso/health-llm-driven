/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockOpenHistory = jest.fn();
const mockPush = jest.fn();
const mockSendMessage = jest.fn();
const mockFetchConversationOpener = jest.fn();
const mockRecordCardAdherence = jest.fn();

jest.mock('expo-router', () => ({
  router: { push: mockPush, setParams: jest.fn() },
  useLocalSearchParams: () => ({}),
  useFocusEffect: (cb: any) => cb(),
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    messages: [],
    isStreaming: false,
    conversationId: undefined,
    sendMessage: mockSendMessage,
    newChat: jest.fn(),
    loadLatestConversation: jest.fn(),
    loadConversation: jest.fn(),
  }),
}));

jest.mock('../../../services/chat', () => ({
  deleteConversation: jest.fn(),
  getConversations: (...args: any[]) => mockOpenHistory(...args),
}));

jest.mock('../../../services/conversationOpener', () => ({
  fetchConversationOpener: (...args: any[]) => mockFetchConversationOpener(...args),
  buildConversationOpenerReplyContext: (opener: any, reply: string) => JSON.stringify({
    entry: 'conversation_opener_quick_reply',
    user_reply: reply,
    opener_text: opener.text,
    source: opener.source,
    source_id: opener.source_id ?? null,
    deep_link: opener.deep_link ?? null,
    action_card_id: opener.source === 'action_card_due' ? opener.source_id ?? null : null,
  }),
  buildConversationOpenerReplyMessage: (opener: any, reply: string) => `针对「${opener.text}」：${reply}`,
}));

jest.mock('../../../services/memoryOpener', () => ({
  fetchMemoryOpener: jest.fn().mockResolvedValue([]),
}));

jest.mock('../../../services/llmPreference', () => ({
  getLlmPreference: jest.fn().mockResolvedValue({ model_id: null, options: [] }),
  updateLlmPreference: jest.fn(),
}));

jest.mock('../../../services/actionCards', () => ({
  recordCardAdherence: (...args: any[]) => mockRecordCardAdherence(...args),
}));

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      brand: '#0A8F8F',
      brandLight: '#E6F7F7',
      labelPrimary: '#111',
      labelSecondary: '#555',
      labelTertiary: '#888',
      separator: '#eee',
      red: '#f00',
    },
  }),
}));

jest.mock('../../../components/chat/ChatBubble', () => 'ChatBubble');
jest.mock('../../../components/chat/BrandCircle', () => 'BrandCircle');
jest.mock('../../../components/chat/ConversationSheet', () => 'ConversationSheet');
jest.mock('../../../components/chat/OpenerCard', () => {
  const React = require('react');
  const { Pressable, Text } = require('react-native');
  const MockOpenerCard = ({ opener, onQuickReply }: any) => (
    <Pressable accessibilityLabel="opener-done" onPress={() => onQuickReply(opener.quick_replies[0])}>
      <Text>{opener.text}</Text>
      <Text>{opener.quick_replies[0]}</Text>
    </Pressable>
  );
  MockOpenerCard.displayName = 'MockOpenerCard';
  return MockOpenerCard;
});
jest.mock('../../../components/chat/ChatInputBar', () => 'ChatInputBar');

import ChatScreen from '../chat';

describe('ChatScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockOpenHistory.mockResolvedValue([]);
    mockFetchConversationOpener.mockResolvedValue(null);
    mockRecordCardAdherence.mockResolvedValue({});
  });

  it('shows a visible history entry on the private coach page', async () => {
    const { getByText, getByLabelText } = render(<ChatScreen />);

    expect(getByText('历史')).toBeTruthy();
    await waitFor(() => {
      expect(getByText('历史')).toBeTruthy();
    });
    await act(async () => {
      fireEvent.press(getByLabelText('对话历史'));
    });

    expect(mockOpenHistory).toHaveBeenCalled();
  });

  it('sends opener quick replies with the opener context so verification has a target', async () => {
    mockFetchConversationOpener.mockResolvedValueOnce({
      text: '今天就是「AI 预测：7 天体重保持 ≤ 71.3kg」的检验日，做到了吗？',
      source: 'action_card_due',
      source_id: 88,
      quick_replies: ['做到了 ✅', '没做 ❌', '调整下计划'],
      deep_link: '/action-cards/88',
      priority: 100,
    });

    const { getByLabelText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('opener-done')).toBeTruthy());
    fireEvent.press(getByLabelText('opener-done'));

    expect(mockSendMessage).toHaveBeenCalledWith(
      expect.stringContaining('AI 预测：7 天体重保持 ≤ 71.3kg'),
      null,
      expect.objectContaining({
        extraContext: expect.stringContaining('AI 预测：7 天体重保持 ≤ 71.3kg'),
      }),
    );
    expect(mockSendMessage.mock.calls[0][0]).toContain('做到了 ✅');
    const extraContext = mockSendMessage.mock.calls[0][2].extraContext;
    expect(JSON.parse(extraContext)).toMatchObject({
      entry: 'conversation_opener_quick_reply',
      user_reply: '做到了 ✅',
      source: 'action_card_due',
      source_id: 88,
    });
    await waitFor(() => {
      expect(mockRecordCardAdherence).toHaveBeenCalledWith(88, 70, 'self_reported');
    });
  });
});
