import React from 'react';
import { Alert, StyleSheet } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';

import type { UIMessage } from '../../../hooks/useChatEngine';

/* eslint-disable @typescript-eslint/no-require-imports */
jest.mock('expo-speech', () => ({ stop: jest.fn() }));
jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));
jest.mock('expo-audio', () => ({ setAudioModeAsync: jest.fn() }));
jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(),
  notificationAsync: jest.fn(),
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium' },
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
const mockSaveChatImageToLibrary = jest.fn();
jest.mock('../../../services/chatImageSave', () => ({
  saveChatImageToLibrary: (...args: any[]) => mockSaveChatImageToLibrary(...args),
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

  it('does not enable native text selection inside bubbles, so long press stays on the custom message menu', () => {
    const { getByText, rerender } = render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'user-selectable-regression',
            role: 'user',
            content: '口腔溃疡应该吃什么药',
            streaming: false,
          }}
        />
      </QueryClientProvider>,
    );

    expect(getByText('口腔溃疡应该吃什么药').props.selectable).not.toBe(true);

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'assistant-streaming-selectable-regression',
            role: 'assistant',
            content: '正在整理建议。',
            streaming: true,
          }}
        />
      </QueryClientProvider>,
    );

    expect(getByText('正在整理建议。').props.selectable).not.toBe(true);
  });

  it('long press on an assistant message opens copy-first actions instead of selecting immediately', () => {
    const onEnterSelection = jest.fn();
    const { getByLabelText } = render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'assistant-action-menu',
            role: 'assistant',
            content: '建议今天午后散步 10 分钟。',
            streaming: false,
          }}
          onEnterSelection={onEnterSelection}
        />
      </QueryClientProvider>,
    );

    fireEvent(getByLabelText('AI: 建议今天午后散步 10 分钟。'), 'longPress');

    expect(onEnterSelection).not.toHaveBeenCalled();
    expect(getByLabelText('复制全文')).toBeTruthy();
    expect(getByLabelText('选择这条消息')).toBeTruthy();

    fireEvent.press(getByLabelText('选择这条消息'));
    expect(onEnterSelection).toHaveBeenCalledWith('assistant-action-menu');
  });

  it('long press on a user message opens copy-first actions and keeps selection secondary', () => {
    const onEnterSelection = jest.fn();
    const { getByLabelText } = render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'user-action-menu',
            role: 'user',
            content: '早餐吃了鸡蛋和咖啡',
            streaming: false,
          }}
          onEnterSelection={onEnterSelection}
        />
      </QueryClientProvider>,
    );

    fireEvent(getByLabelText('你: 早餐吃了鸡蛋和咖啡'), 'longPress');

    expect(onEnterSelection).not.toHaveBeenCalled();
    fireEvent.press(getByLabelText('复制全文'));
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('早餐吃了鸡蛋和咖啡');

    fireEvent(getByLabelText('你: 早餐吃了鸡蛋和咖啡'), 'longPress');
    fireEvent.press(getByLabelText('选择这条消息'));
    expect(onEnterSelection).toHaveBeenCalledWith('user-action-menu');
  });

  it('renders one unified streaming status before the first token', () => {
    const { getByTestId, getByText, queryByTestId } = renderBubble({
      id: 'assistant-status-line',
      role: 'assistant',
      content: '⏳ AI 正在思考中...',
      streaming: true,
      currentStatus: '查看步数数据…',
    });

    // 统一处理状态出现, 文案即 currentStatus; 不再叠一个独立 status line。
    expect(getByTestId('assistant-thinking-panel')).toBeTruthy();
    expect(getByText('查看步数数据…')).toBeTruthy();
    expect(queryByTestId('assistant-status-line')).toBeNull();
    // 未出正文 → 不走富 markdown。
    expect(queryByTestId('rich-markdown')).toBeNull();
  });

  it('hides the status line once the assistant text is present (first token cleared it)', () => {
    // 首 token 后, useChatEngine 会清空 currentStatus。这里模拟"已出正文 + currentStatus 被清"。
    const { queryByTestId, getByText } = renderBubble({
      id: 'assistant-status-cleared',
      role: 'assistant',
      content: '你今天走了 8000 步。',
      streaming: true,
      // currentStatus 未设置 (已清空)
    });

    expect(queryByTestId('assistant-status-line')).toBeNull();
    expect(getByText('你今天走了 8000 步。')).toBeTruthy();
  });

  it('never shows the status line after streaming has finished', () => {
    // 终态即使残留 currentStatus (兜底应已清), 组件也不显示状态行 (仅 streaming 时渲染)。
    const { queryByTestId } = renderBubble({
      id: 'assistant-status-done',
      role: 'assistant',
      content: '完成。',
      streaming: false,
      currentStatus: '正在整理回答…',
    });

    expect(queryByTestId('assistant-status-line')).toBeNull();
  });

  it('renders streaming thinking steps as a compact expandable row above the assistant text', () => {
    const { getByLabelText, getByTestId, getByText, queryByText, queryByTestId } = renderBubble({
      id: 'assistant-streaming-thinking',
      role: 'assistant',
      content: '今晚优先固定睡眠时间。',
      streaming: true,
      thinkingSteps: ['正在理解你的问题', '读取健康数据'],
    });

    expect(queryByTestId('rich-markdown')).toBeNull();
    expect(getByText('小巴处理中 · 2 步')).toBeTruthy();
    expect(getByText('读取健康数据')).toBeTruthy();
    expect(queryByText('小巴正在思考')).toBeNull();
    expect(queryByText('2/2')).toBeNull();
    expect(queryByText('正在理解你的问题')).toBeNull();
    expect(getByLabelText(/当前步骤:读取健康数据/)).toBeTruthy();
    const panelStyle = StyleSheet.flatten(getByTestId('assistant-thinking-panel').props.style);
    expect(panelStyle.alignSelf).toBe('flex-start');
    expect(panelStyle.width).toBeUndefined();
    expect(panelStyle.maxWidth).toBe('100%');
    expect(panelStyle.minWidth).toBeGreaterThanOrEqual(200);
    expect(getByText('今晚优先固定睡眠时间。')).toBeTruthy();

    fireEvent.press(getByLabelText('展开思考步骤'));
    expect(getByText('正在理解你的问题')).toBeTruthy();
    const expandedStyle = StyleSheet.flatten(getByTestId('assistant-thinking-panel').props.style);
    expect(expandedStyle.alignSelf).toBe('stretch');
    expect(expandedStyle.borderRadius).toBeLessThanOrEqual(12);
  });

  it('uses one unified streaming status when currentStatus and thinking steps arrive together', () => {
    const { getByTestId, getByText, queryByTestId, queryByText } = renderBubble({
      id: 'assistant-streaming-status-and-thinking',
      role: 'assistant',
      content: '⏳ AI 正在思考中...',
      streaming: true,
      currentStatus: '正在记录体重和腰围…',
      thinkingSteps: ['正在理解你的问题'],
    });

    expect(getByTestId('assistant-thinking-panel')).toBeTruthy();
    expect(getByText('正在记录体重和腰围…')).toBeTruthy();
    expect(queryByTestId('assistant-status-line')).toBeNull();
    expect(queryByText('⏳ AI 正在思考中...')).toBeNull();
  });

  it('collapses completed thinking steps into an inline status row (expand to reveal steps)', () => {
    const { getByLabelText, getByTestId, getByText, queryByText, queryByLabelText } = renderBubble({
      id: 'assistant-finished-thinking',
      role: 'assistant',
      content: '今天饮食总结如下。',
      streaming: false,
      thinkingSteps: ['正在理解你的问题', '读取记录信息', '整理回复中'],
    });

    // 完成态默认折叠成低干扰胶囊: 「思考完成 · N 步」, 步骤列表隐藏.
    expect(getByText('思考完成 · 3 步')).toBeTruthy();
    const panelStyle = StyleSheet.flatten(getByTestId('assistant-thinking-panel').props.style);
    expect(panelStyle.alignSelf).toBe('flex-start');
    expect(panelStyle.borderRadius).toBeGreaterThanOrEqual(14);
    expect(panelStyle.borderWidth ?? 0).toBe(0);
    expect(panelStyle.backgroundColor).not.toBe('transparent');
    expect(queryByText('正在理解你的问题')).toBeNull();
    expect(queryByLabelText('已完成步骤:整理回复中')).toBeNull();
    // 助手正文不受折叠影响, 始终可见.
    expect(getByText('今天饮食总结如下。')).toBeTruthy();

    // 点 pill 展开 → 步骤列表出现.
    fireEvent.press(getByLabelText('展开思考步骤'));
    expect(getByText('正在理解你的问题')).toBeTruthy();
    expect(getByText('读取记录信息')).toBeTruthy();
    expect(getByText('整理回复中')).toBeTruthy();
    expect(getByLabelText('已完成步骤:整理回复中')).toBeTruthy();
    const expandedPanelStyle = StyleSheet.flatten(getByTestId('assistant-thinking-panel').props.style);
    expect(expandedPanelStyle.alignSelf).toBe('stretch');
    expect(expandedPanelStyle.borderRadius).toBeLessThanOrEqual(12);

    // 再点收起 → 步骤列表重新隐藏.
    fireEvent.press(getByLabelText('收起思考步骤'));
    expect(queryByText('读取记录信息')).toBeNull();
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

  it('offers saving attached chat images to Photos from a long press', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, buttons) => {
      buttons?.find(button => button.text === '保存到相册')?.onPress?.();
    });
    mockSaveChatImageToLibrary.mockResolvedValueOnce(undefined);

    const { getByLabelText } = renderBubble({
      id: 'user-image',
      role: 'user',
      content: '',
      imageUris: ['file:///tmp/lunch.jpg'],
      streaming: false,
    });

    fireEvent(getByLabelText('打开图片 1'), 'longPress');

    await waitFor(() => {
      expect(mockSaveChatImageToLibrary).toHaveBeenCalledWith({ uri: 'file:///tmp/lunch.jpg' });
    });

    alertSpy.mockRestore();
  });

  // Bug 1 regression: LLM 吐脏 markdown (无空格标题 / 黏连表头分隔) 时, done 首帧就应
  // 通过 normalize 后走富 markdown, 不再显示生 markdown 原文等 setState 才刷正。
  const DIRTY_MARKDOWN = [
    '##今日状态总览',
    '',
    '| 指标 | 数值 | 状态 || --- | --- | --- |',
    '| 睡眠 | 7h | 良好 |',
    '',
    '###1. 今晚早睡',
  ].join('\n');

  it('normalizes dirty LLM markdown into a parseable rich tree on the done first frame', () => {
    const { getByTestId, queryByText } = renderBubble({
      id: 'assistant-done-dirty',
      role: 'assistant',
      content: DIRTY_MARKDOWN,
      streaming: false,
    });

    // 走富 markdown 路径 (非纯文本降级), 且传入的是归一化后的内容。
    expect(getByTestId('rich-markdown')).toBeTruthy();
    expect(mockMarkdownMount).toHaveBeenCalled();
    const rendered = mockMarkdownMount.mock.calls[mockMarkdownMount.mock.calls.length - 1][0];
    // renderedMarkdown 非空且已补空格标题 / 拆开表格黏连行。
    expect(typeof rendered).toBe('string');
    expect(rendered.length).toBeGreaterThan(0);
    expect(rendered).toContain('## 今日状态总览');
    expect(rendered).toContain('### 1. 今晚早睡');
    // 无空格黏连标题不再残留。
    expect(rendered).not.toMatch(/^##今日/m);
    expect(rendered).not.toMatch(/^###1\./m);
    // 黏连表格分隔已被拆开处理, 不再逐字出现原始生 markdown 原文。
    expect(queryByText(DIRTY_MARKDOWN)).toBeNull();
  });
});
