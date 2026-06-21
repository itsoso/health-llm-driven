/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockCloseRokidCustomView = jest.fn();
const mockOpenRokidCustomView = jest.fn();
const mockUpdateRokidCustomView = jest.fn();
const mockOpenRokidApp = jest.fn();
const mockQueryRokidApp = jest.fn();
const mockInstallBundledRokidApp = jest.fn();
const mockInstallRokidAppFromFileUri = jest.fn();
const mockStopRokidApp = jest.fn();
const mockCreateRokidPushupSession = jest.fn();
const mockFinishRokidPushupSession = jest.fn();
const mockListRokidPushupEvents = jest.fn();
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
  openRokidApp: (...args: any[]) => mockOpenRokidApp(...args),
  queryRokidApp: (...args: any[]) => mockQueryRokidApp(...args),
  installBundledRokidApp: (...args: any[]) => mockInstallBundledRokidApp(...args),
  installRokidAppFromFileUri: (...args: any[]) => mockInstallRokidAppFromFileUri(...args),
  stopRokidApp: (...args: any[]) => mockStopRokidApp(...args),
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
    mockListRokidPushupEvents.mockResolvedValue([]);
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
    mockQueryRokidApp.mockResolvedValue({
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
      expect(screen.getByText(/完全退出 Reva/)).toBeTruthy();
    });
  });
});
