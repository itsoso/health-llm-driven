import React from 'react';
import { StyleSheet } from 'react-native';
import { render } from '@testing-library/react-native';
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
// Spy on the markdown component so we can assert it is NOT mounted while streaming.
const mockMarkdownMount = jest.fn();
jest.mock('react-native-markdown-display', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const MockMarkdown = ({ children }: { children: string }) => {
    mockMarkdownMount(children);
    return <Text testID="rich-markdown">{children}</Text>;
  };
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

const CONTENT = '## 睡眠分析\n\n你昨晚睡了 7 小时。\n\n建议保持规律作息。';

describe('ChatBubble streaming degraded render', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders plain text (no rich Markdown tree) while the assistant reply is streaming', () => {
    const { getByText, queryByTestId } = renderBubble({
      id: 'assistant-streaming',
      role: 'assistant',
      content: CONTENT,
      streaming: true,
    });

    // Rich markdown component must NOT be mounted during streaming (the perf fix).
    expect(queryByTestId('rich-markdown')).toBeNull();
    expect(mockMarkdownMount).not.toHaveBeenCalled();
    // Raw content shows as plain text, newlines preserved (literal markdown markers visible).
    expect(getByText(CONTENT)).toBeTruthy();
  });

  it('renders streaming thinking steps above the assistant text', () => {
    const { getByLabelText, getByTestId, getByText, queryByTestId } = renderBubble({
      id: 'assistant-streaming-thinking',
      role: 'assistant',
      content: '今晚优先固定睡眠时间。',
      streaming: true,
      thinkingSteps: ['正在理解你的问题', '读取健康数据'],
    });

    expect(queryByTestId('rich-markdown')).toBeNull();
    expect(getByText('阿衡正在思考')).toBeTruthy();
    expect(getByText('2/2')).toBeTruthy();
    expect(getByText('正在理解你的问题')).toBeTruthy();
    expect(getByText('读取健康数据')).toBeTruthy();
    expect(getByLabelText('当前步骤:读取健康数据')).toBeTruthy();
    const panelStyle = StyleSheet.flatten(getByTestId('assistant-thinking-panel').props.style);
    expect(panelStyle.alignSelf).toBe('stretch');
    expect(panelStyle.minWidth).toBeGreaterThanOrEqual(260);
    expect(getByText('今晚优先固定睡眠时间。')).toBeTruthy();
  });

  // 流式期间跳过 sanitizeAiContent + extractRevaUiBlocks 两条重正则 (perf fix).
  // 判别用: [附图: …] 会被 sanitize 剥掉; ```reva-ui``` fence 会被 extract 抽成卡片.
  // 流式中两者都应"未处理" → 原文逐字显示, 无 reva-ui 卡片视图.
  const CONTENT_WITH_MARKERS = [
    '这是回复[附图: lab.jpg]正文。',
    '',
    '```reva-ui',
    '{"v":1,"component":"line_chart","title":"趋势","x":["1","2"],"series":[{"name":"a","points":[1,2]}]}',
    '```',
  ].join('\n');

  it('skips sanitize/extract while streaming (原文直渲, 无 reva-ui 卡片)', () => {
    const { queryByTestId, getByText } = renderBubble({
      id: 'assistant-streaming-markers',
      role: 'assistant',
      content: CONTENT_WITH_MARKERS,
      streaming: true,
    });

    // 未跑 extract → 不生成 reva-ui 卡片视图.
    expect(queryByTestId('assistant-reva-ui-cards')).toBeNull();
    // 未跑 sanitize → [附图: …] 与 ```reva-ui``` fence 原样出现在纯文本里.
    expect(getByText(CONTENT_WITH_MARKERS)).toBeTruthy();
    // 仍是纯 Text 降级路径, 无富 Markdown.
    expect(queryByTestId('rich-markdown')).toBeNull();
    expect(mockMarkdownMount).not.toHaveBeenCalled();
  });

  it('runs sanitize/extract once streaming finishes (剥附图 + 抽 reva-ui 卡片)', () => {
    const { queryByTestId, queryByText } = renderBubble({
      id: 'assistant-done-markers',
      role: 'assistant',
      content: CONTENT_WITH_MARKERS,
      streaming: false,
    });

    // done 后 extract 生效 → reva-ui 卡片视图出现.
    expect(queryByTestId('assistant-reva-ui-cards')).toBeTruthy();
    // done 后 sanitize 生效 → [附图: …] 被剥掉, fence 源码不再逐字显示.
    expect(queryByText(CONTENT_WITH_MARKERS)).toBeNull();
  });

  it('renders rich Markdown once streaming has finished (terminal state unchanged)', () => {
    const { getByTestId } = renderBubble({
      id: 'assistant-done',
      role: 'assistant',
      content: CONTENT,
      streaming: false,
    });

    // Terminal state goes through the rich markdown path.
    expect(getByTestId('rich-markdown')).toBeTruthy();
    expect(mockMarkdownMount).toHaveBeenCalled();
  });
});
