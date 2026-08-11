/**
 * useGPSAutoRefresh — foreground GPS 自动刷新 hook 单测.
 *
 * 覆盖 5 case:
 *   1. 权限未授权 → 不调任何 API
 *   2. 节流期内 + 坐标没动 → 跳过 (不调 backend)
 *   3. 坐标漂移 >50km → 破节流, 调 backend
 *   4. reverseGeocode 成功 → payload 带 city/region/country hint
 *   5. reverseGeocode 失败 → 仍 post lat/lon (无 hint)
 */
import { renderHook, waitFor } from '@testing-library/react-native';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let mockPermissionStatus = 'granted';
let mockPosition = { coords: { latitude: 39.9, longitude: 116.3 } };
let mockReverseGeocodeResult: any[] = [{ city: '北京', region: '北京市', country: '中国' }];

jest.mock('expo-location', () => ({
  Accuracy: { Lowest: 0, Low: 1, Balanced: 2 },
  getForegroundPermissionsAsync: jest.fn(async () => ({ status: mockPermissionStatus })),
  getCurrentPositionAsync: jest.fn(async () => mockPosition),
  reverseGeocodeAsync: jest.fn(async () => mockReverseGeocodeResult),
}));

let mockAsyncStorage: Record<string, string> = {};
jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (k: string) => mockAsyncStorage[k] ?? null),
  setItem: jest.fn(async (k: string, v: string) => { mockAsyncStorage[k] = v; }),
  multiSet: jest.fn(async (entries: [string, string][]) => {
    entries.forEach(([k, v]) => { mockAsyncStorage[k] = v; });
  }),
}));

const mockUpdateGPSLocation: jest.Mock = jest.fn(async () => ({ city: '北京', region: null, country: null }));
const mockReverseGeocodeOnDevice: jest.Mock = jest.fn(async () => ({ city: '北京', region: '北京市', country: '中国' }));
const mockWriteGPSRefreshStatus = jest.fn(async () => undefined);
jest.mock('../../services/location', () => ({
  updateGPSLocation: (lat: number, lon: number, hint?: any) => mockUpdateGPSLocation(lat, lon, hint),
  reverseGeocodeOnDevice: (lat: number, lon: number) => mockReverseGeocodeOnDevice(lat, lon),
}));
jest.mock('../../services/gpsRefreshStatus', () => ({
  writeGPSRefreshStatus: (status: unknown) => mockWriteGPSRefreshStatus(status),
}));

// AppState — 测时不触发 foreground 事件, 只跑 mount 时的 tryRefresh
jest.mock('react-native', () => ({
  AppState: {
    addEventListener: jest.fn(() => ({ remove: jest.fn() })),
  },
  Platform: { OS: 'ios' },
}));

import { useGPSAutoRefresh } from '../useGPSAutoRefresh';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useGPSAutoRefresh', () => {
  beforeEach(() => {
    mockAsyncStorage = {};
    mockPermissionStatus = 'granted';
    mockPosition = { coords: { latitude: 39.9, longitude: 116.3 } };
    mockReverseGeocodeResult = [{ city: '北京', region: '北京市', country: '中国' }];
    mockUpdateGPSLocation.mockClear();
    mockUpdateGPSLocation.mockResolvedValue({ city: '北京', region: null, country: null });
    mockReverseGeocodeOnDevice.mockClear();
    mockWriteGPSRefreshStatus.mockClear();
    mockReverseGeocodeOnDevice.mockResolvedValue({ city: '北京', region: '北京市', country: '中国' });
  });

  it('does not call backend when permission denied', async () => {
    mockPermissionStatus = 'denied';
    renderHook(() => useGPSAutoRefresh(true), { wrapper });
    await new Promise(r => setTimeout(r, 50));
    expect(mockUpdateGPSLocation).not.toHaveBeenCalled();
    expect(mockWriteGPSRefreshStatus).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'permission_required' }),
    );
  });

  it('does not call backend when permission undetermined (onboarding owns first prompt)', async () => {
    mockPermissionStatus = 'undetermined';
    renderHook(() => useGPSAutoRefresh(true), { wrapper });
    await new Promise(r => setTimeout(r, 50));
    expect(mockUpdateGPSLocation).not.toHaveBeenCalled();
  });

  it('skips within throttle when coords unchanged', async () => {
    // 设置 storage: 5min 前刷过的, 坐标和当前完全一样
    mockAsyncStorage['gps_last_refresh_ts'] = String(Date.now() - 5 * 60 * 1000);
    mockAsyncStorage['gps_last_lat'] = '39.9';
    mockAsyncStorage['gps_last_lon'] = '116.3';
    renderHook(() => useGPSAutoRefresh(true), { wrapper });
    await new Promise(r => setTimeout(r, 50));
    expect(mockUpdateGPSLocation).not.toHaveBeenCalled();
  });

  it('breaks throttle when drift > 50km', async () => {
    // 5min 前在北京 (39.9, 116.3), 现在跳到上海 (31.2, 121.4) — 漂 ~1000km
    mockAsyncStorage['gps_last_refresh_ts'] = String(Date.now() - 5 * 60 * 1000);
    mockAsyncStorage['gps_last_lat'] = '39.9';
    mockAsyncStorage['gps_last_lon'] = '116.3';
    mockPosition = { coords: { latitude: 31.2, longitude: 121.4 } };
    renderHook(() => useGPSAutoRefresh(true), { wrapper });
    await waitFor(() => expect(mockUpdateGPSLocation).toHaveBeenCalled());
  });

  it('passes reverseGeocode hint to backend', async () => {
    renderHook(() => useGPSAutoRefresh(true), { wrapper });
    await waitFor(() => expect(mockUpdateGPSLocation).toHaveBeenCalled());
    expect(mockUpdateGPSLocation).toHaveBeenCalledWith(
      39.9, 116.3,
      expect.objectContaining({ city: '北京' }),
    );
    expect(mockWriteGPSRefreshStatus).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'ready', lastSuccessAt: expect.any(Number) }),
    );
  });

  it('records an observable error without clearing the last city when refresh fails', async () => {
    mockUpdateGPSLocation.mockRejectedValueOnce(new Error('offline'));
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined);

    renderHook(() => useGPSAutoRefresh(true), { wrapper });

    await waitFor(() => expect(mockWriteGPSRefreshStatus).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'error', errorKind: 'network_or_server' }),
    ));
    expect(warnSpy).toHaveBeenCalledWith('[GPS] auto-refresh failed:', expect.any(Error));
    warnSpy.mockRestore();
  });

  it('still posts lat/lon when reverseGeocode returns empty hint', async () => {
    mockReverseGeocodeOnDevice.mockResolvedValueOnce({}); // 空对象
    renderHook(() => useGPSAutoRefresh(true), { wrapper });
    await waitFor(() => expect(mockUpdateGPSLocation).toHaveBeenCalled());
    expect(mockUpdateGPSLocation).toHaveBeenCalledWith(39.9, 116.3, {});
  });
});
