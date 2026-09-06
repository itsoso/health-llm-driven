/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { Ionicons } from '@expo/vector-icons';

const mockBack = jest.fn();
const mockRefetch = jest.fn();
const mockInvalidateHealthSnapshot = jest.fn();
const mockConnectCredentials = jest.fn();
const mockVerifyMfa = jest.fn();
const mockSync = jest.fn();
const mockSetSyncEnabled = jest.fn();
const mockDeleteCredentials = jest.fn();
const mockGarminSyncErrorMessage = jest.fn(
  (_error: unknown) => '同步耗时较长，服务器可能仍在继续。请稍后刷新状态，避免重复同步。',
);
let mockStatus: any;

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    data: mockStatus,
    isLoading: false,
    isRefetching: false,
    refetch: mockRefetch,
  }),
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock('../../applib/queryKeys', () => ({
  invalidateHealthSnapshot: (...args: unknown[]) => mockInvalidateHealthSnapshot(...args),
}));

jest.mock('../../services/garmin', () => ({
  fetchGarminStatus: jest.fn(),
  connectGarminCredentials: (...args: unknown[]) => mockConnectCredentials(...args),
  verifyGarminMfa: (...args: unknown[]) => mockVerifyMfa(...args),
  syncGarmin: (...args: unknown[]) => mockSync(...args),
  setGarminSyncEnabled: (...args: unknown[]) => mockSetSyncEnabled(...args),
  deleteGarminCredentials: (...args: unknown[]) => mockDeleteCredentials(...args),
  garminErrorMessage: () => '操作失败，请稍后重试',
  garminSyncErrorMessage: (error: unknown) => mockGarminSyncErrorMessage(error),
}));

import GarminConnectionScreen from '../garmin-connection';

describe('GarminConnectionScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockStatus = {
      bound: false,
      health: 'unbound',
      credentials_valid: null,
      requires_mfa: false,
      sync_enabled: true,
      last_sync_at: null,
      minutes_since_last_sync: null,
      last_error: null,
      error_count: 0,
    };
    mockConnectCredentials.mockResolvedValue({
      success: true,
      mfa_required: false,
      message: '连接成功',
    });
    mockVerifyMfa.mockResolvedValue({ success: true, message: '验证成功', session_id: 'native' });
    mockSync.mockResolvedValue({ status: 'success', message: '同步成功', success_count: 1 });
    mockSetSyncEnabled.mockResolvedValue(undefined);
    mockDeleteCredentials.mockResolvedValue(undefined);
    mockRefetch.mockResolvedValue(undefined);
    mockInvalidateHealthSnapshot.mockResolvedValue(undefined);
  });

  it('binds and tests an unbound Garmin account without displaying the password', async () => {
    const { getByLabelText, getByRole } = render(<GarminConnectionScreen />);

    fireEvent.changeText(getByLabelText('Garmin 邮箱'), 'athlete@example.com');
    fireEvent.changeText(getByLabelText('Garmin 密码'), 'secret-value');
    expect(getByLabelText('Garmin 密码').props.secureTextEntry).toBe(true);
    fireEvent.press(getByRole('button', { name: '连接 Garmin' }));

    await waitFor(() => expect(mockConnectCredentials).toHaveBeenCalledWith({
      garmin_email: 'athlete@example.com',
      garmin_password: 'secret-value',
      is_cn: false,
    }));
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('continues a native login with a six-digit MFA code', async () => {
    mockConnectCredentials.mockResolvedValueOnce({
      success: false,
      mfa_required: true,
      message: '需要验证码',
      mfa_session_id: 'opaque-session',
    });
    const { getByLabelText, getByRole } = render(<GarminConnectionScreen />);

    fireEvent.changeText(getByLabelText('Garmin 邮箱'), 'athlete@example.com');
    fireEvent.changeText(getByLabelText('Garmin 密码'), 'secret-value');
    fireEvent.press(getByRole('button', { name: '连接 Garmin' }));
    await waitFor(() => expect(getByLabelText('Garmin 两步验证码')).toBeTruthy());
    fireEvent.changeText(getByLabelText('Garmin 两步验证码'), '123456');
    fireEvent.press(getByRole('button', { name: '验证并完成连接' }));

    await waitFor(() => expect(mockVerifyMfa).toHaveBeenCalledWith('123456', 'opaque-session'));
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('syncs a healthy connected account and invalidates health data', async () => {
    mockStatus = {
      ...mockStatus,
      bound: true,
      health: 'healthy',
      credentials_valid: true,
      last_sync_at: '2026-08-02T12:00:00Z',
      minutes_since_last_sync: 12,
    };
    const { getByRole, getByText } = render(<GarminConnectionScreen />);

    expect(getByText('连接正常')).toBeTruthy();
    fireEvent.press(getByRole('button', { name: '立即同步 Garmin' }));

    await waitFor(() => expect(mockSync).toHaveBeenCalledWith(1));
    expect(mockInvalidateHealthSnapshot).toHaveBeenCalled();
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('renders a no-data sync as informational instead of a success check', async () => {
    mockStatus = {
      ...mockStatus,
      bound: true,
      health: 'healthy',
      credentials_valid: true,
    };
    mockSync.mockResolvedValueOnce({ status: 'no_data', message: '今天暂无新数据' });
    const { getByRole, getByText, UNSAFE_getAllByType } = render(<GarminConnectionScreen />);

    fireEvent.press(getByRole('button', { name: '立即同步 Garmin' }));

    await waitFor(() => expect(getByText('今天暂无新数据')).toBeTruthy());
    expect(
      UNSAFE_getAllByType(Ionicons).some(
        (icon) => icon.props.name === 'information-circle-outline',
      ),
    ).toBe(true);
  });

  it('does not claim failure when a manual sync times out before the server finishes', async () => {
    mockStatus = {
      ...mockStatus,
      bound: true,
      health: 'healthy',
      credentials_valid: true,
    };
    mockSync.mockRejectedValueOnce({ code: 'ECONNABORTED' });
    const { getByRole, getByText } = render(<GarminConnectionScreen />);

    fireEvent.press(getByRole('button', { name: '立即同步 Garmin' }));

    await waitFor(() => expect(getByText(
      '同步耗时较长，服务器可能仍在继续。请稍后刷新状态，避免重复同步。',
    )).toBeTruthy());
    expect(mockGarminSyncErrorMessage).toHaveBeenCalledWith({ code: 'ECONNABORTED' });
  });

  it('shows an actionable reconnect path for revoked credentials', () => {
    mockStatus = {
      ...mockStatus,
      bound: true,
      health: 'error',
      credentials_valid: false,
      last_error: 'Garmin 连接已失效，请重新连接账号',
      error_count: 3,
    };
    const { getByRole, getByText, getByLabelText } = render(<GarminConnectionScreen />);

    expect(getByText('Garmin 连接已失效，请重新连接账号')).toBeTruthy();
    fireEvent.press(getByRole('button', { name: '重新连接 Garmin' }));

    expect(getByLabelText('Garmin 邮箱')).toBeTruthy();
  });

  it('can pause background sync without deleting the connection', async () => {
    mockStatus = {
      ...mockStatus,
      bound: true,
      health: 'healthy',
      credentials_valid: true,
      sync_enabled: true,
    };
    const { getByRole } = render(<GarminConnectionScreen />);

    fireEvent.press(getByRole('button', { name: '暂停 Garmin 自动同步' }));

    await waitFor(() => expect(mockSetSyncEnabled).toHaveBeenCalledWith(false));
    expect(mockDeleteCredentials).not.toHaveBeenCalled();
    expect(mockRefetch).toHaveBeenCalled();
  });
});
