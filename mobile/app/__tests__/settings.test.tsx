/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
let mockGarminStatus: any = { health: 'healthy', minutes_since_last_sync: 3 };

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush, canGoBack: () => false }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    if (key.includes('profile')) {
      return {
        data: {
          use_manual_location: false,
          detected_location: { city: '杭州', region: '浙江' },
        },
      };
    }
    if (key.includes('garminStatus')) {
      return { data: mockGarminStatus, refetch: jest.fn() };
    }
    return { data: null, refetch: jest.fn() };
  },
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium', Light: 'light' },
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    logout: jest.fn(),
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
    post: jest.fn(),
  },
}));

import SettingsScreen from '../settings';

describe('SettingsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGarminStatus = { health: 'healthy', minutes_since_last_sync: 3 };
  });

  it('surfaces GPS and city positioning as one explicit clickable entry', () => {
    const { getByText } = render(<SettingsScreen />);

    expect(getByText('GPS / 城市定位')).toBeTruthy();
    expect(getByText('浙江')).toBeTruthy();
    expect(getByText('GPS 自动')).toBeTruthy();
    expect(getByText('用于天气 / 空气质量 / 户外建议')).toBeTruthy();
    expect(() => getByText('定位设置')).toThrow();
    fireEvent.press(getByText('GPS / 城市定位'));

    expect(mockPush).toHaveBeenCalledWith('/location');
  });

  it('opens the Rokid health mode from settings', () => {
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('Rokid 眼镜健康模式'));

    expect(mockPush).toHaveBeenCalledWith('/rokid-health');
  });

  it('opens the Rokid push-up coach from settings', () => {
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('Rokid 俯卧撑计数'));

    expect(mockPush).toHaveBeenCalledWith('/rokid-pushup-coach');
  });

  it('opens diagnostics pages from settings', () => {
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('Rokid 自检'));
    fireEvent.press(getByText('App 诊断'));

    expect(mockPush).toHaveBeenCalledWith('/rokid-diagnostics');
    expect(mockPush).toHaveBeenCalledWith('/app-diagnostics');
  });

  it('opens dedicated longevity analysis pages from settings', () => {
    const { getByText } = render(<SettingsScreen />);

    fireEvent.press(getByText('生物年龄'));
    fireEvent.press(getByText('抗衰下一步'));

    expect(mockPush).toHaveBeenCalledWith('/biological-age');
    expect(mockPush).toHaveBeenCalledWith('/longevity-next');
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
});
