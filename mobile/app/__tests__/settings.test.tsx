/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockLogout = jest.fn();
const mockRequestAccountDeletion = jest.fn();
const mockGetAccountDeletionRequest = jest.fn();
const mockCheckNow = jest.fn();
const mockApiPost = jest.fn();
const mockInvalidateQueries = jest.fn();
let mockGarminStatus: any = { health: 'healthy', minutes_since_last_sync: 3 };
let mockProfile: any = {
  use_manual_location: false,
  detected_location: { city: '杭州', region: '浙江' },
};

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush, canGoBack: () => false }),
  useFocusEffect: (callback: () => void) => callback(),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    if (key.includes('profile')) {
      return { data: mockProfile };
    }
    if (key.includes('garminStatus')) {
      return { data: mockGarminStatus, refetch: jest.fn() };
    }
    return { data: null, refetch: jest.fn() };
  },
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium', Light: 'light' },
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    logout: mockLogout,
    user: { username: 'Suntice', email: 'itsoso@126.com' },
    isAuthenticated: true,
  }),
}));

jest.mock('../../hooks/useBiometricLock', () => ({
  useBiometricLock: () => ({
    isEnabled: false,
    isSupported: false,
    toggleEnabled: jest.fn(),
  }),
}));

jest.mock('../../hooks/useAppUpdate', () => ({
  useAppUpdate: () => ({
    status: 'idle',
    error: null,
    checkNow: mockCheckNow,
    applyUpdate: jest.fn(),
    dismiss: jest.fn(),
  }),
}));

jest.mock('expo-constants', () => ({
  __esModule: true,
  default: {
    nativeAppVersion: '1.4.0',
    nativeBuildVersion: '231',
  },
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#000',
      bgCard: '#1C1C1E',
      fill: '#333',
      labelPrimary: '#fff',
      labelSecondary: '#aaa',
      labelTertiary: '#777',
      labelQuaternary: '#48484A',
      separator: '#333',
      brand: '#0A8F8F',
      brandLight: '#123',
    },
    // 走真实 semanticColors, 避免 mock 漏键 (Garmin 状态点 / 登出红用 s.{tone}.solid)
    s: jest.requireActual('../../constants/theme').semanticColors,
  }),
}));

jest.mock('../../components/AppleHealthRow', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const MockAppleHealthRow = () => <Text>Apple Health</Text>;
  MockAppleHealthRow.displayName = 'MockAppleHealthRow';
  return { AppleHealthRow: MockAppleHealthRow };
});

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: (...args: unknown[]) => mockApiPost(...args),
  },
}));

jest.mock('../../services/auth', () => ({
  requestAccountDeletion: (...args: unknown[]) => mockRequestAccountDeletion(...args),
  getAccountDeletionRequest: (...args: unknown[]) => mockGetAccountDeletionRequest(...args),
  authLogoutErrorCode: (error: unknown) => (
    (error as { code?: string } | null)?.code ?? null
  ),
}));

import SettingsScreen from '../settings';

