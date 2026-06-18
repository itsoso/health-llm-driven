/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
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
  useRouter: () => ({ back: mockBack }),
}));

jest.mock('../../modules/rokid-bridge', () => ({
  getRokidIntegrationStatus: (...args: any[]) => mockGetRokidIntegrationStatus(...args),
  getRokidDeviceValidationSteps: (...args: any[]) => mockGetRokidDeviceValidationSteps(...args),
  openRokidRevaCustomView: (...args: any[]) => mockOpenRokidRevaCustomView(...args),
  requestRokidAuthorization: (...args: any[]) => mockRequestRokidAuthorization(...args),
  takeRokidPhotoBase64: (...args: any[]) => mockTakeRokidPhotoBase64(...args),
}));

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
