/* eslint-disable import/first */
import React from 'react';
import { Alert } from 'react-native';
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
const mockGetSmartAgendaToday = jest.fn();
const mockCompleteAgendaItem = jest.fn();
const mockCreateRokidOperation = jest.fn();
const mockAppendRokidOperationEvent = jest.fn();
const mockUploadRokidDiagnostics = jest.fn();
const mockSetClipboardStringAsync = jest.fn();
const mockVoiceStart = jest.fn().mockResolvedValue(undefined);
const mockVoiceStop = jest.fn().mockResolvedValue(undefined);
const mockVoiceDestroy = jest.fn().mockResolvedValue(undefined);
const mockVoiceRemoveAllListeners = jest.fn();
const mockSetAudioModeAsync = jest.fn().mockResolvedValue(undefined);
const mockRequestCameraPermissions = jest.fn();
const mockLaunchCamera = jest.fn();
const mockTranscriptSubscriptionRemove = jest.fn();
let rokidTranscriptListener: ((event: any) => void | Promise<void>) | null = null;
let mockVoiceOnSpeechPartialResults: ((event: { value?: string[] }) => void) | undefined;
let mockVoiceOnSpeechResults: ((event: { value?: string[] }) => void) | undefined;
let mockVoiceOnSpeechEnd: (() => void) | undefined;
let mockVoiceOnSpeechError: ((event: { error?: { message?: string } }) => void) | undefined;

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

jest.mock('../../modules/rokid-bridge', () => {
  const actual = jest.requireActual('../../modules/rokid-bridge');
  return {
    formatRokidLogTimestamp: actual.formatRokidLogTimestamp,
    buildRokidCapabilityGateway: actual.buildRokidCapabilityGateway,
    isRokidBleBlockedByCompanionSuspected: actual.isRokidBleBlockedByCompanionSuspected,
    getRokidIntegrationStatus: (...args: any[]) => mockGetRokidIntegrationStatus(...args),
    getRokidDeviceValidationSteps: (...args: any[]) => mockGetRokidDeviceValidationSteps(...args),
    openRokidRevaCustomView: (...args: any[]) => mockOpenRokidRevaCustomView(...args),
    updateRokidCustomView: (...args: any[]) => mockUpdateRokidCustomView(...args),
    createRokidRevaCustomViewLayout: (options?: any) => JSON.stringify({
      type: 'LinearLayout',
      children: [
        { props: { text: options?.title ?? '小巴健康' } },
        { props: { text: options?.body ?? '' } },
        { props: { text: options?.priority ?? 'manual_confirm' } },
      ],
    }),
    requestRokidAuthorization: (...args: any[]) => mockRequestRokidAuthorization(...args),
    takeRokidPhotoBase64: (...args: any[]) => mockTakeRokidPhotoBase64(...args),
    addRokidTranscriptListener: (...args: any[]) => mockAddRokidTranscriptListener(...args),
  };
});

jest.mock('../../services/rokidAmbient', () => ({
  listRokidGlanceCards: (...args: any[]) => mockListRokidGlanceCards(...args),
  openRokidCompanionIfAvailable: (...args: any[]) => mockOpenRokidCompanionIfAvailable(...args),
  submitRokidVisualInput: (...args: any[]) => mockSubmitRokidVisualInput(...args),
}));

jest.mock('../../services/diet', () => ({
  recognizeFood: (...args: any[]) => mockRecognizeFood(...args),
}));

jest.mock('../../services/agenda', () => ({
  ...jest.requireActual('../../services/agenda'),
  getSmartAgendaToday: (...args: any[]) => mockGetSmartAgendaToday(...args),
  completeAgendaItem: (...args: any[]) => mockCompleteAgendaItem(...args),
}));

jest.mock('../../services/rokidVoiceControl', () => ({
  ...jest.requireActual('../../services/rokidVoiceControl'),
  startRokidVoiceCommandCapture: (...args: any[]) => mockStartRokidVoiceCommandCapture(...args),
  stopRokidVoiceCommandCapture: (...args: any[]) => mockStopRokidVoiceCommandCapture(...args),
  submitRokidVoiceCommand: (...args: any[]) => mockSubmitRokidVoiceCommand(...args),
}));

jest.mock('../../services/rokidOperations', () => {
  const actual = jest.requireActual('../../services/rokidOperations');
  return {
    ...actual,
    createRokidOperation: (...args: any[]) => mockCreateRokidOperation(...args),
    appendRokidOperationEvent: (...args: any[]) => mockAppendRokidOperationEvent(...args),
    uploadRokidDiagnostics: (...args: any[]) => mockUploadRokidDiagnostics(...args),
  };
});

jest.mock('expo-clipboard', () => ({
  setStringAsync: (...args: any[]) => mockSetClipboardStringAsync(...args),
}));

jest.mock('expo-audio', () => ({
  setAudioModeAsync: (...args: any[]) => mockSetAudioModeAsync(...args),
}));

jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: (...args: any[]) => mockRequestCameraPermissions(...args),
  launchCameraAsync: (...args: any[]) => mockLaunchCamera(...args),
}));

jest.mock('@react-native-voice/voice', () => {
  const voice: any = {
    start: (...args: any[]) => mockVoiceStart(...args),
    stop: (...args: any[]) => mockVoiceStop(...args),
    destroy: (...args: any[]) => mockVoiceDestroy(...args),
    removeAllListeners: (...args: any[]) => mockVoiceRemoveAllListeners(...args),
  };
  Object.defineProperty(voice, 'onSpeechPartialResults', {
    get: () => mockVoiceOnSpeechPartialResults,
    set: (handler) => { mockVoiceOnSpeechPartialResults = handler; },
  });
  Object.defineProperty(voice, 'onSpeechResults', {
    get: () => mockVoiceOnSpeechResults,
    set: (handler) => { mockVoiceOnSpeechResults = handler; },
  });
  Object.defineProperty(voice, 'onSpeechEnd', {
    get: () => mockVoiceOnSpeechEnd,
    set: (handler) => { mockVoiceOnSpeechEnd = handler; },
  });
  Object.defineProperty(voice, 'onSpeechError', {
    get: () => mockVoiceOnSpeechError,
    set: (handler) => { mockVoiceOnSpeechError = handler; },
  });
  return { __esModule: true, default: voice };
});

import RokidHealthScreen from '../rokid-health';
import { renderWithProviders } from '../../test-utils';

