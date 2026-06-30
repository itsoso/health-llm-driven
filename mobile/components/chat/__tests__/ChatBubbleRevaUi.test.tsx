import React from 'react';
import { render } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { UIMessage } from '../../../hooks/useChatEngine';

/* eslint-disable @typescript-eslint/no-require-imports */
jest.mock('expo-speech', () => ({ stop: jest.fn() }));
jest.mock('expo-audio', () => ({ setAudioModeAsync: jest.fn() }));
jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(),
  impactAsync: jest.fn(),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Medium: 'medium' },
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

function renderBubble(content: string) {
  const qc = new QueryClient();
  const message: UIMessage = {
    id: 'assistant-reva-ui',
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

describe('ChatBubble reva-ui blocks', () => {
  it('renders deterministic line_chart blocks as native chart cards instead of raw fenced JSON', () => {
    const content = [
      '近半年 HRV 趋势如下:',
      '',
      '```reva-ui',
      '{"v":1,"component":"line_chart","title":"HRV 趋势","unit":"ms","x":["06-29","06-30"],"series":[{"name":"Garmin 夜间 HRV","role":"raw","points":[52,56]},{"name":"7日滚动均值","role":"avg_7d","points":[53,54]}],"annotations":[{"x":"06-30","label":"最新 56 ms · Garmin","kind":"latest"}],"source":"garmin","data_note":"基于 2 天真实数据 · 每日 · Garmin 2d"}',
      '```',
    ].join('\n');

    const { getByText, queryByText } = renderBubble(content);

    expect(getByText('HRV 趋势')).toBeTruthy();
    expect(getByText('Garmin 夜间 HRV')).toBeTruthy();
    expect(getByText('7日滚动均值')).toBeTruthy();
    expect(getByText(/基于 2 天真实数据/)).toBeTruthy();
    expect(queryByText(/```reva-ui/)).toBeNull();
    expect(queryByText(/"component":"line_chart"/)).toBeNull();
  });

  it('renders generic metric_line_chart blocks as dynamic UI components', () => {
    const content = [
      '近半年心率趋势如下:',
      '',
      '```reva-ui',
      '{"v":1,"schema":"reva.metric_line_chart.v1","component":"metric_line_chart","metric":"resting_hr","range":"6m","title":"静息心率趋势","unit":"bpm","x":["06-29","06-30"],"series":[{"name":"Apple Watch 静息心率","role":"device","points":[62,58]},{"name":"7日滚动均值","role":"avg_7d","points":[61,60]}],"annotations":[{"x":"06-30","label":"最新 58 bpm · Apple Watch","kind":"latest"}],"source":"garmin","data_note":"基于 2 天真实数据 · 每日 · Apple Watch 2d"}',
      '```',
    ].join('\n');

    const { getByText, queryByText } = renderBubble(content);

    expect(getByText('静息心率趋势')).toBeTruthy();
    expect(getByText('Apple Watch 静息心率')).toBeTruthy();
    expect(getByText('7日滚动均值')).toBeTruthy();
    expect(getByText(/基于 2 天真实数据/)).toBeTruthy();
    expect(queryByText(/```reva-ui/)).toBeNull();
    expect(queryByText(/"component":"metric_line_chart"/)).toBeNull();
  });
});
