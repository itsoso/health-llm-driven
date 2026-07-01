/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { Keyboard } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockOpenHistory = jest.fn();
const mockPush = jest.fn();
const mockSendMessage = jest.fn();
const mockFetchConversationStarters = jest.fn();
const mockFetchMemoryOpener = jest.fn();
const mockRecordCardAdherence = jest.fn();
const mockRecordCardDecision = jest.fn();
const mockNewChat = jest.fn();
const mockSetParams = jest.fn();
let mockRouteParams: Record<string, string | undefined> = {};
let mockLlmPreference: any = { model_id: null, options: [] };
let mockMessages: any[] = [];
let mockIsStreaming = false;

jest.mock('expo-router', () => ({
  router: {
    push: (...args: any[]) => mockPush(...args),
    setParams: (...args: any[]) => mockSetParams(...args),
  },
  useLocalSearchParams: () => mockRouteParams,
  useFocusEffect: (cb: any) => cb(),
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    messages: mockMessages,
    isStreaming: mockIsStreaming,
    conversationId: undefined,
    sendMessage: mockSendMessage,
    newChat: mockNewChat,
    loadLatestConversation: jest.fn(),
    loadConversation: jest.fn(),
  }),
}));

jest.mock('@react-navigation/bottom-tabs', () => ({
  useBottomTabBarHeight: () => 83,
}));

jest.mock('../../../services/chat', () => ({
  deleteConversation: jest.fn(),
  getConversations: (...args: any[]) => mockOpenHistory(...args),
  updateConversationTitle: jest.fn(),
}));

jest.mock('../../../services/conversationOpener', () => ({
  fetchConversationStarters: (...args: any[]) => mockFetchConversationStarters(...args),
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
  fetchMemoryOpener: (...args: any[]) => mockFetchMemoryOpener(...args),
}));

jest.mock('../../../services/llmPreference', () => ({
  getLlmPreference: jest.fn(() => Promise.resolve(mockLlmPreference)),
  updateLlmPreference: jest.fn(),
}));

