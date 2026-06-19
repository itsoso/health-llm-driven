/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockGetRokidIntegrationStatus = jest.fn();
const mockTakeRokidPhotoBase64 = jest.fn();
const mockRequestRokidAuthorization = jest.fn();
const mockOpenRokidRevaCustomView = jest.fn();
const mockUpdateRokidCustomView = jest.fn();
const mockAddRokidTranscriptListener = jest.fn();
const mockGetRokidDeviceValidationSteps = jest.fn();
const mockListRokidGlanceCards = jest.fn();
const mockOpenRokidCompanionIfAvailable = jest.fn();
const mockSubmitRokidVisualInput = jest.fn();
const mockRecognizeFood = jest.fn();
const mockStartRokidVoiceCommandCapture = jest.fn();
const mockStopRokidVoiceCommandCapture = jest.fn();
const mockSubmitRokidVoiceCommand = jest.fn();
const mockTranscriptSubscriptionRemove = jest.fn();
let rokidTranscriptListener: ((event: any) => void | Promise<void>) | null = null;

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

jest.mock('../../modules/rokid-bridge', () => ({
  getRokidIntegrationStatus: (...args: any[]) => mockGetRokidIntegrationStatus(...args),
  getRokidDeviceValidationSteps: (...args: any[]) => mockGetRokidDeviceValidationSteps(...args),
  openRokidRevaCustomView: (...args: any[]) => mockOpenRokidRevaCustomView(...args),
  updateRokidCustomView: (...args: any[]) => mockUpdateRokidCustomView(...args),
  createRokidRevaCustomViewLayout: (options?: any) => JSON.stringify({
    type: 'LinearLayout',
    children: [
      { props: { text: options?.title ?? 'Reva Health' } },
      { props: { text: options?.body ?? '' } },
      { props: { text: options?.priority ?? 'manual_confirm' } },
    ],
  }),
  requestRokidAuthorization: (...args: any[]) => mockRequestRokidAuthorization(...args),
  takeRokidPhotoBase64: (...args: any[]) => mockTakeRokidPhotoBase64(...args),
  addRokidTranscriptListener: (...args: any[]) => mockAddRokidTranscriptListener(...args),
}));

jest.mock('../../services/rokidAmbient', () => ({
  listRokidGlanceCards: (...args: any[]) => mockListRokidGlanceCards(...args),
  openRokidCompanionIfAvailable: (...args: any[]) => mockOpenRokidCompanionIfAvailable(...args),
  submitRokidVisualInput: (...args: any[]) => mockSubmitRokidVisualInput(...args),
}));

jest.mock('../../services/diet', () => ({
  recognizeFood: (...args: any[]) => mockRecognizeFood(...args),
}));

jest.mock('../../services/rokidVoiceControl', () => ({
  ...jest.requireActual('../../services/rokidVoiceControl'),
  startRokidVoiceCommandCapture: (...args: any[]) => mockStartRokidVoiceCommandCapture(...args),
  stopRokidVoiceCommandCapture: (...args: any[]) => mockStopRokidVoiceCommandCapture(...args),
  submitRokidVoiceCommand: (...args: any[]) => mockSubmitRokidVoiceCommand(...args),
}));

import RokidHealthScreen from '../rokid-health';
import { renderWithProviders } from '../../test-utils';

