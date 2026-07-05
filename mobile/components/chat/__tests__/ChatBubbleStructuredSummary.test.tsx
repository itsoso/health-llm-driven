import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { UIMessage } from '../../../hooks/useChatEngine';

const mockToastShow = jest.fn();

/* eslint-disable @typescript-eslint/no-require-imports */
jest.mock('expo-speech', () => ({ stop: jest.fn() }));
jest.mock('expo-audio', () => ({ setAudioModeAsync: jest.fn() }));
jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  NotificationFeedbackType: { Success: 'success', Error: 'error' },
}));
jest.mock('../../../services/speakWithUserVoice', () => ({
  speakWithUserVoice: jest.fn(),
}));
jest.mock('../../../services/chatResultActions', () => ({
  saveAssistantReplyAsMemory: jest.fn(),
  createRecordFromAssistantReply: jest.fn(),
}));
jest.mock('../../../services/chatCardActions', () => ({
  dispatchChatCardAction: jest.fn(),
}));
jest.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ show: mockToastShow }),
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), setParams: jest.fn() },
}));
jest.mock('react-native-markdown-display', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const MockMarkdown = ({ children }: { children: string }) => <Text>{children}</Text>;
  MockMarkdown.displayName = 'MockMarkdown';
  return MockMarkdown;
});
jest.mock('../BrandCircle', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockBrandCircle = ({ children }: any) => <View>{children}</View>;
  MockBrandCircle.displayName = 'MockBrandCircle';
  return MockBrandCircle;
});
jest.mock('../AttributionChips', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockAttributionChips = () => <View />;
  MockAttributionChips.displayName = 'MockAttributionChips';
  return MockAttributionChips;
});
jest.mock('../cards', () => {
  const React = require('react');
  const { View, Text } = require('react-native');
  return {
    renderCard: jest.fn(() => null),
    getCardActionRuntimeKey: jest.fn((action: any, descriptor?: any) => (
      action.id || `${descriptor?.type ?? 'card'}:${action.action}:${action.label}`
    )),
    __mockCard: <View><Text>今晚晚餐建议</Text></View>,
  };
});
jest.mock('../../../services/actionCards', () => ({
  createInterventionDraft: jest.fn(),
}));
jest.mock('../../../services/interventionDraft', () => ({
  buildInterventionDraft: jest.fn(() => ({})),
}));
jest.mock('../../../utils/share', () => ({
  sharePlainText: jest.fn(),
}));
jest.mock('../../actions/InterventionDraftSheet', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockInterventionDraftSheet = () => <View />;
  MockInterventionDraftSheet.displayName = 'MockInterventionDraftSheet';
  return MockInterventionDraftSheet;
});

const ChatBubble = require('../ChatBubble').default;
const { saveAssistantReplyAsMemory, createRecordFromAssistantReply } = require('../../../services/chatResultActions');
const { dispatchChatCardAction } = require('../../../services/chatCardActions');
const { renderCard, __mockCard } = require('../cards');
const { sharePlainText } = require('../../../utils/share');
const { router } = require('expo-router');
const { createInterventionDraft } = require('../../../services/actionCards');

function renderBubble(content: string) {
  const qc = new QueryClient();
  const message: UIMessage = {
    id: 'assistant-structured',
    role: 'assistant',
    content,
    streaming: false,
  };
  return render(
    <QueryClientProvider client={qc}>
      <ChatBubble item={message} />
    </QueryClientProvider>,
  );
}

