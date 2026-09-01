/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockCloseRokidCustomView = jest.fn();
const mockOpenRokidCustomView = jest.fn();
const mockUpdateRokidCustomView = jest.fn();
const mockPrepareRokidCustomAppSession = jest.fn();
const mockOpenRokidApp = jest.fn();
const mockQueryRokidApp = jest.fn();
const mockInstallBundledRokidApp = jest.fn();
const mockInstallRokidAppFromFileUri = jest.fn();
const mockStopRokidApp = jest.fn();
const mockGetRokidIntegrationStatus = jest.fn();
const mockCreateRokidPushupSession = jest.fn();
const mockFinishRokidPushupSession = jest.fn();
const mockListRokidPushupEvents = jest.fn();
const mockGetRokidPushupSessionReview = jest.fn();
const mockPost = jest.fn();
const mockInvalidateRecordMutation = jest.fn();
const mockGetDocumentAsync = jest.fn();
const mockCreateDownloadResumable = jest.fn();
const mockDownloadResumableDownloadAsync = jest.fn();
const mockGetInfoAsync = jest.fn();
const mockSetClipboardStringAsync = jest.fn();

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack }),
  useFocusEffect: jest.fn(),
}));

jest.mock('expo-haptics', () => ({
  ImpactFeedbackStyle: { Light: 'Light', Medium: 'Medium' },
  impactAsync: jest.fn(),
}));

jest.mock('../../modules/rokid-bridge', () => ({
  closeRokidCustomView: (...args: any[]) => mockCloseRokidCustomView(...args),
  openRokidCustomView: (...args: any[]) => mockOpenRokidCustomView(...args),
  updateRokidCustomView: (...args: any[]) => mockUpdateRokidCustomView(...args),
  prepareRokidCustomAppSession: (...args: any[]) => mockPrepareRokidCustomAppSession(...args),
  openRokidApp: (...args: any[]) => mockOpenRokidApp(...args),
  queryRokidApp: (...args: any[]) => mockQueryRokidApp(...args),
  installBundledRokidApp: (...args: any[]) => mockInstallBundledRokidApp(...args),
  installRokidAppFromFileUri: (...args: any[]) => mockInstallRokidAppFromFileUri(...args),
  stopRokidApp: (...args: any[]) => mockStopRokidApp(...args),
  getRokidIntegrationStatus: (...args: any[]) => mockGetRokidIntegrationStatus(...args),
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: (...args: any[]) => mockGetDocumentAsync(...args),
}));

jest.mock('expo-file-system/legacy', () => ({
  cacheDirectory: 'file://cache/',
  createDownloadResumable: (...args: any[]) => mockCreateDownloadResumable(...args),
  getInfoAsync: (...args: any[]) => mockGetInfoAsync(...args),
}));

jest.mock('expo-clipboard', () => ({
  setStringAsync: (...args: any[]) => mockSetClipboardStringAsync(...args),
}));

jest.mock('../../services/rokidPushupSession', () => {
  const actual = jest.requireActual('../../services/rokidPushupSession');
  return {
    ...actual,
    ROKID_PUSHUP_APP_ACTIVITY: '.MainActivity',
    ROKID_PUSHUP_APP_PACKAGE: 'life.executor.health.rokid.pushup',
    createRokidPushupSession: (...args: any[]) => mockCreateRokidPushupSession(...args),
    finishRokidPushupSession: (...args: any[]) => mockFinishRokidPushupSession(...args),
    listRokidPushupEvents: (...args: any[]) => mockListRokidPushupEvents(...args),
    getRokidPushupSessionReview: (...args: any[]) => mockGetRokidPushupSessionReview(...args),
  };
});

jest.mock('../../services/api', () => ({
  post: (...args: any[]) => mockPost(...args),
}));

jest.mock('../../applib/queryKeys', () => ({
  invalidateRecordMutation: (...args: any[]) => mockInvalidateRecordMutation(...args),
}));

import RokidPushupCoachScreen, { __resetRokidPushupInstallStateForTests } from '../rokid-pushup-coach';
import { renderWithProviders } from '../../test-utils';

