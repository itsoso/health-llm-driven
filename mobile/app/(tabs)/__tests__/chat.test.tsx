/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { Keyboard, StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockOpenHistory = jest.fn();
const mockOpenHistoryPage = jest.fn();
const mockPush = jest.fn();
const mockSendMessage = jest.fn();
const mockFetchConversationStarters = jest.fn();
const mockFetchMemoryOpener = jest.fn();
const mockRecordCardAdherence = jest.fn();
const mockRecordCardDecision = jest.fn();
const mockNewChat = jest.fn();
const mockSetMessages = jest.fn();
const mockSetParams = jest.fn();
let mockRouteParams: Record<string, string | undefined> = {};
let mockLlmPreference: any = { model_id: null, options: [] };
let mockMessages: any[] = [];
let mockIsStreaming = false;

jest.mock('expo-router', () => ({
  router: {
    push: (...args: any[]) => mockPush(...args),
    navigate: (...args: any[]) => mockPush(...args),
    setParams: (...args: any[]) => mockSetParams(...args),
  },
  useLocalSearchParams: () => mockRouteParams,
  useFocusEffect: (cb: any) => cb(),
}));

// 今日简报条走 React Query 的 useTodayTimeline;测试无 QueryClientProvider,mock 掉。
jest.mock('../../../hooks/useTodayTimeline', () => ({
  useTodayTimeline: () => ({ data: undefined }),
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
    setMessages: mockSetMessages,
  }),
}));

jest.mock('@react-navigation/bottom-tabs', () => ({
  useBottomTabBarHeight: () => 83,
}));

