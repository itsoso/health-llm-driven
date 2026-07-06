const mockStorage: Record<string, string> = {};
jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {
    getItem: jest.fn((k: string) => Promise.resolve(mockStorage[k] ?? null)),
    setItem: jest.fn((k: string, v: string) => { mockStorage[k] = v; return Promise.resolve(); }),
  },
}));

/* eslint-disable @typescript-eslint/no-require-imports */
import React from 'react';
import { StyleSheet } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import ChatInputBar from '../ChatInputBar';
import { revaColors } from '../../../constants/revaTheme';

const mockStartRecording = jest.fn();
const mockStopAndTranscribe = jest.fn();
const mockCancelRecording = jest.fn();
const mockExecuteMedicalExamImport = jest.fn();
// 组件传给 useVoiceRecording 的 opts(onTranscript 流转测试用)
let latestVoiceOpts: { onTranscript?: (text: string) => void } | undefined;

jest.mock('../../../hooks/useMediaPicker', () => ({
  useMediaPicker: () => ({
    pendingImages: [],
    removeImage: jest.fn(),
    clearImages: jest.fn(),
    pickImage: jest.fn(),
    takePhoto: jest.fn(),
  }),
}));

jest.mock('../../../hooks/useVoiceRecording', () => ({
  useVoiceRecording: (opts?: { onTranscript?: (text: string) => void }) => {
    latestVoiceOpts = opts;
    return {
      isRecording: false,
      isTranscribing: false,
      durationMs: 0,
      partialText: '',
      startRecording: mockStartRecording,
      stopAndTranscribe: mockStopAndTranscribe,
      cancelRecording: mockCancelRecording,
    };
  },
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));

jest.mock('../../../services/chatMedicalExamImportSkill', () => ({
  executeMedicalExamImportSkillForDocumentAsset: (...args: any[]) => mockExecuteMedicalExamImport(...args),
}));

jest.mock('expo-router', () => ({
  router: { push: jest.fn() },
}));

jest.mock('react-native-reanimated', () => {
  const React = require('react');
  const { View } = require('react-native');
  const AnimatedView = React.forwardRef((props: any, ref: any) => React.createElement(View, { ...props, ref }));
  AnimatedView.displayName = 'AnimatedView';
  return {
    __esModule: true,
    default: { View: AnimatedView },
    useSharedValue: (value: unknown) => ({ value }),
    useAnimatedStyle: (factory: () => unknown) => factory(),
    withRepeat: (value: unknown) => value,
    withTiming: (value: unknown) => value,
    withSpring: (value: unknown) => value,
  };
});

describe('ChatInputBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // 模式记忆跨用例泄漏防护:上个用例切过语音态会让后续挂载异步翻模式
    Object.keys(mockStorage).forEach(k => delete mockStorage[k]);
    latestVoiceOpts = undefined;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('uses Reva surface color for the attachment menu sheet', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    expect(StyleSheet.flatten(getByTestId('attachment-menu-sheet').props.style).backgroundColor)
      .toBe(revaColors.surface);
  });

  it('keeps the attachment menu sheet vertically tight', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const menuSheet = StyleSheet.flatten(getByTestId('attachment-menu-sheet').props.style);
    expect(menuSheet.paddingTop).toBeLessThanOrEqual(8);
    expect(menuSheet.paddingBottom).toBeLessThanOrEqual(28);
  });

  it('keeps the attachment menu handle close to the action grid', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const handle = StyleSheet.flatten(getByTestId('attachment-menu-handle').props.style);
    expect(handle.marginBottom).toBeLessThanOrEqual(10);
  });

  it('renders attachment actions as a compact two-column grid', () => {
    const { getByLabelText, getByTestId, getByText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const actionGrid = StyleSheet.flatten(getByTestId('attachment-action-grid').props.style);
    expect(actionGrid.flexDirection).toBe('row');
    expect(actionGrid.flexWrap).toBe('wrap');
    expect(actionGrid.gap).toBeLessThanOrEqual(8);
    expect(getByText('拍照')).toBeTruthy();
    expect(getByText('相册')).toBeTruthy();
    expect(getByText('文件')).toBeTruthy();
    expect(getByLabelText('导入体检报告')).toBeTruthy();
  });

  it('renders only one compact composer row by default', () => {
    const { getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const composerSurface = StyleSheet.flatten(getByTestId('chat-composer-surface').props.style);
    expect(composerSurface.backgroundColor).toBe(revaColors.surface);
    expect(composerSurface.borderRadius).toBeLessThanOrEqual(22);
    expect(queryByLabelText('Agent 模式')).toBeNull();
  });

  it('keyboard composer controls meet thumb ergonomics (founder 2026-07-05, GPT spec)', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };

    expect(styleOf(getByLabelText('附件菜单')).width).toBeGreaterThanOrEqual(40);
    expect(styleOf(getByTestId('composer-input-wrap')).minHeight).toBeGreaterThanOrEqual(40);
  });

  it('keeps the visible composer chrome slim while preserving touch targets', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };
    const minHitSlop = (node: any) => Math.min(
      node.props.hitSlop?.top ?? 0,
      node.props.hitSlop?.right ?? 0,
      node.props.hitSlop?.bottom ?? 0,
      node.props.hitSlop?.left ?? 0,
    );

    // 2026-07-05 工学契约翻转: 拇指高度对齐 GPT — 场 ≥48, 钮 ≥40(hitSlop 补足 44 有效)
    expect(styleOf(getByLabelText('附件菜单')).width).toBeGreaterThanOrEqual(40);
    expect(styleOf(getByTestId('composer-input-wrap')).minHeight).toBeGreaterThanOrEqual(48);
    expect(minHitSlop(getByLabelText('附件菜单'))).toBeGreaterThanOrEqual(6);
  });

  it('renders WeChat-style mode toggle on the left; text field stays natively tappable', () => {
    // 2026-07-06 founder: 参考微信重设计。文本态 = 纯原生 TextInput(不再有
    // pointerEvents:none 把戏 → 短按聚焦 100% 可靠), 语音入口 = 左侧切换钮。
    const { getByLabelText, queryByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(getByLabelText('切换语音输入')).toBeTruthy();
    expect(queryByTestId('composer-voice-bar')).toBeNull();
    const fieldStyle = StyleSheet.flatten(getByLabelText('消息输入框').props.style);
    expect(fieldStyle.pointerEvents).toBeUndefined();
  });

  it('toggle switches to hold-to-talk bar; holding records, releasing transcribes', () => {
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换语音输入'));
    const bar = getByTestId('composer-voice-bar');

    const nowSpy = jest.spyOn(Date, 'now')
      .mockReturnValueOnce(10_000)   // pressIn
      .mockReturnValueOnce(10_800);  // pressOut: held 800ms → 转写
    fireEvent(bar, 'pressIn', { nativeEvent: { pageY: 300 } });
    fireEvent(bar, 'pressOut');
    nowSpy.mockRestore();

    expect(mockStartRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).toHaveBeenCalled();
    expect(mockCancelRecording).not.toHaveBeenCalled();
  });

  it('quick tap on the voice bar flips back to keyboard instead of recording (founder: 短按要支持文本)', () => {
    const { getByLabelText, getByTestId, queryByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换语音输入'));
    const bar = getByTestId('composer-voice-bar');

    const nowSpy = jest.spyOn(Date, 'now')
      .mockReturnValueOnce(10_000)   // pressIn
      .mockReturnValueOnce(10_120);  // pressOut: 120ms < 250ms → 轻点
    fireEvent(bar, 'pressIn', { nativeEvent: { pageY: 300 } });
    fireEvent(bar, 'pressOut');
    nowSpy.mockRestore();

    expect(mockCancelRecording).toHaveBeenCalled();
    expect(mockStopAndTranscribe).not.toHaveBeenCalled();
    expect(queryByTestId('composer-voice-bar')).toBeNull();
    expect(getByLabelText('消息输入框')).toBeTruthy();
  });

  it('persists composer mode and flips back to text with the transcript visible', async () => {
    const AsyncStorage = require('@react-native-async-storage/async-storage').default;
    const { getByLabelText, getByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换语音输入'));
    expect(getByTestId('composer-voice-bar')).toBeTruthy();
    await waitFor(() =>
      expect(AsyncStorage.setItem).toHaveBeenCalledWith('chat_composer_mode', 'voice'));

    // 转写结果落框 → 自动回文本态给用户过目, 发送键可见
    latestVoiceOpts?.onTranscript?.('今天走了八千步');
    await waitFor(() => expect(getByLabelText('消息输入框').props.value).toBe('今天走了八千步'));
    expect(getByLabelText('发送消息')).toBeTruthy();
  });

  it('has no agent-mode segmented row (founder 2026-07-05: 三模式删除)', () => {
    // 日常/深思/识图 已删:日常=默认无操作,深思/识图 的 instruction 之前经 extra_context
    // 落到后端「入口上下文」注入点(给 deeplink「详细聊」用的)被错误框成「别重新生成
    // 方案」,效果 garbled;识图 冗余(带图自动走视觉)。深浅由 agent 从问题判断。
    const { getByLabelText, queryByText, queryByTestId } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    expect(queryByTestId('agent-mode-segmented-row')).toBeNull();
    expect(queryByText('深思')).toBeNull();
    expect(queryByText('识图')).toBeNull();
  });

  it('sends typed text when Enter is pressed in the composer', () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.changeText(getByLabelText('消息输入框'), '记录晚餐吃了鸡胸肉');
    fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });

    expect(onSend).toHaveBeenCalledWith('记录晚餐吃了鸡胸肉', null);
  });

  it('updates the composer when a follow-up prompt is injected after mount', () => {
    const { getByLabelText, rerender } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    rerender(
      <ChatInputBar
        onSend={jest.fn()}
        isStreaming={false}
        initialText="请基于上一条建议继续追问"
      />,
    );

    expect(getByLabelText('消息输入框').props.value).toBe('请基于上一条建议继续追问');
  });

  it('updates the composer when the same follow-up prompt is injected again', () => {
    const onSend = jest.fn();
    const prompt = '请基于上一条建议继续追问';
    const { getByLabelText, rerender } = render(
      <ChatInputBar
        onSend={onSend}
        isStreaming={false}
        initialText={prompt}
        initialTextKey={1}
      />,
    );

    fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });
    expect(onSend).toHaveBeenCalledWith(prompt, null);
    expect(getByLabelText('消息输入框').props.value).toBe('');

    rerender(
      <ChatInputBar
        onSend={onSend}
        isStreaming={false}
        initialText={prompt}
        initialTextKey={2}
      />,
    );

    expect(getByLabelText('消息输入框').props.value).toBe(prompt);
  });

  it('runs the medical exam import skill from the attachment menu', async () => {
    const DocumentPicker = require('expo-document-picker');
    DocumentPicker.getDocumentAsync.mockResolvedValueOnce({
      canceled: false,
      assets: [{
        uri: 'file:///tmp/report.pdf',
        name: 'report.pdf',
        mimeType: 'application/pdf',
      }],
    });
    const skillResult = {
      skillId: 'medical_exam_import',
      card: {
        type: 'medical_exam_import_result',
        data: { exam_id: 42, items_count: 28, review_required: true },
      },
    };
    mockExecuteMedicalExamImport.mockResolvedValueOnce(skillResult);
    const onMedicalExamImportResult = jest.fn();

    const { getByLabelText } = render(
      <ChatInputBar
        onSend={jest.fn()}
        isStreaming={false}
        onMedicalExamImportResult={onMedicalExamImportResult}
      />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    fireEvent.press(getByLabelText('导入体检报告'));
    fireEvent.press(getByLabelText('选择 PDF 或图片报告'));

    await waitFor(() => {
      expect(mockExecuteMedicalExamImport).toHaveBeenCalledWith({
        uri: 'file:///tmp/report.pdf',
        name: 'report.pdf',
        mimeType: 'application/pdf',
      });
    });
    expect(onMedicalExamImportResult).toHaveBeenCalledWith(skillResult);
  });
});