const flushAsyncUpdates = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('RokidHealthScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    rokidTranscriptListener = null;
    mockVoiceOnSpeechPartialResults = undefined;
    mockVoiceOnSpeechResults = undefined;
    mockVoiceOnSpeechEnd = undefined;
    mockVoiceOnSpeechError = undefined;
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
    mockCreateRokidOperation.mockResolvedValue({ operation_id: 'rokid-test-operation' });
    mockAppendRokidOperationEvent.mockResolvedValue({ id: 1 });
    mockUploadRokidDiagnostics.mockResolvedValue({ id: 2 });
    mockSubmitRokidVoiceCommand.mockResolvedValue({
      command: {
        intent: 'unknown',
        client_action: 'clarify',
        voice_reply: '请再说一遍',
      },
    });
    mockSetClipboardStringAsync.mockResolvedValue(undefined);
    mockSubmitRokidVisualInput.mockResolvedValue({ id: 'visual-001' });
    mockRequestCameraPermissions.mockResolvedValue({ granted: true });
    mockLaunchCamera.mockResolvedValue({
      canceled: false,
      assets: [{ base64: 'phone-jpeg-base64', uri: 'file:///phone/meal.jpg' }],
    });
    mockGetRokidDeviceValidationSteps.mockImplementation((status) => [
      {
        id: 'ios_sdk_linked',
        title: 'iOS SDK 已链接',
        detail: status?.sdkLinked ? '当前包已链接 RGCxrClient:1.0.1。' : '安装 Rokid 版小巴健康包。',
        status: status?.sdkLinked ? 'done' : 'next',
        actionLabel: '安装 Rokid 版小巴健康',
      },
      {
        id: 'hi_rokid_ready',
        title: 'Rokid companion 已连接',
        detail: '在 Rokid AI / Hi Rokid 中确认眼镜已连接。',
        status: status?.hiRokidInstalled && status?.canOpenHiRokid ? 'done' : 'pending',
        actionLabel: '打开 Rokid AI / Hi Rokid',
      },
      {
        id: 'rokid_authorized',
        title: 'CXR-L 授权',
        detail: '在小巴健康中完成 CXR-L 授权回调后继续。',
        status: status?.authorizationState === 'authenticated' ? 'done' : 'next',
        actionLabel: '授权 Rokid',
      },
      {
        id: 'custom_view_running',
        title: '小巴健康眼镜视图',
        detail: '打开小巴健康 CustomView, 确认眼镜端已经显示。',
        status: status?.customViewRunning ? 'done' : 'pending',
        actionLabel: '打开小巴健康眼镜视图',
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
      expect(screen.getByText('Rokid companion 已安装')).toBeTruthy();
      expect(screen.getByText('Bridge 已就绪')).toBeTruthy();
      expect(screen.getByText('SDK 未链接')).toBeTruthy();
      expect(screen.getByText('进公司后 20 个俯卧撑')).toBeTruthy();
    });

    expect(screen.getByText('仅主动触发拍照 / 录音')).toBeTruthy();
    expect(screen.getByText('用药和补剂只生成待确认草稿')).toBeTruthy();

    await act(async () => {
      fireEvent.press(screen.getByText('打开 Rokid AI / Hi Rokid'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockOpenRokidCompanionIfAvailable).toHaveBeenCalledTimes(1);
      expect(screen.getByText('已请求打开 Rokid AI / Hi Rokid')).toBeTruthy();
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
        title: '小巴健康语音控制',
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

  it('shows a voice self-check when Rokid recording starts but no audio stream arrives and copies debug info', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      sdkLinkedReason: 'can_import_RGCxrClient_with_callback_api',
      nativeAppVersion: '1.3.0',
      nativeBuildNumber: '173',
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      companionServerScheme: 'rokidai',
      companionServerHost: 'connect',
      currentDeviceName: 'Glasses_0077',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      activeRecordType: 'reva_voice_command',
      lastAudioEventType: 'record_start_requested',
      lastAudioRecordType: 'reva_voice_command',
      audioStreamChunkCount: 0,
      audioStreamByteCount: 0,
      lastAudioEventAt: '2026-06-20T11:31:54Z',
      lastCustomViewOpenError: 'rokid_custom_view_open_callback_missing; running=false; rawNotify=none; iosBleConnected=true; device=Glasses_0077',
      acceptedCallbackSchemes: ['cxrl', 'life.executor.health.rokid'],
      callbackScheme: 'cxrl',
      callbackSchemeSource: 'info_plist',
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
      expect(screen.getByText('语音自检')).toBeTruthy();
      expect(screen.getByText('录音已请求，但 Rokid 尚未返回音频流')).toBeTruthy();
      expect(screen.getByText('0 chunks · 0 bytes')).toBeTruthy();
      expect(screen.getByText('CustomView 回调缺失，眼镜显示可能已出现但 SDK 未确认')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('复制调试信息'));
      await flushAsyncUpdates();
    });

    expect(mockSetClipboardStringAsync).toHaveBeenCalledTimes(1);
    const copied = mockSetClipboardStringAsync.mock.calls[0]?.[0] as string;
    expect(copied).toContain('Rokid Voice Self Check');
    expect(copied).toContain('build=173');
    expect(copied).toContain('audio.event=record_start_requested');
    expect(copied).toContain('audio.chunks=0');
    expect(copied).toContain('audio.bytes=0');
    expect(copied).toContain('ble.companionBlockedSuspected=false');
    expect(copied).toContain('customView.error=rokid_custom_view_open_callback_missing');
    expect(copied).not.toContain('base64');
    expect(alertSpy).toHaveBeenCalledWith(
      '已复制',
      'Rokid 语音自检信息已复制；本次没有可上传的 operation_id 或上传失败。',
    );
    alertSpy.mockRestore();
  });

  it('opens CustomView before starting native Rokid voice recording', async () => {
    const callOrder: string[] = [];
    mockOpenRokidRevaCustomView.mockImplementationOnce(async () => {
      callOrder.push('open_custom_view');
      return {
        ok: true,
        customViewRunning: true,
        capabilitiesReady: true,
      };
    });
    mockStartRokidVoiceCommandCapture.mockImplementationOnce(async () => {
      callOrder.push('start_record');
      return { ok: true };
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(callOrder).toEqual(['open_custom_view', 'start_record']);
      expect(screen.getByText('Rokid 语音控制已开启')).toBeTruthy();
    });
  });

  it('does not start native Rokid voice recording when CustomView cannot be constructed', async () => {
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_custom_view_open_callback_missing',
      customViewRunning: false,
      capabilitiesReady: false,
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStartRokidVoiceCommandCapture).not.toHaveBeenCalled();
      expect(mockStopRokidVoiceCommandCapture).not.toHaveBeenCalled();
      expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
      expect(screen.getByText(/已切到手机麦克风/)).toBeTruthy();
    });
  });

  it('classifies iOS CustomView callback nil as a phone-mic voice fallback instead of a raw Rokid error', async () => {
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'ios_ble_connected; open_callback_error_code=nil; device=Glasses_0077',
      customViewRunning: false,
      capabilitiesReady: false,
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStartRokidVoiceCommandCapture).not.toHaveBeenCalled();
      expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
      expect(screen.getByText(/手机麦克风兜底已开启/)).toBeTruthy();
      expect(screen.queryByText(/Rokid 语音控制失败: ios_ble_connected/)).toBeNull();
    });
  });

  it('tries native Rokid voice capture when CustomView has display evidence even before running is confirmed', async () => {
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'ios_ble_connected; open_callback_error_code=nil; device=Glasses_0077',
      customViewRunning: false,
      capabilitiesReady: false,
      iosBleConnected: true,
      customViewSessionEvidence: true,
      customViewDisplayInferred: true,
      lastCustomViewSessionEvidenceReason: 'open_callback_false_nil_error_ble_connected',
    });
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'linked',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      customViewRunning: false,
      customViewSessionEvidence: true,
      customViewDisplayInferred: true,
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
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStartRokidVoiceCommandCapture).toHaveBeenCalledTimes(1);
      expect(mockVoiceStart).not.toHaveBeenCalled();
      expect(screen.getByText('Rokid 语音控制已开启')).toBeTruthy();
    });

    await act(async () => {
      await rokidTranscriptListener?.({ transcript: '记录', final: true, capturedAt: '2026-06-20T23:20:00+08:00' });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledWith({
        transcript: '记录这餐',
        confidence: undefined,
        context: 'rokid_health',
        capturedAt: '2026-06-20T23:20:00+08:00',
        meta: {
          operation_id: expect.any(String),
          source_surface: 'rokid_health_mode',
          source_event: 'rokid_transcript',
          raw_transcript: '记录',
          transcript_normalized_by: 'rokid_health_short_food_record',
        },
      });
    });

    await act(async () => {
      fireEvent.press(screen.getByText('复制调试信息'));
      await flushAsyncUpdates();
    });

    const copied = mockSetClipboardStringAsync.mock.calls.at(-1)?.[0] as string;
    expect(copied).toContain('voice.normalizer=short-food-record-v2');
    expect(copied).toContain('route.rawTranscript=记录');
    expect(copied).toContain('route.normalizedTranscript=记录这餐');
    expect(copied).toContain('route.normalizedBy=rokid_health_short_food_record');
  });

  it('accumulates the longest phone-mic transcript and routes the full phrase on speech end', async () => {
    mockStartRokidVoiceCommandCapture.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_audio_session_not_ready',
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
      expect(screen.getByText(/手机麦克风兜底已开启/)).toBeTruthy();
    });

    // iOS zh-CN SFSpeech 在停顿处先抛出截断的 intermediate final "记录",随后才补全 "记录这顿饭"。
    // 修复后:onSpeechResults 不立即路由(否则 Voice.stop 截断),累积取最长;onSpeechEnd 才路由完整句。
    await act(async () => {
      mockVoiceOnSpeechResults?.({ value: ['记录'] });
      mockVoiceOnSpeechResults?.({ value: ['记录这顿饭'] });
      mockVoiceOnSpeechEnd?.();
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledTimes(1);
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledWith({
        transcript: '记录这顿饭',
        confidence: undefined,
        context: 'rokid_health',
        capturedAt: expect.any(String),
        meta: {
          operation_id: expect.any(String),
          source_surface: 'rokid_health_mode',
          source_event: 'phone_mic_fallback',
          fallback_reason: 'rokid_audio_session_not_ready',
        },
      });
    });
  });

  it('restarts phone microphone fallback after an unclear command routes to clarify', async () => {
    mockStartRokidVoiceCommandCapture.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_audio_session_not_ready',
    });
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'unknown',
        client_action: 'clarify',
        voice_reply: '这句我还不能安全执行。你可以说记录这餐、开始俯卧撑, 或指导我运动。',
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

    await waitFor(() => {
      expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
      expect(mockVoiceStart).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      mockVoiceOnSpeechResults?.({ value: ['钢铁侠吧'] });
      mockVoiceOnSpeechEnd?.();
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledWith(expect.objectContaining({
        transcript: '钢铁侠吧',
        context: 'rokid_health',
        meta: expect.objectContaining({
          source_event: 'phone_mic_fallback',
        }),
      }));
      expect(mockVoiceStop).toHaveBeenCalled();
      expect(mockVoiceStart).toHaveBeenCalledTimes(2);
    });
  });

  it('starts phone microphone fallback when native Rokid voice capture cannot bind to a session', async () => {
    mockStartRokidVoiceCommandCapture.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_audio_session_not_ready',
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStartRokidVoiceCommandCapture).toHaveBeenCalledTimes(1);
      expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
      expect(screen.getByText(/手机麦克风兜底已开启/)).toBeTruthy();
    });

    expect(mockOpenRokidRevaCustomView).toHaveBeenCalledWith({
      title: '小巴健康语音控制',
      body: '正在等待明确语音指令',
      priority: 'voice',
    });
  });

  it('executes phone-camera food capture when phone-mic voice routing succeeds but CustomView feedback hangs', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
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
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_glasses_ble_not_connected',
      customViewRunning: false,
      capabilitiesReady: false,
    });
    mockUpdateRokidCustomView.mockImplementation(() => new Promise(() => undefined));
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'food_photo',
        client_action: 'capture_food_photo',
        voice_reply: '我来拍这餐, 识别后会生成待确认的热量和营养记录。',
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

    await waitFor(() => {
      expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
    });

    await act(async () => {
      mockVoiceOnSpeechResults?.({ value: ['记录这顿餐'] });
      mockVoiceOnSpeechEnd?.();
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockLaunchCamera).toHaveBeenCalled();
      expect(mockTakeRokidPhotoBase64).not.toHaveBeenCalled();
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        intent: 'food_scan',
        meta: expect.objectContaining({
          manual_confirm_required: true,
          capture_source: 'phone_camera_fallback',
        }),
      }));
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
          operation_id: expect.any(String),
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
        capturedAt: expect.any(String),
        recognitionResult: expect.objectContaining({
          total_calories: 620,
          total_protein: 32,
          total_carbs: 78,
          total_fat: 20,
        }),
        meta: expect.objectContaining({
          meal_type: expect.any(String),
        }),
      }));
      expect(mockUpdateRokidCustomView).toHaveBeenCalledWith(expect.stringContaining('开始拍照记录这餐'));
      expect(screen.getByText('开始拍照记录这餐')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('复制调试信息'));
      await flushAsyncUpdates();
    });

    const copied = mockSetClipboardStringAsync.mock.calls.at(-1)?.[0] as string;
    expect(copied).toContain('photo.phase=submitted');
    expect(copied).toContain('photo.source=rokid_glasses');
    expect(copied).toContain('photo.bytes=2048');
    expect(copied).not.toContain('jpeg-base64');
  });

  it('shows a saved diet record summary after voice-triggered food photo recognition', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'food_photo',
        client_action: 'capture_food_photo',
        voice_reply: '开始拍照记录这餐',
        parameters: { visual_intent: 'food_scan' },
      },
    });
    mockSubmitRokidVisualInput.mockResolvedValueOnce({
      event: {
        id: 88,
        status: 'processed',
        target_type: 'diet_record',
        target_id: 42,
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
        transcript: '拍一下这餐',
        confidence: 0.93,
        capturedAt: '2026-06-20T16:23:00+08:00',
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('已保存饮食记录：牛肉面 1碗 · 620kcal · 蛋白32g · 碳水78g · 脂肪20g')).toBeTruthy();
      expect(screen.getByText('最近状态: 已保存饮食记录：牛肉面 1碗 · 620kcal · 蛋白32g · 碳水78g · 脂肪20g')).toBeTruthy();
    });
  });

  const smartProtocolItem = (overrides: Record<string, any> = {}) => ({
    id: 'smart_health_protocol_1',
    type: 'hydration',
    title: '晨间喝水 2000ml',
    status: 'pending',
    priority: 50,
    source: { object_type: 'health_protocol', object_id: 1 },
    why_now: '',
    do_now: '',
    verify_by: {},
    replan_policy: {},
    surface: { primary: 'home' },
    autonomy_tier: 'suggest',
    voice_actionable: true,
    can_complete: true,
    can_snooze: true,
    can_skip: true,
    ...overrides,
  });

  const smartTodayResponse = (topItems: Record<string, any>[]) => ({
    agenda_date: '2026-06-25',
    count: topItems.length,
    items: [],
    mode: 'smart',
    source_count: topItems.length,
    smart: { top_items: topItems },
  });

  it('confirms the current pending agenda item from a Rokid "确认" voice transcript', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'confirm',
        client_action: 'confirm_current',
        voice_reply: '收到, 我会确认当前待处理动作。',
        requires_confirmation: true,
      },
    });
    mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayResponse([smartProtocolItem()]));
    mockCompleteAgendaItem.mockResolvedValueOnce({});
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
        transcript: '确认',
        confidence: 0.95,
        capturedAt: '2026-06-25T09:00:00+08:00',
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
        { object_type: 'health_protocol', object_id: 1 },
        'protocol',
        undefined,
        { status: 'done' },
      );
      expect(screen.getByText('已确认：晨间喝水 2000ml')).toBeTruthy();
    });
  });

  it('skips the current pending agenda item from a Rokid "跳过" voice transcript', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'skip',
        client_action: 'skip_current',
        voice_reply: '已准备跳过当前动作。',
      },
    });
    mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayResponse([smartProtocolItem()]));
    mockCompleteAgendaItem.mockResolvedValueOnce({});
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
        transcript: '跳过',
        confidence: 0.95,
        capturedAt: '2026-06-25T09:00:00+08:00',
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
        { object_type: 'health_protocol', object_id: 1 },
        'protocol',
        undefined,
        { status: 'skipped' },
      );
      expect(screen.getByText('已跳过：晨间喝水 2000ml')).toBeTruthy();
    });
  });

  it('snoozes (no write) the current pending agenda item from a Rokid "等会" voice transcript', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'later',
        client_action: 'snooze_current',
        voice_reply: '好, 这个动作稍后再提醒。',
      },
    });
    mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayResponse([smartProtocolItem()]));
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
        transcript: '等会',
        confidence: 0.95,
        capturedAt: '2026-06-25T09:00:00+08:00',
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('稍后再提醒：晨间喝水 2000ml')).toBeTruthy();
    });
    // snooze 不写:完成回路绝不被调用(后端无 snooze 端点,待办保持 pending)。
    expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
  });

  it('fail-louds a Rokid "确认" when the only pending item is medical-grade (R4: no vague-voice auto-confirm)', async () => {
    mockSubmitRokidVoiceCommand.mockResolvedValueOnce({
      command: {
        intent: 'confirm',
        client_action: 'confirm_current',
        voice_reply: '收到, 我会确认当前待处理动作。',
        requires_confirmation: true,
      },
    });
    // 当前唯一待办是用药协议(真实议程 shape:object_type=health_protocol, type=medication,
    // 后端 voice_actionable=false)→ 被安全门排除 → 没有可语音执行的待办。
    mockGetSmartAgendaToday.mockResolvedValueOnce(
      smartTodayResponse([
        smartProtocolItem({
          title: '二甲双胍 0.5g',
          type: 'medication',
          voice_actionable: false,
          source: { object_type: 'health_protocol', object_id: 7 },
        }),
      ]),
    );
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
        transcript: '确认',
        confidence: 0.95,
        capturedAt: '2026-06-25T09:00:00+08:00',
      });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('现在没有可用语音确认的待处理动作，请在手机上查看议程。')).toBeTruthy();
    });
    expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
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
    mockSubmitRokidVisualInput.mockResolvedValueOnce({
      event: {
        id: 501,
        status: 'needs_confirmation',
        target_type: 'diet_draft',
        target_id: 601,
      },
    });
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
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        intent: 'food_scan',
        capturedAt: expect.any(String),
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
        meta: expect.objectContaining({
          privacy_mode: 'workplace',
          source_surface: 'rokid_health_mode',
          raw_media_retained: false,
          manual_confirm_required: true,
          meal_type: expect.any(String),
          image_byte_length: 2048,
          recognition_source: 'diet_recognize',
        }),
      }));
      expect(mockAppendRokidOperationEvent).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
        eventType: 'food_draft_submitted',
        payload: expect.objectContaining({
          visual_input_event_id: 501,
          target_type: 'diet_draft',
          target_id: 601,
        }),
      }));
      expect(screen.getByText('已提交食物视觉记录草稿：牛肉面 1碗 · 620kcal · 蛋白32g · 碳水78g · 脂肪20g')).toBeTruthy();
    });
  });

  it('falls back to the mobile camera (draft, not auto-write) when the glasses photo never returns', async () => {
    // 眼镜拍了照但照片经 BLE 回传卡住 → native promise 永不 resolve, 包装器超时返回 rokid_photo_timeout。
    // council #1 R4: 降级到手机相机, 但仍走 Rokid 草稿流(manual_confirm_required), 绝不深链 diet 自动入库。
    mockTakeRokidPhotoBase64.mockResolvedValueOnce({ ok: false, reason: 'rokid_photo_timeout' });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText('主动触发 食物视觉记录')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByLabelText('主动触发 食物视觉记录'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockLaunchCamera).toHaveBeenCalled();
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        intent: 'food_scan',
        meta: expect.objectContaining({
          manual_confirm_required: true,
          capture_source: 'phone_camera_fallback',
        }),
      }));
      expect(mockPush).not.toHaveBeenCalledWith('/diet?capture=photo');
    });
  });

  it('tries glasses food capture first when iOS BLE is connected even before CustomView running is confirmed', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      customViewRunning: false,
      capabilitiesReady: false,
      lastCustomViewOpenError: 'rokid_custom_view_open_callback_missing; running=false; rawNotify=none; iosBleConnected=true; device=Glasses_0077',
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
      expect(mockLaunchCamera).not.toHaveBeenCalled();
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        intent: 'food_scan',
        meta: expect.objectContaining({
          capture_source: 'rokid_glasses',
        }),
      }));
    });
  });

  it('does not double-route an over-captured glasses transcript (记录这一餐 → 记录这一餐明天天气)', async () => {
    // council #3:iOS 过度捕获让同一句先出 "记录这一餐",随后被环境音拖长成 "记录这一餐明天天气"。
    // 两条是不同字符串 → 旧逻辑会各自路由 → 两次拍照/草稿。去重后只路由一次。
    mockSubmitRokidVoiceCommand.mockResolvedValue({
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

    expect(rokidTranscriptListener).toBeTruthy();

    await act(async () => {
      await rokidTranscriptListener?.({ transcript: '记录这一餐', final: true, capturedAt: '2026-06-20T23:20:00+08:00' });
      await flushAsyncUpdates();
      await rokidTranscriptListener?.({ transcript: '记录这一餐明天天气', final: true, capturedAt: '2026-06-20T23:20:02+08:00' });
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSubmitRokidVoiceCommand).toHaveBeenCalledTimes(1);
      expect(mockTakeRokidPhotoBase64).toHaveBeenCalledTimes(1);
    });
  });

  it('stops native Rokid recording on unmount to avoid background L3 audio capture', async () => {
    // council #2 隐私:启动语音后离屏/卸载必须停原生录音,否则眼镜仍在采 L3 音频且无停止入口。
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    mockStopRokidVoiceCommandCapture.mockClear();

    await act(async () => {
      screen.unmount();
      await flushAsyncUpdates();
    });

    expect(mockStopRokidVoiceCommandCapture).toHaveBeenCalled();
  });

  it('routes the manual fallback button (voice failed) into the R4-safe draft, not diet auto-write', async () => {
    // council #1 R4 round2(Codex 抓到上轮漏的第二处):语音失败时的"手机拍餐"兜底按钮也必须走草稿流,
    // 不能深链 /diet?capture=photo(diet.tsx 立即 createDietRecord 自动入库)。
    // 先让 startVoiceControl 抛错(不可恢复、无 evidence)→ voiceState='failed' → 渲染兜底按钮。
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_unrecoverable_open_error',
      customViewRunning: false,
      capabilitiesReady: false,
      customViewSessionEvidence: false,
    });
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      sdkLinked: true,
      authorizationState: 'authenticated',
      customViewRunning: false,
      capabilitiesReady: false,
      customViewSessionEvidence: false,
      iosBleConnected: false,
    });
    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('启动语音控制')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('启动语音控制'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByLabelText('手机拍餐')).toBeTruthy();
    });

    mockLaunchCamera.mockClear();
    await act(async () => {
      fireEvent.press(screen.getByLabelText('手机拍餐'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockLaunchCamera).toHaveBeenCalled();
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        meta: expect.objectContaining({
          manual_confirm_required: true,
          capture_source: 'phone_camera_fallback',
        }),
      }));
      expect(mockPush).not.toHaveBeenCalledWith('/diet?capture=photo');
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
      expect(screen.getByText('在小巴健康中完成 CXR-L 授权回调后继续。')).toBeTruthy();
      expect(screen.getByText('授权 Rokid')).toBeTruthy();
      expect(screen.getByText('打开小巴健康眼镜视图')).toBeTruthy();
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
      fireEvent.press(screen.getByText('打开小巴健康眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockOpenRokidRevaCustomView).toHaveBeenCalledWith({
        body: '等待小巴健康投递下一条健康行动',
        priority: 'manual_confirm',
        title: '小巴健康 Health',
      });
    });
  });

  it('shows a clear failure when the iOS SDK accepts CustomView open but no running event follows', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
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
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_custom_view_not_running_after_open; commandAccepted=true; rawNotify=none; iosBleConnected=true; device=Glasses_0077',
      customViewCommandAccepted: true,
      customViewRunning: false,
      capabilitiesReady: false,
      pendingSessionEvent: false,
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('已授权')).toBeTruthy();
      expect(screen.getByText('CustomView 未运行')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开小巴健康眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('小巴健康眼镜视图失败: SDK 已接受打开命令，但眼镜端没有回报 CustomView 运行。请确认眼镜端是否显示小巴健康；若未显示，请重新打开眼镜视图。')).toBeTruthy();
      expect(screen.queryByText('小巴健康眼镜视图已打开')).toBeNull();
      expect(screen.queryByText('小巴健康眼镜视图已运行')).toBeNull();
    });
  });

  it('shows iOS BLE connection diagnostics before CustomView is running', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
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
      expect(screen.getByText('iOS BLE: connected=false')).toBeTruthy();
      expect(screen.getByText('CustomView 未运行')).toBeTruthy();
    });
  });

  it('shows a capability route instead of treating silent CustomView as total Rokid failure', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      customAppSupported: true,
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      lastCustomViewOpenError: 'rokid_custom_view_open_callback_missing; running=false; rawNotify=none; iosBleConnected=true; device=Glasses_0077',
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
      expect(screen.getByText('能力路由')).toBeTruthy();
      expect(screen.getByText('推荐路径: 眼镜端 App 优先')).toBeTruthy();
      expect(screen.getByText('运动: 眼镜端 App 优先')).toBeTruthy();
      expect(screen.getByText('饮食: 眼镜拍照优先')).toBeTruthy();
      expect(screen.getByText('显示: CXR-L 阻塞')).toBeTruthy();
      expect(screen.getByText(/CXR-L CustomView 静默/)).toBeTruthy();
      expect(screen.getByText(/眼镜端 App 优先，CXR-L 安装\/启动失败时可用本地计数兜底。/)).toBeTruthy();
    });
  });

  it('routes to mobile fallback when Rokid reports the glasses CXR data channel has no network', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      customAppSupported: true,
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      lastCustomViewOpenError: 'rokid_glasses_no_network; CXR 数据通道(TCP/WiFi)需眼镜联网; rawNotify=cmd=1; subCmd=NoNetwork; status=0; reqId=8; iosBleConnected=true; device=Glasses_0077',
      lastCustomViewRawNotify: 'cmd=1; subCmd=NoNetwork; status=0; reqId=8',
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
      expect(screen.getByText('能力路由')).toBeTruthy();
      expect(screen.getByText('推荐路径: 手机兜底')).toBeTruthy();
      expect(screen.getByText('运动: 眼镜端 App 优先')).toBeTruthy();
      expect(screen.getByText('饮食: 手机拍照兜底')).toBeTruthy();
      expect(screen.getByText(/Rokid 眼镜网络未就绪/)).toBeTruthy();
      expect(screen.queryByText(/未收到 callback\/notify/)).toBeNull();
    });
  });

  it('explains NoNetwork CustomView open failures with WiFi and same-network guidance', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
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
    mockOpenRokidRevaCustomView.mockResolvedValueOnce({
      ok: false,
      reason: 'rokid_glasses_no_network; CXR 数据通道(TCP/WiFi)需眼镜联网; rawNotify=cmd=1; subCmd=NoNetwork; status=0',
      customViewRunning: false,
      capabilitiesReady: false,
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('打开小巴健康眼镜视图')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开小巴健康眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('小巴健康眼镜视图失败: 眼镜网络未就绪: 请在 Rokid AI / Hi Rokid 中确认眼镜已连 WiFi，并让手机与眼镜处在同一可互通网络，再回小巴健康刷新。')).toBeTruthy();
    });
  });

  it('surfaces iOS CXR-L callback builds that did not import RGCxrClient', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: false,
      iosSdkDependencyMode: 'requested_but_unlinked',
      sdkLinkedReason: 'sdk_requested_callback_macro_but_RGCxrClient_unavailable',
      nativeAppVersion: '1.3.0',
      nativeBuildNumber: '153',
      authorizationState: 'not_authenticated',
      iosBleConnected: false,
      cxrCallbackApiEnabled: true,
      cxrNotifySubscriptionMode: 'setNotifyEventListenCmds',
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
      expect(screen.getByText('SDK 请求但未导入')).toBeTruthy();
      expect(screen.getByText('小巴健康 build: version=1.3.0 · build=153')).toBeTruthy();
      expect(screen.getByText('SDK linkage: sdkLinked=false · mode=requested_but_unlinked · reason=sdk_requested_callback_macro_but_RGCxrClient_unavailable')).toBeTruthy();
      expect(screen.getByText('CXR-L API: callbackApi=true · notify=setNotifyEventListenCmds')).toBeTruthy();
    });
  });

  it('shows CustomView payload and raw notify diagnostics for iOS open failures', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      cxrCallbackApiEnabled: true,
      cxrNotifySubscriptionMode: 'setNotifyEventListenCmds',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      lastCustomViewPayloadBytes: 944,
      lastCustomViewPayloadHash: 'fnv1a64:abc123',
      lastCustomViewPayloadShape: 'root=LinearLayout; props=backgroundColor,gravity; children=3:TextView,TextView,TextView',
      lastCustomViewRawNotify: 'Custom_View_Open_Failed reason=invalid_layout',
      lastCustomViewRawNotifyAt: '2026-06-19T06:31:55Z',
      lastCustomViewOpenError: 'Custom_View_Open_Failed reason=invalid_layout',
      lastCustomViewOpenCallbackSuccess: false,
      lastCustomViewOpenCallbackErrorCode: 'invalid_layout',
      lastCustomViewOpenCallbackAt: '2026-06-19T06:31:56Z',
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
      expect(screen.getByText('CXR-L API: callbackApi=true · notify=setNotifyEventListenCmds')).toBeTruthy();
      expect(screen.getByText('CustomView payload: bytes=944 · hash=fnv1a64:abc123')).toBeTruthy();
      expect(screen.getByText('CustomView shape: root=LinearLayout; props=backgroundColor,gravity; children=3:TextView,TextView,TextView')).toBeTruthy();
      expect(screen.getByText('CustomView raw: Custom_View_Open_Failed reason=invalid_layout · 2026-06-19T14:31:55+08:00')).toBeTruthy();
      expect(screen.getByText('CustomView error: Custom_View_Open_Failed reason=invalid_layout')).toBeTruthy();
      expect(screen.getByText('CustomView callback: success=false · errorCode=invalid_layout · 2026-06-19T14:31:56+08:00')).toBeTruthy();
    });
  });

  it('treats delayed iOS Rokid callback state as authorization success', async () => {
    mockGetRokidIntegrationStatus
      .mockResolvedValueOnce({
        platform: 'ios',
        bridgeAvailable: true,
        hiRokidInstalled: true,
        canOpenHiRokid: true,
        mode: 'sdk_probe',
        sdkLinked: true,
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
      })
      .mockResolvedValueOnce({
        platform: 'ios',
        bridgeAvailable: true,
        hiRokidInstalled: true,
        canOpenHiRokid: true,
        mode: 'sdk_probe',
        sdkLinked: true,
        authorizationState: 'not_authenticated',
        sessionMode: 'customView',
        customViewRunning: false,
        capabilitiesReady: false,
        callbackScheme: 'life.executor.health.rokid',
        lastCallbackUrl: 'life.executor.health.rokid://auth/callback?code=abc',
        lastCallbackHandled: true,
        sdkArtifacts: {
          clientM: 'com.rokid.cxr:client-m:1.2.2',
          clientL: 'com.rokid.cxr:client-l:1.0.3',
          iosClient: 'RGCxrClient:1.0.1',
          iosClientCandidate: 'RGCxrClient:1.0.2',
          iosCore: 'RGCoreKit:0.0.2',
        },
      })
      .mockResolvedValue({
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
        callbackScheme: 'life.executor.health.rokid',
        lastCallbackUrl: 'life.executor.health.rokid://auth/callback?code=abc',
        lastCallbackHandled: true,
        sdkArtifacts: {
          clientM: 'com.rokid.cxr:client-m:1.2.2',
          clientL: 'com.rokid.cxr:client-l:1.0.3',
          iosClient: 'RGCxrClient:1.0.1',
          iosClientCandidate: 'RGCxrClient:1.0.2',
          iosCore: 'RGCoreKit:0.0.2',
        },
      });
    mockRequestRokidAuthorization.mockResolvedValue({
      ok: false,
      reason: 'authorization_callback_pending',
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('授权 Rokid')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('授权 Rokid'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('Rokid 已授权')).toBeTruthy();
      expect(screen.queryByText(/Rokid 授权失败/)).toBeNull();
    });
    expect(mockGetRokidIntegrationStatus).toHaveBeenCalledTimes(3);
  });

  it('keeps iOS Rokid authorization timeout recoverable instead of showing a hard failure', async () => {
    const timeoutReason = 'Error Domain=RGCxrClientAuthError Code=-1 "鉴权请求超时" UserInfo={NSLocalizedDescription=鉴权请求超时}';
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticating',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      callbackScheme: 'cxrl',
      callbackUrl: 'cxrl://auth/callback',
      callbackSchemeSource: 'info_plist',
      acceptedCallbackSchemes: ['cxrl', 'life.executor.health.rokid'],
      lastAuthorizationError: timeoutReason,
      lastAuthorizationRequestAt: '2026-06-18T23:51:00Z',
      authorizationRequestTimeoutSeconds: 180,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    });
    mockRequestRokidAuthorization.mockResolvedValue({
      ok: false,
      reason: timeoutReason,
      authorizationState: 'authenticating',
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('授权 Rokid')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('授权 Rokid'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/等待 Rokid 授权回调/)).toBeTruthy();
      expect(screen.getByText(/最近授权错误: 鉴权请求超时/)).toBeTruthy();
      expect(screen.getByText('最近授权请求: 2026-06-19T07:51:00+08:00')).toBeTruthy();
      expect(screen.getByText(/SDK 等待窗口: 180 秒/)).toBeTruthy();
      expect(screen.queryByText(/Rokid 授权失败/)).toBeNull();
    });
  });

  it('shows native Rokid authorization attempt timeline for field debugging', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'not_authenticated',
      sessionMode: 'customView',
      customViewRunning: false,
      capabilitiesReady: false,
      callbackScheme: 'cxrl',
      callbackUrl: 'cxrl://auth/callback',
      callbackSchemeSource: 'info_plist',
      acceptedCallbackSchemes: ['cxrl', 'life.executor.health.rokid'],
      lastAuthorizationAttemptId: 'auth-3',
      authorizationAttemptCount: 3,
      lastAuthorizationPhase: 'authenticate_failed',
      lastAuthorizationDurationMs: 180012,
      lastAuthorizationStateBeforeReset: 'not_authenticated',
      lastAuthorizationStateAfterReset: 'not_authenticated',
      lastAuthorizationStateBeforeAuthenticate: 'not_authenticated',
      authorizationConfigSummary: 'server=rokidai://connect; callback=cxrl://auth/callback; timeout=180s',
      activeRecordType: 'reva_voice_command',
      audioStreamChunkCount: 3,
      audioStreamByteCount: 9600,
      lastAudioEventType: 'stream',
      lastAudioRecordType: 'reva_voice_command',
      lastAudioCodec: 0,
      lastAudioChannels: 1,
      lastAudioChunkBytes: 3200,
      lastAudioTimestamp: '123456789',
      lastAudioEventAt: '2026-06-19T00:02:02Z',
      authDiagnosticTimeline: [
        '2026-06-18T23:59:00Z #auth-3 request_started appName=Reva; scopes=device_control,audio_stream',
        '2026-06-18T23:59:01Z #auth-3 config_refreshed server=rokidai://connect; callback=cxrl://auth/callback; timeout=180s',
        '2026-06-19T00:02:01Z #auth-3 authenticate_failed Error Domain=RGCxrClientAuthError Code=-1',
      ],
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
      expect(screen.getByText('授权 attempt: auth-3 · #3 · phase=authenticate_failed · duration=180012ms')).toBeTruthy();
      expect(screen.getByText('SDK state: beforeReset=not_authenticated · afterReset=not_authenticated · beforeAuth=not_authenticated')).toBeTruthy();
      expect(screen.getByText('Auth config: server=rokidai://connect; callback=cxrl://auth/callback; timeout=180s')).toBeTruthy();
      expect(screen.getByText('Rokid audio: event=stream · active=reva_voice_command · type=reva_voice_command · chunks=3 · bytes=9600 · lastChunk=3200 · codec=0 · channels=1 · ts=123456789 · 2026-06-19T08:02:02+08:00')).toBeTruthy();
      expect(screen.getByText('Callback schemes: accepted=cxrl, life.executor.health.rokid · configured=cxrl · source=info_plist')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T08:02:01+08:00 #auth-3 authenticate_failed Error Domain=RGCxrClientAuthError Code=-1')).toBeTruthy();
    });
  });

  it('keeps CustomView open pending when BLE preflight is false but SDK has not rejected the command', async () => {
    const initialStatus = {
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
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
    } as const;
    mockGetRokidIntegrationStatus
      .mockResolvedValueOnce(initialStatus)
      .mockResolvedValueOnce({
        ...initialStatus,
        customViewPendingRetry: true,
        lastCustomViewAutoRetryAt: '2026-06-19T11:46:21Z',
        authDiagnosticTimeline: [
          '2026-06-19T11:46:18Z #auth-3 custom_view_ble_preflight connected=false; device=Glasses_0077; action=attempt_sdk_open',
          '2026-06-19T11:46:18Z #auth-3 custom_view_open_invoked bleConnected=false; runningAfterInvoke=false; waitingForRunningEvent=true',
          '2026-06-19T11:46:20Z #auth-3 custom_view_open_settled running=false; commandAccepted=true; rawNotify=none; openError=none',
          '2026-06-19T11:46:21Z #auth-3 custom_view_auto_retry trigger=ble_connected; device=Glasses_0077; bytes=944; hash=fnv1a64:24a216e694b6e683',
        ],
      });
    mockOpenRokidRevaCustomView.mockResolvedValue({
      ok: true,
      customViewCommandAccepted: true,
      customViewRunning: false,
      pendingSessionEvent: true,
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('打开小巴健康眼镜视图')).toBeTruthy();
      expect(screen.getByText('iOS BLE: connected=false · device=Glasses_0077')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开小巴健康眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('小巴健康眼镜视图已请求打开，等待眼镜端确认运行。请确认眼镜已显示后刷新。')).toBeTruthy();
      expect(screen.queryByText(/小巴健康眼镜视图失败/)).toBeNull();
      expect(screen.getByText('CustomView retry: pending=true · lastAutoRetry=2026-06-19T19:46:21+08:00')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:18+08:00 #auth-3 custom_view_ble_preflight connected=false; device=Glasses_0077; action=attempt_sdk_open')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:20+08:00 #auth-3 custom_view_open_settled running=false; commandAccepted=true; rawNotify=none; openError=none')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:21+08:00 #auth-3 custom_view_auto_retry trigger=ble_connected; device=Glasses_0077; bytes=944; hash=fnv1a64:24a216e694b6e683')).toBeTruthy();
    });
  });

  it('explains SDK CustomView failures with BLE preflight diagnostics', async () => {
    const initialStatus = {
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
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
    } as const;
    mockGetRokidIntegrationStatus
      .mockResolvedValueOnce(initialStatus)
      .mockResolvedValueOnce({
        ...initialStatus,
        lastCustomViewOpenError: 'rokid_glasses_ble_not_connected; open_callback_error_code=nil; device=Glasses_0077',
        lastCustomViewOpenCallbackSuccess: false,
        lastCustomViewOpenCallbackErrorCode: 'nil',
        lastCustomViewOpenCallbackAt: '2026-06-19T11:46:20Z',
        authDiagnosticTimeline: [
          '2026-06-19T11:46:18Z #auth-3 custom_view_ble_preflight connected=false; device=Glasses_0077; action=attempt_sdk_open',
          '2026-06-19T11:46:18Z #auth-3 custom_view_open_invoked bleConnected=false; runningAfterInvoke=false; waitingForRunningEvent=true',
          '2026-06-19T11:46:20Z #auth-3 custom_view_open_callback commandAccepted=false; errorCode=nil; running=false; bleConnected=false; device=Glasses_0077',
        ],
      });
    mockOpenRokidRevaCustomView.mockResolvedValue({
      ok: false,
      reason: 'rokid_glasses_ble_not_connected; open_callback_error_code=nil; device=Glasses_0077',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('打开小巴健康眼镜视图')).toBeTruthy();
      expect(screen.getByText('iOS BLE: connected=false · device=Glasses_0077')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开小巴健康眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      // BLE 未连不再是终态失败:显示"已排队、连上自动重发"的等待态(council 共识 P2)
      expect(screen.getByText(/已排队/)).toBeTruthy();
      expect(screen.getByText(/完全退出 Rokid AI \/ Hi Rokid/)).toBeTruthy();
      expect(screen.getByText('CustomView error: rokid_glasses_ble_not_connected; open_callback_error_code=nil; device=Glasses_0077')).toBeTruthy();
      expect(screen.getByText('CustomView callback: success=false · errorCode=nil · 2026-06-19T19:46:20+08:00')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:18+08:00 #auth-3 custom_view_ble_preflight connected=false; device=Glasses_0077; action=attempt_sdk_open')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:20+08:00 #auth-3 custom_view_open_callback commandAccepted=false; errorCode=nil; running=false; bleConnected=false; device=Glasses_0077')).toBeTruthy();
    });
  });

  it('does not blame BLE when a queued CustomView retry is already connected on refresh', async () => {
    const connectedStatus = {
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
      sessionMode: 'customView',
      customViewPendingRetry: true,
      customViewRunning: false,
      capabilitiesReady: false,
      sdkArtifacts: {
        clientM: 'com.rokid.cxr:client-m:1.2.2',
        clientL: 'com.rokid.cxr:client-l:1.0.3',
        iosClient: 'RGCxrClient:1.0.1',
        iosClientCandidate: 'RGCxrClient:1.0.2',
        iosCore: 'RGCoreKit:0.0.2',
      },
    } as const;
    mockGetRokidIntegrationStatus.mockResolvedValue(connectedStatus);
    mockOpenRokidRevaCustomView.mockResolvedValue({
      ok: false,
      reason: 'rokid_glasses_ble_not_connected; pending_retry_on_ble_connect; device=Glasses_0077',
      customViewPendingRetry: true,
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
    });

    const screen = renderWithProviders(<RokidHealthScreen />);

    await waitFor(() => {
      expect(screen.getByText('iOS BLE: connected=true · device=Glasses_0077')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开小巴健康眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/已排队, 但 SDK 尚未回报 CustomView 运行/)).toBeTruthy();
      expect(screen.queryByText(/眼镜蓝牙未连接,已排队/)).toBeNull();
    });
  });

  it('falls back to the mobile food camera when the iOS glasses BLE link is explicitly disconnected', async () => {
    mockGetRokidIntegrationStatus.mockResolvedValue({
      platform: 'ios',
      bridgeAvailable: true,
      hiRokidInstalled: true,
      canOpenHiRokid: true,
      mode: 'sdk_probe',
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: false,
      iosBleDeviceName: 'Glasses_0077',
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
      // council #1 R4: 用手机相机但仍走 Rokid 草稿流, 不再 router.push('/diet?capture=photo')(那条自动入库)
      expect(mockLaunchCamera).toHaveBeenCalled();
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith(expect.objectContaining({
        meta: expect.objectContaining({
          manual_confirm_required: true,
          capture_source: 'phone_camera_fallback',
        }),
      }));
      expect(mockPush).not.toHaveBeenCalledWith('/diet?capture=photo');
    });
  });
});
