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
import { Alert, AppState, StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

import ChatInputBar from '../ChatInputBar';
import { revaColors } from '../../../constants/revaTheme';

const mockExecuteMedicalExamImport = jest.fn();
const mockRouterPush = jest.fn();
const mockStartDictation = jest.fn();
const mockStopDictation = jest.fn();
const mockCancelDictation = jest.fn();
let appStateHandler: ((state: string) => void) | undefined;
let latestRealtimeDictationOptions: any;
let mockRealtimeDictationState = {
  isDictating: false,
  error: null as string | null,
};
let mockPendingImages: any[] = [];
const mockSetPendingImages = jest.fn();
const mockRemoveImage = jest.fn();
const mockClearImages = jest.fn().mockResolvedValue(undefined);
const mockReleaseImagesAfterSend = jest.fn();
const mockTakePhoto = jest.fn();
const mockPickImage = jest.fn();
const mockLoadChatDraft = jest.fn();
const mockPersistChatDraft = jest.fn().mockResolvedValue(undefined);
const mockHydrateDraftImages = jest.fn();
const mockClearPersistedChatDraft = jest.fn().mockResolvedValue(undefined);
const mockCleanupDraftFiles = jest.fn().mockResolvedValue(undefined);
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);

jest.mock('../../../hooks/useMediaPicker', () => ({
  useMediaPicker: () => ({
    pendingImages: mockPendingImages,
    setPendingImages: mockSetPendingImages,
    removeImage: mockRemoveImage,
    clearImages: mockClearImages,
    releaseImagesAfterSend: mockReleaseImagesAfterSend,
    pickImage: (...args: any[]) => mockPickImage(...args),
    takePhoto: (...args: any[]) => mockTakePhoto(...args),
  }),
}));

jest.mock('../../../services/chatDraftStorage', () => ({
  loadChatDraft: (...args: any[]) => mockLoadChatDraft(...args),
  persistChatDraft: (...args: any[]) => mockPersistChatDraft(...args),
  hydrateDraftImagesForSend: (...args: any[]) => mockHydrateDraftImages(...args),
  clearPersistedChatDraft: (...args: any[]) => mockClearPersistedChatDraft(...args),
  cleanupAbandonedChatDraftFiles: (...args: any[]) => mockCleanupDraftFiles(...args),
}));

jest.mock('../../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: () => 'lt_1s',
}));

jest.mock('../../../hooks/useRealtimeDictation', () => ({
  useRealtimeDictation: (options: any) => {
    latestRealtimeDictationOptions = options;
    return {
      isDictating: mockRealtimeDictationState.isDictating,
      durationMs: 640,
      audioLevel: 0.42,
      error: mockRealtimeDictationState.error,
      startDictation: mockStartDictation,
      stopDictation: mockStopDictation,
      cancelDictation: mockCancelDictation,
    };
  },
}), { virtual: true });

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));

jest.mock('../../../services/chatMedicalExamImportSkill', () => ({
  buildMedicalExamImportSkillResult: (...args: any[]) => mockExecuteMedicalExamImport(...args),
}));

jest.mock('../../medical/MedicalExamImportFlow', () => {
  const React = require('react');
  const { Pressable, Text } = require('react-native');
  return function MockMedicalExamImportFlow(props: any) {
    if (!props.visible) return null;
    return React.createElement(
      Pressable,
      {
        accessibilityLabel: '确认模拟导入',
        onPress: () => props.onImported({
          examId: 42,
          exam_id: 42,
          source: 'pdf',
          reviewRequired: true,
        }),
      },
      React.createElement(Text, null, '体检报告导入流程'),
    );
  };
});

