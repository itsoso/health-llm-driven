/* eslint-disable import/first */
import { act, renderHook, waitFor } from '@testing-library/react-native';

const mockHasHardware = jest.fn();
const mockIsEnrolled = jest.fn();
const mockGetItem = jest.fn();

jest.mock('react-native', () => ({
  AppState: {
    currentState: 'active',
    addEventListener: jest.fn(() => ({ remove: jest.fn() })),
  },
  Platform: { OS: 'ios' },
}));
jest.mock('expo-local-authentication', () => ({
  hasHardwareAsync: (...args: unknown[]) => mockHasHardware(...args),
  isEnrolledAsync: (...args: unknown[]) => mockIsEnrolled(...args),
  authenticateAsync: jest.fn(),
}));
jest.mock('expo-secure-store', () => ({
  getItemAsync: (...args: unknown[]) => mockGetItem(...args),
  setItemAsync: jest.fn(),
}));

import { useBiometricLock } from '../useBiometricLock';

describe('useBiometricLock initialization', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockHasHardware.mockResolvedValue(true);
    mockIsEnrolled.mockResolvedValue(true);
  });

  it('stays unready while secure storage is pending, then locks before becoming ready', async () => {
    let resolveStored: ((value: string | null) => void) | undefined;
    mockGetItem.mockReturnValue(new Promise<string | null>((resolve) => { resolveStored = resolve; }));
    const { result } = renderHook(() => useBiometricLock(true));

    await waitFor(() => expect(mockGetItem).toHaveBeenCalledWith('biometric_lock_enabled'));
    expect(result.current.isReady).toBe(false);

    await act(async () => { resolveStored?.('true'); });
    expect(result.current.isReady).toBe(true);
    expect(result.current.isEnabled).toBe(true);
    expect(result.current.isLocked).toBe(true);
  });

  it('fails closed and can recover through the exposed retry', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    mockGetItem.mockRejectedValueOnce(new Error('secure storage unavailable'));
    const { result } = renderHook(() => useBiometricLock(true));

    await waitFor(() => expect(result.current.initializationFailed).toBe(true));
    expect(result.current.isReady).toBe(false);

    mockGetItem.mockResolvedValueOnce(null);
    await act(async () => { await result.current.retryInitialization(); });
    expect(result.current.initializationFailed).toBe(false);
    expect(result.current.isReady).toBe(true);
    expect(result.current.isLocked).toBe(false);
    warn.mockRestore();
  });
});