describe('SettingsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGarminStatus = { health: 'healthy', minutes_since_last_sync: 3 };
    mockProfile = {
      use_manual_location: false,
      detected_location: { city: '杭州', region: '浙江' },
    };
    mockRequestAccountDeletion.mockResolvedValue({
      status: 'requested',
      request_id: 42,
      estimated_completion_days: 7,
      requested_at: '2026-06-28T00:00:00Z',
    });
    mockGetAccountDeletionRequest.mockResolvedValue({ status: 'none' });
    mockCheckNow.mockResolvedValue('current');
    mockLogout.mockResolvedValue(undefined);
  });

  it('surfaces GPS and city positioning as one explicit clickable entry', () => {
    const { getByText } = render(<SettingsScreen />);

    expect(getByText('GPS / 城市定位')).toBeTruthy();
    expect(getByText('杭州')).toBeTruthy();
    expect(getByText('GPS 自动')).toBeTruthy();
    expect(getByText('用于天气 / 空气质量 / 户外建议')).toBeTruthy();
    expect(() => getByText('定位设置')).toThrow();
    fireEvent.press(getByText('GPS / 城市定位'));

    expect(mockPush).toHaveBeenCalledWith('/location');
  });

  it('uses the manual city only while manual location is enabled', () => {
    mockProfile = {
      use_manual_location: true,
      manual_location: { city: '上海', region: null },
      detected_location: { city: '杭州', region: '浙江' },
    };

    const { getByText, queryByText } = render(<SettingsScreen />);

    expect(getByText('上海')).toBeTruthy();
    expect(queryByText('杭州')).toBeNull();
    expect(getByText('手动城市')).toBeTruthy();
  });

  it('falls back to the detected region only when the detected city is missing', () => {
    mockProfile = {
      use_manual_location: false,
      detected_location: { city: null, region: '浙江省' },
    };

    const { getByText } = render(<SettingsScreen />);

    expect(getByText('浙江')).toBeTruthy();
  });

  it('refreshes the cached profile whenever settings gains focus', () => {
    render(<SettingsScreen />);

    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['profile'] });
  });

  it('hides deferred native and experimental entries in the App Store production UI', () => {
    const { queryByText } = render(<SettingsScreen />);

    expect(queryByText('Siri 语音记录')).toBeNull();
    expect(queryByText('Rokid 眼镜健康模式')).toBeNull();
    expect(queryByText('Rokid 俯卧撑计数')).toBeNull();
    expect(queryByText('Rokid 自检')).toBeNull();
    expect(queryByText('高级与实验')).toBeNull();
    expect(queryByText('AI 模型')).toBeNull();
  });

  it('opens one health analysis hub instead of scattering analysis rows in settings', () => {
    const { getByText, queryByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('健康分析'));

    expect(mockPush).toHaveBeenCalledWith('/insights');
    expect(queryByText('我的进度')).toBeNull();
    expect(queryByText('代谢健康画像')).toBeNull();
    expect(queryByText('生物年龄')).toBeNull();
    expect(queryByText('抗衰下一步')).toBeNull();
    expect(queryByText('肝脏趋势')).toBeNull();
  });

  it('opens the privacy policy instead of rendering a dead row', () => {
    const { getByRole } = render(<SettingsScreen />);

    fireEvent.press(getByRole('button', { name: '隐私政策' }));

    expect(mockPush).toHaveBeenCalledWith('/privacy-policy');
  });

  it('exposes privacy and deletion rows as named accessibility buttons', () => {
    const { getByRole } = render(<SettingsScreen />);

    expect(getByRole('button', { name: '隐私政策' })).toBeTruthy();
    expect(getByRole('button', { name: '删除账号与数据' })).toBeTruthy();
  });

  it('opens account security for password management', () => {
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('账号安全'));

    expect(mockPush).toHaveBeenCalledWith('/account-security');
  });

  it('explains that the user remains signed in when the logout barrier fails', async () => {
    mockLogout.mockRejectedValueOnce({ code: 'LOGOUT_BARRIER_FAILED' });
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, _message, buttons) => {
      if (title === '退出登录') {
        void buttons?.find((button) => button.style === 'destructive')?.onPress?.();
      }
    });
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('退出登录'));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith(
      '退出失败',
      expect.stringContaining('仍保持登录'),
    ));
    alertSpy.mockRestore();
  });

  it('explains that logout is safe when only residue cleanup remains', async () => {
    mockLogout.mockRejectedValueOnce({ code: 'LOGOUT_CLEANUP_INCOMPLETE' });
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, _message, buttons) => {
      if (title === '退出登录') {
        void buttons?.find((button) => button.style === 'destructive')?.onPress?.();
      }
    });
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('退出登录'));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith(
      '已安全退出',
      expect.stringContaining('清理'),
    ));
    alertSpy.mockRestore();
  });

  it('lets the user request account deletion from the app', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation((title, message, buttons) => {
      if (title === '删除账号与数据') {
        buttons?.find((button) => button.style === 'destructive')?.onPress?.();
      }
    });
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('删除账号与数据'));

    await waitFor(() => expect(mockRequestAccountDeletion).toHaveBeenCalledTimes(1));
    expect(mockLogout).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalledWith(
      '删除请求已提交',
      expect.stringContaining('7 天'),
      expect.any(Array),
    );
    alertSpy.mockRestore();
  });

  it('does not show negative Garmin sync age when server time is ahead', () => {
    mockGarminStatus = {
      bound: true,
      health: 'healthy',
      last_sync_at: '2026-06-23T12:50:00+08:00',
      minutes_since_last_sync: -471,
    };

    const { getByText, queryByText } = render(<SettingsScreen />);

    expect(queryByText('-471 分钟前')).toBeNull();
    expect(getByText('刚刚同步')).toBeTruthy();
  });

  it('opens Garmin recovery instead of starting a blind sync from settings', () => {
    mockGarminStatus = {
      bound: true,
      health: 'error',
      credentials_valid: false,
      requires_mfa: false,
      last_error: 'Garmin 连接已失效，请重新连接账号',
      error_count: 3,
    };
    const { getByRole } = render(<SettingsScreen />);

    fireEvent.press(getByRole('button', { name: 'Garmin 连接，凭证失效' }));

    expect(mockPush).toHaveBeenCalledWith('/garmin-connection');
    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('shows the real build and allows a manual update check', async () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const { getByText } = render(<SettingsScreen />);

    expect(getByText('1.4.0 (231)')).toBeTruthy();
    fireEvent.press(getByText('检查更新'));

    await waitFor(() => expect(mockCheckNow).toHaveBeenCalledWith({ force: true }));
    expect(alertSpy).toHaveBeenCalledWith('已是最新版本', '当前没有需要下载的更新。');
    alertSpy.mockRestore();
  });
});
