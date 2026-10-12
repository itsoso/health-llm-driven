/* eslint-disable import/first */
import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
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

  it('shows partial activity sync despite a recent prior success without asking for login', () => {
    const message = '运动记录未完整同步，请稍后重新同步；上次成功时间不代表本轮运动已完整同步。';
    mockStatus = { ...mockStatus, bound: true, health: 'stale', credentials_valid: true,
      last_sync_at: '2026-10-09T02:00:00Z', minutes_since_last_sync: 5, last_error: message };
    const { getByText, queryByText } = render(<GarminConnectionScreen />);
    expect(getByText(message)).toBeTruthy();
    expect(queryByText('连接正常')).toBeNull();
    expect(queryByText('需要重新连接')).toBeNull();
    expect(queryByText('最近同步：5 分钟前')).toBeNull();
  });

  it('keeps contradictory healthy status with future time as a warning', () => {
    mockStatus = { ...mockStatus, bound: true, health: 'healthy', credentials_valid: true,
      minutes_since_last_sync: -480, last_error: '同步时间异常' };
    const { getByText, queryByText } = render(<GarminConnectionScreen />);
    expect(getByText('同步时间异常')).toBeTruthy();
    expect(queryByText('连接正常')).toBeNull();
  });

  it('offers read-only status refresh while a sync request is pending', async () => {
    mockStatus = { ...mockStatus, bound: true, credentials_valid: true };
    let finish!: (value: unknown) => void;
    mockSync.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    const { getByRole } = render(<GarminConnectionScreen />);
    fireEvent.press(getByRole('button', { name: '立即同步 Garmin' }));
    fireEvent.press(getByRole('button', { name: '刷新连接状态' }));
    await waitFor(() => expect(mockRefetch).toHaveBeenCalledTimes(1));
    expect(mockSync).toHaveBeenCalledTimes(1);
    await act(async () => finish({ status: 'success', message: '同步完成' }));
  });

  it('separates post-sync refresh from sync and does not report refresh failure as sync failure', async () => {
    mockStatus = { ...mockStatus, bound: true, credentials_valid: true };
    let fail!: (error: Error) => void;
    mockInvalidateHealthSnapshot.mockReturnValueOnce(new Promise((_resolve, reject) => { fail = reject; }));
    const { getByRole, getByText, queryByText } = render(<GarminConnectionScreen />);
    fireEvent.press(getByRole('button', { name: '立即同步 Garmin' }));
    await waitFor(() => expect(getByRole('button', { name: '正在刷新同步结果…' })).toBeTruthy());
    expect(queryByText('同步中…')).toBeNull();
    await act(async () => fail(new Error('synthetic refresh failure')));
    expect(getByText('同步请求已完成，但页面刷新失败。请刷新连接状态核实结果，无需再次同步。')).toBeTruthy();
    expect(mockGarminSyncErrorMessage).not.toHaveBeenCalled();
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('reports a failed read-only refetch without issuing sync or credential writes', async () => {
    mockStatus = { ...mockStatus, bound: true, credentials_valid: true };
    mockRefetch.mockResolvedValueOnce({ isError: true, error: new Error('synthetic') });
    const { getByRole, getByText } = render(<GarminConnectionScreen />);
    fireEvent.press(getByRole('button', { name: '刷新连接状态' }));
    await waitFor(() => expect(getByText('连接状态刷新失败，请稍后重试；这不代表同步已停止。')).toBeTruthy());
    expect(mockSync).not.toHaveBeenCalled();
    expect(mockConnectCredentials).not.toHaveBeenCalled();
    expect(mockSetSyncEnabled).not.toHaveBeenCalled();
    expect(mockDeleteCredentials).not.toHaveBeenCalled();
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
