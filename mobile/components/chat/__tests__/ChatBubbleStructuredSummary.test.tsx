import React from 'react';
import { Alert, StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { UIMessage } from '../../../hooks/useChatEngine';

const mockToastShow = jest.fn();
const mockRememberVerifiedWriteReceipt = jest.fn().mockResolvedValue(undefined);
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('1_3s');
const mockLoadCardActionReceipt = jest.fn().mockResolvedValue(undefined);
const mockSaveCardActionReceipt = jest.fn().mockResolvedValue(undefined);
const mockSaveChatImageToLibrary = jest.fn().mockResolvedValue(undefined);
const mockShareLocalImage = jest.fn().mockResolvedValue(undefined);
const mockCreateInterventionDraft = jest.fn().mockResolvedValue({ id: 88 });
const mockDietShareComposer = jest.fn();
const mockAlert = jest.spyOn(Alert, 'alert');
const mockCaptureRefCalls: { testID?: string; options: unknown }[] = [];
let mockCaptureRefResult = 'file:///tmp/diet-card.png';

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
jest.mock('../../../services/chatCardActions', () => ({
  dispatchChatCardAction: jest.fn(),
}));
jest.mock('../../../services/conversationContinuity', () => ({
  rememberVerifiedWriteReceipt: (...args: any[]) => mockRememberVerifiedWriteReceipt(...args),
}));
jest.mock('../../../services/cardActionReceiptStorage', () => ({
  buildCardActionReceiptIdentity: jest.fn((action: any, cardType: string) => (
    `${cardType}:${action.id || action.action}:${action.endpoint || ''}`
  )),
  loadCardActionCompletion: async (...args: any[]) => {
    const receipt = await mockLoadCardActionReceipt(...args);
    return receipt ? { verified: true, receipt } : undefined;
  },
  saveCardActionReceipt: (...args: any[]) => mockSaveCardActionReceipt(...args),
}));
jest.mock('../../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
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
  const MockMarkdown = ({ children }: { children: string }) => {
    if (String(children || '').includes('THROW_MARKDOWN')) {
      throw new Error('markdown render failed');
    }
    return <Text>{children}</Text>;
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
jest.mock('../cards', () => {
  const React = require('react');
  const { View, Text } = require('react-native');
  return {
    renderCard: jest.fn(() => null),
    getCardActionRuntimeKey: jest.fn((action: any, descriptor?: any) => (
      action.id || `${descriptor?.type ?? 'card'}:${action.action}:${action.label}`
    )),
    getCardActionRuntimeGroupKey: jest.fn((action: any, descriptor?: any) => (
      (action.action === 'write_intent.confirm' || action.action === 'write_intent.dismiss')
        && action.payload?.write_intent_id
        ? `write_intent:${action.payload.write_intent_id}`
        : action.id || `${descriptor?.type ?? 'card'}:${action.action}:${action.label}`
    )),
    __mockCard: <View><Text>今晚晚餐建议</Text></View>,
  };
});
jest.mock('../../../utils/share', () => ({
  sharePlainText: jest.fn(),
  sharePlainCaption: jest.fn(),
  shareLocalImage: (...args: any[]) => mockShareLocalImage(...args),
}));
jest.mock('react-native-view-shot', () => ({
  captureRef: (target: any, options: unknown) => {
    mockCaptureRefCalls.push({ testID: target?.props?.testID, options });
    return Promise.resolve(mockCaptureRefResult);
  },
}));
jest.mock('../../../services/chatImageSave', () => ({
  saveChatImageToLibrary: (...args: any[]) => mockSaveChatImageToLibrary(...args),
}));
jest.mock('../../../services/actionCards', () => ({
  createInterventionDraft: (...args: any[]) => mockCreateInterventionDraft(...args),
}));
jest.mock('../../diet/DietShareComposer', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    DietShareComposer: (props: any) => {
      mockDietShareComposer(props);
      return <View testID="mock-diet-share-composer" />;
    },
  };
});

const ChatBubble = require('../ChatBubble').default;
const { dispatchChatCardAction } = require('../../../services/chatCardActions');
const { renderCard, __mockCard } = require('../cards');
const { sharePlainText } = require('../../../utils/share');
const { sharePlainCaption } = require('../../../utils/share');
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

function verifiedReceipt(
  resourceType = 'diet_record',
  resourceId = '77',
  action?: 'create' | 'update' | 'delete',
) {
  return {
    operationId: `${resourceType}:${resourceId}`,
    status: 'verified' as const,
    resourceType,
    resourceId,
    ...(action ? { action } : {}),
    completedAt: '2026-07-09T12:00:00.000Z',
    verified: true as const,
  };
}

describe('ChatBubble structured summary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockToastShow.mockClear();
    renderCard.mockReset();
    renderCard.mockReturnValue(null);
    mockLoadCardActionReceipt.mockReset();
    mockLoadCardActionReceipt.mockResolvedValue(undefined);
    mockSaveCardActionReceipt.mockReset();
    mockSaveCardActionReceipt.mockResolvedValue(undefined);
    mockCaptureRefCalls.length = 0;
    mockCaptureRefResult = 'file:///tmp/diet-card.png';
    mockSaveChatImageToLibrary.mockReset();
    mockSaveChatImageToLibrary.mockResolvedValue(undefined);
    mockShareLocalImage.mockReset();
    mockShareLocalImage.mockResolvedValue(undefined);
    mockDietShareComposer.mockClear();
    mockCreateInterventionDraft.mockReset();
    mockCreateInterventionDraft.mockResolvedValue({ id: 88 });
    mockAlert.mockImplementation((_title, _message, buttons) => {
      buttons?.find(button => button.style !== 'cancel')?.onPress?.();
    });
  });

  it('summarizes markdown metric tables and today advice for mobile scanning', () => {
    const { getByText, getByTestId, queryByText } = renderBubble(`
| 指标 | 数值 | 状态 |
| --- | --- | --- |
| 睡眠 | 89 分 | ✅ 优秀 |
| HRV | 62.0ms 较7日均值 ↑7% | ✅ |
| 饮水 | 0ml/2000ml | ⚠️ 0% |

📌 今日建议：
1. 饮水未达标，上午补充 500ml
2. 饭后散步 10 分钟
`);

    expect(getByText('小巴')).toBeTruthy();
    expect(getByTestId('assistant-metric-grid')).toBeTruthy();
    expect(getByTestId('assistant-action-card')).toBeTruthy();
    expect(getByText('睡眠')).toBeTruthy();
    expect(getByText('89 分')).toBeTruthy();
    expect(getByText('今天只做')).toBeTruthy();
    expect(getByText('饮水未达标，上午补充 500ml')).toBeTruthy();
    expect(getByText('饭后散步 10 分钟')).toBeTruthy();
    expect(queryByText(/\| 指标 \| 数值 \| 状态 \|/)).toBeNull();
  });

  it('keeps metric cells dense enough to scan without dominating the conversation', () => {
    const { getAllByTestId } = renderBubble(`
| 指标 | 数值 | 状态 |
| --- | --- | --- |
| 睡眠 | 89 分 | ✅ 优秀 |
| HRV | 62ms | ✅ 正常 |
`);

    const cells = getAllByTestId(/^assistant-metric-cell-/);
    expect(cells.length).toBe(2);
    cells.forEach(cell => {
      const style = StyleSheet.flatten(cell.props.style);
      expect(style.minHeight).toBeLessThanOrEqual(76);
      expect(style.paddingVertical).toBeLessThanOrEqual(8);
    });
  });

  it('strips markdown heading/list/bold markers from today advice items', () => {
    const { getByText, queryByText } = renderBubble(`
📌 今日建议：
1. ### ✅ 饭后散步 10 分钟
2. **上午补水 500ml**
`);

    expect(getByText('今天只做')).toBeTruthy();
    // "### " heading marker stripped
    expect(getByText('✅ 饭后散步 10 分钟')).toBeTruthy();
    // "**bold**" emphasis stripped
    expect(getByText('上午补水 500ml')).toBeTruthy();
    // no literal markdown markers leak into the card
    expect(queryByText(/###/)).toBeNull();
  });

  it('does not mistake an informational mention of advice for a today action', () => {
    const { queryByTestId, getByText } = renderBubble(`
根据你最近的记录，为你整理了当前的用药方案、身体状况及关键建议与注意事项。

### 💊 一、近期主要用药清单

加斯清：按医生处方使用。

### 🏥 二、当前主要病症与身体状态

胃肠道修复中，需要继续观察。
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/当前主要病症与身体状态/)).toBeTruthy();
  });

  it('does not turn a section title under today advice into an executable action', () => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：

### 二、当前主要病症与身体状态

胃部仍在修复期，继续观察即可。
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/当前主要病症与身体状态/)).toBeTruthy();
  });

  it.each([
    '今晚将处方药增加为两片并继续服用',
    '今晚吃阿司匹林一片',
    '二甲双胍改为两片',
    '补充辅酶Q10一粒',
  ])('never turns free-form medication guidance into an add-to-today action: %s', (medicationAdvice) => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：
1. ${medicationAdvice}
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(new RegExp(medicationAdvice))).toBeTruthy();
  });

  it('does not turn a short noun plan into an executable action', () => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：
1. 睡眠与训练计划
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/睡眠与训练计划/)).toBeTruthy();
  });

  it.each([
    '今天补水 9999ml',
    '睡前补水 1500ml',
    '饭后散步 999999分钟',
    '今晚低强度走路 180分钟',
    '今晚低强度走路 30000步',
    '今晚 99点前睡觉',
    '晚餐增加盐 500克',
    '晚餐增加蛋白质 500克',
    '下一餐多吃主食 500g',
    '下一餐多吃糖 500g',
  ])('rejects unsafe or impossible action values: %s', unsafeAdvice => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：
1. ${unsafeAdvice}
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(new RegExp(unsafeAdvice))).toBeTruthy();
  });

  it.each([
    '睡前休息',
    '记录症状',
    '监测血压',
  ])('does not treat an unscoped action-like section title as a today action: %s', sectionTitle => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：
${sectionTitle}
睡眠情况需要持续观察。
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(new RegExp(sectionTitle))).toBeTruthy();
  });

  it('preserves the complete markdown section when safe and medication advice are mixed', () => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：
1. 饭后散步 10 分钟
2. 今晚服用阿司匹林一片
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/今日建议/)).toBeTruthy();
    expect(getByText(/饭后散步 10 分钟/)).toBeTruthy();
    expect(getByText(/今晚服用阿司匹林一片/)).toBeTruthy();
  });

  it('does not let a blank line bypass complete section validation', () => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：
1. 饭后散步 10 分钟

2. 今晚服用阿司匹林一片
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/今日建议/)).toBeTruthy();
    expect(getByText(/饭后散步 10 分钟/)).toBeTruthy();
    expect(getByText(/今晚服用阿司匹林一片/)).toBeTruthy();
  });

  it('accepts a time-scoped low-risk 今日行动 header', () => {
    const { getByTestId, getByText } = renderBubble(`
📌 今日行动：
1. 饭后散步 10 分钟
`);

    expect(getByTestId('assistant-action-card')).toBeTruthy();
    expect(getByText('饭后散步 10 分钟')).toBeTruthy();
  });

  it('does not infer a today action from a bare 行动 header', () => {
    const { queryByTestId, getByText } = renderBubble(`
行动：
1. 饭后散步 10 分钟
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/饭后散步 10 分钟/)).toBeTruthy();
  });

  it('keeps standalone markdown headings out of the action affordance', () => {
    const { queryByTestId, getByText } = renderBubble(`
📌 今日建议：

### 睡眠与训练安排

今晚根据恢复状态再决定训练内容。
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/睡眠与训练安排/)).toBeTruthy();
  });

  it('preserves rejected advice markdown when metric extraction still runs', () => {
    const { queryByTestId, getByText, queryByText } = renderBubble(`
| 指标 | 数值 | 状态 |
| --- | --- | --- |
| 睡眠 | 75 分 | 一般 |

📌 今日建议：

### 用药与监测安排

继续按医生处方执行，任何剂量调整先咨询医生。
`);

    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(getByText(/用药与监测安排/)).toBeTruthy();
    expect(getByText(/任何剂量调整先咨询医生/)).toBeTruthy();
    expect(queryByText(/\| 指标 \| 数值 \| 状态 \|/)).toBeNull();
  });

  it('uses a calm light action surface instead of a dark hero card', () => {
    const { getByTestId, getByText } = renderBubble(
      '📌 今日建议：\n1. 今晚暂停高强度训练，优先睡眠与轻活动',
    );

    const actionCardStyle = StyleSheet.flatten(getByTestId('assistant-action-card').props.style);
    const actionTitleStyle = StyleSheet.flatten(
      getByText('今晚暂停高强度训练，优先睡眠与轻活动').props.style,
    );
    expect(actionCardStyle.backgroundColor).toBe('#FBFAF7');
    expect(actionTitleStyle.color).toBe('#16201B');
  });

  it('promotes the assistant identity without changing the conclusion reading scale', () => {
    const { getByText, getByTestId } = renderBubble('今晚先补水 300ml，再散步 10 分钟。');

    const label = getByText('小巴');
    const dot = getByTestId('assistant-conclusion-dot');
    const container = getByTestId('assistant-conclusion');
    const conclusion = getByText('今晚先补水 300ml，再散步 10 分钟。');
    const labelStyle = StyleSheet.flatten(label.props.style);
    const dotStyle = StyleSheet.flatten(dot.props.style);
    const containerStyle = StyleSheet.flatten(container.props.style);
    const conclusionStyle = StyleSheet.flatten(conclusion.props.style);
    expect(labelStyle).toMatchObject({
      fontSize: 16,
      lineHeight: 22,
      fontWeight: '700',
      color: '#176F49',
    });
    expect(dotStyle).toMatchObject({
      width: 6,
      height: 6,
      borderRadius: 3,
      backgroundColor: '#1F8A5B',
    });
    expect(conclusionStyle).toMatchObject({
      fontSize: 15,
      lineHeight: 23,
      fontWeight: '400',
    });
    expect(containerStyle.gap).toBe(8);
    expect(label.props.allowFontScaling).not.toBe(false);
    expect(conclusion.props.allowFontScaling).not.toBe(false);
    expect(conclusion.props.numberOfLines).toBeUndefined();
  });

  it('does not render an action card for placeholder advice', () => {
    const { getByTestId, queryByTestId, queryByText } = renderBubble(`
| 指标 | 数值 | 状态 |
| --- | --- | --- |
| 饮食 | 1710 kcal | 已记录 |

📌 今日建议：
--
`);

    expect(getByTestId('assistant-metric-grid')).toBeTruthy();
    expect(queryByTestId('assistant-action-card')).toBeNull();
    expect(queryByText('--')).toBeNull();
  });

  it('renders a short write receipt as body text instead of an oversized conclusion', () => {
    const receipt = '已记录症状：打喷嚏（记录号 74，说“撤销”可以删除）';
    const { getByText, queryByTestId } = renderBubble(receipt);

    expect(queryByTestId('assistant-conclusion')).toBeNull();
    expect(getByText(receipt)).toBeTruthy();
  });

  it('opens a direct today-plan confirmation instead of sending a second plan prompt', async () => {
    const qc = new QueryClient();
    const onSendSuggestedPrompt = jest.fn();
    const message: UIMessage = {
      id: 'assistant-today-action',
      role: 'assistant',
      content: '📌 今日建议：\n1. 今晚暂停高强度训练，优先睡眠与轻活动',
      streaming: false,
    };
    const { getByLabelText, getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} onSendSuggestedPrompt={onSendSuggestedPrompt} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByLabelText('把建议加入今天计划'));

    expect(onSendSuggestedPrompt).not.toHaveBeenCalled();
    expect(getByText('加入今日计划')).toBeTruthy();
    expect(getByLabelText('今日计划标题')).toBeTruthy();

    await act(async () => {
      fireEvent.press(getByLabelText('确认加入今日计划'));
    });
    await waitFor(() => {
      expect(mockCreateInterventionDraft).toHaveBeenCalledWith(expect.objectContaining({
        title: expect.stringContaining('暂停高强度训练'),
        source_type: 'chat',
        verification_days: 1,
      }));
    });
  });

  it('keeps a compact WeChat and Xiaohongshu share rail while speech remains in the long-press menu', () => {
    const { getByText, getByLabelText, getByTestId, queryByText } = renderBubble(
      '建议今晚 23:00 前睡觉，并在睡前 3 小时停止正餐。',
    );

    expect(queryByText('加入今日计划')).toBeNull();
    expect(queryByText('保存记忆')).toBeNull();
    expect(queryByText('生成记录')).toBeNull();
    expect(queryByText('继续追问')).toBeNull();
    expect(getByText('微信')).toBeTruthy();
    expect(getByText('小红书')).toBeTruthy();
    expect(getByLabelText('微信分享这条回复')).toBeTruthy();
    expect(getByLabelText('小红书分享这条回复')).toBeTruthy();
    expect(() => getByLabelText('语音播报')).toThrow();

    fireEvent(getByTestId('assistant-message-surface'), 'longPress');
    expect(getByLabelText('分享这条回复')).toBeTruthy();
    expect(getByLabelText('语音播报')).toBeTruthy();
  });

  it('does not expose social sharing for interrupted assistant replies', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-interrupted',
      role: 'assistant',
      content: '这条回复只生成了一部分',
      streaming: false,
      completionStatus: 'interrupted',
    };
    const { queryByLabelText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(queryByLabelText('微信分享这条回复')).toBeNull();
    expect(queryByLabelText('小红书分享这条回复')).toBeNull();
  });

  it('falls back to readable text when markdown rendering fails', () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      expect(() => {
        const { getByText } = renderBubble('THROW_MARKDOWN\n\n这条内容仍然要显示');
        expect(getByText(/这条内容仍然要显示/)).toBeTruthy();
      }).not.toThrow();
    } finally {
      errorSpy.mockRestore();
      warnSpy.mockRestore();
    }
  });

  it('does not offer a second prose-derived write after health_record already completed', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-record-complete',
      role: 'assistant',
      content: '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal',
      streaming: false,
      toolsUsed: ['health_record'],
      completionStatus: 'complete',
    };

    const { queryByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(queryByText('加入今日计划')).toBeNull();
    expect(queryByText('保存记忆')).toBeNull();
    expect(queryByText('生成记录')).toBeNull();
    expect(queryByText('继续追问')).toBeNull();
  });

  it('shares assistant replies under the 小巴 persona', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);

    const { getByLabelText, getByTestId } = renderBubble('今天先补水 300ml, 晚饭后散步 15 分钟。');

    fireEvent(getByTestId('assistant-message-surface'), 'longPress');
    fireEvent.press(getByLabelText('分享这条回复'));
    fireEvent.press(getByLabelText('系统分享'));

    await waitFor(() => {
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '小巴 · 建议',
      }));
    });
  });

  it('shares assistant replies from the Xiaohongshu action too', async () => {
    sharePlainCaption.mockResolvedValueOnce(undefined);

    const { getByLabelText, getByTestId } = renderBubble('今天午餐记录完成，晚饭少油并补 30g 蛋白。');

    fireEvent(getByTestId('assistant-message-surface'), 'longPress');
    fireEvent.press(getByLabelText('分享这条回复'));
    fireEvent.press(getByLabelText('小红书文案'));

    await waitFor(() => {
      expect(sharePlainCaption).toHaveBeenCalledWith(expect.objectContaining({
        title: '小巴 · 小红书文案',
        message: expect.not.stringContaining('http'),
      }));
      expect(sharePlainCaption).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('小巴给我的今日建议'),
      }));
      expect(sharePlainText).not.toHaveBeenCalled();
      expect(sharePlainCaption).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('#健康管理 #生活方式改善 #小巴'),
      }));
    });
  });

  it('shares completed diet records with a polished social note', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);

    const content = [
      '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal（蛋白 30g / 碳水 70g / 脂肪 17g）',
      '晚餐建议：优先补 40g 蛋白，少油少刺激。',
    ].join('\n');
    const { getByLabelText, getByTestId } = renderBubble(content);

    fireEvent(getByTestId('assistant-message-surface'), 'longPress');
    fireEvent.press(getByLabelText('分享这条回复'));
    fireEvent.press(getByLabelText('系统分享'));

    await waitFor(() => {
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('今天这餐被小巴认真记下来了'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('#饮食记录 #健康管理 #小巴'),
      }));
    });
  });

  it('renders backend source metadata and opens memory management from a memory source', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-sources',
      role: 'assistant',
      content: '今晚优先休息。',
      streaming: false,
      sourcesUsed: ['用户记忆', 'Garmin 数据 (14 天 HRV/睡眠/RHR)'],
    };
    const { getByText, getByLabelText, queryByText, queryByLabelText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByText('回答依据 · 2项')).toBeTruthy();
    expect(queryByText('使用数据 · 2 项')).toBeNull();
    expect(queryByLabelText('展开执行透视')).toBeNull();
    fireEvent.press(getByLabelText('展开回答依据'));
    expect(getByText('用户记忆')).toBeTruthy();
    expect(getByText('Garmin 数据 (14 天 HRV/睡眠/RHR)')).toBeTruthy();
    fireEvent.press(getByLabelText('查看 AI 记忆来源：用户记忆'));
    expect(router.push).toHaveBeenCalledWith('/memory');
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
    renderCard.mockReturnValue(__mockCard);
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

  it('opens the editable composer instead of capturing the operational diet card', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);
    renderCard.mockReturnValue(__mockCard);
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-diet-share',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      writeReceipts: [verifiedReceipt('diet_record', '770')],
      cardData: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        suggestions: ['晚餐优先补 40g 蛋白'],
        photo_url: '/api/v1/upload/files/diet/1/lunch.jpg',
      },
    };

    const { getByLabelText, getByTestId, queryByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} imageAuthToken="secret-token" />
      </QueryClientProvider>,
    );

    expect(queryByText('保存图片')).toBeNull();
    expect(getByTestId('assistant-card-share-actions')).toBeTruthy();
    expect(queryByText('截图可直接发微信 / 小红书')).toBeNull();

    expect(getByTestId('assistant-card-share-actions')).toHaveStyle({
      flexDirection: 'row',
      flexWrap: 'wrap',
    });
    expect(getByLabelText('编辑分享图')).toBeTruthy();
    expect(getByLabelText('分享卡片正文')).toBeTruthy();
    fireEvent.press(getByLabelText('编辑分享图'));
    expect(mockCaptureRefCalls).toHaveLength(0);
    expect(getByTestId('mock-diet-share-composer')).toBeTruthy();
    expect(mockDietShareComposer).toHaveBeenLastCalledWith(expect.objectContaining({
      record: expect.objectContaining({ id: 770, meal_type: 'lunch' }),
      photoSource: {
        uri: 'https://health.executor.life/api/v1/upload/files/diet/1/lunch.jpg',
        headers: { Authorization: 'Bearer secret-token' },
      },
    }));

    fireEvent.press(getByLabelText('分享卡片正文'));

    await waitFor(() => {
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '小巴 · 饮食记录',
        message: expect.stringContaining('今天这餐被小巴认真记下来了'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('今日饮食打卡'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('今日策略'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('#小红书饮食日记 #朋友圈打卡 #小巴'),
      }));
    });
  });

  it('does not put an editable diet draft inside the message long-press responder', () => {
    renderCard.mockReturnValue(__mockCard);
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-editable-diet-draft',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: {
        meal_type: 'lunch',
        food_items: '待修正午餐',
        calories: 650,
      },
      cardActions: [{
        id: 'confirm-editable-diet-draft',
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { meal_type: 'lunch', food_items: '待修正午餐' } },
      }],
    };

    const { getByTestId, queryByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByTestId('assistant-editable-card-interaction-surface')).toBeTruthy();
    expect(queryByTestId('assistant-card-interaction-surface')).toBeNull();
  });

  it('does not share an unconfirmed diet draft as a completed meal record', () => {
    renderCard.mockReturnValue(__mockCard);
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-diet-draft-unconfirmed',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: {
        meal_type: 'lunch',
        food_items: '待确认午餐',
        calories: 650,
      },
      cardActions: [{
        id: 'confirm-diet-draft',
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { meal_type: 'lunch', food_items: '待确认午餐' } },
      }],
    };

    const { getByTestId, queryByLabelText, queryByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByTestId('assistant-editable-card-interaction-surface')).toBeTruthy();
    expect(queryByTestId('assistant-card-interaction-surface')).toBeNull();
    expect(queryByLabelText('分享卡片正文')).toBeNull();
  });

  it('shares a card-only diet quality result with progress and next action', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);
    renderCard.mockReturnValue(__mockCard);
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-diet-quality-share',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'record_quality',
      cardData: {
        domain: 'diet',
        title: '午餐已记录',
        summary: '770 kcal · 蛋白 30g · 碳水 70g',
        progress: {
          calories_total: 1040,
          meals_count: 2,
          protein_total_g: 37,
          protein_target_g: 112,
          remaining_protein_g: 75,
        },
        next_action: '晚餐优先 40g 蛋白，少油少刺激。',
      },
    };

    const { getByLabelText, getByTestId, queryByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(queryByText('截图可直接发微信 / 小红书')).toBeNull();
    fireEvent(getByTestId('assistant-card-interaction-surface'), 'longPress');
    fireEvent.press(getByLabelText('分享卡片正文'));

    await waitFor(() => {
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        title: '小巴 · 饮食记录',
        message: expect.stringContaining('今日摄入 1040 kcal'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('蛋白进度 37/112g'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('下一步：晚餐优先 40g 蛋白，少油少刺激。'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('今日饮食打卡'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('今日策略'),
      }));
      expect(sharePlainText).toHaveBeenCalledWith(expect.objectContaining({
        message: expect.stringContaining('#小红书饮食日记 #朋友圈打卡 #小巴'),
      }));
    });
  });

  it('dispatches server card actions from the chat bubble', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      receipt: verifiedReceipt('agenda_event', '71'),
    });
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
        expect.any(String),
        expect.objectContaining({
          cardType: 'vitals',
          cardData: { sleep: '8h' },
        }),
      );
    });
  });

  it('shows the backend reason when a diet card confirmation fails', async () => {
    dispatchChatCardAction.mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: '饮食照片草稿已过期，请重新拍照' },
      },
    });
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
      id: 'assistant-diet-card-error',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: { food_items: '胡萝卜 约3段 · 南瓜 约2块 · 红枣 约3颗' },
      cardActions: [{
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '胡萝卜 约3段', meal_type: 'breakfast' } },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('饮食照片草稿已过期，请重新拍照', 'error');
    });
  });

  it('does not expose backend internals from a server error detail', async () => {
    dispatchChatCardAction.mockRejectedValueOnce({
      response: {
        status: 500,
        data: { detail: '创建记录失败: psycopg2.errors.UniqueViolation token=secret' },
      },
    });
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
      id: 'assistant-diet-card-server-error',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: { food_items: '胡萝卜 约3段' },
      cardActions: [{
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '胡萝卜 约3段', meal_type: 'breakfast' } },
      }],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('操作失败，请稍后重试', 'error');
    });
  });

  it('shows a verified resource receipt after a write card action completes', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      receipt: {
        operationId: 'agenda.complete:71',
        status: 'verified',
        resourceType: 'agenda_event',
        resourceId: '71',
        completedAt: '2026-07-09T12:00:00.000Z',
        verified: true,
      },
    });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>完成行动</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-write-receipt',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'vitals',
      cardData: { sleep: '8h' },
      cardActions: [{
        label: '完成行动',
        action: 'agenda.complete',
        endpoint: '/agenda/complete',
        requires_manual_confirm: true,
        payload: { source: { object_type: 'health_protocol', object_id: 7 } },
      }],
    };

    const { getByText, getByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('完成行动'));

    await waitFor(() => {
      expect(getByTestId('write-receipt')).toBeTruthy();
      expect(getByText('已写入 · 今日行动 #71')).toBeTruthy();
      expect(mockRememberVerifiedWriteReceipt).toHaveBeenCalledWith(expect.objectContaining({
        operationId: 'agenda.complete:71',
        resourceType: 'agenda_event',
        resourceId: '71',
        verified: true,
      }));
      expect(mockSaveCardActionReceipt).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ resourceType: 'agenda_event', resourceId: '71' }),
      );
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('write_receipt_terminal', {
      phase: 'verified',
      duration_bucket: '1_3s',
      action_type: 'agenda.complete',
      verified: true,
    });
  });

  it('locks the completed card but shows a persistence warning when its duplicate guard cannot be saved', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      receipt: verifiedReceipt('diet_record', '72'),
    });
    mockRememberVerifiedWriteReceipt.mockRejectedValueOnce(new Error('secure store unavailable'));
    mockSaveCardActionReceipt.mockRejectedValueOnce(new Error('receipt index unavailable'));
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认午餐</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-card-receipt-persistence-failed',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: { food_items: '鸡胸肉', meal_type: 'lunch' },
      cardActions: [{
        id: 'confirm-lunch-72',
        label: '确认午餐',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '鸡胸肉', meal_type: 'lunch' } },
      }],
    };

    const { getByText, getByTestId, queryByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认午餐'));

    await waitFor(() => {
      expect(getByTestId('write-receipt-warning')).toBeTruthy();
      expect(getByText('已写入，但本机未保存防重复凭证')).toBeTruthy();
    });
    expect(queryByTestId('write-receipt')).toBeNull();
    fireEvent.press(getByText('确认午餐'));
    expect(dispatchChatCardAction).toHaveBeenCalledTimes(1);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('write_receipt_terminal', {
      phase: 'unverified',
      duration_bucket: '1_3s',
      action_type: 'diet_record.create',
      verified: false,
      error_code: 'card_receipt_persistence_failed',
    });
  });

  it('shows a durable direct-tool receipt on a completed assistant message', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-direct-tool-receipt',
      role: 'assistant',
      content: '午餐已记录。',
      streaming: false,
      writeReceipts: [verifiedReceipt('diet_record', '701')],
    };

    const { getByText, getByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByTestId('write-receipt')).toBeTruthy();
    expect(getByText('已保存到今日饮食 · 记录 #701')).toBeTruthy();
  });

  it('shows the actual action for verified health update and delete receipts', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-health-manage-action-receipts',
      role: 'assistant',
      content: '健康记录已处理。',
      streaming: false,
      writeReceipts: [
        verifiedReceipt('water_record', '718', 'update'),
        verifiedReceipt('water_record', '719', 'delete'),
      ],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByText('已更新 · 健康数据 #718')).toBeTruthy();
    expect(getByText('已删除 · 健康数据 #719')).toBeTruthy();
  });

  it('falls back to the legacy label for an unsupported receipt action', () => {
    const qc = new QueryClient();
    const receipt = {
      ...verifiedReceipt('water_record', '720'),
      action: 'replace',
    } as any;
    const message: UIMessage = {
      id: 'assistant-invalid-health-receipt-action',
      role: 'assistant',
      content: '健康记录已处理。',
      streaming: false,
      writeReceipts: [receipt],
    };

    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByText('已写入 · 健康数据 #720')).toBeTruthy();
  });

  it('keeps an AIGC draft receipt internal because the confirmation card owns visible state', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-aigc-draft-receipt',
      role: 'assistant',
      content: '创作草稿已准备。',
      streaming: false,
      writeReceipts: [verifiedReceipt(
        'aigc_media_confirmation',
        'aigc_confirm_0123456789abcdef0123456789abcdef',
      )],
    };

    const { getByText, queryByTestId, queryByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByText('创作草稿已准备。')).toBeTruthy();
    expect(queryByTestId('write-receipt')).toBeNull();
    expect(queryByText(/aigc_confirm_/)).toBeNull();
  });

  it('shows every direct receipt from a text-confirmed medication batch', () => {
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-direct-medication-batch-receipts',
      role: 'assistant',
      content: '已记录本次服药，共2条。',
      streaming: false,
      writeReceipts: [
        verifiedReceipt('medication_log', '801'),
        verifiedReceipt('medication_log', '802'),
      ],
    };

    const { getAllByTestId, getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getAllByTestId('write-receipt')).toHaveLength(2);
    expect(getByText('已写入 · 用药记录 #801')).toBeTruthy();
    expect(getByText('已写入 · 用药记录 #802')).toBeTruthy();
  });

  it('blocks two same-frame presses before React state has time to update', async () => {
    let resolveAction!: (value: any) => void;
    dispatchChatCardAction.mockReturnValueOnce(new Promise(resolve => { resolveAction = resolve; }));
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>查看详情</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-double-press',
      role: 'assistant',
      content: '',
      cardType: 'metric_chart',
      cardData: { metric: 'hrv' },
      cardActions: [{
        id: 'open-hrv',
        label: '查看详情',
        action: 'route.open',
        payload: { route: '/indicator-history?type=hrv' },
      }],
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    act(() => {
      fireEvent.press(getByText('查看详情'));
      fireEvent.press(getByText('查看详情'));
    });

    expect(dispatchChatCardAction).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveAction({ status: 'opened', route: '/indicator-history?type=hrv' });
    });
  });

  it('restores a durable card receipt and prevents the completed write from running again', async () => {
    mockLoadCardActionReceipt.mockResolvedValueOnce(verifiedReceipt('diet_record', '77'));
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-restored-receipt',
      role: 'assistant',
      content: '',
      cardType: 'diet_draft',
      cardData: { food_items: '鸡胸肉', meal_type: 'lunch' },
      cardActions: [{
        id: 'confirm-lunch-77',
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        payload: { record: { food_items: '鸡胸肉', meal_type: 'lunch' } },
      }],
    };
    const { getByText, getByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(getByTestId('write-receipt')).toBeTruthy());
    fireEvent.press(getByText('确认记录'));

    expect(dispatchChatCardAction).not.toHaveBeenCalled();
  });

  it('fails closed and keeps caches intact when a write action has no receipt', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed' });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认写入</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
    const message: UIMessage = {
      id: 'assistant-card-missing-write-receipt',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'record',
      cardData: { type: 'exercise', detail: '散步 20 分钟' },
      cardActions: [{
        label: '确认写入',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };

    const { getByText, queryByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认写入'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith('操作失败，请稍后重试', 'error');
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(queryByTestId('write-receipt')).toBeNull();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('write_receipt_terminal', {
      phase: 'unverified',
      duration_bucket: '1_3s',
      action_type: 'write_intent.confirm',
      verified: false,
      error_code: 'write_receipt_missing_identity',
    });
  });

  it('shows every medication write receipt and an incomplete safety-screening advisory', async () => {
    const receipts = [
      verifiedReceipt('medication_log', '101'),
      verifiedReceipt('medication_log', '102'),
    ];
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      write_receipts: receipts,
      receipt: receipts[1],
      safety_alerts: [{
        rule_id: 'medication.safety_precheck_incomplete',
        category: 'medication',
        severity: { value: 3, label: 'high', label_zh: '警告' },
        title: '自动安全筛查暂未完成',
        message: '这不代表当前用药组合安全。',
        action: '如有明显不适，请及时就医。',
      }],
    });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认用药记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
    const message: UIMessage = {
      id: 'assistant-medication-batch',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'medication_draft',
      cardData: { items: [{ medication_name: '伊托必利' }, { medication_name: '替普瑞酮' }] },
      cardActions: [{
        label: '确认用药记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };

    const { getByText, getAllByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认用药记录'));

    await waitFor(() => expect(getAllByTestId('write-receipt')).toHaveLength(2));
    expect(getByText('已写入 · 用药记录 #101')).toBeTruthy();
    expect(getByText('已写入 · 用药记录 #102')).toBeTruthy();
    expect(getByText('自动安全筛查暂未完成')).toBeTruthy();
    expect(getByText('这不代表当前用药组合安全。')).toBeTruthy();
    expect(mockRememberVerifiedWriteReceipt).toHaveBeenCalledTimes(1);
    expect(mockRememberVerifiedWriteReceipt).toHaveBeenCalledWith(receipts[1]);
    expect(mockToastShow).toHaveBeenCalledWith(
      '已记录；自动安全筛查暂未完成，不代表当前用药组合安全',
      'info',
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['medications'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['medicationToday'] });
  });

  it('locks confirm and dismiss together for the same write intent', async () => {
    let resolveConfirm!: (value: any) => void;
    dispatchChatCardAction.mockReturnValueOnce(new Promise(resolve => { resolveConfirm = resolve; }));
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text, View } = require('react-native');
      return (
        <View>
          {descriptor.actions.map((action: any) => (
            <Pressable key={action.id} onPress={() => options.onAction(action, descriptor)}>
              <Text>{action.label}</Text>
            </Pressable>
          ))}
        </View>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-medication-group-lock',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: { items: [{ medication_name: '伊托必利' }] },
      cardActions: [
        {
          id: 'confirm-medication-42',
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/42/confirm',
          requires_manual_confirm: true,
          payload: { write_intent_id: 42 },
        },
        {
          id: 'dismiss-medication-42',
          label: '取消记录',
          action: 'write_intent.dismiss',
          endpoint: '/write-intents/42/dismiss',
          requires_manual_confirm: true,
          payload: { write_intent_id: 42 },
        },
      ],
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    act(() => {
      fireEvent.press(getByText('确认记录'));
      fireEvent.press(getByText('取消记录'));
    });

    expect(dispatchChatCardAction).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveConfirm({
        status: 'completed',
        decision_status: 'executed',
        receipt: verifiedReceipt('medication_log', '101'),
      });
    });
  });

  it('does not invent or persist a verified receipt for dismissal', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'dismissed',
      decision_status: 'dismissed',
    });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      if (!descriptor.actions?.[0]) return <Text>已取消</Text>;
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>{descriptor.actions[0].label}</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-dismiss-medication',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: { items: [{ medication_name: '伊托必利' }] },
      cardActions: [{
        id: 'dismiss-medication-42',
        label: '取消记录',
        action: 'write_intent.dismiss',
        endpoint: '/write-intents/42/dismiss',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('取消记录'));

    await waitFor(() => expect(mockToastShow).toHaveBeenCalledWith('已忽略', 'success'));
    expect(mockSaveCardActionReceipt).not.toHaveBeenCalled();
    expect(mockRememberVerifiedWriteReceipt).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).not.toHaveBeenCalledWith(
      'write_receipt_terminal',
      expect.objectContaining({ action_type: 'write_intent.dismiss', verified: true }),
    );
  });

  it('shows the authoritative dismissed terminal when a confirm loses the cross-device race', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'dismissed',
      decision_status: 'dismissed',
    });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-confirm-lost-race',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: {
        write_intent_id: 42,
        items: [{ medication_name: '伊托必利' }],
      },
      cardActions: [{
        id: 'confirm-medication-42',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => expect(mockToastShow).toHaveBeenCalledWith('已忽略', 'success'));
    expect(mockToastShow).not.toHaveBeenCalledWith('操作失败，请稍后重试', 'error');
    expect(mockSaveCardActionReceipt).not.toHaveBeenCalled();
    expect(mockRememberVerifiedWriteReceipt).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).not.toHaveBeenCalledWith(
      'write_receipt_terminal',
      expect.objectContaining({ verified: true }),
    );
  });

  it('shows the authoritative executed terminal when a dismiss loses the cross-device race', async () => {
    const receipts = [
      verifiedReceipt('medication_log', '101'),
      verifiedReceipt('medication_log', '102'),
    ];
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      decision_status: 'executed',
      receipt: receipts[1],
      write_receipts: receipts,
    });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>取消记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-dismiss-lost-race',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: {
        write_intent_id: 42,
        items: [
          { medication_name: '伊托必利' },
          { medication_name: '替普瑞酮' },
        ],
      },
      cardActions: [{
        id: 'dismiss-medication-42',
        label: '取消记录',
        action: 'write_intent.dismiss',
        endpoint: '/write-intents/42/dismiss',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };
    const { getByText, getAllByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('取消记录'));

    await waitFor(() => expect(getAllByTestId('write-receipt')).toHaveLength(2));
    expect(mockToastShow).toHaveBeenCalledWith('已执行', 'success');
    expect(mockToastShow).not.toHaveBeenCalledWith('已忽略', 'success');
    expect(mockRememberVerifiedWriteReceipt).toHaveBeenCalledWith(receipts[1]);
  });

  it('uses truthful confirmation copy for dismissing a medication plan', () => {
    mockAlert.mockImplementation(jest.fn());
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>{descriptor.actions[0].label}</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-dismiss-copy',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: { items: [{ medication_name: '伊托必利' }] },
      cardActions: [{
        id: 'dismiss-medication-42',
        label: '取消',
        action: 'write_intent.dismiss',
        endpoint: '/write-intents/42/dismiss',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('取消'));

    expect(mockAlert).toHaveBeenCalledWith(
      '取消这组用药记录？',
      '确认取消后，这组待确认记录不会写入。',
      expect.arrayContaining([
        expect.objectContaining({ text: '再看看', style: 'cancel' }),
        expect.objectContaining({ text: '确认取消', style: 'destructive' }),
      ]),
    );
  });

  it('shows an expired terminal state instead of a retry error for a 409 confirmation', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'expired',
      decision_status: 'expired',
    });
    renderCard.mockImplementation((descriptor: any, options: any) => {
      const { Pressable, Text } = require('react-native');
      return (
        <Pressable onPress={() => options.onAction(descriptor.actions[0], descriptor)}>
          <Text>确认记录</Text>
        </Pressable>
      );
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-expired-medication',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: { items: [{ medication_name: '伊托必利' }] },
      cardActions: [{
        id: 'confirm-medication-42',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByText('确认记录'));

    await waitFor(() => {
      expect(mockToastShow).toHaveBeenCalledWith(
        '确认已过期，未写入；请重新发送完整用药记录',
        'info',
      );
    });
    expect(mockToastShow).not.toHaveBeenCalledWith('操作失败，请稍后重试', 'error');
    expect(mockRememberVerifiedWriteReceipt).not.toHaveBeenCalled();
  });

  it('shows every frozen medication safety alert in the confirmation surface', () => {
    renderCard.mockReturnValue(__mockCard);
    const safetyAlerts = Array.from({ length: 4 }, (_, index) => ({
      rule_id: `medication.rule.${index}`,
      category: 'medication',
      severity: { value: 3, label: 'high', label_zh: '警告' },
      title: `安全提示 ${index + 1}`,
      message: `提示内容 ${index + 1}`,
    }));
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-restored-medication-alerts',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: { decision_status: 'executed' },
      decisionStatus: 'executed',
      safetyAlerts,
    };
    const { getByText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    safetyAlerts.forEach(alert => {
      expect(getByText(alert.title)).toBeTruthy();
      expect(getByText(alert.message)).toBeTruthy();
    });
    expect(() => getByText('还有 1 条安全提示')).toThrow();
    expect(() => getByText('查看全部安全提示')).toThrow();
  });

  it('does not wrap a card with actions in another pressable interaction surface', () => {
    renderCard.mockImplementation(() => {
      const { Pressable, Text } = require('react-native');
      return <Pressable accessibilityLabel="确认记录"><Text>确认记录</Text></Pressable>;
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-actionable-medication-a11y',
      role: 'assistant',
      content: '',
      cardType: 'medication_draft',
      cardData: { items: [{ medication_name: '伊托必利' }] },
      cardActions: [{
        id: 'confirm-medication-42',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        payload: { write_intent_id: 42 },
      }],
    };
    const { getByTestId, queryByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByTestId('assistant-actionable-card-interaction-surface')).toBeTruthy();
    expect(queryByTestId('assistant-card-interaction-surface')).toBeNull();
  });

  it('does not wrap an AIGC video player in the message pressable', () => {
    renderCard.mockImplementation(() => {
      const { Pressable, Text } = require('react-native');
      return <Pressable accessibilityLabel="播放短视频"><Text>播放短视频</Text></Pressable>;
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-aigc-video-player',
      role: 'assistant',
      content: '',
      cardType: 'aigc_media_job',
      cardData: {
        job_id: 'aigc_video_done',
        kind: 'text_to_video',
        status: 'succeeded',
        progress: 100,
      },
    };
    const { getByTestId, queryByTestId } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByTestId('assistant-actionable-card-interaction-surface')).toBeTruthy();
    expect(queryByTestId('assistant-card-interaction-surface')).toBeNull();
  });

  it('shows diet-specific success feedback after confirming a diet card', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({ status: 'completed', receipt: verifiedReceipt() });
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

  it('keeps text sharing but disables image editing when a restored record has no accessible photo', () => {
    renderCard.mockImplementationOnce(() => {
      const { Text } = require('react-native');
      return <Text>午餐已记录</Text>;
    });
    const qc = new QueryClient();
    const message: UIMessage = {
      id: 'assistant-recorded-diet-share',
      role: 'assistant',
      content: '',
      streaming: false,
      cardType: 'diet_draft',
      cardData: {
        recorded: true,
        record_id: 805,
        meal_type: 'lunch',
        food_items: '番茄炒蛋面 1 碗',
        calories: 420,
      },
      cardActions: [],
      writeReceipts: [],
    };

    const { getByText, getByLabelText, queryByLabelText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    expect(getByText('午餐已记录')).toBeTruthy();
    expect(getByLabelText('编辑分享图')).toHaveAccessibilityState({ disabled: true });
    expect(getByLabelText('编辑分享图').props.accessibilityHint).toBe('需要这餐的可用照片才能编辑分享图');
    expect(getByText('没有可用餐食照片，仅支持分享正文')).toBeTruthy();
    expect(getByLabelText('分享卡片正文')).toBeTruthy();
    expect(queryByLabelText('分享卡片图片')).toBeNull();
  });

  it('does not expose exact nutrition or AI advice in low-confidence diet share text', async () => {
    sharePlainText.mockResolvedValueOnce(undefined);
    renderCard.mockImplementationOnce(() => {
      const { Text } = require('react-native');
      return <Text>晚餐已记录</Text>;
    });
    const qc = new QueryClient();
    const message = {
      id: 'diet-low-confidence-share',
      role: 'assistant' as const,
      content: '',
      timestamp: Date.now(),
      cardType: 'diet_draft',
      cardData: {
        recorded: true,
        record_id: 991,
        meal_type: 'dinner',
        food_items: '一份不确定的晚餐',
        calories: 987,
        protein: 43,
        carbs: 101,
        fat: 35,
        ai_confidence: 0.42,
        suggestions: ['下一餐精确补充 37g 蛋白质'],
      },
      writeReceipts: [],
    };

    const { getByLabelText } = render(
      <QueryClientProvider client={qc}>
        <ChatBubble item={message} />
      </QueryClientProvider>,
    );

    fireEvent.press(getByLabelText('分享卡片正文'));
    await waitFor(() => expect(sharePlainText).toHaveBeenCalledTimes(1));
    const payload = sharePlainText.mock.calls[0][0];
    expect(payload.message).toContain('营养待核对');
    expect(payload.message).not.toContain('987');
    expect(payload.message).not.toContain('43g');
    expect(payload.message).not.toContain('101');
    expect(payload.message).not.toContain('37g');
  });

  it('shows nutrition estimation feedback after confirming an incomplete diet card', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      nutrition_status: 'estimated',
      patch: {
        recorded: true,
        record_id: 88,
        calories: 620,
        protein: 28,
        carbs: 78,
        fat: 18,
      },
      receipt: verifiedReceipt('diet_record', '88'),
    });
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
    await waitFor(() => {
      expect(renderCard).toHaveBeenLastCalledWith(
        expect.objectContaining({
          type: 'diet_draft',
          data: expect.objectContaining({
            recorded: true,
            record_id: 88,
            calories: 620,
            protein: 28,
            carbs: 78,
            fat: 18,
          }),
        }),
        expect.any(Object),
      );
    });
  });

  it('keeps the saved-record feedback visible when diet nutrition estimation fails', async () => {
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      nutrition_status: 'estimate_failed',
      receipt: verifiedReceipt('diet_record', '89'),
    });
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
    mockAlert.mockImplementation(jest.fn());
    dispatchChatCardAction.mockResolvedValueOnce({
      status: 'completed',
      receipt: verifiedReceipt('smart_reminder', '18'),
    });
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
    expect(mockAlert).toHaveBeenCalledWith(
      '记录 30 个俯卧撑？',
      '将写入今天的运动记录',
      expect.any(Array),
    );

    const buttons = mockAlert.mock.calls[0][2] as { onPress?: () => void }[];
    await act(async () => {
      buttons[1].onPress?.();
    });

    await waitFor(() => {
      expect(dispatchChatCardAction).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'write_intent.confirm' }),
        expect.any(String),
        expect.objectContaining({
          cardType: 'record',
          cardData: expect.objectContaining({ type: 'exercise' }),
        }),
      );
    });

  });
});
