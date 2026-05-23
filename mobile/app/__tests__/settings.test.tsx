/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
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
      return { data: { health: 'healthy', minutes_since_last_sync: 3 }, refetch: jest.fn() };
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
      separator: '#333',
      brand: '#0A8F8F',
      brandLight: '#123',
    },
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
  });

  it('surfaces GPS location in the current city section', () => {
    const { getByText } = render(<SettingsScreen />);

    expect(getByText('当前城市')).toBeTruthy();
    fireEvent.press(getByText('GPS 定位'));

    expect(mockPush).toHaveBeenCalledWith('/location');
  });
});
