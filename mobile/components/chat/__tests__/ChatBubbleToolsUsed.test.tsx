import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
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
  return {
    __esModule: true,
    default: MockAttributionChips,
    AttributionDetails: MockAttributionChips,
    normalizedAttributionCount: (sources?: unknown[]) => sources?.length || 0,
  };
});
jest.mock('../cards', () => ({
  renderCard: jest.fn(() => null),
}));
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

function renderBubble(message: UIMessage) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ChatBubble item={message} />
    </QueryClientProvider>,
  );
}

const CONTENT = '已为你记录今天的体重。';

// 透视面板 (AgentTransparencyPanel) 折叠头的展开按钮 accessibilityLabel —
// toolsUsed 现在经 buildAgentTransparency 收进这个面板, 展开后以 "调用 Skill" 行 + chip 呈现.
const EXPAND_LABEL = '展开回答依据';

describe('ChatBubble 调用 Skill 展示 (透视面板)', () => {
  it('renders an always-visible medical source panel below a completed health answer', () => {
    const { getByText, getByLabelText } = renderBubble({
      id: 'assistant-bmi-citations',
      role: 'assistant',
      content: '你的 BMI 是 22.9，属于正常范围。',
      streaming: false,
      completionStatus: 'complete',
      medicalCitations: [
        {
          sourceId: 'cdc:adult-bmi-categories',
          title: '成人 BMI 计算方法与分类',
          organization: '美国疾病控制与预防中心',
          url: 'https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html',
          topic: 'bmi',
          claimScope: 'BMI 是筛查指标。',
        },
      ],
    });

    expect(getByText('参考来源')).toBeTruthy();
    expect(getByText('成人 BMI 计算方法与分类')).toBeTruthy();
    expect(getByLabelText('打开参考来源：成人 BMI 计算方法与分类')).toBeTruthy();
  });

  it('toolsUsed 非空且非流式 → 技术详情二次展开后可见工具调用', () => {
    const { getByText, queryByText, getByLabelText, getByTestId } = renderBubble({
      id: 'assistant-tools',
      role: 'assistant',
      content: CONTENT,
      streaming: false,
      toolsUsed: ['health_record', 'health_query'],
    });

    // 面板默认折叠: 头部可见, Skill 明细尚未展开
    const expander = getByLabelText(EXPAND_LABEL);
    expect(expander).toBeTruthy();
    expect(getByTestId('assistant-utility-panel')).toHaveStyle({
      alignSelf: 'stretch',
    });
    expect(queryByText('调用 Skill')).toBeNull();

    // 一级展开仍保持用户依据优先，工具名默认不抢占。
    fireEvent.press(expander);
    expect(getByTestId('assistant-utility-panel')).toHaveStyle({
      alignSelf: 'stretch',
    });
    expect(queryByText('调用工具')).toBeNull();
    expect(queryByText('health_record')).toBeNull();

    fireEvent.press(getByLabelText('展开技术详情'));
    expect(getByText('调用工具')).toBeTruthy();
    expect(getByText('health_record')).toBeTruthy();
    expect(getByText('health_query')).toBeTruthy();
  });

  it('toolsUsed 空 → 不渲染透视面板 (无 "调用 Skill" 块)', () => {
    const { queryByText, queryByLabelText } = renderBubble({
      id: 'assistant-no-tools',
      role: 'assistant',
      content: CONTENT,
      streaming: false,
      toolsUsed: [],
    });

    expect(queryByLabelText(EXPAND_LABEL)).toBeNull();
    expect(queryByText('调用 Skill')).toBeNull();
  });

  it('失败回合把 toolsUsed 明确标为尝试调用', () => {
    const { getByText, getByLabelText, queryByText } = renderBubble({
      id: 'assistant-failed-tool-attempt',
      role: 'assistant',
      content: '记录服务暂停，这次没有写入。',
      streaming: false,
      toolsUsed: ['health_record'],
      completionStatus: 'error',
    });

    fireEvent.press(getByLabelText(EXPAND_LABEL));
    expect(queryByText('尝试调用工具')).toBeNull();
    fireEvent.press(getByLabelText('展开技术详情'));
    expect(getByText('尝试调用工具')).toBeTruthy();
    expect(queryByText('调用工具')).toBeNull();
  });

  it('toolsUsed undefined → 不渲染', () => {
    const { queryByText, queryByLabelText } = renderBubble({
      id: 'assistant-undef-tools',
      role: 'assistant',
      content: CONTENT,
      streaming: false,
    });

    expect(queryByLabelText(EXPAND_LABEL)).toBeNull();
    expect(queryByText('调用 Skill')).toBeNull();
  });

  it('流式期 (streaming) 即使有 toolsUsed 也不渲染', () => {
    const { queryByText, queryByLabelText } = renderBubble({
      id: 'assistant-streaming-tools',
      role: 'assistant',
      content: CONTENT,
      streaming: true,
      toolsUsed: ['health_record'],
    });

    expect(queryByLabelText(EXPAND_LABEL)).toBeNull();
    expect(queryByText('调用 Skill')).toBeNull();
  });
});