jest.mock('expo-router', () => ({
  router: { push: (...args: any[]) => mockRouterPush(...args) },
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
  const enterKeyboardMode = (view: { getByLabelText: (label: string) => any }) => {
    fireEvent.press(view.getByLabelText('切换到键盘输入'));
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockStartDictation.mockResolvedValue(true);
    mockStopDictation.mockResolvedValue(undefined);
    mockCancelDictation.mockResolvedValue(undefined);
    mockPendingImages = [];
    mockSetPendingImages.mockReset();
    mockClearImages.mockResolvedValue(undefined);
    mockTakePhoto.mockReset();
    mockPickImage.mockReset();
    mockLoadChatDraft.mockImplementation(() => new Promise(() => {}));
    mockPersistChatDraft.mockResolvedValue(undefined);
    mockHydrateDraftImages.mockImplementation(async (images: any[]) => images);
    mockClearPersistedChatDraft.mockResolvedValue(undefined);
    mockCleanupDraftFiles.mockResolvedValue(undefined);
    mockEmitClientEvent.mockResolvedValue(undefined);
    appStateHandler = undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_event: string, handler: (state: string) => void) => {
      appStateHandler = handler;
      return { remove: jest.fn() };
    }) as any);
    latestRealtimeDictationOptions = undefined;
    mockRealtimeDictationState = { isDictating: false, error: null };
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('defaults to voice input with a compact icon-only keyboard switch', () => {
    const { getByLabelText, getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    expect(getByLabelText('按住说话')).toBeTruthy();
    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
    expect(getByTestId('icon-keyboard-outline')).toBeTruthy();
    expect(queryByLabelText('消息输入框')).toBeNull();
  });

  it('shows wrapping cloud transcript while holding and submits the final text on release', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    mockStopDictation.mockResolvedValueOnce('记录今天在机场吃了一份番茄鸡蛋面并喝了五百毫升水');
    const { getByLabelText, getByTestId, queryByText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent(getByLabelText('按住说话'), 'responderGrant', {
        nativeEvent: { pageX: 220, pageY: 620 },
      });
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript(
        '记录今天在机场吃了一份番茄鸡蛋面并喝了五百毫升水',
        { provider: 'dashscope_qwen_asr_realtime', durationMs: 420, empty: false },
      );
    });

    const transcript = getByTestId('voice-live-transcript');
    expect(transcript.props.children).toContain('记录今天在机场吃了一份番茄鸡蛋面');
    expect(StyleSheet.flatten(transcript.props.style)).toEqual(expect.objectContaining({
      flexShrink: 1,
    }));
    expect(queryByText('取消')).toBeNull();
    expect(queryByText('转为文字')).toBeNull();

    await act(async () => {
      fireEvent(getByLabelText('按住说话'), 'responderRelease');
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockStartDictation).toHaveBeenCalledTimes(1);
    expect(mockStopDictation).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith(
      '记录今天在机场吃了一份番茄鸡蛋面并喝了五百毫升水',
      null,
      expect.objectContaining({ channel: 'voice' }),
    );
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
    expect(getByText('拍照记餐')).toBeTruthy();
    expect(getByText('相册')).toBeTruthy();
    expect(getByText('文件')).toBeTruthy();
    expect(getByLabelText('导入体检报告')).toBeTruthy();
  });

  it('stages a meal photo so the user can continue shooting before one combined send', async () => {
    const photo = { uri: 'file:///meal.jpg', base64: 'base64-meal', type: 'jpeg' };
    mockTakePhoto.mockResolvedValueOnce([photo]);
    const onSend = jest.fn().mockResolvedValue(true);
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    await act(async () => {
      fireEvent.press(getByLabelText('拍照记餐'));
      await Promise.resolve();
    });

    expect(mockRouterPush).not.toHaveBeenCalled();
    expect(mockTakePhoto).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    expect(mockReleaseImagesAfterSend).not.toHaveBeenCalled();
  });

  it('does not mix an existing generic attachment into a new meal capture session', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    mockPendingImages = [{
      uri: 'file:///documents/chat-drafts/report.jpeg',
      base64: 'report',
      type: 'jpeg',
    }];
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} captureMealPhotoToken={0} />,
    );

    await act(async () => {
      view.rerender(
        <ChatInputBar onSend={jest.fn()} isStreaming={false} captureMealPhotoToken={1} />,
      );
      await Promise.resolve();
    });

    expect(mockTakePhoto).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith(
      '先处理已选图片',
      expect.stringContaining('不会把普通附件自动当成餐食照片'),
    );
  });

  it('offers separate camera and library actions after the first photo is staged', async () => {
    mockPendingImages = [
      { uri: 'file:///meal-1.jpg', base64: 'meal-1', type: 'jpeg' },
    ];
    mockTakePhoto.mockResolvedValueOnce([
      { uri: 'file:///meal-2.jpg', base64: 'meal-2', type: 'jpeg' },
    ]);

    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('继续拍照'));
      await Promise.resolve();
    });
    await act(async () => {
      fireEvent.press(getByLabelText('继续从相册选择'));
      await Promise.resolve();
    });

    expect(mockTakePhoto).toHaveBeenCalledTimes(1);
    expect(mockPickImage).toHaveBeenCalledTimes(1);
  });

  it('submits all staged meal photos once with one meal-record context', async () => {
    const firstPhoto = { uri: 'file:///meal-1.jpg', base64: 'meal-1', type: 'jpeg' };
    const secondPhoto = { uri: 'file:///meal-2.jpg', base64: 'meal-2', type: 'jpeg' };
    mockTakePhoto.mockResolvedValueOnce([firstPhoto]);
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(view.getByLabelText('附件菜单'));
    await act(async () => {
      fireEvent.press(view.getByLabelText('拍照记餐'));
      await Promise.resolve();
    });

    mockPendingImages = [firstPhoto, secondPhoto];
    view.rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await act(async () => {
      fireEvent.press(view.getByLabelText('发送消息'));
      await Promise.resolve();
    });

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith(
      '记录这餐',
      [firstPhoto, secondPhoto],
      expect.objectContaining({
        extraContext: expect.stringContaining('diet_photo_record'),
      }),
    );
    expect(mockReleaseImagesAfterSend).toHaveBeenCalledTimes(1);
  });

  it('renders only one compact composer row by default', () => {
    const { getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    const composerSurface = StyleSheet.flatten(getByTestId('chat-composer-surface').props.style);
    expect(composerSurface.backgroundColor).toBe(revaColors.paper);
    expect(composerSurface.backgroundColor).not.toBe('#1F1F1F');
    expect(composerSurface.borderRadius).toBeLessThanOrEqual(22);
    expect(queryByLabelText('Agent 模式')).toBeNull();
  });

  it('keeps the primary composer controls visually compact', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);

    const voice = StyleSheet.flatten(view.getByTestId('composer-voice-mode').props.style);
    const input = StyleSheet.flatten(view.getByTestId('wechat-composer-input').props.style);
    const plus = StyleSheet.flatten(view.getByTestId('composer-plus').props.style);
    expect(voice.width).toBeLessThanOrEqual(40);
    expect(input.minHeight).toBe(48);
    expect(plus.width).toBeLessThanOrEqual(40);
  });

  it('uses Reva warm surfaces for the mobile composer input instead of dark chrome', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };

    const inputSurface = styleOf(getByTestId('wechat-composer-input'));
    const field = getByLabelText('消息输入框');
    const fieldStyle = StyleSheet.flatten(field.props.style);

    expect(inputSurface.backgroundColor).toBe(revaColors.surface);
    expect(inputSurface.backgroundColor).not.toBe('#2B2B2B');
    expect(inputSurface.borderColor).toBe(revaColors.lineStrong);
    expect(field.props.placeholderTextColor).toBe(revaColors.ink3);
    expect(fieldStyle.color).toBe(revaColors.ink1);
  });

  it('exposes the multiline text input instead of collapsing it into the outer press surface', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);

    expect(view.getByTestId('wechat-composer-input').props.accessible).toBe(false);
    expect(view.getByLabelText('消息输入框').props.accessibilityLabel).toBe('消息输入框');
  });

  it('keyboard composer controls meet thumb ergonomics in the WeChat-style layout', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;

    const styleOf = (node: any) => {
      const style = node.props.style;
      return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
    };

    expect(styleOf(getByLabelText('附件菜单')).width).toBeGreaterThanOrEqual(40);
    expect(styleOf(getByLabelText('切换到语音输入')).width).toBeGreaterThanOrEqual(40);
    expect(StyleSheet.flatten(getByTestId('wechat-composer-input').props.style).minHeight).toBeGreaterThanOrEqual(48);
  });

  it('keeps the visible composer chrome slim while preserving touch targets', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;

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
    expect(styleOf(getByLabelText('切换到语音输入')).height).toBeGreaterThanOrEqual(40);
    expect(StyleSheet.flatten(getByTestId('wechat-composer-input').props.style).minHeight).toBeGreaterThanOrEqual(48);
    expect(minHitSlop(getByLabelText('附件菜单'))).toBeGreaterThanOrEqual(6);
  });

  it('renders WeChat-style text controls after tapping the keyboard switch', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId, queryByLabelText } = view;

    expect(getByLabelText('切换到语音输入')).toBeTruthy();
    expect(getByLabelText('实时语音转文字')).toBeTruthy();
    expect(queryByLabelText('按住说话')).toBeNull();
    const inputSurface = StyleSheet.flatten(getByTestId('wechat-composer-input').props.style);
    expect(inputSurface.flexDirection).toBe('row');
    expect(inputSurface.borderRadius).toBeLessThanOrEqual(10);
  });

  it('keeps an empty text composer compact on focus without starting cloud ASR', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;

    const compactSurface = StyleSheet.flatten(getByTestId('wechat-composer-input').props.style);
    expect(compactSurface.minHeight).toBe(48);

    fireEvent.press(getByTestId('wechat-composer-input'));

    const focusedSurface = StyleSheet.flatten(getByTestId('wechat-composer-input').props.style);
    expect(focusedSurface.minHeight).toBe(compactSurface.minHeight);
    expect(focusedSurface.borderRadius).toBe(compactSurface.borderRadius);
    expect(getByLabelText('实时语音转文字')).toBeTruthy();
    expect(mockStartDictation).not.toHaveBeenCalled();
  });

  it('makes the focused composer voice action discoverable without implying hold-to-talk', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;

    fireEvent.press(getByTestId('wechat-composer-input'));

    const surface = StyleSheet.flatten(getByTestId('wechat-composer-input').props.style);
    expect(surface.borderColor).toBe(revaColors.green500);
    expect(getByLabelText('消息输入框').props.placeholder).toBe('问小巴，或点麦克风说话');
  });

  it('does not add a third quick-action rail when the empty composer is focused', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByTestId, queryByTestId } = view;

    expect(queryByTestId('smart-composer-quick-actions')).toBeNull();
    fireEvent.press(getByTestId('wechat-composer-input'));

    expect(queryByTestId('smart-composer-quick-actions')).toBeNull();
  });

  it('grows the composer from text content and caps it at three lines', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const field = view.getByLabelText('消息输入框');
    const surface = () => StyleSheet.flatten(view.getByTestId('wechat-composer-input').props.style);

    fireEvent(field, 'contentSizeChange', {
      nativeEvent: { contentSize: { height: 66 } },
    });
    expect(surface().minHeight).toBeGreaterThan(48);

    fireEvent(field, 'contentSizeChange', {
      nativeEvent: { contentSize: { height: 200 } },
    });
    expect(surface().minHeight).toBeLessThanOrEqual(84);
  });

  it('toggles from keyboard input back into WeChat hold-to-talk mode', () => {
    const { getByLabelText, getByTestId, queryByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('切换到键盘输入'));
    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
    expect(getByLabelText('按住说话')).toBeTruthy();
    expect(queryByLabelText('消息输入框')).toBeNull();
    const holdSurface = StyleSheet.flatten(getByTestId('wechat-hold-to-talk').props.style);
    expect(holdSurface.minHeight).toBeGreaterThanOrEqual(48);
    expect(holdSurface.backgroundColor).toBe(revaColors.surface);
  });

  it('starts hold-to-talk voice input from the WeChat hold surface', async () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', { nativeEvent: { pageX: 220, pageY: 300 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderRelease');
    await act(async () => { await Promise.resolve(); });

    expect(mockStartDictation).toHaveBeenCalled();
    expect(mockStopDictation).toHaveBeenCalled();
  });

  it('submits a hold-to-talk transcript through the voice confirmation channel', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    mockStopDictation.mockResolvedValueOnce('午餐吃了鸡胸肉');
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', {
      nativeEvent: { pageX: 220, pageY: 300 },
    });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderRelease');
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith(
        '午餐吃了鸡胸肉',
        null,
        expect.objectContaining({ channel: 'voice' }),
      );
    });
  });

  it('normalizes hold-to-talk transcript and sends voice draft context to the Agent', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    mockStopDictation.mockResolvedValueOnce('今天 h r v 下降 体重 73.1 公斤');
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', {
      nativeEvent: { pageX: 220, pageY: 300 },
    });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderRelease');
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      const [, , options] = onSend.mock.calls[0];
      expect(onSend).toHaveBeenCalledWith(
        '今天 HRV 下降 体重 73.1kg',
        null,
        expect.objectContaining({ channel: 'voice', extraContext: expect.any(String) }),
      );
      const context = JSON.parse(options.extraContext);
      expect(context.voice_draft).toMatchObject({
        source: 'hold_to_talk',
        raw: '今天 h r v 下降 体重 73.1 公斤',
        normalized: '今天 HRV 下降 体重 73.1kg',
      });
    });
  });

  it('restores a hold-to-talk transcript as editable text when voice submit is rejected', async () => {
    const onSend = jest.fn().mockResolvedValue(false);
    mockStopDictation.mockResolvedValueOnce('机场贵宾厅吃了番茄鸡蛋面');
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    const { getByLabelText, queryByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', {
      nativeEvent: { pageX: 220, pageY: 300 },
    });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderRelease');
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith(
        '机场贵宾厅吃了番茄鸡蛋面',
        null,
        expect.objectContaining({ channel: 'voice' }),
      );
      expect(queryByLabelText('按住说话')).toBeNull();
      expect(getByLabelText('消息输入框').props.value).toBe('机场贵宾厅吃了番茄鸡蛋面');
      expect(getByLabelText('发送消息')).toBeTruthy();
    });
    expect(alertSpy).toHaveBeenCalledWith('发送失败', '语音已转成文字并保留在输入框里，请修改后重试。');
  });

  it('keeps the empty field directly focusable because voice has its own left button', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    expect(StyleSheet.flatten(getByLabelText('消息输入框').props.style).pointerEvents).toBe('auto');
  });

  it('recovers a tappable, focusable field after a voice→blur cycle (Bug 2: 语音后键盘可再弹)', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;

    const field = getByLabelText('消息输入框');
    fireEvent(field, 'focus');
    expect(StyleSheet.flatten(field.props.style).pointerEvents).toBe('auto');
    fireEvent(field, 'blur');
    expect(StyleSheet.flatten(field.props.style).pointerEvents).toBe('auto');

    fireEvent.press(getByTestId('wechat-composer-input'));
    fireEvent(field, 'focus');
    expect(StyleSheet.flatten(field.props.style).pointerEvents).toBe('auto');
  });

  it('cancels hold-to-talk when the finger slides left', async () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', { nativeEvent: { pageX: 260, pageY: 620 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderMove', { nativeEvent: { pageX: 120, pageY: 620 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderRelease');

    expect(mockCancelDictation).toHaveBeenCalled();
    expect(mockStopDictation).not.toHaveBeenCalled();
  });

  it('keeps hold-to-talk transcript editable when the finger slides right', async () => {
    const onSend = jest.fn();
    mockStopDictation.mockResolvedValueOnce('记录午餐吃了鸡胸肉');
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', { nativeEvent: { pageX: 160, pageY: 620 } });
    await act(async () => { await Promise.resolve(); });
    fireEvent(getByLabelText('按住说话'), 'responderMove', { nativeEvent: { pageX: 310, pageY: 620 } });
    fireEvent(getByLabelText('按住说话'), 'responderRelease');
    await act(async () => { await Promise.resolve(); });
    expect(mockStopDictation).toHaveBeenCalled();
    expect(getByLabelText('切换到语音输入')).toBeTruthy();
    expect(getByLabelText('消息输入框').props.value).toBe('记录午餐吃了鸡胸肉');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('starts realtime dictation from the microphone inside the input field', () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    fireEvent.press(getByLabelText('实时语音转文字'));
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 500 毫升');
    });

    expect(mockStartDictation).toHaveBeenCalled();
    expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 500ml');
  });

  it('starts realtime dictation by holding the input field while the keyboard composer stays active', async () => {
    const onSend = jest.fn();
    mockStopDictation.mockResolvedValueOnce('记录今天喝水 500 毫升');
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, getByTestId } = view;
    const inputSurface = getByTestId('wechat-composer-input');

    await act(async () => {
      fireEvent(inputSurface, 'longPress');
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 300 毫升');
    });

    expect(mockStartDictation).toHaveBeenCalledTimes(1);
    expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 300ml');

    await act(async () => {
      fireEvent(inputSurface, 'pressOut');
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockStopDictation).toHaveBeenCalledTimes(1);
    expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 500ml');
    expect(getByLabelText('切换到语音输入')).toBeTruthy();
    expect(onSend).not.toHaveBeenCalled();
  });

  it('starts realtime dictation from the text input body only after the hold threshold', async () => {
    jest.useFakeTimers();
    const onSend = jest.fn();
    mockStopDictation.mockResolvedValueOnce('记录今天喝水 500 毫升');
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;
    const textInput = getByLabelText('消息输入框');

    await act(async () => {
      fireEvent(textInput, 'pressIn');
      jest.advanceTimersByTime(259);
      await Promise.resolve();
    });
    expect(mockStartDictation).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(1);
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 300 毫升');
    });

    expect(mockStartDictation).toHaveBeenCalledTimes(1);
    expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 300ml');

    await act(async () => {
      fireEvent(textInput, 'pressOut');
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockStopDictation).toHaveBeenCalledTimes(1);
    expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 500ml');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('stops realtime dictation from the active microphone button', async () => {
    const onSend = jest.fn();
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    mockRealtimeDictationState = { isDictating: true, error: null };
    view.rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await waitFor(() => expect(view.getByLabelText('停止实时语音转文字')).toBeTruthy());
    const { getByLabelText } = view;

    const mic = getByLabelText('停止实时语音转文字');
    fireEvent.press(mic);

    expect(mic.props.accessibilityState).toEqual(expect.objectContaining({ selected: true }));
    expect(mockStopDictation).toHaveBeenCalled();
  });

  it('keeps realtime dictation explicitly disabled after tapping the active microphone again', async () => {
    const onSend = jest.fn();
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, rerender } = view;
    mockRealtimeDictationState = { isDictating: true, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await waitFor(() => expect(getByLabelText('停止实时语音转文字')).toBeTruthy());

    await act(async () => {
      fireEvent.press(getByLabelText('停止实时语音转文字'));
      await Promise.resolve();
    });
    expect(mockStopDictation).toHaveBeenCalled();

    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);

    const disabledMic = await waitFor(() => getByLabelText('语音监听已禁用'));
    expect(disabledMic.props.accessibilityState).toEqual(expect.objectContaining({ selected: false }));
    const disabledMicStyle = StyleSheet.flatten(disabledMic.props.style);
    expect(disabledMicStyle.backgroundColor).toBe(revaColors.paper2);
    expect(disabledMicStyle.backgroundColor).not.toBe('#2B2B2B');
    expect(disabledMicStyle.borderColor).toBe(revaColors.lineStrong);

    fireEvent.press(disabledMic);

    expect(mockStartDictation).toHaveBeenCalled();
  });

  it('does not enter hold mode while realtime dictation is still starting', async () => {
    let resolveStart!: (started: boolean) => void;
    mockStartDictation.mockImplementationOnce(() => new Promise<boolean>((resolve) => {
      resolveStart = resolve;
    }));
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, queryByLabelText } = view;

    fireEvent.press(getByLabelText('实时语音转文字'));
    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(queryByLabelText('按住说话')).toBeNull();
    expect(getByLabelText('消息输入框')).toBeTruthy();

    await act(async () => {
      resolveStart(true);
    });
  });

  it('waits for realtime audio release before switching to hold mode', async () => {
    let resolveStop!: (text: string) => void;
    mockStopDictation.mockImplementationOnce(() => new Promise<string>((resolve) => {
      resolveStop = resolve;
    }));
    const onSend = jest.fn();
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, queryByLabelText } = view;
    mockRealtimeDictationState = { isDictating: true, error: null };
    view.rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await waitFor(() => expect(getByLabelText('停止实时语音转文字')).toBeTruthy());

    fireEvent.press(getByLabelText('切换到语音输入'));

    expect(mockStopDictation).toHaveBeenCalledTimes(1);
    expect(queryByLabelText('按住说话')).toBeNull();

    await act(async () => {
      resolveStop('');
    });
    await waitFor(() => expect(getByLabelText('按住说话')).toBeTruthy());
  });

  it('stops realtime dictation after submit and keeps the microphone available', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, rerender } = view;
    mockRealtimeDictationState = { isDictating: true, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await waitFor(() => expect(getByLabelText('停止实时语音转文字')).toBeTruthy());

    fireEvent.changeText(getByLabelText('消息输入框'), '记录今天喝水 500 毫升');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockStopDictation).toHaveBeenCalled();
      expect(onSend).toHaveBeenCalledWith('记录今天喝水 500 毫升', null, undefined);
    });

    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={true} />);
    await waitFor(() => expect(getByLabelText('实时语音转文字')).toBeTruthy());
  });

  it('keeps typed send available while 小巴 is streaming', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    fireEvent.changeText(getByLabelText('消息输入框'), '继续补充一个问题');

    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    expect(onSend).toHaveBeenCalledWith('继续补充一个问题', null, undefined);
  });

  it('allows realtime dictation to start while 小巴 is streaming', async () => {
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });

    expect(mockStartDictation).toHaveBeenCalledTimes(1);
  });

  it('submits realtime microphone transcription through the voice channel', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 500 毫升', {
        provider: 'dashscope_qwen_asr',
        model: 'qwen3-asr-flash',
        durationMs: 1560,
        confidence: 'high',
      });
    });
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      const [, , options] = onSend.mock.calls[0];
      expect(onSend).toHaveBeenCalledWith(
        '记录今天喝水 500ml',
        null,
        expect.objectContaining({ channel: 'voice', extraContext: expect.any(String) }),
      );
      const context = JSON.parse(options.extraContext);
      expect(context.voice_draft).toMatchObject({
        source: 'realtime_mic',
        raw: '记录今天喝水 500 毫升',
        normalized: '记录今天喝水 500ml',
        confidence: 'high',
        asr_provider: 'dashscope_qwen_asr',
        asr_model: 'qwen3-asr-flash',
        asr_duration_ms: 1560,
      });
    });
  });

  it('includes the final transcript returned while realtime recognition stops', async () => {
    mockStopDictation.mockResolvedValueOnce('记录今天喝水 500 毫升');
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水');
    });
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    expect(onSend).toHaveBeenCalledWith(
      '记录今天喝水 500ml',
      null,
      expect.objectContaining({ channel: 'voice', extraContext: expect.any(String) }),
    );
  });

  it('returns to the typed channel after the user edits realtime transcription', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水');
    });
    fireEvent.changeText(getByLabelText('消息输入框'), '记录今天喝水 500 毫升');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('记录今天喝水 500 毫升', null, undefined);
    });
  });

  it('does not let a late realtime transcript overwrite text edited by the user', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水');
    });

    fireEvent.changeText(getByLabelText('消息输入框'), '改成记录今天喝咖啡');
    act(() => {
      // iOS may deliver a final/late ASR event after the TextInput has changed.
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 500 毫升');
    });

    expect(getByLabelText('消息输入框').props.value).toBe('改成记录今天喝咖啡');
  });

  it('keeps realtime microphone text editable when voice submit is rejected', async () => {
    const onSend = jest.fn().mockResolvedValue(false);
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    await act(async () => {
      fireEvent.press(getByLabelText('实时语音转文字'));
      await Promise.resolve();
    });
    act(() => {
      latestRealtimeDictationOptions.onTranscript('记录今天喝水 500 毫升');
    });
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith(
        '记录今天喝水 500ml',
        null,
        expect.objectContaining({ channel: 'voice' }),
      );
      expect(getByLabelText('消息输入框').props.value).toBe('记录今天喝水 500ml');
      expect(getByLabelText('发送消息')).toBeTruthy();
    });
    expect(alertSpy).toHaveBeenCalledWith('发送失败', '语音已转成文字并保留在输入框里，请修改后重试。');
  });

  it('cancels active dictation when the app moves to the background', async () => {
    const onSend = jest.fn();
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText, rerender } = view;
    mockRealtimeDictationState = { isDictating: true, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await waitFor(() => expect(getByLabelText('停止实时语音转文字')).toBeTruthy());

    expect(appStateHandler).toBeDefined();
    act(() => {
      appStateHandler?.('background');
    });

    await waitFor(() => expect(mockCancelDictation).toHaveBeenCalled());
    mockRealtimeDictationState = { isDictating: false, error: null };
    rerender(<ChatInputBar onSend={onSend} isStreaming={false} />);
    await waitFor(() => expect(getByLabelText('语音监听已禁用')).toBeTruthy());
  });

  it('cancels hold-to-talk when the app moves to the background', async () => {
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent(getByLabelText('按住说话'), 'responderGrant', {
      nativeEvent: { pageX: 220, pageY: 620 },
    });
    await act(async () => { await Promise.resolve(); });
    act(() => {
      appStateHandler?.('background');
    });

    await waitFor(() => expect(mockCancelDictation).toHaveBeenCalled());
    expect(getByLabelText('切换到键盘输入')).toBeTruthy();
  });

  it('sends the selected agent mode as chat context without polluting the user text', async () => {
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    fireEvent.press(getByLabelText('深思模式'));
    fireEvent.press(getByLabelText('切换到键盘输入'));
    fireEvent.changeText(getByLabelText('消息输入框'), '帮我调整训练计划');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(onSend).toHaveBeenCalledWith(
      '帮我调整训练计划',
      null,
      expect.objectContaining({
        extraContext: expect.stringContaining('"mode":"deep"'),
      }),
    );
  });

  it('renders agent modes as a single compact segmented row in the attachment menu', () => {
    const { getByLabelText, getByTestId, getByText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(getByLabelText('附件菜单'));

    const modeRow = StyleSheet.flatten(getByTestId('agent-mode-segmented-row').props.style);
    expect(modeRow.flexDirection).toBe('row');
    expect(modeRow.minHeight).toBeLessThanOrEqual(38);
    expect(getByText('日常')).toBeTruthy();
    expect(getByText('深思')).toBeTruthy();
    expect(getByText('识图')).toBeTruthy();
    expect(getByLabelText('深思模式')).toBeTruthy();
  });

  it('sends typed text when Enter is pressed in the composer', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    fireEvent.changeText(getByLabelText('消息输入框'), '记录晚餐吃了鸡胸肉');
    await act(async () => {
      fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });
      await Promise.resolve();
    });

    expect(onSend).toHaveBeenCalledWith('记录晚餐吃了鸡胸肉', null, undefined);
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

  it('restores a persisted text and image draft on mount', async () => {
    const restoredImages = [{
      uri: 'file:///documents/chat-drafts/lunch.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    }];
    mockLoadChatDraft.mockResolvedValueOnce({ text: '继续确认午餐', images: restoredImages });
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    await waitFor(() => {
      expect(getByLabelText('消息输入框').props.value).toBe('继续确认午餐');
      expect(mockSetPendingImages).toHaveBeenCalledWith(restoredImages, 9);
    });
  });

  it('does not let a late draft hydration overwrite a photo captured after mount', async () => {
    let resolveDraft!: (value: unknown) => void;
    mockLoadChatDraft.mockImplementationOnce(() => new Promise(resolve => {
      resolveDraft = resolve;
    }));
    mockTakePhoto.mockResolvedValueOnce([{
      uri: 'file:///documents/chat-drafts/new-meal.jpeg',
      base64: 'new-meal',
      type: 'jpeg',
    }]);
    const oldImages = [{
      uri: 'file:///documents/chat-drafts/old-meal.jpeg',
      base64: '',
      type: 'jpeg',
    }];
    const view = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    fireEvent.press(view.getByLabelText('附件菜单'));
    await act(async () => {
      fireEvent.press(view.getByLabelText('拍照记餐'));
      await Promise.resolve();
    });
    await act(async () => {
      resolveDraft({ text: '过时草稿', images: oldImages });
      await Promise.resolve();
    });

    expect(mockSetPendingImages).not.toHaveBeenCalledWith(oldImages);
  });

  it('flushes the latest draft immediately when iOS moves to the background', async () => {
    mockLoadChatDraft.mockResolvedValueOnce({ text: '', images: [] });
    const { getByLabelText } = render(
      <ChatInputBar onSend={jest.fn()} isStreaming={false} />,
    );

    await waitFor(() => expect(mockSetPendingImages).toHaveBeenCalledWith([], 9));
    fireEvent.press(getByLabelText('切换到键盘输入'));
    fireEvent.changeText(getByLabelText('消息输入框'), '切后台前必须保存');

    act(() => {
      appStateHandler?.('background');
    });

    await waitFor(() => {
      expect(mockPersistChatDraft).toHaveBeenCalledWith(
        '切后台前必须保存',
        [],
        expect.any(Number),
        {},
      );
    });
  });

  it('keeps private image bytes when the caller does not explicitly accept the send', async () => {
    const storedImage = {
      uri: 'file:///documents/chat-drafts/lunch.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    };
    const hydratedImage = { ...storedImage, base64: 'private-base64' };
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([hydratedImage]);
    const onSend = jest.fn();
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('请分析这些图片', [hydratedImage], undefined);
      expect(mockReleaseImagesAfterSend).not.toHaveBeenCalled();
      expect(mockClearImages).not.toHaveBeenCalled();
      expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('chat_attachment_terminal', {
      phase: 'failed',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: 'lt_1s',
      payload_bucket: 'lt_256kb',
      error_code: 'server_not_accepted',
    }, expect.objectContaining({ eventKey: expect.any(String) }));
  });

  it('allows only one attachment send and one terminal event for rapid repeated presses', async () => {
    const storedImage = {
      uri: 'file:///documents/chat-drafts/rapid-lunch.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    };
    const hydratedImage = { ...storedImage, base64: 'private-base64' };
    let acceptSend: ((accepted: boolean) => void) | undefined;
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([hydratedImage]);
    const onSend = jest.fn(() => new Promise<boolean>((resolve) => {
      acceptSend = resolve;
    }));
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    act(() => {
      fireEvent.press(view.getByLabelText('发送消息'));
      fireEvent.press(view.getByLabelText('发送消息'));
    });
    await waitFor(() => expect(onSend).toHaveBeenCalledTimes(1));

    await act(async () => {
      acceptSend?.(true);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(mockEmitClientEvent).toHaveBeenCalledTimes(1);
    });
  });

  it('keeps durable photo files while a queued send is awaiting server acceptance', async () => {
    const storedImage = {
      uri: 'file:///documents/chat-drafts/queued-lunch.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    };
    const hydratedImage = { ...storedImage, base64: 'private-base64' };
    let acceptSend: ((accepted: boolean) => void) | undefined;
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([hydratedImage]);
    const onSend = jest.fn(() => new Promise<boolean>((resolve) => {
      acceptSend = resolve;
    }));
    const { getByLabelText } = render(
      <ChatInputBar onSend={onSend} isStreaming={true} />,
    );

    act(() => {
      fireEvent.press(getByLabelText('发送消息'));
    });
    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('请分析这些图片', [hydratedImage], undefined);
    });
    expect(mockReleaseImagesAfterSend).not.toHaveBeenCalled();
    expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();

    await act(async () => {
      acceptSend?.(true);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(mockReleaseImagesAfterSend).toHaveBeenCalledTimes(1);
      expect(mockClearPersistedChatDraft).toHaveBeenCalledTimes(1);
    });
  });

  it('keeps accepted image drafts until the terminal event is durably queued', async () => {
    const storedImage = {
      uri: 'file:///documents/chat-drafts/terminal-persist.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    };
    const hydratedImage = { ...storedImage, base64: 'private-base64' };
    let persistTerminal: (() => void) | undefined;
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([hydratedImage]);
    mockEmitClientEvent.mockImplementationOnce(() => new Promise<void>((resolve) => {
      persistTerminal = resolve;
    }));
    const view = render(
      <ChatInputBar onSend={jest.fn().mockResolvedValue(true)} isStreaming={false} />,
    );

    act(() => {
      fireEvent.press(view.getByLabelText('发送消息'));
    });
    await waitFor(() => {
      expect(mockEmitClientEvent).toHaveBeenCalledWith(
        'chat_attachment_terminal',
        expect.objectContaining({ phase: 'accepted' }),
        expect.objectContaining({ eventKey: expect.any(String) }),
      );
    });

    expect(mockReleaseImagesAfterSend).not.toHaveBeenCalled();
    expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();

    await act(async () => {
      persistTerminal?.();
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(mockReleaseImagesAfterSend).toHaveBeenCalledTimes(1);
      expect(mockClearPersistedChatDraft).toHaveBeenCalledTimes(1);
    });
  });

  it('does not report an accepted image send as failed when terminal telemetry persistence fails', async () => {
    const storedImage = {
      uri: 'file:///documents/chat-drafts/accepted-telemetry-failure.jpeg',
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    };
    const hydratedImage = { ...storedImage, base64: 'private-base64' };
    const alertSpy = jest.spyOn(Alert, 'alert');
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([hydratedImage]);
    mockEmitClientEvent.mockRejectedValueOnce(
      new Error('client_event_outbox_persistence_failed'),
    );
    const view = render(
      <ChatInputBar onSend={jest.fn().mockResolvedValue(true)} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(view.getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockReleaseImagesAfterSend).toHaveBeenCalledTimes(1);
      expect(mockClearPersistedChatDraft).toHaveBeenCalledTimes(1);
    });
    expect(alertSpy).not.toHaveBeenCalledWith(
      '发送失败',
      expect.any(String),
    );
    expect(mockEmitClientEvent).toHaveBeenCalledTimes(1);
  });

  it('publishes an empty in-memory snapshot before accepted-send cleanup can trigger background persistence', async () => {
    mockLoadChatDraft.mockResolvedValueOnce({ text: '', images: [] });
    let snapshotPersistedDuringRelease: unknown[] | undefined;
    let releasing = false;
    mockPersistChatDraft.mockImplementation(async (...args: unknown[]) => {
      if (releasing) snapshotPersistedDuringRelease = args;
    });
    mockReleaseImagesAfterSend.mockImplementation(() => {
      releasing = true;
      appStateHandler?.('background');
      releasing = false;
      return Promise.resolve();
    });
    const view = render(
      <ChatInputBar onSend={jest.fn().mockResolvedValue(true)} isStreaming={false} />,
    );
    await waitFor(() => expect(mockSetPendingImages).toHaveBeenCalledWith([], 9));
    enterKeyboardMode(view);
    fireEvent.changeText(view.getByLabelText('消息输入框'), '已发送后不能复活');

    await act(async () => {
      fireEvent.press(view.getByLabelText('发送消息'));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(snapshotPersistedDuringRelease).toEqual([
      '',
      [],
      expect.any(Number),
      {},
    ]);
  });

  it('retains the draft when send rejects immediately', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    jest.spyOn(console, 'warn').mockImplementation(jest.fn());
    const onSend = jest.fn().mockRejectedValue(new Error('network unavailable'));
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    fireEvent.changeText(getByLabelText('消息输入框'), '这条草稿不能丢');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('发送失败', expect.stringContaining('草稿已保留'));
    });
    expect(getByLabelText('消息输入框').props.value).toBe('这条草稿不能丢');
    expect(mockClearImages).not.toHaveBeenCalled();
    expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();
  });

  it('retains the draft when the chat engine explicitly rejects before server acceptance', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    const storedImage = {
      uri: 'file:///documents/chat-drafts/offline-lunch.jpeg',
      base64: '',
      type: 'jpeg',
    };
    mockPendingImages = [storedImage];
    mockHydrateDraftImages.mockResolvedValueOnce([{ ...storedImage, base64: 'private-base64' }]);
    const onSend = jest.fn().mockResolvedValue(false);
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );
    enterKeyboardMode(view);
    const { getByLabelText } = view;

    fireEvent.changeText(getByLabelText('消息输入框'), '离线时也不能丢');
    await act(async () => {
      fireEvent.press(getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('发送失败', expect.stringContaining('草稿已保留'));
    });
    expect(getByLabelText('消息输入框').props.value).toBe('离线时也不能丢');
    expect(mockClearImages).not.toHaveBeenCalled();
    expect(mockClearPersistedChatDraft).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('chat_attachment_terminal', {
      phase: 'failed',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: 'lt_1s',
      payload_bucket: 'lt_256kb',
      error_code: 'server_not_accepted',
    }, expect.objectContaining({ eventKey: expect.any(String) }));
  });

  it('reports local image hydration failures without leaking draft identifiers', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    jest.spyOn(console, 'warn').mockImplementation(jest.fn());
    mockPendingImages = [{
      uri: 'file:///documents/chat-drafts/private-meal.jpeg',
      base64: '',
      type: 'jpeg',
    }];
    mockHydrateDraftImages.mockRejectedValueOnce(new Error('private file path'));
    const onSend = jest.fn();
    const view = render(
      <ChatInputBar onSend={onSend} isStreaming={false} />,
    );

    await act(async () => {
      fireEvent.press(view.getByLabelText('发送消息'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        '发送失败',
        expect.stringContaining('草稿已保留'),
      );
    });
    expect(onSend).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('chat_attachment_terminal', {
      phase: 'failed',
      stage: 'local_prepare',
      image_count: 1,
      duration_bucket: 'lt_1s',
      payload_bucket: 'unknown',
      error_code: 'draft_hydration_failed',
    }, expect.objectContaining({ eventKey: expect.any(String) }));
  });

  it('updates the composer when the same follow-up prompt is injected again', async () => {
    const onSend = jest.fn().mockResolvedValue(true);
    const prompt = '请基于上一条建议继续追问';
    const { getByLabelText, rerender } = render(
      <ChatInputBar
        onSend={onSend}
        isStreaming={false}
        initialText={prompt}
        initialTextKey={1}
      />,
    );

    await act(async () => {
      fireEvent(getByLabelText('消息输入框'), 'keyPress', { nativeEvent: { key: 'Enter' } });
      await Promise.resolve();
    });
    expect(onSend).toHaveBeenCalledWith(prompt, null, undefined);
    await waitFor(() => expect(getByLabelText('消息输入框').props.value).toBe(''));

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
    const skillResult = {
      skillId: 'medical_exam_import',
      card: {
        type: 'medical_exam_import_result',
        data: { exam_id: 42, items_count: 28, review_required: true },
      },
    };
    mockExecuteMedicalExamImport.mockReturnValueOnce(skillResult);
    const onMedicalExamImportResult = jest.fn();

    const { getByLabelText, getByText } = render(
      <ChatInputBar
        onSend={jest.fn()}
        isStreaming={false}
        onMedicalExamImportResult={onMedicalExamImportResult}
      />,
    );

    fireEvent.press(getByLabelText('附件菜单'));
    fireEvent.press(getByLabelText('导入体检报告'));
    expect(getByText('体检报告导入流程')).toBeTruthy();
    fireEvent.press(getByLabelText('确认模拟导入'));

    expect(mockExecuteMedicalExamImport).toHaveBeenCalledWith(expect.objectContaining({
      examId: 42,
      source: 'pdf',
    }));
    expect(onMedicalExamImportResult).toHaveBeenCalledWith(skillResult);
  });
});