const flushAsyncUpdates = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('RokidHealthScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    rokidTranscriptListener = null;
    mockAddRokidTranscriptListener.mockImplementation((listener) => {
      rokidTranscriptListener = listener;
      return { remove: mockTranscriptSubscriptionRemove };
    });
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'android',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: false,
      installedPackage: 'com.rokid.sprite.global.aiapp',
      sdkClassProbe: {
        'clientM.cxrApi': false,
        'clientL.cxrLink': false,
      },
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });
    mockListRokidGlanceCards.mockResolvedValue([
      { id: 'pushups', title: '进公司后 20 个俯卧撑', priority: 'P1' },
      { id: 'walk', title: '午饭后步行 10 分钟', priority: 'P2' },
    ]);
    mockOpenRokidCompanionIfAvailable.mockResolvedValue({
      opened: true,
      status: { canOpenHiRokid: true },
    });
    mockTakeRokidPhotoBase64.mockResolvedValue({
      ok: true,
      base64: 'jpeg-base64',
      mimeType: 'image/jpeg',
      byteLength: 2048,
      imageUri: 'private://rokid/meal-001.jpg',
      imageSha256: 'sha256-meal-001',
    });
    mockRecognizeFood.mockResolvedValue({
      success: true,
      foods: [
        {
          name: '牛肉面',
          quantity: '1碗',
          calories: 620,
          protein: 32,
          carbs: 78,
          fat: 20,
          fiber: 4,
          confidence: 0.76,
        },
      ],
      meal_description: '牛肉面 1碗',
      health_tips: '高盐餐后补水, 下餐增加蔬菜。',
      total_calories: 620,
      total_protein: 32,
      total_carbs: 78,
      total_fat: 20,
      total_fiber: 4,
      error: null,
    });
    mockRequestRokidAuthorization.mockResolvedValue({ ok: true, tokenLength: 24 });
    mockOpenRokidRevaCustomView.mockResolvedValue({
      ok: true,
      customViewRunning: true,
      capabilitiesReady: true,
    });
    mockUpdateRokidCustomView.mockResolvedValue({ ok: true });
    mockStartRokidVoiceCommandCapture.mockResolvedValue({ ok: true });
    mockStopRokidVoiceCommandCapture.mockResolvedValue({ ok: true });
    mockSubmitRokidVoiceCommand.mockResolvedValue({
      command: {
        intent: 'unknown',
        client_action: 'clarify',
        voice_reply: '请再说一遍',
      },
    });
    mockSubmitRokidVisualInput.mockResolvedValue({ id: 'visual-001' });
    mockGetRokidDeviceValidationSteps.mockImplementation((status) => [
      {
        id: 'ios_sdk_linked',
        title: 'iOS SDK 已链接',
        detail: status?.sdkLinked ? '当前包已链接 RGCxrClient:1.0.1。' : '安装 Rokid 版 Reva 包。',
        status: status?.sdkLinked ? 'done' : 'next',
        actionLabel: '安装 Rokid 版 Reva',
      },
      {
        id: 'hi_rokid_ready',
        title: 'Hi Rokid 已连接',
        detail: '在 Hi Rokid 中确认眼镜已连接。',
        status: status?.hiRokidInstalled && status?.canOpenHiRokid ? 'done' : 'pending',
        actionLabel: '打开 Hi Rokid',
      },
      {
        id: 'rokid_authorized',
        title: 'CXR-L 授权',
        detail: '在 Reva 中完成 CXR-L 授权回调后继续。',
        status: status?.authorizationState === 'authenticated' ? 'done' : 'next',
        actionLabel: '授权 Rokid',
      },
      {
        id: 'custom_view_running',
        title: 'Reva 眼镜视图',
        detail: '打开 Reva CustomView, 确认眼镜端已经显示。',
        status: status?.customViewRunning ? 'done' : 'pending',
        actionLabel: '打开 Reva 眼镜视图',
      },
      {
        id: 'capture_ready',
        title: '拍照能力就绪',
        detail: '完成会话构建后再进行食物视觉记录。',
        status: status?.capabilitiesReady ? 'done' : 'pending',
        actionLabel: '拍照验证',
      },
    ]);
  });

  it('shows bridge status, privacy boundaries, and pending Rokid glance cards', async () => {
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('Rokid 眼镜健康模式')).toBeTruthy();
      expect(screen.getByText('Hi Rokid 已安装')).toBeTruthy();
      expect(screen.getByText('Bridge 已就绪')).toBeTruthy();
      expect(screen.getByText('SDK 未链接')).toBeTruthy();
      expect(screen.getByText('进公司后 20 个俯卧撑')).toBeTruthy();
    });

    expect(screen.getByText('仅主动触发拍照 / 录音')).toBeTruthy();
    expect(screen.getByText('用药和补剂只生成待确认草稿')).toBeTruthy();

    await act(async () => {
      fireEvent.press(screen.getByText('打开 Hi Rokid'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockOpenRokidCompanionIfAvailable).toHaveBeenCalledTimes(1);
      expect(screen.getByText('已请求打开 Hi Rokid')).toBeTruthy();
    });
  });

  it('opens the Rokid push-up coach from health mode', async () => {
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('俯卧撑计数')).toBeTruthy();
    });

    fireEvent.press(screen.getByLabelText('打开 Rokid 俯卧撑计数'));

    expect(mockPush).toHaveBeenCalledWith('/rokid-pushup-coach');
  });

  it('starts and stops a bounded Rokid voice control session from health mode', async () => {
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('语音控制')).toBeTruthy();
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStartRokidVoiceCommandCapture).toHaveBeenCalledTimes(1);
      expect(mockOpenRokidRevaCustomView).toHaveBeenCalledWith({
        title: 'Reva 语音控制',
        body: '正在等待明确语音指令',
        priority: 'voice',
      });
      expect(screen.getByText('Rokid 语音控制已开启')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('停止语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStopRokidVoiceCommandCapture).toHaveBeenCalledTimes(1);
      expect(mockTranscriptSubscriptionRemove).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Rokid 语音控制已停止')).toBeTruthy();
    });
  });

  it('ignores late Rokid transcripts after the voice session starts stopping', async () => {
    let resolveStop: (value: Record<string, unknown>) => void = () => undefined;
    mockStopRokidVoiceCommandCapture.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveStop = resolve;
      }),
    );
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    expect(rokidTranscriptListener).toBeTruthy();

    fireEvent.press(screen.getByText('停止语音控制'));
    expect(mockTranscriptSubscriptionRemove).toHaveBeenCalledTimes(1);

    await act(async () => {
      await rokidTranscriptListener?.({
        transcript: '拍一下这餐',
        confidence: 0.9,
      });
      await flushAsyncUpdates();
    });

    expect(mockSubmitRokidVoiceCommand).not.toHaveBeenCalled();

    await act(async () => {
      resolveStop({ ok: true });
      await flushAsyncUpdates();
    });
  });

  it('routes a Rokid food voice transcript into photo capture and nutrition recognition', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'food_photo',
        client_action: 'capture_food_photo',
        voice_reply: '开始拍照记录这餐',
        parameters: { visual_intent: 'food_scan' },
      },
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    expect(mockAddRokidTranscriptListener).toHaveBeenCalledTimes(1);
    expect(rokidTranscriptListener).toBeTruthy();

    await act(async () => {
      await rokidTranscriptListener?.({
        transcript: '拍一下这餐',
        confidence: 0.93,
        capturedAt: '2026-06-19T21:40:00+08:00',
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledWith({
        transcript: '拍一下这餐',
        confidence: 0.93,
        context: 'rokid_health',
        capturedAt: '2026-06-19T21:40:00+08:00',
        meta: {
          source_surface: 'rokid_health_mode',
          source_event: 'rokid_transcript',
        },
      });
      expect(mockTakeRokidPhotoBase64).toHaveBeenCalledWith({
        width: 1024,
        height: 768,
        quality: 80,
      });
      expect(mockRecognizeFood).toHaveBeenCalledWith('jpeg-base64');
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        intent: 'food_scan',
        recognitionResult: expect.objectContaining({
          total_calories: 620,
          total_protein: 32,
          total_carbs: 78,
          total_fat: 20,
        }),
      }));
      expect(mockUpdateRokidCustomView).toHaveBeenCalledWith(expect.stringContaining('开始拍照记录这餐'));
      expect(screen.getByText('开始拍照记录这餐')).toBeTruthy();
    });
  });

  it('routes a Rokid push-up voice transcript into the push-up coach flow', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'pushup_start',
        client_action: 'open_pushup_coach',
        route: '/rokid-pushup-coach',
        voice_reply: '打开俯卧撑教练',
        parameters: { target_reps: 20 },
      },
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await act(async () => {
      await rokidTranscriptListener?.({
        transcript: '开始二十个俯卧撑',
        confidence: 0.9,
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledWith(expect.objectContaining({
        transcript: '开始二十个俯卧撑',
        confidence: 0.9,
        context: 'rokid_health',
      }));
      expect(mockPush).toHaveBeenCalledWith('/rokid-pushup-coach');
      expect(screen.getByText('打开俯卧撑教练')).toBeTruthy();
    });
  });

  it('does not route non-final Rokid transcript events to the command router', async () => {
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await act(async () => {
      await rokidTranscriptListener?.({
        transcript: '拍一下这餐',
        final: false,
      });
      await flushAsyncUpdates();
    });

    expect(mockSubmitRokidVoiceCommand).not.toHaveBeenCalled();
    expect(mockTakeRokidPhotoBase64).not.toHaveBeenCalled();
  });

  it('submits an explicit food photo capture with nutrition recognition as an ambient visual draft', async () => {
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText('主动触发 食物视觉记录')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByLabelText('主动触发 食物视觉记录'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockTakeRokidPhotoBase64).toHaveBeenCalledWith({
        width: 1024,
        height: 768,
        quality: 80,
      });
      expect(mockRecognizeFood).toHaveBeenCalledWith('jpeg-base64');
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith({
        intent: 'food_scan',
        imageUri: 'private://rokid/meal-001.jpg',
        imageSha256: undefined,
        recognitionResult: {
          success: true,
          foods: [
            {
              name: '牛肉面',
              quantity: '1碗',
              calories: 620,
              protein: 32,
              carbs: 78,
              fat: 20,
              fiber: 4,
              confidence: 0.76,
            },
          ],
          meal_description: '牛肉面 1碗',
          health_tips: '高盐餐后补水, 下餐增加蔬菜。',
          total_calories: 620,
          total_protein: 32,
          total_carbs: 78,
          total_fat: 20,
          total_fiber: 4,
          error: null,
        },
        confidence: 0.76,
        privacyClass: 'health_l3',
        meta: {
          privacy_mode: 'workplace',
          source_surface: 'rokid_health_mode',
          raw_media_retained: false,
          manual_confirm_required: true,
          image_byte_length: 2048,
          recognition_source: 'diet_recognize',
        },
      });
      expect(screen.getByText('已提交食物视觉记录草稿')).toBeTruthy();
    });
  });

  it('shows the iOS authorization and customView steps before capture is available', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      iosSdkDependencyMode: 'linked',
      authorizationState: 'not_authenticated',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      callbackScheme: 'life.executor.health.rokid',
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('真机验证')).toBeTruthy();
      expect(screen.getByText('下一步: 授权 Rokid')).toBeTruthy();
      expect(screen.getByText('在 Reva 中完成 CXR-L 授权回调后继续。')).toBeTruthy();
      expect(screen.getByText('授权 Rokid')).toBeTruthy();
      expect(screen.getByText('打开 Reva 眼镜视图')).toBeTruthy();
      expect(screen.getByText('能力未就绪')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('授权 Rokid'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockRequestRokidAuthorization).toHaveBeenCalledWith({
        appName: 'Reva',
        scopes: ['device_control', 'audio_stream'],
      });
      expect(screen.getByText('Rokid 已授权')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开 Reva 眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockOpenRokidRevaCustomView).toHaveBeenCalledWith({
        body: '等待 Reva 投递下一条健康行动',
        priority: 'manual_confirm',
        title: 'Reva Health',
      });
    });
  });

  it('blocks iOS photo capture until the customView scene is running', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText('主动触发 食物视觉记录')).toBeTruthy();
      expect(screen.getByText('能力未就绪')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByLabelText('主动触发 食物视觉记录'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockTakeRokidPhotoBase64).not.toHaveBeenCalled();
      expect(mockSubmitRokidVisualInput).not.toHaveBeenCalled();
      expect(screen.getByText('食物视觉记录失败: rokid_custom_view_not_ready')).toBeTruthy();
    });
  });
});
