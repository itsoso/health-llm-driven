import AsyncStorage from '@react-native-async-storage/async-storage';

const mockCreateVault = jest.fn();
const mockDeleteVault = jest.fn();

jest.mock('../../modules/local-health-kernel', () => ({
  createLocalHealthVault: (...args: unknown[]) => mockCreateVault(...args),
  deleteLocalHealthVault: (...args: unknown[]) => mockDeleteVault(...args),
}));

import {
  APP_MODE_STORAGE_KEY,
  createPersistedLocalIdentity,
  loadAppModePreference,
  persistAppModePreference,
} from '../localIdentity';

describe('local identity preference', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await AsyncStorage.clear();
  });

  it('persists a local identity only after the passcode-bound vault succeeds', async () => {
    mockCreateVault.mockResolvedValue(undefined);

    await expect(createPersistedLocalIdentity(
      'strict_local',
      () => 'local-fixed-id',
    )).resolves.toEqual({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-fixed-id',
    });

    expect(mockCreateVault).toHaveBeenCalledWith('local-fixed-id');
    expect(await loadAppModePreference()).toEqual({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: 'local-fixed-id',
    });
    expect(mockDeleteVault).not.toHaveBeenCalled();
  });

  it('leaves no local identity preference when vault creation fails', async () => {
    mockCreateVault.mockRejectedValue(
      new Error('device_passcode_required'),
    );

    await expect(createPersistedLocalIdentity(
      'strict_local',
      () => 'must-not-persist',
    )).rejects.toThrow('device_passcode_required');

    expect(await AsyncStorage.getItem(APP_MODE_STORAGE_KEY)).toBeNull();
    expect(mockDeleteVault).not.toHaveBeenCalled();
  });

  it('retains the local vault reference when the user switches to cloud mode', async () => {
    await persistAppModePreference({
      schemaVersion: 1,
      mode: 'cloud_account',
      localIdentityId: 'local-existing-id',
    });

    expect(await loadAppModePreference()).toEqual({
      schemaVersion: 1,
      mode: 'cloud_account',
      localIdentityId: 'local-existing-id',
    });
  });

  it('fails closed for malformed local-session metadata', async () => {
    await AsyncStorage.setItem(APP_MODE_STORAGE_KEY, JSON.stringify({
      schemaVersion: 1,
      mode: 'strict_local',
      localIdentityId: null,
    }));

    await expect(loadAppModePreference()).rejects.toThrow(
      'invalid_local_session_preference',
    );
  });
});
