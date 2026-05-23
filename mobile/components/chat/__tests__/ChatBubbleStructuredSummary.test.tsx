import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { UIMessage } from '../../../hooks/useChatEngine';

/* eslint-disable @typescript-eslint/no-require-imports */
jest.mock('expo-speech', () => ({ stop: jest.fn() }));
jest.mock('expo-audio', () => ({ setAudioModeAsync: jest.fn() }));
jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(),
  notificationAsync: jest.fn(),
  NotificationFeedbackType: { Success: 'success' },
}));
jest.mock('../../../services/speakWithUserVoice', () => ({
  speakWithUserVoice: jest.fn(),
}));
jest.mock('../../../services/chatResultActions', () => ({
  saveAssistantReplyAsMemory: jest.fn(),
}));
jest.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ show: jest.fn() }),
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
const { renderCard, __mockCard } = require('../cards');

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
});
