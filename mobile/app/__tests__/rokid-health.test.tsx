/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockGetRokidIntegrationStatus = jest.fn();
const mockTakeRokidPhotoBase64 = jest.fn();
const mockRequestRokidAuthorization = jest.fn();
const mockOpenRokidRevaCustomView = jest.fn();
const mockGetRokidDeviceValidationSteps = jest.fn();
const mockListRokidGlanceCards = jest.fn();
const mockOpenRokidCompanionIfAvailable = jest.fn();
const mockSubmitRokidVisualInput = jest.fn();

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

jest.mock('../../modules/rokid-bridge', () => {
  const actual = jest.requireActual('../../modules/rokid-bridge');
  return {
    formatRokidLogTimestamp: actual.formatRokidLogTimestamp,
    getRokidIntegrationStatus: (...args: any[]) => mockGetRokidIntegrationStatus(...args),
    getRokidDeviceValidationSteps: (...args: any[]) => mockGetRokidDeviceValidationSteps(...args),
    openRokidRevaCustomView: (...args: any[]) => mockOpenRokidRevaCustomView(...args),
    requestRokidAuthorization: (...args: any[]) => mockRequestRokidAuthorization(...args),
    takeRokidPhotoBase64: (...args: any[]) => mockTakeRokidPhotoBase64(...args),
  };
});

jest.mock('../../services/rokidAmbient', () => ({
  listRokidGlanceCards: (...args: any[]) => mockListRokidGlanceCards(...args),
  openRokidCompanionIfAvailable: (...args: any[]) => mockOpenRokidCompanionIfAvailable(...args),
  submitRokidVisualInput: (...args: any[]) => mockSubmitRokidVisualInput(...args),
}));

import RokidHealthScreen from '../rokid-health';
import { renderWithProviders } from '../../test-utils';

const flushAsyncUpdates = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('RokidHealthScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
      imageUri: 'private://rokid/meal-001.jpg',
      imageSha256: 'sha256-meal-001',
    });
    mockRequestRokidAuthorization.mockResolvedValue({ ok: true, tokenLength: 24 });
    mockOpenRokidRevaCustomView.mockResolvedValue({
      ok: true,
      customViewRunning: true,
      capabilitiesReady: true,
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
        title: 'Rokid companion 已连接',
        detail: '在 Rokid AI / Hi Rokid 中确认眼镜已连接。',
        status: status?.hiRokidInstalled && status?.canOpenHiRokid ? 'done' : 'pending',
        actionLabel: '打开 Rokid AI / Hi Rokid',
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

  it('submits an explicit food photo capture as an ambient visual draft', async () => {
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
      expect(mockSubmitRokidVisualInput).toHaveBeenCalledWith({
        intent: 'food_scan',
        imageUri: 'private://rokid/meal-001.jpg',
        imageSha256: 'sha256-meal-001',
        privacyClass: 'health_l3',
        meta: {
          privacy_mode: 'workplace',
          source_surface: 'rokid_health_mode',
          raw_media_retained: false,
          manual_confirm_required: true,
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
      fireEvent.press(screen.getByText('打开 Reva 眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('Reva 眼镜视图失败: SDK 已接受打开命令，但眼镜端没有回报 CustomView 运行。请确认眼镜端是否显示 Reva；若未显示，请重新打开眼镜视图。')).toBeTruthy();
      expect(screen.queryByText('Reva 眼镜视图已打开')).toBeNull();
      expect(screen.queryByText('Reva 眼镜视图已运行')).toBeNull();
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
      expect(screen.getByText('Reva build: version=1.3.0 · build=153')).toBeTruthy();
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
      expect(screen.getByText('打开 Reva 眼镜视图')).toBeTruthy();
      expect(screen.getByText('iOS BLE: connected=false · device=Glasses_0077')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开 Reva 眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('Reva 眼镜视图已请求打开，等待眼镜端确认运行。请确认眼镜已显示后刷新。')).toBeTruthy();
      expect(screen.queryByText(/Reva 眼镜视图失败/)).toBeNull();
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
      expect(screen.getByText('打开 Reva 眼镜视图')).toBeTruthy();
      expect(screen.getByText('iOS BLE: connected=false · device=Glasses_0077')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('打开 Reva 眼镜视图'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/Reva 眼镜视图失败: 眼镜蓝牙链路未连接/)).toBeTruthy();
      expect(screen.getByText(/「完全退出」Rokid AI \/ Hi Rokid/)).toBeTruthy();
      expect(screen.getByText('CustomView error: rokid_glasses_ble_not_connected; open_callback_error_code=nil; device=Glasses_0077')).toBeTruthy();
      expect(screen.getByText('CustomView callback: success=false · errorCode=nil · 2026-06-19T19:46:20+08:00')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:18+08:00 #auth-3 custom_view_ble_preflight connected=false; device=Glasses_0077; action=attempt_sdk_open')).toBeTruthy();
      expect(screen.getByText('Native: 2026-06-19T19:46:20+08:00 #auth-3 custom_view_open_callback commandAccepted=false; errorCode=nil; running=false; bleConnected=false; device=Glasses_0077')).toBeTruthy();
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