describe('ChatBubble structured summary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockToastShow.mockClear();
  });

  it('summarizes markdown metric tables and today advice for mobile scanning', () => {
    const { getByText, queryByText } = renderBubble(`
| 指标 | 数值 | 状态 |
| --- | --- | --- |
| 睡眠 | 89 分 | ✅ 优秀 |
| HRV | 62.0ms 较7日均值 ↑7% | ✅ |
| 饮水 | 0ml/2000ml | ⚠️ 0% |

📌 今日建议：
1. 饮水未达标，上午补充 500ml
2. 基因提示：MTHFR TT 影响叶酸代谢
`);

    expect(getByText('指标摘要')).toBeTruthy();
    expect(getByText('睡眠')).toBeTruthy();
    expect(getByText('89 分')).toBeTruthy();
    expect(getByText('今日建议')).toBeTruthy();
    expect(getByText('饮水未达标，上午补充 500ml')).toBeTruthy();
    expect(queryByText(/\| 指标 \| 数值 \| 状态 \|/)).toBeNull();
  });

  it('strips markdown heading/list/bold markers from today advice items', () => {
    const { getByText, queryByText } = renderBubble(`
📌 今日建议：
1. ### ✅ 你已有的（继续保持）
2. **补水** 上午 500ml
`);

    expect(getByText('今日建议')).toBeTruthy();
    // "### " heading marker stripped
    expect(getByText('✅ 你已有的（继续保持）')).toBeTruthy();
    // "**bold**" emphasis stripped
    expect(getByText('补水 上午 500ml')).toBeTruthy();
    // no literal markdown markers leak into the card
    expect(queryByText(/###/)).toBeNull();
  });

  it('shows executable actions for completed assistant replies and can save memory', async () => {
    saveAssistantReplyAsMemory.mockResolvedValueOnce(undefined);

    const { getByText } = renderBubble('建议今晚 23:00 前睡觉，并在睡前 3 小时停止正餐。');

    expect(getByText('加入今日计划')).toBeTruthy();
    expect(getByText('保存记忆')).toBeTruthy();
    expect(getByText('生成记录')).toBeTruthy();
    expect(getByText('继续追问')).toBeTruthy();

    fireEvent.press(getByText('保存记忆'));

    await waitFor(() => {
      expect(saveAssistantReplyAsMemory).toHaveBeenCalledWith('建议今晚 23:00 前睡觉，并在睡前 3 小时停止正餐。');
    });
    expect(getByText('已保存')).toBeTruthy();
  });

  it('adds an assistant reply to today plan directly from the result action', async () => {
    createInterventionDraft.mockResolvedValueOnce({ id: 77 });

    const { getByText } = renderBubble('今晚 23:00 前睡觉，并在睡前 3 小时停止正餐。');

    fireEvent.press(getByText('加入今日计划'));

    await waitFor(() => {
      expect(createInterventionDraft).toHaveBeenCalled();
    });
    expect(mockToastShow).toHaveBeenCalledWith('已加入今日计划', 'success');
  });

  it('creates a record from a diet-like assistant reply instead of only opening the record tab', async () => {
    createRecordFromAssistantReply.mockResolvedValueOnce({
      status: 'created',
      type: 'diet',
      message: '已记录午餐：煎牛肉能量碗 + 姜黄鲜柠维C茶',
    });
    const content = '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal（蛋白 30g / 碳水 70g / 脂肪 17g）';

    const { getByText } = renderBubble(content);

    fireEvent.press(getByText('生成记录'));

    await waitFor(() => {
      expect(createRecordFromAssistantReply).toHaveBeenCalledWith(content);
    });
    expect(router.push).not.toHaveBeenCalledWith('/(tabs)/record');
    expect(mockToastShow).toHaveBeenCalledWith('已记录午餐：煎牛肉能量碗 + 姜黄鲜柠维C茶', 'success');
    expect(getByText('已生成')).toBeTruthy();
  });

  it('refreshes today execution surfaces after generating a record from an assistant reply', async () => {
    createRecordFromAssistantReply.mockResolvedValueOnce({
      status: 'created',
      type: 'diet',
      message: '已记录午餐',
    });
    const qc = new QueryClient();
    const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
    const message: UIMessage = {
      id: 'assistant-record-refresh',
      role: 'assistant',
      content: '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal',
      streaming: false,
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('生成记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('已记录午餐', 'success');
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['daily-artifact', 'me'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['today-dynamic-view', 'mobile.today'] });
  });

  it('injects follow-up prompts into the current chat input instead of pushing the same tab', () => {
    const { getByText } = renderBubble('晚餐后散步 15 分钟，明早观察 HRV 和主观恢复。');

    fireEvent.press(getByText('继续追问'));

    expect(router.setParams).toHaveBeenCalledWith(expect.objectContaining({
      prompt: expect.stringContaining('继续追问'),
      promptNonce: expect.any(String),
    }));
    expect(router.push).not.toHaveBeenCalledWith(expect.objectContaining({ pathname: '/(tabs)/chat' }));
    expect(getByText('已放入输入框')).toBeTruthy();
  });

  it('shares assistant replies under the 小巴 persona', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);

    const { getByLabelText } = renderBubble('今天先补水 300ml, 晚饭后散步 15 分钟。');

    fireEvent.press(getByLabelText('分享'));

    await waitFor(() => {
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '小巴 · 建议',
      }));
    });
  });

  it('normalizes headerless markdown tables before rendering assistant replies', () => {
    const { getByText, queryByText } = renderBubble(`
🟢 第三优先级（第 14-30 天优化）

|---|---|---|
| 维生素 D3 2000IU | ✅ 继续，VD 已从 18.9→32.3 ng/mL | 2023 缺乏 →2025 达标 |
| 甘氨酸镁 2 片（睡前） | ✅ 继续，助睡眠 + 肌肉放松 | 睡眠 89 分 |
`);

    expect(getByText(/维生素 D3 2000IU/)).toBeTruthy();
    expect(getByText(/甘氨酸镁 2 片/)).toBeTruthy();
    expect(queryByText(/\|---\|---\|---\|/)).toBeNull();
    expect(queryByText(/\| 维生素 D3 2000IU \|/)).toBeNull();
  });

  it('constrains server-rendered cards inside the assistant column', () => {
    renderCard.mockReturnValueOnce(__mockCard);
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'menu_share',
      cardData: {
        title: '今晚晚餐建议',
        items: [{ name: '白灼虾', qty: '100g', kcal: 90 }],
      },
    };

    const { getByTestId, getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByText('今晚晚餐建议')).toBeTruthy();
    expect(getByTestId('assistant-card-frame')).toHaveStyle({
      flex: 1,
      minWidth: 0,
      maxWidth: '100%',
    });
  });

  it('dispatches server card actions from the chat bubble', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed' });
    renderCard.mockImplementationOnce((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>完成</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-action',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'vitals',
      cardData: { sleep: '8h' },
      cardActions: [{
        label: '完成',
        action: 'agenda.complete',
        endpoint: '/agenda/complete',
        requires_manual_confirm: true,
        payload: { source: { object_type: 'health_protocol', object_id: 7 } },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(dispatchChatCardAction).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'agenda.complete' }),
      );
    });
  });

  it('shows diet-specific success feedback after confirming a diet card', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed' });
    renderCard.mockImplementationOnce((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-diet-card-action',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: { food_items: '鸡胸肉 200g', meal_type: 'lunch' },
      cardActions: [{
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '鸡胸肉 200g', meal_type: 'lunch' } },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('已记录饮食', 'success');
    });
  });

  it('shows nutrition estimation feedback after confirming an incomplete diet card', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed', nutrition_status: 'estimated' });
    renderCard.mockImplementationOnce((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-diet-card-action-estimated',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: { food_items: '牛肉面', meal_type: 'lunch' },
      cardActions: [{
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '牛肉面', meal_type: 'lunch' } },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('已记录饮食，营养已估算', 'success');
    });
  });

  it('keeps the saved-record feedback visible when diet nutrition estimation fails', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed', nutrition_status: 'estimate_failed' });
    renderCard.mockImplementationOnce((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-diet-card-action-estimate-failed',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: { food_items: '鸡蛋 2 个', meal_type: 'breakfast' },
      cardActions: [{
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '鸡蛋 2 个', meal_type: 'breakfast' } },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('已记录饮食，营养估算稍后补充', 'info');
    });
  });

  it('refreshes dependent data and shows feedback before opening routed card actions', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'opened',
      route: '/indicator-history?type=hrv',
    });
    renderCard.mockImplementationOnce((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>查看HRV历史</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
    const message: UIMessage = {
      id: 'assistant-card-route-action',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'metric_chart',
      cardData: { metric: 'hrv', title: '最近半年 HRV' },
      cardActions: [{
        id: 'open-hrv-history',
        label: '查看HRV历史',
        action: 'route.open',
        payload: { route: '/indicator-history?type=hrv' },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('查看HRV历史'));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith('/indicator-history?type=hrv');
    });
    expect(mockToastShow).toHaveBeenCalledWith('已打开', 'success');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['daily-artifact', 'me'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['write-intents'] });
  });

  it('asks for confirmation before dispatching write card actions', async () => {
    const { Alert } = require('react-native');
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed' });
    renderCard.mockImplementationOnce((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-confirmation',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'record',
      cardData: { type: 'exercise', detail: '俯卧撑 30 个' },
      cardActions: [{
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
        confirmation: {
          title: '记录 30 个俯卧撑？',
          detail: '将写入今天的运动记录',
          confirm_label: '确认记录',
          cancel_label: '再看看',
        },
      } as any],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    expect(dispatchChatCardAction).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith(
      '记录 30 个俯卧撑？',
      '将写入今天的运动记录',
      expect.any(Array),
    );

    const buttons = alertSpy.mock.calls[0][2] as { onPress?: () => void }[];
    await act(async () => {
      buttons[1].onPress?.();
    });

    await waitFor(() => {
      expect(dispatchChatCardAction).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'write_intent.confirm' }),
      );
    });

    alertSpy.mockRestore();
  });
});
