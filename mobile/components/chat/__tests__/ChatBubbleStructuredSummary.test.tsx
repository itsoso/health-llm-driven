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
}));
jest.mock('../../../services/chatCardActions', () => ({
  dispatchChatCardAction: jest.fn(),
}));
jest.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ show: mockToastShow }),
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn() },
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
const { saveAssistantReplyAsMemory } = require('../../../services/chatResultActions');
const { dispatchChatCardAction } = require('../../../services/chatCardActions');
const { renderCard, __mockCard } = require('../cards');
const { sharePlainText } = require('../../../utils/share');
const { router } = require('expo-router');

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
  });

  it('shares assistant replies under the 阿衡 persona', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);

    const { getByLabelText } = renderBubble('今天先补水 300ml, 晚饭后散步 15 分钟。');

    fireEvent.press(getByLabelText('分享'));

    await waitFor(() => {
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '阿衡 · 建议',
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
