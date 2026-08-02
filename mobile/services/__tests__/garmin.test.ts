/* eslint-disable import/first */

const mockGet = jest.fn();
const mockPost = jest.fn();
const mockDelete = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}));

import {
  deleteGarminCredentials,
  fetchGarminStatus,
  garminErrorMessage,
  saveGarminCredentials,
  setGarminSyncEnabled,
  syncGarmin,
  testGarminConnection,
  verifyGarminMfa,
} from '../garmin';

describe('Garmin service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses the signed-in user Garmin endpoints without retaining a password', async () => {
    const input = {
      garmin_email: 'athlete@example.com',
      garmin_password: 'not-retained',
      is_cn: false,
    };
    mockGet.mockResolvedValueOnce({ data: { bound: false, health: 'unbound' } });
    mockPost
      .mockResolvedValueOnce({ data: { id: 7, garmin_email: input.garmin_email } })
      .mockResolvedValueOnce({ data: { success: true, mfa_required: false, message: 'ok' } });

    await expect(fetchGarminStatus()).resolves.toMatchObject({ health: 'unbound' });
    await saveGarminCredentials(input);
    await expect(testGarminConnection(input)).resolves.toMatchObject({ success: true });

    expect(mockGet).toHaveBeenCalledWith('/data-collection/garmin/me/credential-status');
    expect(mockPost).toHaveBeenNthCalledWith(1, '/auth/garmin/credentials', input);
    expect(mockPost).toHaveBeenNthCalledWith(2, '/auth/garmin/test-connection', input);
  });

  it('submits only the MFA code and opaque user-bound session id', async () => {
    mockPost.mockResolvedValueOnce({ data: { success: true, message: 'verified', session_id: 'native' } });

    await verifyGarminMfa('123456', 'opaque-session');

    expect(mockPost).toHaveBeenCalledWith('/auth/garmin/verify-mfa', {
      mfa_code: '123456',
      mfa_session_id: 'opaque-session',
    });
  });

  it('supports manual sync, pausing, resuming and disconnecting', async () => {
    mockPost
      .mockResolvedValueOnce({ data: { status: 'success', success_count: 1 } })
      .mockResolvedValueOnce({ data: { sync_enabled: false } })
      .mockResolvedValueOnce({ data: { sync_enabled: true } });
    mockDelete.mockResolvedValueOnce({ data: { message: 'deleted' } });

    await syncGarmin(3);
    await setGarminSyncEnabled(false);
    await setGarminSyncEnabled(true);
    await deleteGarminCredentials();

    expect(mockPost).toHaveBeenNthCalledWith(1, '/data-collection/garmin/me/sync?days=3');
    expect(mockPost).toHaveBeenNthCalledWith(2, '/auth/garmin/toggle-sync?enabled=false');
    expect(mockPost).toHaveBeenNthCalledWith(3, '/auth/garmin/toggle-sync?enabled=true');
    expect(mockDelete).toHaveBeenCalledWith('/auth/garmin/credentials');
  });

  it('only surfaces a string server detail and otherwise uses a safe fallback', () => {
    expect(garminErrorMessage({ response: { data: { detail: '请重新连接账号' } } })).toBe('请重新连接账号');
    expect(garminErrorMessage({ response: { data: { detail: { password: 'secret' } } } })).toBe('操作失败，请稍后重试');
    expect(garminErrorMessage(new Error('request included a password'))).toBe('操作失败，请稍后重试');
  });
});