jest.mock('../../../services/chat', () => ({
  deleteConversation: jest.fn(),
  getConversations: (...args: any[]) => mockOpenHistory(...args),
  // 历史列表现在走分页接口 — 打开 sheet 时调它 (返回 { items, total })
  getConversationsPage: (...args: any[]) => mockOpenHistoryPage(...args),
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
// EmptyStateHome renders real (opening bubble + quick-reply chips). It pulls
// formatOpenerText from the real OpenerCard module, so we do NOT mock OpenerCard.
jest.mock('../../../components/chat/ChatInputBar', () => 'ChatInputBar');
// BriefingStrip 走 React Query, 本 suite 无 provider;
// 它们的内部行为各自有专属测试, 这里 mock 掉避免 provider 依赖。ChatHeader 保留真实 (断言其 DOM)。
jest.mock('../../../components/chat/BriefingStrip', () => 'BriefingStrip');

import ChatScreen from '../chat';

describe('ChatScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // clearAllMocks 不排空 mockResolvedValueOnce 队列 —— 对 fetch mock 显式 reset,
    // 免得上个 test 多排的 once-value 泄漏进下个 test 的 starter/opener 渲染。
    mockFetchConversationStarters.mockReset();
    mockFetchMemoryOpener.mockReset();
    mockOpenHistory.mockResolvedValue([]);
    mockOpenHistoryPage.mockResolvedValue({ items: [], total: 0 });
    mockFetchConversationStarters.mockResolvedValue({ opener: null, suggestions: null });
    mockFetchMemoryOpener.mockResolvedValue([]);
    mockRecordCardAdherence.mockResolvedValue({});
    mockRecordCardDecision.mockResolvedValue({});
    mockRouteParams = {};
    mockLlmPreference = { model_id: null, options: [] };
    mockMessages = [];
    mockIsStreaming = false;
  });

  it('empty chat with nothing to say auto-summons keyboard once opener fetch settles, and bumps on 新建对话', async () => {
    // 阿衡没话可说(opener 缺席 + 无记忆) → fetch 落定后才唤起键盘。
    mockFetchConversationStarters.mockResolvedValue({ opener: null, suggestions: null });
    mockFetchMemoryOpener.mockResolvedValue([]);

    const { UNSAFE_getAllByType, getByLabelText } = render(<ChatScreen />);

    const bar = () => UNSAFE_getAllByType('ChatInputBar' as any)[0];
    // opener fetch 落定后 → token 递增(>0), 键盘唤起。
    let initial = 0;
    await waitFor(() => {
      initial = bar().props.autoFocusToken;
      expect(initial).toBeGreaterThan(0);
    });

    // 新建对话 → 再次递增(新窗口也唤起)
    await act(async () => {
      fireEvent.press(getByLabelText('新建对话'));
    });
    expect(bar().props.autoFocusToken).toBeGreaterThan(initial);
  });

  it('does NOT summon the keyboard when 阿衡 has an opening message (opener present)', async () => {
    // 阿衡有开场消息 → 让话被看见, 不抢键盘。
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '今天就是「提前晚餐」的检验日，做到了吗？',
        source: 'action_card_due',
        source_id: 1,
        quick_replies: ['做到了 ✅', '没做 ❌'],
        deep_link: null,
        priority: 100,
      },
      suggestions: null,
    });
    mockFetchMemoryOpener.mockResolvedValue([]);

    const { UNSAFE_getAllByType, getByText } = render(<ChatScreen />);

    const bar = () => UNSAFE_getAllByType('ChatInputBar' as any)[0];
    // 等 opener 落定。opener.text 在气泡里紧跟折进的问候语, 用正则匹配同一 Text 段。
    await waitFor(() => {
      expect(getByText(/今天就是「提前晚餐」的检验日，做到了吗？/)).toBeTruthy();
    });
    // 键盘 token 始终保持 0 —— 阿衡有话说时不弹键盘。
    expect(bar().props.autoFocusToken).toBe(0);
  });

  it('briefing strip hides on dismiss and stays hidden after 新建对话', async () => {
    const { UNSAFE_getAllByType, UNSAFE_queryAllByType, getByLabelText } = render(<ChatScreen />);

    // 冷启可见(mock 成字符串组件 'BriefingStrip')
    const strips = UNSAFE_getAllByType('BriefingStrip' as any);
    expect(strips.length).toBe(1);
    expect(typeof strips[0].props.onDismiss).toBe('function');

    // 点 X → 隐藏
    await act(async () => {
      strips[0].props.onDismiss();
    });
    expect(UNSAFE_queryAllByType('BriefingStrip' as any).length).toBe(0);
  });

  it('新建对话 hides the briefing strip by default', async () => {
    const { UNSAFE_getAllByType, UNSAFE_queryAllByType, getByLabelText } = render(<ChatScreen />);
    expect(UNSAFE_getAllByType('BriefingStrip' as any).length).toBe(1);

    await act(async () => {
      fireEvent.press(getByLabelText('新建对话'));
    });
    expect(mockNewChat).toHaveBeenCalled();
    expect(UNSAFE_queryAllByType('BriefingStrip' as any).length).toBe(0);
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
      expect(mockOpenHistoryPage).toHaveBeenCalled();
    });
  });

  it('shows 阿衡 in the header and hides the model name inline (revealed on pull-down)', async () => {
    // Agent-native header (2026-07-03): 只露品牌名「阿衡 ⌄」, 模型名收进下拉 sheet。
    // 当前模型仍进 picker trigger 的 accessibilityLabel(供读屏 + 打开 sheet 时勾选)。
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

    const { getByText, queryByText, getByLabelText } = render(<ChatScreen />);

    // 品牌名可见。
    await waitFor(() => {
      expect(getByText('阿衡')).toBeTruthy();
    });
    // 模型名(完整 or 压缩)都不再内联显示在 header。
    expect(queryByText('Qwen3.7 Plus 推理 · 阿里')).toBeNull();
    expect(queryByText('Qwen3.7 Plus')).toBeNull();
    // 但仍可通过 picker trigger 的无障碍标签拿到当前(压缩)模型名 → 点开 sheet 切换。
    await waitFor(() => {
      expect(getByLabelText('切换 AI 模型，当前 Qwen3.7 Plus')).toBeTruthy();
    });
  });

  it('keeps the chat header visually compact without removing controls', async () => {
    const { getByLabelText, getByTestId } = render(<ChatScreen />);

    await waitFor(() => {
      expect(mockFetchConversationStarters).toHaveBeenCalled();
    });

    const styleOf = (node: any) => StyleSheet.flatten(node.props.style);
    const minHitSlop = (node: any) => {
      const { hitSlop } = node.props;
      if (typeof hitSlop === 'number') return hitSlop;
      return Math.min(
        hitSlop?.top ?? 0,
        hitSlop?.right ?? 0,
        hitSlop?.bottom ?? 0,
        hitSlop?.left ?? 0,
      );
    };

    expect(styleOf(getByTestId('chat-header-surface')).minHeight).toBeLessThanOrEqual(40);
    expect(styleOf(getByLabelText('新建对话')).width).toBeLessThanOrEqual(28);
    expect(styleOf(getByLabelText('对话历史')).width).toBeLessThanOrEqual(28);
    expect(styleOf(getByLabelText('更多会诊操作')).width).toBeLessThanOrEqual(28);
    expect(minHitSlop(getByLabelText('新建对话'))).toBeGreaterThanOrEqual(8);
    expect(minHitSlop(getByLabelText('对话历史'))).toBeGreaterThanOrEqual(8);
    expect(minHitSlop(getByLabelText('更多会诊操作'))).toBeGreaterThanOrEqual(8);
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

  it('keeps the chat header compact', async () => {
    const { getByLabelText, getByTestId } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByTestId('chat-header-surface')).toBeTruthy();
    });
    const headerSurface = StyleSheet.flatten(getByTestId('chat-header-surface').props.style);
    expect(headerSurface.minHeight).toBeLessThanOrEqual(42);
    expect(headerSurface.paddingVertical).toBeLessThanOrEqual(2);
    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style).width).toBeLessThanOrEqual(30);
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style).width).toBeLessThanOrEqual(30);
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style).width).toBeLessThanOrEqual(30);
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
      expect(mockOpenHistoryPage).toHaveBeenCalled();
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

    await waitFor(() => expect(getByLabelText('一键回复: 做到了 ✅')).toBeTruthy());
    fireEvent.press(getByLabelText('一键回复: 做到了 ✅'));

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
      expect(getByText(/今天就是「夜间血氧复盘」的检验日，做到了吗？/)).toBeTruthy();
      expect(getByText(/旧记忆/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(getByLabelText('一键回复: 做到了 ✅'));
    });

    await waitFor(() => {
      expect(mockFetchConversationStarters).toHaveBeenCalledTimes(2);
      expect(mockFetchMemoryOpener).toHaveBeenCalledTimes(2);
      expect(queryByText(/今天就是「夜间血氧复盘」的检验日，做到了吗？/)).toBeNull();
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

  it('shows a composer-adjacent chips row with the camera chip first on empty chat', async () => {
    mockFetchConversationStarters.mockResolvedValue({
      opener: null,
      suggestions: [{ text: '分析我的睡眠质量', key: 'sleep', priority: 10 }],
    });

    const { getByLabelText } = render(<ChatScreen />);

    // Fixed 拍照记一餐 chip 存在 → 点击走 proven route push('/diet?capture=photo')。
    await waitFor(() => {
      expect(getByLabelText('拍照记一餐')).toBeTruthy();
    });
    fireEvent.press(getByLabelText('拍照记一餐'));
    expect(mockPush).toHaveBeenCalledWith('/diet?capture=photo');

    // 动态 starter suggestion 也进 composer 行, 点击走既有发送。
    await waitFor(() => {
      expect(getByLabelText('向阿衡提问: 分析我的睡眠质量')).toBeTruthy();
    });
    fireEvent.press(getByLabelText('向阿衡提问: 分析我的睡眠质量'));
    expect(mockSendMessage).toHaveBeenCalledWith('分析我的睡眠质量', null, undefined);
  });

  it('hides the composer chips row once the conversation has messages', async () => {
    mockMessages = [
      { id: 'u-1', role: 'user', content: '早餐吃了鸡蛋' },
      { id: 'a-1', role: 'assistant', content: '好的。', completionStatus: 'complete' },
    ];

    const { queryByLabelText } = render(<ChatScreen />);

    await waitFor(() => expect(mockFetchConversationStarters).toHaveBeenCalled());
    // messages 非空 → composer chips row 不渲染。
    expect(queryByLabelText('拍照记一餐')).toBeNull();
  });

  it('keeps the docked-tab chat composer close to the global tab bar and above the iOS keyboard', async () => {
    const keyboardListeners: Record<string, (event: any) => void> = {};
    jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });

    const { getByTestId } = render(<ChatScreen />);
    await waitFor(() => expect(mockFetchConversationStarters).toHaveBeenCalled());

    // The global tab bar stays docked; the composer only needs a tiny separator breath.
    expect(getByTestId('chat-bottom-spacer')).toHaveStyle({ height: 4 });

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
