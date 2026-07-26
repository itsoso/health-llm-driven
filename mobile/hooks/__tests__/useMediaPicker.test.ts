/**
 * useMediaPicker — 拍照/选图发送前的图片承重路径。
 *
 * 核心不变量(2026-07 加固):
 * 1. 每张图都经 expo-image-manipulator 缩放(最长边 ≤1568px)+ JPEG q0.7 重压缩,
 *    再取 base64 —— 绝不把 12MP 原图 base64 直接塞进请求(卡 JS 线程 + 413/超时);
 * 2. manipulator 未回 base64 / 抛异常 → 排除该图 + 弹「该图片无法读取，已跳过」,
 *    绝不下发 base64:''(假成功);
 * 3. 对外契约不变:pendingImage / pendingImages 仍是 { uri, base64, type }。
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

const mockGetDocument = jest.fn();
jest.mock('expo-document-picker', () => ({
  getDocumentAsync: (...args: any[]) => mockGetDocument(...args),
}));

const mockManipulateAsync = jest.fn();
jest.mock('expo-image-manipulator', () => ({
  manipulateAsync: (...args: any[]) => mockManipulateAsync(...args),
  SaveFormat: { JPEG: 'jpeg', PNG: 'png', WEBP: 'webp' },
}));

const mockDeleteTemporaryImage = jest.fn().mockResolvedValue(undefined);
jest.mock('expo-file-system/legacy', () => ({
  deleteAsync: (...args: any[]) => mockDeleteTemporaryImage(...args),
}));

const mockMaterializeDraftImages = jest.fn();
const mockDeleteDraftImage = jest.fn().mockResolvedValue(undefined);
jest.mock('../../services/chatDraftStorage', () => ({
  materializeDraftImages: (...args: any[]) => mockMaterializeDraftImages(...args),
  deleteDraftImage: (...args: any[]) => mockDeleteDraftImage(...args),
}));

jest.spyOn(Alert, 'alert').mockImplementation(() => {});

import { useMediaPicker } from '../useMediaPicker';

// 默认:manipulator 回一张压好的小图。测试可覆写。
function mockManipulatorOk(base64 = 'compressed-base64', uri = 'file:///manip-out.jpg') {
  mockManipulateAsync.mockResolvedValue({ uri, width: 1568, height: 1176, base64 });
}

function alertTitles(): string[] {
  return (Alert.alert as jest.Mock).mock.calls.map(c => String(c[0]));
}

describe('useMediaPicker', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockManipulatorOk();
    mockMaterializeDraftImages.mockImplementation(async (images: any[]) => images);
    mockDeleteDraftImage.mockResolvedValue(undefined);
  });

  describe('contextual image limits', () => {
    const image = (index: number) => ({
      uri: `file:///generic-${index}.jpg`,
      base64: `base64-${index}`,
      type: 'jpeg',
    });

    it('keeps up to nine ordinary attachments', async () => {
      const { result } = renderHook(() => useMediaPicker());

      await act(async () => {
        await result.current.addImages(Array.from({ length: 4 }, (_, index) => image(index)));
      });

      expect(result.current.pendingImages).toHaveLength(4);
      expect(Alert.alert).not.toHaveBeenCalledWith('已达上限', expect.any(String));
    });

    it('applies the three-photo limit only when the caller requests meal capture', async () => {
      const { result } = renderHook(() => useMediaPicker());

      await act(async () => {
        await result.current.addImages(
          Array.from({ length: 4 }, (_, index) => image(index)),
          3,
        );
      });

      expect(result.current.pendingImages).toHaveLength(3);
      expect(Alert.alert).toHaveBeenCalledWith(
        '本餐最多 3 张照片',
        expect.stringContaining('已保留前 3 张'),
      );
    });
  });

  // ── pickImage ──

  describe('pickImage', () => {
    it('requests media library permission before opening picker', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({ canceled: true });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(mockRequestMediaLibraryPermissions).toHaveBeenCalledTimes(1);
      expect(mockLaunchImageLibrary).toHaveBeenCalledTimes(1);
    });

    it('does NOT ask the picker for inline base64/quality (manipulator owns encoding)', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({ canceled: true });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      const opts = mockLaunchImageLibrary.mock.calls[0][0];
      // manipulator 可用时探针为真 → base64:false(picker 不内联),不设 quality(不预压)
      expect(opts.base64).toBe(false);
      expect(opts.quality).toBeUndefined();
      expect(opts).toEqual(expect.objectContaining({ mediaTypes: ['images'], allowsMultipleSelection: true }));
    });

    it('runs the picked asset through manipulateAsync (resize + JPEG compress) and returns the manipulated base64', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        // 4032x3024 → 最长边远超 1568,应触发按 width 缩放
        assets: [{ uri: 'file:///photo.heic', width: 4032, height: 3024 }],
      });
      mockManipulateAsync.mockResolvedValue({ uri: 'file:///small.jpg', width: 1568, height: 1176, base64: 'tiny-jpeg' });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      // 命中 manipulator:resize(最长边→1568,横图按 width) + compress 0.7 + JPEG + base64
      expect(mockManipulateAsync).toHaveBeenCalledTimes(1);
      const [uri, actions, saveOptions] = mockManipulateAsync.mock.calls[0];
      expect(uri).toBe('file:///photo.heic');
      expect(actions).toEqual([{ resize: { width: 1568 } }]);
      expect(saveOptions).toEqual({ compress: 0.7, format: 'jpeg', base64: true });

      // 返回的是 manipulator 产出的小图 base64 + uri,type 恒为 jpeg
      expect(result.current.pendingImage).toEqual({
        uri: 'file:///small.jpg',
        base64: 'tiny-jpeg',
        type: 'jpeg',
      });
      expect(mockMaterializeDraftImages).toHaveBeenCalledWith([
        expect.objectContaining({ uri: 'file:///small.jpg', base64: 'tiny-jpeg', type: 'jpeg' }),
      ]);
      expect(mockDeleteTemporaryImage).toHaveBeenCalledWith(
        'file:///small.jpg',
        { idempotent: true },
      );
    });

    it('resizes by the LONGER edge — portrait photo resizes by height', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///portrait.jpg', width: 3024, height: 4032 }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      const [, actions] = mockManipulateAsync.mock.calls[0];
      expect(actions).toEqual([{ resize: { height: 1568 } }]);
    });

    it('does NOT upscale — a small image gets recompressed with no resize action', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///small.png', width: 800, height: 600 }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      const [, actions, saveOptions] = mockManipulateAsync.mock.calls[0];
      expect(actions).toEqual([]);
      expect(saveOptions).toEqual({ compress: 0.7, format: 'jpeg', base64: true });
    });

    it('EXCLUDES an asset whose manipulation yields empty base64 and never emits base64:""', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///broken.jpg', width: 4000, height: 3000 }],
      });
      // manipulator "成功" 但没回 base64 —— 旧代码会静默下发空图
      mockManipulateAsync.mockResolvedValue({ uri: 'file:///out.jpg', width: 1568, height: 1176, base64: '' });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(result.current.pendingImage).toBeNull();
      expect(result.current.pendingImages).toEqual([]);
      expect(alertTitles()).toContain('该图片无法读取，已跳过');
    });

    it('EXCLUDES an asset when manipulateAsync throws, keeps the good ones, and warns once', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [
          { uri: 'file:///bad.jpg', width: 4000, height: 3000 },
          { uri: 'file:///good.jpg', width: 4000, height: 3000 },
        ],
      });
      mockManipulateAsync
        .mockRejectedValueOnce(new Error('decode failed'))
        .mockResolvedValueOnce({ uri: 'file:///good-out.jpg', width: 1568, height: 1176, base64: 'good-b64' });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      // 坏图被排除,好图保留
      expect(result.current.pendingImages).toEqual([
        { uri: 'file:///good-out.jpg', base64: 'good-b64', type: 'jpeg' },
      ]);
      // 一次性提示跳过,且不是把整批当「选择图片失败」
      expect(alertTitles()).toContain('该图片无法读取，已跳过');
      expect(alertTitles()).not.toContain('选择图片失败');
    });

    it('does not set pendingImage when user cancels', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({ canceled: true });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(result.current.pendingImage).toBeNull();
      expect(mockManipulateAsync).not.toHaveBeenCalled();
    });

    it('shows alert when permission denied', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: false });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(Alert.alert).toHaveBeenCalledWith('需要相册权限', expect.any(String));
      expect(mockLaunchImageLibrary).not.toHaveBeenCalled();
    });

    it('shows alert on exception', async () => {
      mockRequestMediaLibraryPermissions.mockRejectedValue(new Error('Native module error'));

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(Alert.alert).toHaveBeenCalledWith('选择图片失败', expect.stringContaining('Native module error'));
    });
  });

  // ── takePhoto ──

  describe('takePhoto', () => {
    it('requests camera permission before launching camera', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({ canceled: true });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      expect(mockRequestCameraPermissions).toHaveBeenCalledTimes(1);
      expect(mockLaunchCamera).toHaveBeenCalledTimes(1);
    });

    it('manipulates the photo and returns the compressed base64, keeping the { uri, base64, type } shape', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///camera.jpg', width: 4032, height: 3024 }],
      });
      mockManipulateAsync.mockResolvedValue({ uri: 'file:///cam-small.jpg', width: 1568, height: 1176, base64: 'cam-b64' });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      expect(result.current.pendingImage).toEqual({
        uri: 'file:///cam-small.jpg',
        base64: 'cam-b64',
        type: 'jpeg',
      });
      // 相机也不再向 picker 要 base64 —— 交给 manipulator
      const camOpts = mockLaunchCamera.mock.calls[0][0];
      expect(camOpts.base64).toBe(false);
      expect(camOpts.quality).toBeUndefined();
      expect(camOpts).toEqual(expect.objectContaining({ mediaTypes: ['images'] }));
    });

    it('keeps the first photo while a second camera capture is added', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera
        .mockResolvedValueOnce({
          canceled: false,
          assets: [{ uri: 'file:///camera-1.jpg', width: 4032, height: 3024 }],
        })
        .mockResolvedValueOnce({
          canceled: false,
          assets: [{ uri: 'file:///camera-2.jpg', width: 4032, height: 3024 }],
        });
      mockManipulateAsync
        .mockResolvedValueOnce({ uri: 'file:///cam-1-small.jpg', base64: 'cam-1', width: 1568, height: 1176 })
        .mockResolvedValueOnce({ uri: 'file:///cam-2-small.jpg', base64: 'cam-2', width: 1568, height: 1176 });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });
      await act(async () => { await result.current.takePhoto(); });

      expect(result.current.pendingImages).toEqual([
        expect.objectContaining({ uri: 'file:///cam-1-small.jpg', base64: 'cam-1' }),
        expect.objectContaining({ uri: 'file:///cam-2-small.jpg', base64: 'cam-2' }),
      ]);
      expect(mockLaunchCamera).toHaveBeenCalledTimes(2);
    });

    it('EXCLUDES the photo and alerts when manipulation yields no base64 (no empty image sent)', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///camera.jpg', width: 4032, height: 3024 }],
      });
      mockManipulateAsync.mockResolvedValue({ uri: 'file:///out.jpg', width: 1568, height: 1176, base64: undefined });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      expect(result.current.pendingImage).toBeNull();
      expect(alertTitles()).toContain('该图片无法读取，已跳过');
    });

    it('shows alert when camera permission denied', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: false });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      expect(Alert.alert).toHaveBeenCalledWith('需要相机权限', expect.any(String));
      expect(mockLaunchCamera).not.toHaveBeenCalled();
    });

    it('shows alert on camera exception', async () => {
      mockRequestCameraPermissions.mockRejectedValue(new Error('Camera unavailable'));

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      expect(Alert.alert).toHaveBeenCalledWith('拍照失败', expect.stringContaining('Camera unavailable'));
    });
  });

  // ── pickFile ──

  describe('pickFile', () => {
    it('sets pickedFileName when file is selected', async () => {
      mockGetDocument.mockResolvedValue({
        canceled: false,
        assets: [{ name: 'report.pdf', uri: 'file:///report.pdf' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickFile(); });

      expect(result.current.pickedFileName).toBe('report.pdf');
    });

    it('does not set fileName when user cancels', async () => {
      mockGetDocument.mockResolvedValue({ canceled: true });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickFile(); });

      expect(result.current.pickedFileName).toBeNull();
    });

    it('shows alert on exception', async () => {
      mockGetDocument.mockRejectedValue(new Error('Picker failed'));

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickFile(); });

      expect(Alert.alert).toHaveBeenCalledWith('选择文件失败', expect.stringContaining('Picker failed'));
    });
  });

  // ── clearImages ──

  describe('clearImages', () => {
    it('clears pending image state', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///x.jpg', width: 4000, height: 3000 }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });
      expect(result.current.pendingImage).not.toBeNull();

      await act(async () => { await result.current.clearImages(); });
      expect(result.current.pendingImage).toBeNull();
      expect(mockDeleteDraftImage).toHaveBeenCalledWith(
        expect.objectContaining({ uri: 'file:///manip-out.jpg' }),
      );
    });

    it('releases accepted private images from composer state and deletes their draft files', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///accepted.jpg', base64: 'data', mimeType: 'image/jpeg' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      await act(async () => { await result.current.releaseImagesAfterSend(); });

      expect(result.current.pendingImage).toBeNull();
      expect(mockDeleteDraftImage).toHaveBeenCalledWith(
        expect.objectContaining({ uri: 'file:///manip-out.jpg' }),
      );
    });
  });
});
