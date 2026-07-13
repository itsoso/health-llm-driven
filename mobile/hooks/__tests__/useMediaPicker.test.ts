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

const mockMaterializeDraftImages = jest.fn();
const mockDeleteDraftImage = jest.fn().mockResolvedValue(undefined);
jest.mock('../../services/chatDraftStorage', () => ({
  materializeDraftImages: (...args: any[]) => mockMaterializeDraftImages(...args),
  deleteDraftImage: (...args: any[]) => mockDeleteDraftImage(...args),
}));

jest.spyOn(Alert, 'alert');

import { useMediaPicker } from '../useMediaPicker';

describe('useMediaPicker', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockMaterializeDraftImages.mockImplementation(async (images: any[]) => images);
    mockDeleteDraftImage.mockResolvedValue(undefined);
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

    it('sets pendingImage when user picks an image', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///photo.jpg', base64: 'abc123', mimeType: 'image/png' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(result.current.pendingImage).toEqual({
        uri: 'file:///photo.jpg',
        base64: 'abc123',
        type: 'png',
      });
      expect(mockMaterializeDraftImages).toHaveBeenCalledWith([
        expect.objectContaining({ uri: 'file:///photo.jpg', base64: 'abc123', type: 'png' }),
      ]);
    });

    it('does not set pendingImage when user cancels', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({ canceled: true });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(result.current.pendingImage).toBeNull();
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

    it('defaults to jpeg when mimeType is missing', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///photo.jpg', base64: 'data', mimeType: undefined }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(result.current.pendingImage?.type).toBe('jpeg');
    });

    it('defaults to empty string when base64 is null', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue({ granted: true });
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///p.jpg', base64: null, mimeType: 'image/jpeg' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.pickImage(); });

      expect(result.current.pendingImage?.base64).toBe('');
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

    it('sets pendingImage when photo is taken', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///camera.jpg', base64: 'camdata', mimeType: 'image/jpeg' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      expect(result.current.pendingImage).toEqual({
        uri: 'file:///camera.jpg',
        base64: 'camdata',
        type: 'jpeg',
      });
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

  // ── clearPendingImage ──

  describe('clearPendingImage', () => {
    it('clears pending image state', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///x.jpg', base64: 'data', mimeType: 'image/jpeg' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });
      expect(result.current.pendingImage).not.toBeNull();

      await act(async () => { await result.current.clearImages(); });
      expect(result.current.pendingImage).toBeNull();
      expect(mockDeleteDraftImage).toHaveBeenCalledWith(
        expect.objectContaining({ uri: 'file:///x.jpg' }),
      );
    });

    it('releases accepted images from composer state without deleting their display files', async () => {
      mockRequestCameraPermissions.mockResolvedValue({ granted: true });
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///accepted.jpg', base64: 'data', mimeType: 'image/jpeg' }],
      });

      const { result } = renderHook(() => useMediaPicker());
      await act(async () => { await result.current.takePhoto(); });

      act(() => { result.current.releaseImagesAfterSend(); });

      expect(result.current.pendingImage).toBeNull();
      expect(mockDeleteDraftImage).not.toHaveBeenCalled();
    });
  });
});
