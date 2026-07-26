/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { Alert, FlatList, Keyboard, StyleSheet } from 'react-native';
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
const mockLoadLatestConversation = jest.fn();
const mockLoadMoreHistory = jest.fn();
const mockSaveChatImageToLibrary = jest.fn();
const mockShareImage = jest.fn();
let mockRouteParams: Record<string, string | undefined> = {};
let mockLlmPreference: any = { model_id: null, options: [] };
let mockMessages: any[] = [];
let mockIsStreaming = false;
let mockActiveTurn: any = { phase: 'idle', recoverable: false, label: undefined };
let mockHasMoreHistory = false;
let mockIsLoadingMoreHistory = false;
let mockTodayTimelineData: any = undefined;
let mockTodayDynamicViewData: any = undefined;
let mockDailyPlanData: any = undefined;

jest.mock('expo-router', () => ({
  router: {
    push: (...args: any[]) => mockPush(...args),
    navigate: (...args: any[]) => mockPush(...args),
    setParams: (...args: any[]) => mockSetParams(...args),
  },
  useLocalSearchParams: () => mockRouteParams,
  useFocusEffect: (cb: any) => cb(),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = JSON.stringify(queryKey);
    if (key.includes('today-dynamic-view')) {
      return { data: mockTodayDynamicViewData, isLoading: false, isSuccess: Boolean(mockTodayDynamicViewData) };
    }
    if (key.includes('daily-plan')) {
      return { data: mockDailyPlanData, isLoading: false, isSuccess: Boolean(mockDailyPlanData) };
    }
    return { data: undefined, isLoading: false, isSuccess: false };
  },
}));

// 今日焦点走 React Query 的 useTodayTimeline;测试无 QueryClientProvider,mock 掉。
jest.mock('../../../hooks/useTodayTimeline', () => ({
  useTodayTimeline: () => ({ data: mockTodayTimelineData }),
}));

jest.mock('../../../hooks/useChatEngine', () => ({
  useChatEngine: () => ({
    messages: mockMessages,
    isStreaming: mockIsStreaming,
    activeTurn: mockActiveTurn,
    conversationId: undefined,
    sendMessage: mockSendMessage,
    newChat: mockNewChat,
    loadLatestConversation: mockLoadLatestConversation,
    loadConversation: jest.fn(),
    loadMoreHistory: mockLoadMoreHistory,
    hasMoreHistory: mockHasMoreHistory,
    isLoadingMoreHistory: mockIsLoadingMoreHistory,
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

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ token: 'review-token' }),
}));

jest.mock('../../../services/chatImageSave', () => ({
  saveChatImageToLibrary: (...args: any[]) => mockSaveChatImageToLibrary(...args),
}));

