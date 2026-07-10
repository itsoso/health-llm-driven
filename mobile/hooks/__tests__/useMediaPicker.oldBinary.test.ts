/**
 * useMediaPicker — 旧二进制(OTA 安全)承重路径。
 *
 * 场景:这份 JS 通过 OTA 落到一个 package.json 里还没有 expo-image-manipulator 的
 * 旧二进制(如 TestFlight build 209)。该包的 NativeImageManipulatorModule 在 import
 * 时 eager 调 requireNativeModule('ExpoImageManipulator') —— native 侧缺失会抛错。
 * useMediaPicker 用 guarded require 探测,catch 后降级为 null,绝不让 bundle 加载崩溃。
 *
 * 这里把 expo-image-manipulator 的 require 直接 mock 成抛错来复现"旧二进制",
 * 验证:(1) 兜底走 picker 内联 base64,不崩;(2) fail-loud 仍生效(空 base64 排除+告警)。
 */
import { renderHook, act } from '@testing-library/react-native';
import { Alert } from 'react-native';

const mockRequestMediaLibraryPermissions = jest.fn();
const mockLaunchImageLibrary = jest.fn();
const mockRequestCameraPermissions = jest.fn();
const mockLaunchCamera = jest.fn();

jest.mock('expo-image-picker', () => ({
  requestMediaLibraryPermissionsAsync: (...args: any[]) => mockRequestMediaLibraryPermissions(...args),
  launchImageLibraryAsync: (...args: any[]) => mockLaunchImageLibrary(...args),
  requestCameraPermissionsAsync: (...args: any[]) => mockRequestCameraPermissions(...args),
  launchCameraAsync: (...args: any[]) => mockLaunchCamera(...args),
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));

// 复现旧二进制:require 该包即抛(等价于 requireNativeModule 找不到 native 模块)。
jest.mock('expo-image-manipulator', () => {
  throw new Error('requireNativeModule: ExpoImageManipulator could not be found');
});

jest.spyOn(Alert, 'alert').mockImplementation(() => {});
// probe 在 useMediaPicker 模块加载时会 console.warn 一次 —— 先装 spy 再加载以静音。
jest.spyOn(console, 'warn').mockImplementation(() => {});

// 用 require(而非 import)确保 spy 先于探针执行:ES import 会被提升到文件顶部,
// 会赶在 spy 之前触发探针的 console.warn,污染测试输出。
const { useMediaPicker } = require('../useMediaPicker') as typeof import('../useMediaPicker');

function alertTitles(): string[] {
  return (Alert.alert as jest.Mock).mock.calls.map(c => String(c[0]));
}

describe('useMediaPicker — old binary (image-manipulator native module absent)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does NOT crash on import — probe swallowed the missing native module', () => {
    // 若 guarded require 没兜住,import '../useMediaPicker' 时就会抛,renderHook 到不了这里。
    const { result } = renderHook(() => useMediaPicker());
    expect(typeof result.current.pickImage).toBe('function');
    expect(result.current.pendingImage).toBeNull();
  });

  it('falls back to picker inline base64 (base64:true requested, uncompressed) and keeps { uri, base64, type }', async () => {
    mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
    mockLaunchImageLibrary.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///p.jpg', base64: 'picker-inline-b64', mimeType: 'image/jpeg', width: 4032, height: 3024 }],
    });

    const { result } = renderHook(() => useMediaPicker());
    await act(async () => { await result.current.pickImage(); });

    // 旧二进制:向 picker 要 base64(fallback),用它内联的 base64 直接发
    expect(mockLaunchImageLibrary.mock.calls[0][0].base64).toBe(true);
    expect(mockLaunchImageLibrary.mock.calls[0][0].quality).toBe(0.8);
    expect(result.current.pendingImage).toEqual({
      uri: 'file:///p.jpg',
      base64: 'picker-inline-b64',
      type: 'jpeg',
    });
  });

  it('still EXCLUDES an asset with falsy base64 and alerts — never emits base64:""', async () => {
    mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
    mockLaunchImageLibrary.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///p.jpg', base64: '', mimeType: 'image/jpeg', width: 4032, height: 3024 }],
    });

    const { result } = renderHook(() => useMediaPicker());
    await act(async () => { await result.current.pickImage(); });

    expect(result.current.pendingImage).toBeNull();
    expect(result.current.pendingImages).toEqual([]);
    expect(alertTitles()).toContain('该图片无法读取，已跳过');
  });

  it('takePhoto falls back to picker base64 on old binary and preserves the real type', async () => {
    mockRequestCameraPermissions.mockResolvedValue({ granted: true });
    mockLaunchCamera.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///cam.png', base64: 'cam-inline', mimeType: 'image/png', width: 4032, height: 3024 }],
    });

    const { result } = renderHook(() => useMediaPicker());
    await act(async () => { await result.current.takePhoto(); });

    expect(mockLaunchCamera.mock.calls[0][0].base64).toBe(true);
    expect(result.current.pendingImage).toEqual({
      uri: 'file:///cam.png',
      base64: 'cam-inline',
      type: 'png',
    });
  });
});
