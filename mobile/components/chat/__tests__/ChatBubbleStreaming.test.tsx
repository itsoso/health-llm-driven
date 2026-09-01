import React from 'react';
import { Alert, StyleSheet, TextInput } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';

import type { UIMessage } from '../../../hooks/useChatEngine';

const mockToastShow = jest.fn();

/* eslint-disable @typescript-eslint/no-require-imports */
jest.mock('expo-speech', () => ({ stop: jest.fn() }));
jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));
jest.mock('expo-audio', () => ({ setAudioModeAsync: jest.fn() }));
jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success' },
}));
jest.mock('../../../services/speakWithUserVoice', () => ({
  speakWithUserVoice: jest.fn(),
}));
jest.mock('../../../services/chatResultActions', () => ({
  saveAssistantReplyAsMemory: jest.fn(),
  createRecordFromAssistantReply: jest.fn(),
}));
jest.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ show: mockToastShow }),
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn() },
}));
// Spy on the markdown component so we can assert streaming replies render as Markdown.
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
  shareImage: (...args: any[]) => mockShareImage(...args),
  sharePlainText: jest.fn(),
}));
const mockSaveChatImageToLibrary = jest.fn();
const mockShareImage = jest.fn();
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
const { renderCard } = require('../cards');
const { createRecordFromAssistantReply } = require('../../../services/chatResultActions');

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

  it('renders rich Markdown while the assistant reply is streaming', () => {
    const { getByTestId } = renderBubble({
      id: 'assistant-streaming',
      role: 'assistant',
      content: CONTENT,
      streaming: true,
    });

    expect(getByTestId('rich-markdown')).toBeTruthy();
    expect(getByTestId('assistant-message-surface').props.accessible).toBe(true);
    expect(mockMarkdownMount).toHaveBeenCalled();
    expect(mockMarkdownMount).toHaveBeenLastCalledWith(CONTENT);
  });

  it('normalizes malformed assistant content before streaming render and accessibility output', () => {
    const { getByLabelText } = renderBubble({
      id: 'assistant-streaming-normalized',
      role: 'assistant',
      content: '第一段<br />第二段\n.\n.\n.\n.\n.\n.\n下一步。',
      streaming: true,
    });

    expect(mockMarkdownMount).toHaveBeenLastCalledWith('第一段\n第二段\n下一步。');
    expect(getByLabelText('AI: 第一段\n第二段\n下一步。')).toBeTruthy();
  });

  it('copies the same normalized assistant text that is rendered', async () => {
    const { getByLabelText } = renderBubble({
      id: 'assistant-normalized-copy',
      role: 'assistant',
      content: '建议一<br>建议二',
      streaming: false,
    });

    await act(async () => {
      fireEvent.press(getByLabelText('复制回答'));
      await Promise.resolve();
    });

    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('建议一\n建议二');
  });

  it('reveals message time only after tapping user and assistant bubbles', () => {
    const user = render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'user-time',
            role: 'user',
            content: '飞机准备起飞 记录下来',
            streaming: false,
            createdAt: '2026-07-14T12:30:00',
          }}
        />
      </QueryClientProvider>,
    );

    expect(user.queryByTestId('message-time')).toBeNull();
    fireEvent.press(user.getByLabelText(/你发送于/));
    expect(user.getByTestId('message-time').props.children).toBe('12:30');
    user.unmount();

    const assistant = render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'assistant-time',
            role: 'assistant',
            content: '已记录。',
            streaming: false,
            createdAt: '2026-07-14T12:31:00',
          }}
        />
      </QueryClientProvider>,
    );

    expect(assistant.queryByTestId('message-time')).toBeNull();
    fireEvent.press(assistant.getByTestId('assistant-message-surface'));
    expect(assistant.getByTestId('message-time').props.children).toBe('12:31');
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

  it('renders a normal assistant reply as an unframed content surface', () => {
    const { getByTestId, getByText, queryByTestId } = renderBubble({
      id: 'assistant-unframed',
      role: 'assistant',
      content: '今天先补水 300ml，再做 10 分钟轻活动。',
      streaming: false,
    });

    const style = StyleSheet.flatten(getByTestId('assistant-message-surface').props.style);
    expect(style.backgroundColor).toBe('transparent');
    expect(style.shadowOpacity ?? 0).toBe(0);
    expect(style.paddingHorizontal).toBe(0);
    expect(getByText('小巴')).toBeTruthy();
    expect(getByTestId('assistant-conclusion')).toBeTruthy();
    expect(queryByTestId('assistant-avatar')).toBeNull();
  });

  it('passes the existing suggested-prompt sender into health evidence cards', () => {
    const onSendSuggestedPrompt = jest.fn();
    const cardData = {
      missing_discriminators: [{
        question: '近期是否有严重外伤？',
        choices: ['有', '没有', '不确定'],
      }],
    };

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'assistant-health-evidence',
            role: 'assistant',
            content: '',
            streaming: false,
            cardType: 'health_evidence',
            cardData,
            sourceMessageId: 314,
            sourceTurnId: 'turn-parent-7',
          }}
          onSendSuggestedPrompt={onSendSuggestedPrompt}
        />
      </QueryClientProvider>,
    );

    expect(renderCard).toHaveBeenCalledWith(
      {
        type: 'health_evidence',
        data: cardData,
        actions: undefined,
      },
      expect.objectContaining({
        onSendSuggestedPrompt,
        healthEvidenceParent: {
          messageRef: 314,
          turnRef: 'turn-parent-7',
        },
      }),
    );
  });

  it('long press on an assistant message opens copy-first progressive actions instead of selecting immediately', () => {
    const onEnterSelection = jest.fn();
    const { getByLabelText, getByTestId, queryByLabelText } = render(
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

    expect(queryByLabelText('分享这条回复')).toBeNull();
    expect(queryByLabelText('语音播报')).toBeNull();
    fireEvent(getByTestId('assistant-message-surface'), 'longPress');

    expect(onEnterSelection).not.toHaveBeenCalled();
    expect(getByLabelText('复制全文')).toBeTruthy();
    expect(getByLabelText('选择这条消息')).toBeTruthy();
    expect(getByLabelText('分享这条回复')).toBeTruthy();
    expect(getByLabelText('语音播报')).toBeTruthy();
    expect(queryByLabelText('保存为记录')).toBeNull();

    fireEvent.press(getByLabelText('选择这条消息'));
    expect(onEnterSelection).toHaveBeenCalledWith('assistant-action-menu');
  });

  it('does not expose client-side prose-to-record writes for assistant replies', () => {
    const { getByLabelText, getByTestId, queryByLabelText } = renderBubble({
      id: 'assistant-prose-write-disabled',
      role: 'assistant',
      content: '已记录血压 185/85 mmHg。',
      streaming: false,
    });

    fireEvent(getByTestId('assistant-message-surface'), 'longPress');

    expect(queryByLabelText('保存为记录')).toBeNull();
    expect(getByLabelText('复制全文')).toBeTruthy();
    expect(getByLabelText('分享这条回复')).toBeTruthy();
    expect(getByLabelText('语音播报')).toBeTruthy();
    expect(createRecordFromAssistantReply).not.toHaveBeenCalled();
  });

  it('never exposes record saving for streaming, interrupted, or failed assistant output', () => {
    const { getByLabelText, queryByLabelText, rerender } = renderBubble({
      id: 'assistant-streaming-bp-fragment',
      role: 'assistant',
      content: '血压 185/85',
      streaming: true,
    });

    fireEvent(getByLabelText('AI: 血压 185/85'), 'longPress');
    expect(queryByLabelText('保存为记录')).toBeNull();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'assistant-interrupted-bp-fragment',
            role: 'assistant',
            content: '血压 185/85',
            streaming: false,
            completionStatus: 'interrupted',
          }}
        />
      </QueryClientProvider>,
    );
    fireEvent(getByLabelText('AI: 血压 185/85'), 'longPress');
    expect(queryByLabelText('保存为记录')).toBeNull();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ChatBubble
          item={{
            id: 'assistant-error-bp-fragment',
            role: 'assistant',
            content: '血压 185/85',
            streaming: false,
            completionStatus: 'error',
          }}
        />
      </QueryClientProvider>,
    );
    fireEvent(getByLabelText('AI: 血压 185/85'), 'longPress');
    expect(queryByLabelText('保存为记录')).toBeNull();
  });

  it.each([
    ['streaming', { streaming: true }],
    ['interrupted', { streaming: false, completionStatus: 'interrupted' as const }],
    ['failed', { streaming: false, completionStatus: 'error' as const }],
  ])('does not expose completion-only actions for %s assistant output', (_label, state) => {
    const { getByTestId, queryByLabelText } = renderBubble({
      id: `assistant-${_label}-partial-actions`,
      role: 'assistant',
      content: '血压 185/85，建议先',
      ...state,
    });

    fireEvent(getByTestId('assistant-message-surface'), 'longPress');

    expect(queryByLabelText('复制全文')).toBeNull();
    expect(queryByLabelText('分享这条回复')).toBeNull();
    expect(queryByLabelText('语音播报')).toBeNull();
  });

  it('long press on a user message opens copy-first actions and keeps selection secondary', async () => {
    const onEnterSelection = jest.fn();
    const { getByLabelText, queryByLabelText } = render(
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
    expect(getByLabelText('分享这条消息')).toBeTruthy();
    expect(queryByLabelText('语音播报')).toBeNull();
    await act(async () => {
      fireEvent.press(getByLabelText('复制全文'));
      await Promise.resolve();
    });
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('早餐吃了鸡蛋和咖啡');

    fireEvent(getByLabelText('你: 早餐吃了鸡蛋和咖啡'), 'longPress');
    fireEvent.press(getByLabelText('选择这条消息'));
    expect(onEnterSelection).toHaveBeenCalledWith('user-action-menu');
  });

  it('shows a compact copy action that changes in place after copying', async () => {
    const { getByLabelText, queryByLabelText } = renderBubble({
      id: 'assistant-conclusion-copy',
      role: 'assistant',
      content: '建议今天午后散步 10 分钟。',
      streaming: false,
    });

    // 完成回复直接显示紧凑复制图标,不需要长按。
    const copyBtn = getByLabelText('复制回答');
    expect(copyBtn).toBeTruthy();
    // 长按菜单尚未展开 → 没有「复制全文」
    expect(queryByLabelText('复制全文')).toBeNull();

    await act(async () => {
      fireEvent.press(copyBtn);
      await Promise.resolve();
    });
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('建议今天午后散步 10 分钟。');
    await waitFor(() => expect(getByLabelText('已复制')).toBeTruthy());
  });

  it('hides the conclusion copy button while the assistant reply is still streaming', () => {
    const { queryByLabelText } = renderBubble({
      id: 'assistant-streaming-no-copy',
      role: 'assistant',
      content: '正在分析…',
      streaming: true,
    });
    expect(queryByLabelText('复制回答')).toBeNull();
  });

  it('renders one unified streaming status before the first token', () => {
    const { getAllByTestId, getByTestId, getByText, queryByTestId } = renderBubble({
      id: 'assistant-status-line',
      role: 'assistant',
      content: '⏳ AI 正在思考中...',
      streaming: true,
      currentStatus: '查看步数数据…',
    });

    // 统一处理状态出现, 文案即 currentStatus; 不再叠一个独立 status line。
    expect(getByTestId('assistant-thinking-panel')).toBeTruthy();
    expect(getAllByTestId('assistant-thinking-indicator')).toHaveLength(1);
    expect(getByText('正在分析')).toBeTruthy();
    expect(getByText('查看步数数据…')).toBeTruthy();
    expect(getByTestId('assistant-thinking-skeleton')).toBeTruthy();
    expect(queryByTestId('assistant-status-line')).toBeNull();
    // 未出正文 → 不走富 markdown。
    expect(queryByTestId('rich-markdown')).toBeNull();
    expect(mockMarkdownMount).not.toHaveBeenCalled();
  });

  it('uses the same thinking panel while waiting for the first status event', () => {
    const { getAllByTestId, getByTestId, getByText, queryByTestId } = renderBubble({
      id: 'assistant-waiting-for-status',
      role: 'assistant',
      content: '',
      streaming: true,
    });

    expect(getByTestId('assistant-thinking-panel')).toBeTruthy();
    expect(getAllByTestId('assistant-thinking-indicator')).toHaveLength(1);
    expect(getByText('正在理解你的问题…')).toBeTruthy();
    expect(queryByTestId('assistant-status-line')).toBeNull();
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

  it('renders streaming thinking steps as one stable analysis panel above the assistant text', () => {
    const { getByLabelText, getByTestId, getByText, queryByText, queryByTestId } = renderBubble({
      id: 'assistant-streaming-thinking',
      role: 'assistant',
      content: '今晚优先固定睡眠时间。',
      streaming: true,
      thinkingSteps: ['正在理解你的问题', '读取健康数据'],
    });

    expect(getByTestId('rich-markdown')).toBeTruthy();
    expect(mockMarkdownMount).toHaveBeenCalled();
    expect(getByText('正在分析')).toBeTruthy();
    expect(getByText('读取健康数据')).toBeTruthy();
    expect(queryByText('小巴正在思考')).toBeNull();
    expect(queryByText('2/2')).toBeNull();
    expect(getByText('正在理解你的问题')).toBeTruthy();
    expect(getByLabelText(/当前步骤:读取健康数据/)).toBeTruthy();
    const panelStyle = StyleSheet.flatten(getByTestId('assistant-thinking-panel').props.style);
    expect(panelStyle.alignSelf).toBe('stretch');
    expect(panelStyle.width).toBe('100%');
    expect(panelStyle.borderRadius).toBeLessThanOrEqual(10);
    expect(panelStyle.borderLeftWidth).toBeGreaterThanOrEqual(2);
    expect(queryByTestId('assistant-thinking-skeleton')).toBeNull();
    expect(getByText('今晚优先固定睡眠时间。')).toBeTruthy();
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

  it('presents completed thinking steps as a concise process summary', () => {
    const { getByLabelText, getByTestId, getByText, queryByText, queryByTestId } = renderBubble({
      id: 'assistant-finished-thinking',
      role: 'assistant',
      content: '今天饮食总结如下。',
      streaming: false,
      thinkingSteps: ['正在理解你的问题', '读取记录信息', '整理回复中'],
    });

    expect(queryByTestId('assistant-thinking-panel')).toBeNull();
    expect(queryByText('思考完成')).toBeNull();
    expect(getByTestId('assistant-utility-panel')).toBeTruthy();
    expect(getByTestId('assistant-message-surface').props.accessible).toBe(false);
    expect(queryByText('正在理解你的问题')).toBeNull();
    expect(getByText('今天饮食总结如下。')).toBeTruthy();

    expect(getByLabelText('展开回答依据')).toHaveStyle({ minHeight: 44 });
    expect(getByLabelText('复制回答')).toHaveStyle({ width: 44, height: 44 });
    fireEvent.press(getByLabelText('展开回答依据'));
    expect(getByText('处理摘要')).toBeTruthy();
    expect(getByText('理解你的问题')).toBeTruthy();
    expect(getByText('读取记录信息')).toBeTruthy();
    expect(getByText('整理回答')).toBeTruthy();
    expect(queryByText('思考过程')).toBeNull();
    expect(queryByText('正在理解你的问题')).toBeNull();
    expect(queryByText('整理回复中')).toBeNull();

    fireEvent.press(getByLabelText('收起回答依据'));
    expect(queryByText('读取记录信息')).toBeNull();
  });

  it('shows concrete observations and limitations before generic execution records', () => {
    const { getByLabelText, getByText, queryByText } = renderBubble({
      id: 'assistant-structured-answer-evidence',
      role: 'assistant',
      content: '今天建议降低训练强度。',
      streaming: false,
      sourcesUsed: ['在服补剂 (10 种)', '主目标: 总体健康'],
      thinkingSteps: ['正在查询健康数据', '检查健康数据', '整理回复中'],
      answerEvidence: {
        version: 'answer-evidence.v1',
        summary: '本轮获得 1 条可核对数据，1 项需注意',
        basis: [{
          id: 'wearable.hrv.latest',
          label: 'HRV',
          observation: '31 ms',
          context: '今天 07:55',
          source: 'Garmin',
          purpose: '用于评估恢复与活动承受度',
          freshness: 'current',
        }],
        limitations: [{
          id: 'wearable.resting-heart-rate',
          title: '静息心率未同步',
          detail: '昨晚没有可用记录',
          handling: '未按正常值处理，运动建议已保持保守',
        }],
      },
    });

    expect(getByText('回答依据 · 2项')).toBeTruthy();
    fireEvent.press(getByLabelText('展开回答依据'));
    expect(getByText('关键依据')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    expect(getByText('31 ms')).toBeTruthy();
    expect(getByText('用于评估恢复与活动承受度')).toBeTruthy();
    expect(getByText('Garmin')).toBeTruthy();
    expect(getByText('当前数据')).toBeTruthy();
    expect(getByText('数据限制')).toBeTruthy();
    expect(getByText('静息心率未同步')).toBeTruthy();
    expect(getByText('未按正常值处理，运动建议已保持保守')).toBeTruthy();
    expect(queryByText('处理摘要')).toBeNull();
    expect(queryByText('在服补剂 (10 种)')).toBeNull();
    expect(queryByText('主目标: 总体健康')).toBeNull();
    expect(queryByText('查询健康数据')).toBeNull();

    fireEvent.press(getByLabelText('展开技术详情'));
    expect(getByText('执行记录')).toBeTruthy();
    expect(getByText(/查询健康数据/)).toBeTruthy();
    expect(getByText(/整理回答/)).toBeTruthy();
  });

  it('shows structured evidence before verified text without enabling completion actions', () => {
    const { getByLabelText, getByText, queryByLabelText } = renderBubble({
      id: 'assistant-streaming-answer-evidence',
      role: 'assistant',
      content: '',
      streaming: true,
      answerEvidence: {
        version: 'answer-evidence.v1',
        summary: '本轮获得 1 条可核对数据',
        basis: [{
          id: 'wearable.hrv.latest',
          label: 'HRV',
          observation: '31 ms',
          source: 'Garmin',
          purpose: '用于评估恢复与活动承受度',
        }],
        limitations: [],
      },
    });

    expect(getByText('回答依据 · 1项')).toBeTruthy();
    expect(queryByLabelText('复制回答')).toBeNull();
    expect(queryByLabelText('微信分享这条回复')).toBeNull();
    fireEvent.press(getByLabelText('展开回答依据'));
    expect(getByText('HRV')).toBeTruthy();
    expect(getByText('31 ms')).toBeTruthy();
  });

  it('labels retained evidence when the reply ends incomplete', () => {
    const { getByLabelText, getByText } = renderBubble({
      id: 'assistant-interrupted-answer-evidence',
      role: 'assistant',
      content: '本轮回答没有完整结束。',
      streaming: false,
      completionStatus: 'interrupted',
      answerEvidence: {
        version: 'answer-evidence.v1',
        summary: '本轮获得 1 条可核对数据',
        basis: [{
          id: 'wearable.hrv.latest',
          label: 'HRV',
          observation: '31 ms',
          source: 'Garmin',
          purpose: '用于评估恢复与活动承受度',
        }],
        limitations: [],
      },
    });

    fireEvent.press(getByLabelText('展开回答依据'));
    expect(getByText('回复未完整结束，以下依据仅用于核对本轮处理。')).toBeTruthy();
  });

  it('keeps unavailable steps honest and hides diagnostics behind technical details', () => {
    const { getByLabelText, getByTestId, getByText, queryByText } = renderBubble({
      id: 'assistant-finished-process-warning',
      role: 'assistant',
      content: '今天的步数暂时没有同步。',
      streaming: false,
      thinkingSteps: ['正在查询健康数据', '记录信息暂时不可用', '整理回复中'],
      elapsedMs: 6100,
      llmRounds: 2,
      model: 'qwen3.6-flash',
      toolsUsed: ['health_query'],
      llmUsage: {
        run_id: 'run_safe_123',
        providers: ['tokenplan'],
        calls: 2,
        prompt_tokens: 640,
        completion_tokens: 80,
        total_tokens: 720,
        tokenplan_cost_cny: 0.002,
        tokenplan_cost_estimated: true,
        failed_calls: 1,
        items: [{
          run_id: 'run_safe_123',
          success: false,
          error_code: 'upstream_timeout',
          error_message: 'SECRET health payload and stack trace',
          recovery_action: 'fallback_attempted',
        }],
      },
    });

    fireEvent.press(getByLabelText('展开回答依据'));

    expect(getByText('完成 2 个处理步骤，1 项需要注意')).toBeTruthy();
    expect(getByTestId('icon-alert-circle-outline')).toBeTruthy();
    expect(getByText('查询健康数据')).toBeTruthy();
    expect(getByLabelText('需要注意：记录信息暂时不可用')).toBeTruthy();
    expect(queryByText(/qwen3\.6-flash/)).toBeNull();
    expect(queryByText('成本估算')).toBeNull();
    expect(queryByText('health_query')).toBeNull();
    expect(queryByText(/SECRET health payload/)).toBeNull();

    fireEvent.press(getByLabelText('展开技术详情'));
    expect(getByText(/qwen3\.6-flash/)).toBeTruthy();
    expect(getByText('成本估算')).toBeTruthy();
    expect(getByText('Token')).toBeTruthy();
    expect(getByText('失败信息')).toBeTruthy();
    expect(getByText('追踪信息')).toBeTruthy();
    expect(getByText('调用工具')).toBeTruthy();
    expect(getByText('health_query')).toBeTruthy();
    expect(queryByText(/SECRET health payload/)).toBeNull();
  });

  // 流式期间正文仍走统一清洗管线,但卡片等到权威 done 后再挂载,
  // 避免一个尚未稳定的协议块产生交互表面。
  const CONTENT_WITH_MARKERS = [
    '这是回复[附图: lab.jpg]正文。',
    '',
    '```reva-ui',
    '{"v":1,"component":"line_chart","title":"趋势","x":["1","2"],"series":[{"name":"a","points":[1,2]}]}',
    '```',
  ].join('\n');

  it('normalizes streaming content but waits for done before rendering cards', () => {
    const { queryByTestId, getByTestId } = renderBubble({
      id: 'assistant-streaming-markers',
      role: 'assistant',
      content: CONTENT_WITH_MARKERS,
      streaming: true,
    });

    expect(queryByTestId('assistant-reva-ui-cards')).toBeNull();
    expect(getByTestId('rich-markdown')).toBeTruthy();
    expect(mockMarkdownMount).toHaveBeenLastCalledWith('这是回复正文。');
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

  it('does not make editable inline cards part of the assistant bubble touch target', () => {
    (renderCard as jest.Mock).mockReturnValueOnce(
      <TextInput
        accessibilityLabel="卡片食物描述"
        value="牛肉面"
        onChangeText={jest.fn()}
      />,
    );
    const editableCardContent = [
      '```reva-ui',
      JSON.stringify({
        v: 1,
        component: 'record_quality',
        domain: 'diet',
        expanded_sections: ['adjust_record'],
        adjust_record: {
          record_id: 123,
          meal_type: 'dinner',
          food_items: '牛肉面',
        },
      }),
      '```',
    ].join('\n');

    const { getByLabelText, queryByLabelText } = renderBubble({
      id: 'assistant-inline-editable-card',
      role: 'assistant',
      content: editableCardContent,
      streaming: false,
    });

    expect(getByLabelText('卡片食物描述')).toBeTruthy();
    expect(queryByLabelText('AI: 图表卡片')).toBeNull();
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

  it('downloads and shares a protected chat image from the long-press menu', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, buttons) => {
      buttons?.find(button => button.text === '分享图片')?.onPress?.();
    });
    mockShareImage.mockResolvedValueOnce(undefined);
    const qc = new QueryClient();
    const imageUri = 'https://health.executor.life/api/v1/upload/files/chat/7/lunch.jpg';
    const { getByLabelText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble
          item={{
            id: 'user-protected-image',
            role: 'user',
            content: '',
            imageUris: [imageUri],
            streaming: false,
          }}
          imageAuthToken="auth-token"
        />
      </QueryClientProvider>,
    );

    fireEvent(getByLabelText('打开图片 1'), 'longPress');

    await waitFor(() => {
      expect(mockShareImage).toHaveBeenCalledWith(imageUri, {
        target: 'more',
        cacheKey: 'user-protected-image',
        headers: { Authorization: 'Bearer auth-token' },
      });
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
    const { getByTestId, getByText, queryByText } = renderBubble({
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
    expect(getByTestId('assistant-conclusion')).toBeTruthy();
    expect(getByText('今日状态总览')).toBeTruthy();
    expect(rendered).not.toContain('## 今日状态总览');
    expect(rendered).toContain('### 1. 今晚早睡');
    // 无空格黏连标题不再残留。
    expect(rendered).not.toMatch(/^##今日/m);
    expect(rendered).not.toMatch(/^###1\./m);
    // 黏连表格分隔已被拆开处理, 不再逐字出现原始生 markdown 原文。
    expect(queryByText(DIRTY_MARKDOWN)).toBeNull();
  });

  it('normalizes dirty LLM markdown while streaming so raw heading markers do not show', () => {
    const { getByTestId, queryByText } = renderBubble({
      id: 'assistant-streaming-dirty',
      role: 'assistant',
      content: DIRTY_MARKDOWN,
      streaming: true,
    });

    expect(getByTestId('rich-markdown')).toBeTruthy();
    expect(mockMarkdownMount).toHaveBeenCalled();
    const rendered = mockMarkdownMount.mock.calls[mockMarkdownMount.mock.calls.length - 1][0];
    expect(rendered).toContain('## 今日状态总览');
    expect(rendered).toContain('### 1. 今晚早睡');
    expect(rendered).not.toMatch(/^##今日/m);
    expect(rendered).not.toMatch(/^###1\./m);
    expect(queryByText(DIRTY_MARKDOWN)).toBeNull();
  });
});