jest.mock('../../../utils/share', () => ({
  shareImage: (...args: any[]) => mockShareImage(...args),
  shareLocalImage: jest.fn(),
  sharePlainText: jest.fn(),
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
  const MockChatBubble = ({ item, selectionMode, selected, onToggleSelected, onEnterSelection, onViewImage }: any) => (
    <>
      <Pressable
        accessibilityLabel={`message-${item.id}`}
        accessibilityState={selectionMode ? { selected } : undefined}
        onLongPress={() => onEnterSelection?.(item.id)}
        onPress={() => onToggleSelected?.(item.id)}
      >
        <Text>{item.content}</Text>
        <Text>{selectionMode ? (selected ? 'selected' : 'unselected') : 'normal'}</Text>
      </Pressable>
      {item.imageUris?.[0] ? (
        <Pressable
          accessibilityLabel={`open-image-${item.id}`}
          onPress={() => onViewImage?.(item.imageUris[0])}
        />
      ) : null}
    </>
  );
  MockChatBubble.displayName = 'MockChatBubble';
  return MockChatBubble;
});
jest.mock('../../../components/chat/BrandCircle', () => 'BrandCircle');
jest.mock('../../../components/chat/ConversationSheet', () => 'ConversationSheet');
// EmptyStateHome renders real (opening bubble + quick-reply chips). It pulls
// formatOpenerText from the real OpenerCard module, so we do NOT mock OpenerCard.
jest.mock('../../../components/chat/ChatInputBar', () => 'ChatInputBar');

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
    mockFetchConversationStarters.mockResolvedValue({ opener: null, suggestions: null, onboarding: false });
    mockFetchMemoryOpener.mockResolvedValue([]);
    mockRecordCardAdherence.mockResolvedValue({});
    mockRecordCardDecision.mockResolvedValue({});
    mockRouteParams = {};
    mockLlmPreference = { model_id: null, options: [] };
    mockMessages = [];
    mockIsStreaming = false;
    mockActiveTurn = { phase: 'idle', recoverable: false, label: undefined };
    mockHasMoreHistory = false;
    mockIsLoadingMoreHistory = false;
    mockTodayTimelineData = undefined;
    mockTodayDynamicViewData = undefined;
    mockDailyPlanData = undefined;
    mockLoadLatestConversation.mockResolvedValue(undefined);
    mockSaveChatImageToLibrary.mockResolvedValue(undefined);
    mockShareImage.mockResolvedValue(undefined);
  });

  it('lets the reviewer save an image from the full-screen preview', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    mockMessages = [{
      id: 'photo-1',
      role: 'user',
      content: '午餐照片',
      imageUris: ['https://health.executor.life/api/v1/upload/files/chat/7/meal.jpg'],
    }];
    const view = render(<ChatScreen />);

    fireEvent.press(view.getByLabelText('open-image-photo-1'));
    fireEvent(view.getByLabelText('预览图片，长按可保存或分享'), 'longPress');

    const actions = alertSpy.mock.calls.at(-1)?.[2] as any[];
    await act(async () => {
      actions.find(action => action.text === '保存到相册').onPress();
      await Promise.resolve();
    });

    expect(mockSaveChatImageToLibrary).toHaveBeenCalledWith({
      uri: 'https://health.executor.life/api/v1/upload/files/chat/7/meal.jpg',
      headers: { Authorization: 'Bearer review-token' },
    });
  });

  it('lets the reviewer share a protected image from the full-screen preview', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    mockMessages = [{
      id: 'photo-2',
      role: 'user',
      content: '晚餐照片',
      imageUris: ['https://health.executor.life/api/v1/upload/files/chat/8/dinner.jpg'],
    }];
    const view = render(<ChatScreen />);

    fireEvent.press(view.getByLabelText('open-image-photo-2'));
    fireEvent(view.getByLabelText('预览图片，长按可保存或分享'), 'longPress');

    const actions = alertSpy.mock.calls.at(-1)?.[2] as any[];
    await act(async () => {
      actions.find(action => action.text === '分享图片').onPress();
      await Promise.resolve();
    });

    expect(mockShareImage).toHaveBeenCalledWith(
      'https://health.executor.life/api/v1/upload/files/chat/8/dinner.jpg',
      {
        target: 'more',
        cacheKey: 'viewer-image',
        headers: { Authorization: 'Bearer review-token' },
      },
    );
  });

  it('keeps one stable bootstrap shell until history, opener, and memory settle', async () => {
    let resolveStarters!: (value: any) => void;
    let resolveMemory!: (value: any[]) => void;
    let resolveHistory!: () => void;
    mockFetchConversationStarters.mockReturnValueOnce(new Promise(resolve => { resolveStarters = resolve; }));
    mockFetchMemoryOpener.mockReturnValueOnce(new Promise(resolve => { resolveMemory = resolve; }));
    mockLoadLatestConversation.mockReturnValueOnce(new Promise<void>(resolve => { resolveHistory = resolve; }));

    const view = render(<ChatScreen />);

    expect(view.getByLabelText('正在准备小巴')).toBeTruthy();
    expect(view.queryByText('今天的健康状况如何？')).toBeNull();
    expect(view.queryByText(/今天先确认午餐记录/)).toBeNull();

    await act(async () => {
      resolveStarters({
        opener: {
          text: '今天先确认午餐记录。',
          source: 'daily_focus',
          quick_replies: [],
          priority: 10,
        },
        suggestions: [{ text: '查询全天饮食', key: 'diet', priority: 10 }],
        onboarding: false,
      });
      resolveMemory([{ id: 1, type: 'diet', type_label: '饮食', content: '关注晚餐时间' }]);
      await Promise.resolve();
    });
    expect(view.getByLabelText('正在准备小巴')).toBeTruthy();
    expect(view.queryByText(/今天先确认午餐记录/)).toBeNull();

    await act(async () => {
      resolveHistory();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(view.queryByLabelText('正在准备小巴')).toBeNull();
      expect(view.getByText(/今天先确认午餐记录/)).toBeTruthy();
      expect(view.getByText('依据 1 条饮食')).toBeTruthy();
      expect(view.queryByText('查询全天饮食')).toBeNull();
    });
  });

  it('empty chat with nothing to say auto-summons keyboard once opener fetch settles, and bumps on 新建对话', async () => {
    // 小巴没话可说(opener 缺席 + 无记忆) → fetch 落定后才唤起键盘。
    mockFetchConversationStarters.mockResolvedValue({ opener: null, suggestions: null, onboarding: false });
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

  it('routes empty-state meal photo capture through the chat composer', async () => {
    mockFetchConversationStarters.mockResolvedValue({ opener: null, suggestions: null, onboarding: false });
    mockFetchMemoryOpener.mockResolvedValue([]);

    const { UNSAFE_getAllByType, getByLabelText } = render(<ChatScreen />);
    const bar = () => UNSAFE_getAllByType('ChatInputBar' as any)[0];

    await waitFor(() => {
      expect(bar().props.autoFocusToken).toBeGreaterThan(0);
    });
    const before = bar().props.captureMealPhotoToken ?? 0;

    await act(async () => {
      fireEvent.press(getByLabelText('拍照记一餐'));
    });

    expect(mockPush).not.toHaveBeenCalledWith('/diet?capture=photo&return_to=chat');
    expect(bar().props.captureMealPhotoToken).toBeGreaterThan(before);
  });

  it('does NOT summon the keyboard when 小巴 has an opening message (opener present)', async () => {
    // 小巴有开场消息 → 让话被看见, 不抢键盘。
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '今天就是「提前晚餐」的检验日，做到了吗？',
        source: 'action_card_due',
        source_id: 1,
        quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }],
        deep_link: null,
        priority: 100,
      },
      suggestions: null,
      onboarding: false,
    });
    mockFetchMemoryOpener.mockResolvedValue([]);

    const { UNSAFE_getAllByType, getByText } = render(<ChatScreen />);

    const bar = () => UNSAFE_getAllByType('ChatInputBar' as any)[0];
    // 等 opener 落定。opener.text 在气泡里紧跟折进的问候语, 用正则匹配同一 Text 段。
    await waitFor(() => {
      expect(getByText(/今天就是「提前晚餐」的检验日，做到了吗？/)).toBeTruthy();
    });
    // 键盘 token 始终保持 0 —— 小巴有话说时不弹键盘。
    expect(bar().props.autoFocusToken).toBe(0);
  });

  it('does not reserve conversation header space for an unscheduled pending action', () => {
    mockTodayTimelineData = {
      date: '2026-07-16',
      current_window: 'afternoon',
      now: 'timeline-1',
      items: [{
        id: 'timeline-1',
        kind: 'action',
        time_window: 'afternoon',
        title: '餐后步行 10 分钟',
        subtitle: '现在可以做',
        icon: 'walk-outline',
        color: '#1F8A5B',
        status: 'pending',
        priority: 9,
        can_complete: true,
        complete_ref: null,
        deep_link: '/agenda',
        severity: null,
        proof: null,
      }],
      past: { completed_count: 1, events: [] },
      counts: { actionable: 2, overdue: 0, info: 0 },
    };

    const { queryByTestId, queryByText } = render(<ChatScreen />);

    expect(queryByTestId('chat-today-focus-card')).toBeNull();
    expect(queryByText('餐后步行 10 分钟')).toBeNull();
    expect(queryByText('今日重点')).toBeNull();
  });

  it('shows one direct context strip for a due action', () => {
    mockTodayTimelineData = {
      items: [{
        id: 'timeline-1', kind: 'action', title: '记录体重和腰围', subtitle: '现在可以做',
        status: 'due', priority: 9, can_complete: true, deep_link: '/agenda',
      }],
      past: { completed_count: 0, events: [] },
      counts: { actionable: 1, overdue: 0, info: 0 },
    };

    const { getByText, queryByText } = render(<ChatScreen />);

    expect(getByText('现在')).toBeTruthy();
    expect(getByText('记录体重和腰围')).toBeTruthy();
    expect(queryByText('现在最重要')).toBeNull();
    expect(queryByText(/接下来/)).toBeNull();
  });

  it('dismisses a due hint completely and keeps Today available in more actions', async () => {
    mockTodayTimelineData = {
      items: [{
        id: 'timeline-1', kind: 'action', title: '记录体重和腰围', subtitle: '现在可以做',
        status: 'due', priority: 9, can_complete: true, deep_link: '/agenda',
      }],
      past: { completed_count: 0, events: [] },
      counts: { actionable: 1, overdue: 0, info: 0 },
    };

    const view = render(<ChatScreen />);

    expect(view.getByText('记录体重和腰围')).toBeTruthy();
    fireEvent.press(view.getByLabelText('关闭当前提示'));
    expect(view.queryByTestId('chat-today-focus-card')).toBeNull();
    expect(view.queryByText('已隐藏，点此展开')).toBeNull();

    fireEvent.press(view.getByLabelText('更多会诊操作'));
    fireEvent.press(view.getByText('今日计划'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/today');
  });

  it('shows a recoverable Agent failure and retries only the latest text message', async () => {
    mockTodayTimelineData = {
      items: [{ id: 'timeline-1', kind: 'action', title: '补水', status: 'pending', priority: 9 }],
      past: { completed_count: 0, events: [] },
      counts: { actionable: 1, overdue: 0, info: 0 },
    };
    mockMessages = [{
      id: 'u1', role: 'user', content: '查询今天饮食', sourceTurnId: 'turn-current',
    }];
    mockActiveTurn = {
      phase: 'failed',
      recoverable: true,
      label: '网络中断，已保留内容',
      errorCode: 'stream_request_failed',
      turnId: 'turn-current',
    };

    const { getByText, getByLabelText } = render(<ChatScreen />);

    expect(getByText('网络中断，已保留内容')).toBeTruthy();
    fireEvent.press(getByLabelText('重试上一轮'));
    await waitFor(() => expect(mockSendMessage).toHaveBeenCalledWith('查询今天饮食', null));
  });

  it('does not retry an older text turn when the failed current turn contains an image', () => {
    mockMessages = [
      { id: 'u-old', role: 'user', content: '查询今天饮食', sourceTurnId: 'turn-old' },
      {
        id: 'u-image',
        role: 'user',
        content: '记录这餐',
        imageUris: ['https://health.example/api/v1/upload/files/chat/3/meal.jpg'],
        sourceTurnId: 'turn-image',
      },
    ];
    mockActiveTurn = {
      phase: 'failed',
      recoverable: true,
      label: '上一轮未完成，内容已保留',
      errorCode: 'stream_error_event',
      turnId: 'turn-image',
    };

    const view = render(<ChatScreen />);

    expect(view.getByText('上一轮未完成，内容已保留')).toBeTruthy();
    expect(view.queryByLabelText('重试上一轮')).toBeNull();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('shows a visible history entry on the private coach page', async () => {
    const { getAllByText, getByLabelText } = render(<ChatScreen />);

    expect(getAllByText('小巴').length).toBeGreaterThan(0);
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

  it('shows 小巴 in the header and hides the model name inline (revealed on pull-down)', async () => {
    // Agent-native header (2026-07-03): 只露品牌名「小巴 ⌄」, 模型名收进下拉 sheet。
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
      expect(getByText('小巴')).toBeTruthy();
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
    expect(styleOf(getByLabelText('新建对话')).width).toBe(42);
    expect(styleOf(getByLabelText('对话历史')).width).toBe(42);
    expect(styleOf(getByLabelText('更多会诊操作')).width).toBe(42);
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
    expect(queryByText('回复中')).toBeNull();
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
    expect(StyleSheet.flatten(getByLabelText('新建对话').props.style).width).toBe(42);
    expect(StyleSheet.flatten(getByLabelText('对话历史').props.style).width).toBe(42);
    expect(StyleSheet.flatten(getByLabelText('更多会诊操作').props.style).width).toBe(42);
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
        quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }, { text: '调整下计划' }],
        deep_link: '/action-cards/88',
        priority: 100,
      },
      suggestions: null,
      onboarding: false,
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
          quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }, { text: '调整下计划' }],
          deep_link: '/action-cards/89',
          priority: 100,
        },
        suggestions: null,
        onboarding: false,
      })
      .mockResolvedValueOnce({
        opener: null,
        suggestions: [{ text: '复盘昨晚夜间血氧和睡眠恢复', key: 'recovery_history', priority: 60 }],
        onboarding: false,
      });

    mockFetchMemoryOpener
      .mockResolvedValueOnce([{ id: 1, type: 'medical', type_label: '医疗', content: '旧记忆' }])
      .mockResolvedValueOnce([{ id: 2, type: 'medical', type_label: '医疗', content: '更新后的记忆' }]);

    const { getByLabelText, queryByText, getByText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText(/今天就是「夜间血氧复盘」的检验日，做到了吗？/)).toBeTruthy();
      expect(getByText('依据 1 条医疗')).toBeTruthy();
      expect(queryByText(/旧记忆/)).toBeNull();
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

    const { UNSAFE_getAllByType, getByLabelText } = render(<ChatScreen />);
    const bar = () => UNSAFE_getAllByType('ChatInputBar' as any)[0];

    // Fixed 拍照记一餐 chip 存在 → 点击触发 ChatInputBar 直接拍照进当前对话。
    await waitFor(() => {
      expect(getByLabelText('拍照记一餐')).toBeTruthy();
    });
    const before = bar().props.captureMealPhotoToken ?? 0;
    fireEvent.press(getByLabelText('拍照记一餐'));
    expect(mockPush).not.toHaveBeenCalledWith('/diet?capture=photo&return_to=chat');
    expect(bar().props.captureMealPhotoToken).toBeGreaterThan(before);

    // 动态 starter suggestion 也进 composer 行, 点击走既有发送。
    await waitFor(() => {
      expect(getByLabelText('向小巴提问: 分析我的睡眠质量')).toBeTruthy();
    });
    fireEvent.press(getByLabelText('向小巴提问: 分析我的睡眠质量'));
    expect(mockSendMessage).toHaveBeenCalledWith(
      '分析我的睡眠质量',
      null,
      expect.objectContaining({ onAccepted: expect.any(Function) }),
    );
  });

  it('hides generic composer suggestions when an opener owns the empty conversation', async () => {
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '今晚按计划完成了吗？',
        source: 'action_card_due',
        source_id: 7,
        quick_replies: [{ text: '做到了' }, { text: '调整计划' }],
        deep_link: null,
        priority: 100,
      },
      suggestions: [{ text: '分析我的睡眠质量', key: 'sleep', priority: 10 }],
      onboarding: false,
    });

    const { getByLabelText, queryByLabelText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('一键回复: 做到了')).toBeTruthy());
    expect(queryByLabelText('拍照记一餐')).toBeNull();
    expect(queryByLabelText('向小巴提问: 分析我的睡眠质量')).toBeNull();
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

  // ── 冷启动包 (P0-3) ─────────────────────────────────────────────────────
  it('cold start (onboarding=true) does NOT fall back to DEFAULT_SUGGESTIONS', async () => {
    // 零信号冷启动用户: 后端带 onboarding=true + 它自己的 onboarding chips。
    // 客户端禁止把 starters 回落成假设有历史数据的 DEFAULT_SUGGESTIONS。
    mockFetchConversationStarters.mockResolvedValue({
      opener: null,
      suggestions: [{ text: '连接我的 Garmin / Apple Watch', key: 'onboarding', priority: 100 }],
      onboarding: true,
    });

    const { getByLabelText, queryByText } = render(<ChatScreen />);

    // 后端返回的 onboarding chip 原样渲染进 composer 行。
    await waitFor(() => {
      expect(getByLabelText('向小巴提问: 连接我的 Garmin / Apple Watch')).toBeTruthy();
    });
    // DEFAULT_SUGGESTIONS 的文案(假设有历史数据)不出现。
    expect(queryByText('今天的健康状况如何？')).toBeNull();
    expect(queryByText('HRV趋势分析')).toBeNull();
  });

  it('cold start with empty backend starters still suppresses DEFAULT_SUGGESTIONS', async () => {
    // onboarding=true 但后端 suggestions 为空 → 仍不回注默认(只剩固定拍照 chip)。
    mockFetchConversationStarters.mockResolvedValue({
      opener: null,
      suggestions: null,
      onboarding: true,
    });

    const { getByLabelText, queryByText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('拍照记一餐')).toBeTruthy());
    expect(queryByText('今天的健康状况如何？')).toBeNull();
    expect(queryByText('分析我的睡眠质量')).toBeNull();
  });

  it('an action quick reply navigates locally instead of sending text', async () => {
    // 冷启动 opener 的 quick reply 带 action → 点击走本地导航, 不发文本。
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '欢迎！先从这三件事之一开始，我就能帮你看懂身体。',
        source: 'memory_fact',
        source_id: null,
        quick_replies: [
          { text: '拍照记一餐', action: 'photo_meal' },
          { text: '记录体重', action: 'record_weight' },
          { text: '连接设备', action: 'connect_device' },
        ],
        deep_link: null,
        priority: 5,
      },
      suggestions: null,
      onboarding: true,
    });

    const { getByLabelText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('一键回复: 记录体重')).toBeTruthy());
    fireEvent.press(getByLabelText('一键回复: 记录体重'));

    // record_weight → /body-measurements 本地导航, 不发消息。
    expect(mockPush).toHaveBeenCalledWith('/body-measurements');
    expect(mockSendMessage).not.toHaveBeenCalled();

    fireEvent.press(getByLabelText('一键回复: 连接设备'));
    expect(mockPush).toHaveBeenCalledWith('/settings');

    fireEvent.press(getByLabelText('一键回复: 拍照记一餐'));
    expect(mockPush).toHaveBeenCalledWith('/diet?capture=photo&return_to=chat');
    // 三个 action 全程零发送。
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('a no-action quick reply still sends text (behavior unchanged)', async () => {
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '今天就是「提前晚餐」的检验日，做到了吗？',
        source: 'action_card_due',
        source_id: 7,
        quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }],
        deep_link: null,
        priority: 100,
      },
      suggestions: null,
      onboarding: false,
    });

    const { getByLabelText } = render(<ChatScreen />);

    await waitFor(() => expect(getByLabelText('一键回复: 做到了 ✅')).toBeTruthy());
    fireEvent.press(getByLabelText('一键回复: 做到了 ✅'));

    // 无 action → 走既有发送路径, 不做本地导航。
    expect(mockSendMessage).toHaveBeenCalled();
    expect(mockSendMessage.mock.calls[0][0]).toContain('做到了 ✅');
    expect(mockPush).not.toHaveBeenCalledWith('/body-measurements');
    expect(mockPush).not.toHaveBeenCalledWith('/settings');
  });

  it('hides opener reply actions when the iOS keyboard takes over the viewport', async () => {
    const keyboardListeners: Record<string, (event: any) => void> = {};
    const keyboardSpy = jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '今晚按计划完成了吗？',
        source: 'action_card_due',
        source_id: 7,
        quick_replies: [{ text: '做到了' }, { text: '调整计划' }],
        deep_link: null,
        priority: 100,
      },
      suggestions: null,
      onboarding: false,
    });

    const { getByLabelText, queryByLabelText } = render(<ChatScreen />);
    await waitFor(() => expect(getByLabelText('一键回复: 做到了')).toBeTruthy());

    act(() => {
      keyboardListeners.keyboardDidShow({
        endCoordinates: { height: 336 },
      });
    });

    expect(queryByLabelText('一键回复: 做到了')).toBeNull();
    expect(queryByLabelText('一键回复: 调整计划')).toBeNull();
    expect(queryByLabelText('换个话题')).toBeNull();
    keyboardSpy.mockRestore();
  });

  it('hides non-critical Today context while the keyboard owns the viewport', () => {
    const keyboardListeners: Record<string, (event: any) => void> = {};
    const keyboardSpy = jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });
    mockTodayTimelineData = {
      items: [{
        id: 'lab-review',
        kind: 'action',
        title: '复查血脂四项',
        status: 'overdue',
        priority: 9,
        can_complete: true,
        deep_link: '/agenda',
      }],
      past: { completed_count: 0, events: [] },
      counts: { actionable: 1, overdue: 1, info: 0 },
    };

    const view = render(<ChatScreen />);
    expect(view.getByText('复查血脂四项')).toBeTruthy();

    act(() => {
      keyboardListeners.keyboardDidShow({
        endCoordinates: { height: 336 },
      });
    });

    expect(view.queryByText('复查血脂四项')).toBeNull();
    expect(view.queryByTestId('chat-today-focus-card')).toBeNull();
    keyboardSpy.mockRestore();
  });

  it('keeps active Agent status visible when the keyboard opens', () => {
    const keyboardListeners: Record<string, (event: any) => void> = {};
    const keyboardSpy = jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });
    mockTodayTimelineData = {
      items: [{
        id: 'lab-review',
        kind: 'action',
        title: '复查血脂四项',
        status: 'overdue',
        priority: 9,
        can_complete: true,
        deep_link: '/agenda',
      }],
      past: { completed_count: 0, events: [] },
      counts: { actionable: 1, overdue: 1, info: 0 },
    };
    mockActiveTurn = {
      phase: 'generating',
      recoverable: false,
      label: '小巴正在整理…',
      turnId: 'turn-current',
    };

    const view = render(<ChatScreen />);
    expect(view.getByText('小巴正在整理…')).toBeTruthy();

    act(() => {
      keyboardListeners.keyboardDidShow({
        endCoordinates: { height: 336 },
      });
    });

    expect(view.getByText('小巴正在整理…')).toBeTruthy();
    expect(view.queryByText('复查血脂四项')).toBeNull();
    keyboardSpy.mockRestore();
  });

  it('third state (onboarding, no opener, no memory) shows the Quick Start card', async () => {
    // opener 因故未到 + 无记忆, 但 onboarding=true → 出 Quick Start 卡(三动作)。
    mockFetchConversationStarters.mockResolvedValue({
      opener: null,
      suggestions: null,
      onboarding: true,
    });
    mockFetchMemoryOpener.mockResolvedValue([]);

    const { getByLabelText } = render(<ChatScreen />);

    await waitFor(() => {
      // Quick Start 卡的三个动作按钮都在。
      expect(getByLabelText('记录体重')).toBeTruthy();
      expect(getByLabelText('连接设备')).toBeTruthy();
    });

    // 点卡里的「连接设备」→ 本地导航 /settings。
    fireEvent.press(getByLabelText('连接设备'));
    expect(mockPush).toHaveBeenCalledWith('/settings');
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('does NOT show the Quick Start card when the opener arrives (no bubble+card+chips stacking)', async () => {
    // opener 正常到达 → 走开场气泡, 不出 Quick Start 卡。
    mockFetchConversationStarters.mockResolvedValue({
      opener: {
        text: '今天就是「提前晚餐」的检验日，做到了吗？',
        source: 'action_card_due',
        source_id: 1,
        quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }],
        deep_link: null,
        priority: 100,
      },
      suggestions: null,
      onboarding: true,
    });

    const { getByText, queryByLabelText } = render(<ChatScreen />);

    await waitFor(() => {
      expect(getByText(/今天就是「提前晚餐」的检验日，做到了吗？/)).toBeTruthy();
    });
    // Quick Start 卡的「记录体重」/「连接设备」动作按钮不渲染(opener 气泡已占位)。
    expect(queryByLabelText('记录体重')).toBeNull();
    expect(queryByLabelText('连接设备')).toBeNull();
  });

  it('keeps the agent-native chat composer compact and above the iOS keyboard', async () => {
    const keyboardListeners: Record<string, (event: any) => void> = {};
    jest.spyOn(Keyboard, 'addListener').mockImplementation((eventName: any, callback: any) => {
      keyboardListeners[String(eventName)] = callback;
      return { remove: jest.fn() } as any;
    });

    const { getByTestId } = render(<ChatScreen />);
    await waitFor(() => expect(mockFetchConversationStarters).toHaveBeenCalled());

    expect(getByTestId('chat-message-list').props.keyboardShouldPersistTaps).toBe('always');

    // No global tab bar: spacer = insets.bottom (jest mock 为 0) + 12 呼吸;
    // 真机 = home indicator 安全区 + 12 —— 输入栏悬浮不贴底 (阿福式)。
    expect(getByTestId('chat-bottom-spacer')).toHaveStyle({ height: 12 });

    act(() => {
      keyboardListeners.keyboardDidShow({
        endCoordinates: { height: 336 },
      });
    });

    expect(getByTestId('chat-bottom-spacer')).toHaveStyle({ height: 336 });
  });

  it('keeps the transcript in a shrinkable viewport when the composer grows', async () => {
    mockMessages = [
      { id: 'u-1', role: 'user', content: '一段会换行的输入内容' },
      { id: 'a-1', role: 'assistant', content: '最后一条回复', completionStatus: 'complete' },
    ];

    const { getByTestId } = render(<ChatScreen />);
    await waitFor(() => expect(getByTestId('chat-message-list')).toBeTruthy());

    expect(StyleSheet.flatten(getByTestId('chat-message-list').props.style)).toMatchObject({
      flex: 1,
      minHeight: 0,
    });
  });

  it('offers a compact control to load earlier messages at the top of the transcript', async () => {
    mockHasMoreHistory = true;
    mockMessages = [
      { id: 'u-1', role: 'user', content: '较新的问题' },
      { id: 'a-1', role: 'assistant', content: '较新的回复', completionStatus: 'complete' },
    ];

    const view = render(<ChatScreen />);
    await waitFor(() => expect(view.getByLabelText('加载更早消息')).toBeTruthy());

    fireEvent.press(view.getByLabelText('加载更早消息'));

    expect(mockLoadMoreHistory).toHaveBeenCalledTimes(1);
  });

  it('disables the earlier-message control while history is loading', async () => {
    mockHasMoreHistory = true;
    mockIsLoadingMoreHistory = true;

    const view = render(<ChatScreen />);
    await waitFor(() => expect(view.getByLabelText('正在加载更早消息')).toBeTruthy());

    fireEvent.press(view.getByLabelText('正在加载更早消息'));

    expect(mockLoadMoreHistory).not.toHaveBeenCalled();
  });

  it('keeps a newly sent turn pinned through the first transcript relayout', async () => {
    mockMessages = [
      { id: 'u-1', role: 'user', content: '上一条问题' },
      { id: 'a-1', role: 'assistant', content: '上一条回复', completionStatus: 'complete' },
    ];
    mockSendMessage.mockReturnValue(new Promise(() => {}));

    const view = render(<ChatScreen />);
    await waitFor(() => expect(mockFetchConversationStarters).toHaveBeenCalled());
    const list = view.getByTestId('chat-message-list');
    const bar = view.UNSAFE_getAllByType('ChatInputBar' as any)[0];
    const scrollToEnd = jest.spyOn(FlatList.prototype, 'scrollToEnd');

    try {
      act(() => {
        list.props.onScrollBeginDrag();
      });
      act(() => {
        void bar.props.onSend('新问题');
      });
      scrollToEnd.mockClear();

      // The first post-send layout event can still describe the old viewport.
      // It must not cancel following the new user bubble and streamed answer.
      fireEvent.scroll(list, {
        nativeEvent: {
          layoutMeasurement: { height: 500 },
          contentOffset: { y: 0 },
          contentSize: { height: 1500 },
        },
      });
      act(() => {
        list.props.onContentSizeChange();
      });

      expect(scrollToEnd).toHaveBeenCalledTimes(1);
    } finally {
      scrollToEnd.mockRestore();
    }
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
    expect(getByText('更多操作')).toBeTruthy();
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