jest.mock('../../../services/actionCards', () => ({
  recordCardAdherence: (...args: any[]) => mockRecordCardAdherence(...args),
  recordCardDecision: (...args: any[]) => mockRecordCardDecision(...args),
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

jest.mock('../../../components/chat/ChatBubble', () => {
  const React = require('react');
  const { Pressable, Text } = require('react-native');
  const MockChatBubble = ({ item, selectionMode, selected, onToggleSelected, onEnterSelection }: any) => (
    <Pressable
      accessibilityLabel={`message-${item.id}`}
      accessibilityState={selectionMode ? { selected } : undefined}
      onLongPress={() => onEnterSelection?.(item.id)}
      onPress={() => onToggleSelected?.(item.id)}
    >
      <Text>{item.content}</Text>
      <Text>{selectionMode ? (selected ? 'selected' : 'unselected') : 'normal'}</Text>
    </Pressable>
  );
  MockChatBubble.displayName = 'MockChatBubble';
  return MockChatBubble;
});
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
    mockFetchConversationStarters.mockResolvedValue({ opener: null, suggestions: null });
    mockFetchMemoryOpener.mockResolvedValue([]);
    mockRecordCardAdherence.mockResolvedValue({});
    mockRecordCardDecision.mockResolvedValue({});
    mockRouteParams = {};
    mockLlmPreference = { model_id: null, options: [] };
    mockMessages = [];
    mockIsStreaming = false;
  });

  it('shows a visible history entry on the private coach page', async () => {
    const { getAllByText, getByLabelText } = render(<ChatScreen />);

    expect(getAllByText('阿衡').length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(getByLabelText('对话历史')).toBeTruthy();
    });
    await act(async () => {
      fireEvent.press(getByLabelText('对话历史'));
    });

    await waitFor(() => {
      expect(mockOpenHistory).toHaveBeenCalled();
    });
  });

  it('uses a short readable model label in the chat header', async () => {
    mockLlmPreference = {
      model_id: 'qwen3.7-plus',
      options: [
        {
          id: 'qwen3.7-plus',
          label: 'Qwen3.7 Plus 推理 · 阿里',
          provider: '阿里',
          model: 'qwen3.7-plus',
          speed_tier: 'reasoning',
          note: '',
        },
      ],
    };

    const { getByText, queryByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText('Qwen3.7 Plus')).toBeTruthy();
    });
    expect(queryByText('Qwen3.7 Plus 推理 · 阿里')).toBeNull();
  });

  it('opens model switching from the top-left header instead of the more sheet', async () => {
    mockLlmPreference = {
      model_id: 'qwen3.7-plus',
      options: [
        {
          id: 'qwen3.7-plus',
          label: 'Qwen3.7 Plus 推理 · 阿里',
          provider: '阿里',
          model: 'qwen3.7-plus',
          speed_tier: 'reasoning',
          note: '',
        },
        {
          id: 'qwen3.6-plus',
          label: 'Qwen3.6 Plus 推理 · 阿里',
          provider: '阿里',
          model: 'qwen3.6-plus',
          speed_tier: 'reasoning',
          note: '',
        },
      ],
    };

    const { getByLabelText, getByText, queryByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(getByLabelText('更多会诊操作'));
    });
    expect(queryByText('切换 AI 模型')).toBeNull();

    await act(async () => {
      fireEvent.press(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus'));
    });
    expect(getByText('切换 AI 模型')).toBeTruthy();
    expect(queryByText('Qwen3.6 Plus 推理 · 阿里')).toBeNull();
  });

  it('keeps the selected model visible and switchable while a reply is streaming', async () => {
    mockIsStreaming = true;
    mockLlmPreference = {
      model_id: 'qwen3.7-plus',
      options: [
        {
          id: 'qwen3.7-plus',
          label: 'Qwen3.7 Plus 推理 · 阿里',
          provider: '阿里',
          model: 'qwen3.7-plus',
          speed_tier: 'reasoning',
          note: '',
        },
        {
          id: 'minimax-m2.5',
          label: 'MiniMax M2.5 推理 · MiniMax',
          provider: 'MiniMax',
          model: 'minimax-m2.5',
          speed_tier: 'reasoning',
          note: '',
        },
      ],
    };

    const { getByLabelText, getByText, queryByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus')).toBeTruthy();
    });
    expect(getByText('回复中')).toBeTruthy();
    expect(queryByText('正在回复')).toBeNull();

    await act(async () => {
      fireEvent.press(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus'));
    });
    expect(getByText('切换 AI 模型')).toBeTruthy();
  });

  it('starts a new chat from a first-level header action', async () => {
    mockFetchConversationStarters
      .mockResolvedValueOnce({
        opener: null,
        suggestions: [{ text: '今天饮水 300/2000ml，帮我安排剩余补水', key: 'water', priority: 50 }],
      })
      .mockResolvedValueOnce({
        opener: null,
        suggestions: [{ text: '复盘我最近一次跑步（5.2km / 30min / 均心率 145）', key: 'workout', priority: 50 }],
      });

    const { getByLabelText, getByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText('今天饮水 300/2000ml，帮我安排剩余补水')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(getByLabelText('新建对话'));
    });

    await waitFor(() => {
      expect(mockFetchConversationStarters).toHaveBeenCalledTimes(2);
      expect(getByText('复盘我最近一次跑步（5.2km / 30min / 均心率 145）')).toBeTruthy();
    });
    expect(mockNewChat).toHaveBeenCalled();
  });

  it('replaces the low-frequency phone action with first-level history', async () => {
    const { getByLabelText, queryByLabelText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByLabelText('对话历史')).toBeTruthy();
    });
    expect(queryByLabelText('开始语音对话')).toBeNull();
    await act(async () => {
      fireEvent.press(getByLabelText('对话历史'));
    });

    await waitFor(() => {
      expect(mockOpenHistory).toHaveBeenCalled();
    });
    expect(mockPush).not.toHaveBeenCalledWith(expect.objectContaining({
      pathname: '/voice-chat',
    }));
  });

  it('sends opener quick replies with the opener context so verification has a target', async () => {
    mockFetchConversationStarters.mockResolvedValueOnce({
      opener: {
        text: '今天就是「AI 预测：7 天体重保持 ≤ 71.3kg」的检验日，做到了吗？',
        source: 'action_card_due',
        source_id: 88,
        quick_replies: ['做到了 ✅', '没做 ❌', '调整下计划'],
        deep_link: '/action-cards/88',
        priority: 100,
      },
      suggestions: null,
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

  it('refreshes opener and memory state after opener feedback is clicked', async () => {
    mockFetchConversationStarters
      .mockResolvedValueOnce({
        opener: {
          text: '今天就是「夜间血氧复盘」的检验日，做到了吗？',
          source: 'action_card_due',
          source_id: 89,
          quick_replies: ['做到了 ✅', '没做 ❌', '调整下计划'],
          deep_link: '/action-cards/89',
          priority: 100,
        },
        suggestions: null,
      })
      .mockResolvedValueOnce({
        opener: null,
        suggestions: [{ text: '复盘昨晚夜间血氧和睡眠恢复', key: 'recovery_history', priority: 60 }],
      });

    mockFetchMemoryOpener
      .mockResolvedValueOnce([{ id: 1, type: 'medical', type_label: '医疗', content: '旧记忆' }])
      .mockResolvedValueOnce([{ id: 2, type: 'medical', type_label: '医疗', content: '更新后的记忆' }]);

    const { getByLabelText, queryByText, getByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText('今天就是「夜间血氧复盘」的检验日，做到了吗？')).toBeTruthy();
      expect(getByText(/旧记忆/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(getByLabelText('opener-done'));
    });

    await waitFor(() => {
      expect(mockFetchConversationStarters).toHaveBeenCalledTimes(2);
      expect(mockFetchMemoryOpener).toHaveBeenCalledTimes(2);
      expect(queryByText('今天就是「夜间血氧复盘」的检验日，做到了吗？')).toBeNull();
      expect(getByText('复盘昨晚夜间血氧和睡眠恢复')).toBeTruthy();
      expect(getByText(/更新后的记忆/)).toBeTruthy();
    });
  });

  it('uses dynamic starter suggestions when backend provides them', async () => {
    mockFetchConversationStarters.mockResolvedValueOnce({
      opener: null,
      suggestions: [
        { text: '解读我最近一次体检（关注: LDL-C）', key: 'exam', priority: 60 },
        { text: '帮我提升补剂依从率（近7天完成率 42.9%）', key: 'supplement', priority: 70 },
      ],
    });

    const { getByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText('解读我最近一次体检（关注: LDL-C）')).toBeTruthy();
    });
    expect(getByText('帮我提升补剂依从率（近7天完成率 42.9%）')).toBeTruthy();
  });

  it('frames empty chat suggestions as direct next actions with health context', async () => {
    const { getByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText(/阿衡 · 会带上你的健康上下文/)).toBeTruthy();
    });
  });

  it('moves the immersive chat composer above the iOS keyboard without reserving the global tab bar', async () => {
    const keyboardListeners: Record<string, (event: any) => void> = {};
    jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });

    const { getByTestId } = render(<ChatScreen />);
    await waitFor(() => expect(mockFetchConversationStarters).toHaveBeenCalled());

    // Chat tab hides the global tab bar; composer only needs a small home-indicator breath.
    expect(getByTestId('chat-bottom-spacer')).toHaveStyle({ height: 8 });

    act(() => {
      keyboardListeners.keyboardDidShow({
        endCoordinates: { height: 336 },
      });
    });

    expect(getByTestId('chat-bottom-spacer')).toHaveStyle({ height: 336 });
  });

  it('shows a visible cancel action after long-pressing a message into multi-select', async () => {
    mockMessages = [
      { id: 'u-1', role: 'user', content: '早餐吃了鸡蛋和咖啡' },
      { id: 'a-1', role: 'assistant', content: '建议今天午后散步 10 分钟。', completionStatus: 'complete' },
    ];

    const { getByLabelText, getByText, queryByText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('message-u-1')).toBeTruthy());
    await act(async () => {
      fireEvent(getByLabelText('message-u-1'), 'longPress');
    });

    expect(getByText('已选择 1 条')).toBeTruthy();
    await act(async () => {
      fireEvent.press(getByLabelText('取消多选'));
    });

    await waitFor(() => {
      expect(queryByText('已选择 1 条')).toBeNull();
    });
  });

  it('exits multi-select when the last selected message is deselected', async () => {
    mockMessages = [
      { id: 'u-1', role: 'user', content: '早餐吃了鸡蛋和咖啡' },
      { id: 'a-1', role: 'assistant', content: '建议今天午后散步 10 分钟。', completionStatus: 'complete' },
    ];

    const { getByLabelText, getByText, queryByText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('message-u-1')).toBeTruthy());
    await act(async () => {
      fireEvent(getByLabelText('message-u-1'), 'longPress');
    });
    expect(getByText('已选择 1 条')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByLabelText('message-u-1'));
    });

    await waitFor(() => {
      expect(queryByText('已选择 0 条')).toBeNull();
      expect(queryByText('已选择 1 条')).toBeNull();
    });
  });

  it('keeps new chat out of the low-frequency more sheet', async () => {
    mockFetchConversationStarters
      .mockResolvedValueOnce({
        opener: null,
        suggestions: [{ text: '今天饮水 300/2000ml，帮我安排剩余补水', key: 'water', priority: 50 }],
      });

    const { getByLabelText, getByText, queryByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText('今天饮水 300/2000ml，帮我安排剩余补水')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(getByLabelText('更多会诊操作'));
    });

    expect(queryByText('新建对话')).toBeNull();
    expect(queryByText('对话历史')).toBeNull();
    expect(getByText('会诊工具')).toBeTruthy();
  });

  it('starts a new conversation when opened from an Agent context entry', async () => {
    mockRouteParams = {
      prompt: '请基于我近 7 天睡眠数据分析今晚最该调整的 3 件事。',
      context: '{"from":"sleep/7d"}',
      badge: '基于近 7 天睡眠',
      newChat: '1',
    };

    render(<ChatScreen />);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith(
        '请基于我近 7 天睡眠数据分析今晚最该调整的 3 件事。',
        null,
        expect.objectContaining({
          extraContext: '{"from":"sleep/7d"}',
          forceNewConversation: true,
        }),
      );
    });
    expect(mockNewChat).toHaveBeenCalled();
  });

  it('handles a second Agent context entry while the chat tab is already mounted', async () => {
    mockRouteParams = {
      prompt: '先分析睡眠。',
      context: '{"from":"sleep/7d"}',
      badge: '基于睡眠',
      newChat: '1',
    };

    const screen = render(<ChatScreen />);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith(
        '先分析睡眠。',
        null,
        expect.objectContaining({ forceNewConversation: true }),
      );
    });

    mockRouteParams = {
      prompt: '再分析饮食。',
      context: '{"from":"diet/today"}',
      badge: '基于今日饮食',
      newChat: '1',
    };
    screen.rerender(<ChatScreen />);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith(
        '再分析饮食。',
        null,
        expect.objectContaining({
          extraContext: '{"from":"diet/today"}',
          forceNewConversation: true,
        }),
      );
    });
    expect(mockNewChat).toHaveBeenCalledTimes(2);
  });
});
