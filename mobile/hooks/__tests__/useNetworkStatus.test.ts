import { renderHook, act } from '@testing-library/react-native';

let mockCallback: ((state: any) => void) | null = null;

jest.mock('@react-native-community/netinfo', () => ({
  addEventListener: jest.fn((cb: any) => {
    mockCallback = cb;
    return jest.fn();
  }),
}));

import { useNetworkStatus } from '../useNetworkStatus';

describe('useNetworkStatus', () => {
  beforeEach(() => {
    mockCallback = null;
  });

  it('defaults to online', () => {
    const { result } = renderHook(() => useNetworkStatus());
    expect(result.current.isOnline).toBe(true);
  });

  it('updates to offline when connection lost', () => {
    const { result } = renderHook(() => useNetworkStatus());
    act(() => {
      mockCallback?.({ isConnected: false });
    });
    expect(result.current.isOnline).toBe(false);
  });

  it('updates back to online when connection restored', () => {
    const { result } = renderHook(() => useNetworkStatus());
    act(() => {
      mockCallback?.({ isConnected: false, isInternetReachable: false });
    });
    expect(result.current.isOnline).toBe(false);
    act(() => {
      mockCallback?.({ isConnected: true, isInternetReachable: true });
    });
    expect(result.current.isOnline).toBe(true);
  });

  it('treats an unreachable connected network as offline', () => {
    const { result } = renderHook(() => useNetworkStatus());
    act(() => {
      mockCallback?.({ isConnected: true, isInternetReachable: false });
    });
    expect(result.current.isOnline).toBe(false);
  });

  it('keeps the last known state while reachability is still probing', () => {
    const { result } = renderHook(() => useNetworkStatus());
    act(() => {
      mockCallback?.({ isConnected: false, isInternetReachable: false });
    });
    expect(result.current.isOnline).toBe(false);
    act(() => {
      mockCallback?.({ isConnected: true, isInternetReachable: null });
    });
    expect(result.current.isOnline).toBe(false);
    act(() => {
      mockCallback?.({ isConnected: true, isInternetReachable: true });
    });
    expect(result.current.isOnline).toBe(true);
  });
});