const flushAsyncUpdates = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('RokidPushupCoachScreen', () => {
  beforeEach(() => {
    __resetRokidPushupInstallStateForTests();
    jest.clearAllMocks();
    mockOpenRokidCustomView.mockResolvedValue({ ok: true });
    mockUpdateRokidCustomView.mockResolvedValue({ ok: true });
    mockCloseRokidCustomView.mockResolvedValue({ ok: true });
    mockPrepareRokidCustomAppSession.mockResolvedValue({ ok: true, cxrInitializationMode: 'customApp' });
    mockCreateRokidPushupSession.mockResolvedValue({
      id: 7,
      target_reps: 20,
      open_url: 'reva://rokid/pushup?session_id=7',
      ingest_url: 'https://health.executor.life/api/v1/devices/rokid/pushup-sessions/7/events',
    });
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockInstallBundledRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockInstallRokidAppFromFileUri.mockResolvedValue({ ok: true, installed: true });
    mockOpenRokidApp.mockResolvedValue({ ok: true, opened: true });
    mockStopRokidApp.mockResolvedValue({ ok: true, stopped: true });
    mockGetRokidIntegrationStatus.mockResolvedValue({
      nativeBuildNumber: '179',
      nativeAppVersion: '1.3.0',
      sdkLinked: true,
      cxrInitializationMode: 'customApp',
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
    });
    mockListRokidPushupEvents.mockResolvedValue([]);
    mockGetRokidPushupSessionReview.mockResolvedValue({
      session_id: 7,
      session_quality: { reps: 5, avg_quality_score: 88, event_count: 5 },
      training_context: null,
      observations: ['节奏稳定。'],
      teaching_links: [],
      guidance_alerts: [],
      disclaimer: '仅供参考。',
    });
    mockPost.mockResolvedValue({ data: { id: 123 } });
    mockInvalidateRecordMutation.mockResolvedValue(undefined);
    mockCreateDownloadResumable.mockImplementation((_url, _target, _options, onProgress) => ({
      downloadAsync: () => {
        onProgress?.({
          totalBytesWritten: 94513327,
          totalBytesExpectedToWrite: 94513327,
        });
        return mockDownloadResumableDownloadAsync();
      },
    }));
    mockDownloadResumableDownloadAsync.mockResolvedValue({ status: 200, uri: 'file://cache/rokid-pushup-glasses.apk' });
    mockGetInfoAsync.mockResolvedValue({ exists: true, uri: 'file://cache/rokid-pushup-glasses.apk', size: 94513327 });
    mockGetDocumentAsync.mockResolvedValue({ canceled: true, assets: [] });
    mockSetClipboardStringAsync.mockResolvedValue(undefined);
  });

  it('installs the bundled glasses APK before starting real pose recognition when the app is missing', async () => {
    mockQueryRokidApp.mockReset();
    mockQueryRokidApp
      .mockResolvedValueOnce({ ok: true, installed: false })
      .mockResolvedValueOnce({ ok: true, installed: true });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockPrepareRokidCustomAppSession).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
      expect(mockInstallBundledRokidApp).toHaveBeenCalledWith({
        resourceName: 'rokid-pushup-glasses',
        resourceExtension: 'apk',
        packageName: 'life.executor.health.rokid.pushup',
      });
      expect(mockOpenRokidApp).toHaveBeenCalledWith({
        packageName: 'life.executor.health.rokid.pushup',
        activityName: '.MainActivity',
        url: 'reva://rokid/pushup?session_id=7',
      });
      expect(screen.getByText('眼镜端识别已启动, 等待姿态数据...')).toBeTruthy();
    });

    expect(mockPrepareRokidCustomAppSession.mock.invocationCallOrder[0]).toBeLessThan(
      mockQueryRokidApp.mock.invocationCallOrder[0],
    );
    expect(mockQueryRokidApp).toHaveBeenCalledTimes(2);
  });

  it('polls glasses reps, saves the exercise record, and stops the real session', async () => {
    mockListRokidPushupEvents
      .mockResolvedValueOnce([
        {
          id: 11,
          session_id: 7,
          user_id: 3,
          event_type: 'rep',
          reps: 5,
          phase: 'up',
          quality_score: 88,
          payload: { suggestion: '保持稳定节奏。' },
          occurred_at: '2026-06-19T12:00:00Z',
          created_at: '2026-06-19T12:00:00Z',
        },
      ])
      .mockResolvedValue([]);

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockOpenRokidApp).toHaveBeenCalledWith({
        packageName: 'life.executor.health.rokid.pushup',
        activityName: '.MainActivity',
        url: 'reva://rokid/pushup?session_id=7',
      });
      expect(screen.getByText('已接收 1 条眼镜姿态事件')).toBeTruthy();
      expect(screen.getByText('5')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('保存本组'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/daily-health/exercise', expect.objectContaining({
        exercise_type: '俯卧撑',
        reps: 5,
        sets: 1,
        intensity: 'moderate',
        notes: expect.stringContaining('Rokid 俯卧撑计数: 5/20'),
      }));
      expect(screen.getByText('已保存')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('停止'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockFinishRokidPushupSession).toHaveBeenCalledWith(7);
      expect(mockStopRokidApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
      expect(screen.getByText('眼镜端识别已停止')).toBeTruthy();
    });
  });

  it('surfaces glasses session_state events during real pushup polling', async () => {
    mockListRokidPushupEvents
      .mockResolvedValueOnce([
        {
          id: 12,
          session_id: 7,
          user_id: 3,
          event_type: 'session_state',
          reps: null,
          phase: null,
          payload: {
            state: 'camera_status',
            message: '相机已启动',
            detail: 'back_camera',
          },
          occurred_at: '2026-06-19T12:00:00Z',
          created_at: '2026-06-19T12:00:00Z',
        },
      ])
      .mockResolvedValue([]);

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('眼镜端状态: 相机已启动 · back_camera')).toBeTruthy();
    });
  });

  it('does not claim "已停止" when stopRokidApp is rejected (council R3: no fake success)', async () => {
    // 原生 stopApp 被拒时是 resolve {ok:false}(不抛)。旧代码不检查 ok → 即便被拒也显"已停止"。
    mockListRokidPushupEvents.mockResolvedValue([]);
    mockStopRokidApp.mockResolvedValue({ ok: false, reason: 'rokid_app_stop_rejected' });
    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });
    await waitFor(() => {
      expect(mockOpenRokidApp).toHaveBeenCalled();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('停止'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockStopRokidApp).toHaveBeenCalledWith('life.executor.health.rokid.pushup');
      // 不假装成功:停止被拒 → 不得显"已停止",应落失败态并暴露原因
      expect(screen.queryByText('眼镜端识别已停止')).toBeNull();
      expect(screen.getByText(/rokid_app_stop_rejected|rokid_pushup_app_stop_failed/)).toBeTruthy();
    });
  });

  it('keeps local counting and saving available when the public APK download fails', async () => {
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: false });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });
    mockDownloadResumableDownloadAsync.mockRejectedValue(new Error('download failed'));
    mockGetDocumentAsync.mockResolvedValue({ canceled: true, assets: [] });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/眼镜端 App 下载失败/)).toBeTruthy();
      expect(screen.getAllByText(/本地计数/).length).toBeGreaterThan(0);
    });
    expect(mockGetDocumentAsync).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.press(screen.getByText('+1 校准'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText('1')).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('保存本组'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/daily-health/exercise', expect.objectContaining({
        exercise_type: '俯卧撑',
        reps: 1,
        sets: 1,
      }));
      expect(screen.getByText('已保存')).toBeTruthy();
    });
  });

  it('downloads the public APK when the bundled resource is missing without opening the picker', async () => {
    mockQueryRokidApp.mockReset();
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });
    mockDownloadResumableDownloadAsync.mockResolvedValue({ status: 200, uri: 'file://cache/rokid-pushup-glasses.apk' });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('安装/更新眼镜端 App'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockCreateDownloadResumable).toHaveBeenCalledWith(
        'https://health.executor.life/rokid-pushup-glasses.apk',
        'file://cache/rokid-pushup-glasses.apk',
        {},
        expect.any(Function),
      );
      expect(mockInstallRokidAppFromFileUri).toHaveBeenCalledWith({
        fileUri: 'file://cache/rokid-pushup-glasses.apk',
        packageName: 'life.executor.health.rokid.pushup',
      });
      expect(screen.getByText('眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)')).toBeTruthy();
    });
    expect(mockGetDocumentAsync).not.toHaveBeenCalled();
  });

  it('retries the public APK download after a transient iOS TLS failure', async () => {
    mockQueryRokidApp.mockReset();
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });
    let downloadAttempts = 0;
    mockCreateDownloadResumable.mockImplementation((_url, _target, _options, onProgress) => ({
      downloadAsync: () => {
        downloadAttempts += 1;
        if (downloadAttempts === 1) {
          onProgress?.({
            totalBytesWritten: 76251100,
            totalBytesExpectedToWrite: 94513327,
          });
          return Promise.reject(new Error('Unable to download file: Error Domain=NSURLErrorDomain Code=-1200 "TLS错误导致安全连接失败。"'));
        }
        onProgress?.({
          totalBytesWritten: 94513327,
          totalBytesExpectedToWrite: 94513327,
        });
        return Promise.resolve({ status: 200, uri: 'file://cache/rokid-pushup-glasses.apk' });
      },
    }));

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('安装/更新眼镜端 App'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockCreateDownloadResumable).toHaveBeenCalledTimes(2);
      expect(screen.getByText(/download_retry attempt=2\/3/)).toBeTruthy();
      expect(mockInstallRokidAppFromFileUri).toHaveBeenCalledWith({
        fileUri: 'file://cache/rokid-pushup-glasses.apk',
        packageName: 'life.executor.health.rokid.pushup',
      });
      expect(screen.getByText('眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)')).toBeTruthy();
    });
  });

  it('logs install heartbeat while the native APK transfer is still pending', async () => {
    jest.useFakeTimers();
    let resolveInstall: ((result: { ok: boolean; installed: boolean }) => void) | undefined;
    try {
      mockQueryRokidApp.mockReset();
      mockQueryRokidApp.mockResolvedValue({ ok: true, installed: true });
      mockInstallBundledRokidApp.mockResolvedValue({
        ok: false,
        reason: 'rokid_apk_resource_missing',
      });
      mockInstallRokidAppFromFileUri.mockReturnValue(new Promise((resolve) => {
        resolveInstall = resolve;
      }));

      const screen = renderWithProviders(<RokidPushupCoachScreen />);

      await act(async () => {
        fireEvent.press(screen.getByText('安装/更新眼镜端 App'));
        await Promise.resolve();
        await Promise.resolve();
      });

      await act(async () => {
        jest.advanceTimersByTime(30_000);
        await Promise.resolve();
      });

      expect(screen.getByText(/install_file_uri_pending/)).toBeTruthy();
      expect(screen.getByText(/native_status phase=before_file_install/)).toBeTruthy();

      await act(async () => {
        resolveInstall?.({ ok: true, installed: true });
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(screen.getByText('眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)')).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it('shows and copies install diagnostics across download, install, and confirmation phases', async () => {
    mockQueryRokidApp.mockReset();
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: true });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('安装/更新眼镜端 App'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/安装诊断/)).toBeTruthy();
      expect(screen.getByText(/download_start/)).toBeTruthy();
      expect(screen.getByText(/download_complete/)).toBeTruthy();
      expect(screen.getByText(/install_file_uri_result/)).toBeTruthy();
      expect(screen.getByText(/query_app_attempt/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.press(screen.getByText('复制安装日志'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockSetClipboardStringAsync).toHaveBeenCalledWith(expect.stringContaining('download_start'));
      expect(mockSetClipboardStringAsync).toHaveBeenCalledWith(expect.stringContaining('install_file_uri_result'));
    });
  });

  it('opens the file picker only from the manual APK install action', async () => {
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: false });
    mockGetDocumentAsync.mockResolvedValue({ canceled: true, assets: [] });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('手动选择 APK 安装'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockGetDocumentAsync).toHaveBeenCalledWith({
        copyToCacheDirectory: true,
        multiple: false,
        type: [
          'application/vnd.android.package-archive',
          'application/octet-stream',
          'public.data',
        ],
      });
      expect(screen.getByText(/rokid_apk_picker_cancelled/)).toBeTruthy();
    });
  });

  it('surfaces public APK download failures instead of replacing them with picker cancellation', async () => {
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: false });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });
    mockDownloadResumableDownloadAsync.mockResolvedValue({ status: 404, uri: 'file://cache/rokid-pushup-glasses.apk' });
    mockGetDocumentAsync.mockResolvedValue({ canceled: true, assets: [] });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('安装/更新眼镜端 App'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getAllByText(/rokid_apk_download_http_404/).length).toBeGreaterThan(0);
    });
    expect(mockGetDocumentAsync).not.toHaveBeenCalled();
  });

  it('explains when the Rokid SDK is already locked into the wrong CXR session mode', async () => {
    mockPrepareRokidCustomAppSession.mockResolvedValue({
      ok: false,
      installed: false,
      reason: 'rokid_cxrl_wrong_session_mode',
      cxrInitializationMode: 'customView',
      relaunchRequired: true,
    });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('启动眼镜识别'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/Rokid CXR-L 当前已在 customView 会话/)).toBeTruthy();
      expect(screen.getByText(/完全退出小巴/)).toBeTruthy();
      expect(screen.getByText(/不要先打开小巴健康眼镜视图/)).toBeTruthy();
      expect(screen.queryByText(/完全退出 Reva/)).toBeNull();
    });
    expect(mockQueryRokidApp).not.toHaveBeenCalled();
    expect(mockInstallBundledRokidApp).not.toHaveBeenCalled();
    expect(mockCreateDownloadResumable).not.toHaveBeenCalled();
  });

  it('preserves background download diagnostics after leaving the page and distinguishes install failure from download failure', async () => {
    let progressHandler: ((progress: {
      totalBytesWritten: number;
      totalBytesExpectedToWrite: number;
    }) => void) | undefined;
    let resolveDownload: ((result: { status: number; uri: string }) => void) | undefined;

    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: false });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });
    mockInstallRokidAppFromFileUri.mockResolvedValue({
      ok: false,
      installed: false,
      reason: 'rokid_app_install_rejected',
      cxrInitializationMode: 'customApp',
      iosBleConnected: true,
    });
    mockCreateDownloadResumable.mockImplementation((_url, _target, _options, onProgress) => {
      progressHandler = onProgress;
      return {
        downloadAsync: () => new Promise((resolve) => {
          resolveDownload = resolve;
        }),
      };
    });

    const firstScreen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(firstScreen.getByText('安装/更新眼镜端 App'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(mockCreateDownloadResumable).toHaveBeenCalled();
    });

    firstScreen.unmount();

    await act(async () => {
      progressHandler?.({
        totalBytesWritten: 72 * 1024 * 1024,
        totalBytesExpectedToWrite: 94513327,
      });
      resolveDownload?.({ status: 200, uri: 'file://cache/rokid-pushup-glasses.apk' });
      await flushAsyncUpdates();
    });

    const secondScreen = renderWithProviders(<RokidPushupCoachScreen />);

    await waitFor(() => {
      expect(secondScreen.getByText(/下载已完成，但安装到眼镜失败/)).toBeTruthy();
      expect(secondScreen.getByText(/download_complete/)).toBeTruthy();
      expect(secondScreen.getByText(/install_file_uri_result/)).toBeTruthy();
      expect(secondScreen.queryByText(/眼镜端 App 下载失败/)).toBeNull();
    });
  });

  it('ignores a stale post-save review response and a late response after unmount (#10)', async () => {
    // Reach a running real session with reps so 保存本组 triggers the review fetch.
    mockListRokidPushupEvents
      .mockResolvedValueOnce([
        {
          id: 11,
          session_id: 7,
          user_id: 3,
          event_type: 'rep',
          reps: 5,
          phase: 'up',
          quality_score: 88,
          payload: { suggestion: '保持稳定节奏。' },
          occurred_at: '2026-06-19T12:00:00Z',
          created_at: '2026-06-19T12:00:00Z',
        },
      ])
      .mockResolvedValue([]);

    // Each review fetch returns a controllable deferred so we can resolve out of order.
    const deferreds: { resolve: (v: any) => void }[] = [];
    mockGetRokidPushupSessionReview.mockReset();
    mockGetRokidPushupSessionReview.mockImplementation(
      () => new Promise((resolve) => deferreds.push({ resolve })),
    );

    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      const screen = renderWithProviders(<RokidPushupCoachScreen />);

      await act(async () => {
        fireEvent.press(screen.getByText('启动眼镜识别'));
        await flushAsyncUpdates();
      });
      await waitFor(() => {
        expect(screen.getByText('5')).toBeTruthy();
      });

      // First save → review fetch #1 (deferred, in-flight).
      await act(async () => {
        fireEvent.press(screen.getByText('保存本组'));
        await flushAsyncUpdates();
      });
      // Second save → review fetch #2 supersedes #1.
      await act(async () => {
        fireEvent.press(screen.getByText('已保存'));
        await flushAsyncUpdates();
      });

      expect(deferreds.length).toBe(2);

      // Resolve the STALE first fetch last — its content must be dropped (reqId mismatch).
      await act(async () => {
        deferreds[0].resolve({
          session_id: 7,
          session_quality: { reps: 5, avg_quality_score: 88, event_count: 5 },
          training_context: null,
          observations: ['STALE 不该出现的复盘'],
          teaching_links: [],
          guidance_alerts: [],
          disclaimer: '仅供参考。',
        });
        await flushAsyncUpdates();
      });
      expect(screen.queryByText(/STALE 不该出现的复盘/)).toBeNull();

      // Unmount, then resolve the latest fetch — late response must not setState on a
      // gone component (no console.error about unmounted updates).
      screen.unmount();
      await act(async () => {
        deferreds[1].resolve({
          session_id: 7,
          session_quality: { reps: 5, avg_quality_score: 88, event_count: 5 },
          training_context: null,
          observations: ['LATE 卸载后不该 setState'],
          teaching_links: [],
          guidance_alerts: [],
          disclaimer: '仅供参考。',
        });
        await flushAsyncUpdates();
      });

      const unmountedSetState = errorSpy.mock.calls.find((args) =>
        String(args[0]).includes("can't perform a React state update on an unmounted"),
      );
      expect(unmountedSetState).toBeUndefined();
    } finally {
      errorSpy.mockRestore();
    }
  });

  it('infers install rejection when old native bridge returns installed=false without a reason', async () => {
    mockQueryRokidApp.mockResolvedValue({ ok: true, installed: false });
    mockInstallBundledRokidApp.mockResolvedValue({
      ok: false,
      reason: 'rokid_apk_resource_missing',
    });
    mockInstallRokidAppFromFileUri.mockResolvedValue({
      ok: false,
      installed: false,
      apkFileName: 'rokid-pushup-glasses.apk',
      byteLength: 94513327,
    });
    mockGetRokidIntegrationStatus.mockResolvedValue({
      nativeBuildNumber: '176',
      nativeAppVersion: '1.3.0',
      sdkLinked: true,
      cxrInitializationMode: 'customView',
      authorizationState: 'authenticated',
      iosBleConnected: true,
      iosBleDeviceName: 'Glasses_0077',
    });

    const screen = renderWithProviders(<RokidPushupCoachScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('安装/更新眼镜端 App'));
      await flushAsyncUpdates();
    });

    await waitFor(() => {
      expect(screen.getByText(/下载已完成，但安装到眼镜失败/)).toBeTruthy();
      expect(screen.getByText(/rokid_app_install_rejected_without_reason/)).toBeTruthy();
      expect(screen.getByText(/native_status phase=after_file_install_failure/)).toBeTruthy();
      expect(screen.getAllByText(/nativeBuild=176/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/requiredBuild>=179/).length).toBeGreaterThan(0);
    });
  });
});
