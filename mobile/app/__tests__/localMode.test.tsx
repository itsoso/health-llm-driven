/* eslint-disable import/first */
import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render } from '@testing-library/react-native';

const mockStartLocalMode = jest.fn();
const mockSwitchMode = jest.fn();

jest.mock('../../hooks/useAppSession', () => ({
  useAppSession: () => ({
    session: null,
    isLoading: false,
    errorCode: null,
    startLocalMode: mockStartLocalMode,
    switchMode: mockSwitchMode,
  }),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    login: jest.fn(),
    loginByPhoneCode: jest.fn(),
  }),
}));

jest.mock('../../services/auth', () => ({
  loadCredentials: jest.fn().mockResolvedValue(null),
  requestPhoneCode: jest.fn(),
  saveCredentials: jest.fn(),
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff', bgCard: '#fff', brandLight: '#eee', brand: '#15976c',
      labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#888',
      separator: '#ddd',
    },
  }),
}));

import LoginScreen from '../login';

describe('local mode onboarding', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockStartLocalMode.mockResolvedValue(undefined);
  });

  it('offers a no-registration local start and explains recovery once created', async () => {
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const screen = render(<LoginScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('无需注册，立即本地使用'));
    });

    expect(mockStartLocalMode).toHaveBeenCalledWith('strict_local');
    expect(alert).toHaveBeenCalledWith(
      '本地保险库已创建',
      expect.stringContaining('恢复文件和恢复密钥'),
      expect.any(Array),
    );
    alert.mockRestore();
  });

  it('maps a missing device passcode to actionable setup guidance', async () => {
    mockStartLocalMode.mockRejectedValue(new Error('device_passcode_required'));
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const screen = render(<LoginScreen />);

    await act(async () => {
      fireEvent.press(screen.getByText('无需注册，立即本地使用'));
    });

    expect(alert).toHaveBeenCalledWith(
      '需要先设置锁屏密码',
      expect.stringContaining('iPhone 设置'),
    );
    alert.mockRestore();
  });
});
