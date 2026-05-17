/**
 * useGPSOnboardingPrompt — 一次性 GPS 权限询问 hook 单测.
 *
 * 覆盖 3 case:
 *   1. 全条件满足 → visible=true
 *   2. AsyncStorage key 已设置 → visible=false (永不再弹)
 *   3. profile.use_manual_location=true → 不弹 (用户在 manual 模式)
 *   4. 权限不是 undetermined (已 granted 或 denied) → 不弹
 */
import { renderHook, waitFor } from '@testing-library/react-native';

let mockPermissionStatus = 'undetermined';
let mockUseManual = false;

jest.mock('expo-location', () => ({
  getForegroundPermissionsAsync: jest.fn(async () => ({ status: mockPermissionStatus })),
  requestForegroundPermissionsAsync: jest.fn(async () => ({ status: 'granted' })),
}));

let mockAsyncStorage: Record<string, string> = {};
jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (k: string) => mockAsyncStorage[k] ?? null),
  setItem: jest.fn(async (k: string, v: string) => { mockAsyncStorage[k] = v; }),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(async () => ({ data: { use_manual_location: mockUseManual } })),
  },
}));

import { useGPSOnboardingPrompt } from '../useGPSOnboardingPrompt';

describe('useGPSOnboardingPrompt', () => {
  beforeEach(() => {
    mockAsyncStorage = {};
    mockPermissionStatus = 'undetermined';
    mockUseManual = false;
  });

  it('shows when undetermined + not manual + not seen', async () => {
    const { result } = renderHook(() => useGPSOnboardingPrompt(true));
    await waitFor(() => expect(result.current.visible).toBe(true), { timeout: 2000 });
  });

  it('does not show when storage key already set', async () => {
    mockAsyncStorage['gps_prompt_seen_v1'] = '1';
    const { result } = renderHook(() => useGPSOnboardingPrompt(true));
    await new Promise(r => setTimeout(r, 1300));
    expect(result.current.visible).toBe(false);
  });

  it('does not show when use_manual_location is true', async () => {
    mockUseManual = true;
    const { result } = renderHook(() => useGPSOnboardingPrompt(true));
    await new Promise(r => setTimeout(r, 1300));
    expect(result.current.visible).toBe(false);
  });

  it('does not show when permission already decided', async () => {
    mockPermissionStatus = 'denied';
    const { result } = renderHook(() => useGPSOnboardingPrompt(true));
    await new Promise(r => setTimeout(r, 1300));
    expect(result.current.visible).toBe(false);
  });

  it('does not show when disabled', async () => {
    const { result } = renderHook(() => useGPSOnboardingPrompt(false));
    await new Promise(r => setTimeout(r, 1300));
    expect(result.current.visible).toBe(false);
  });

  it('onAllow hides modal and sets storage key', async () => {
    const { result } = renderHook(() => useGPSOnboardingPrompt(true));
    await waitFor(() => expect(result.current.visible).toBe(true), { timeout: 2000 });
    const allowResult = await result.current.onAllow();
    expect(allowResult.granted).toBe(true);
    expect(mockAsyncStorage['gps_prompt_seen_v1']).toBe('1');
    await waitFor(() => expect(result.current.visible).toBe(false));
  });

  it('onLater hides modal and sets storage key (never reprompted)', async () => {
    const { result } = renderHook(() => useGPSOnboardingPrompt(true));
    await waitFor(() => expect(result.current.visible).toBe(true), { timeout: 2000 });
    await result.current.onLater();
    expect(mockAsyncStorage['gps_prompt_seen_v1']).toBe('1');
    await waitFor(() => expect(result.current.visible).toBe(false));
  });
});
