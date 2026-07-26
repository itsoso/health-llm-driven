const mockRequestPermissionsAsync = jest.fn();
const mockSaveToLibraryAsync = jest.fn();
const mockDownloadAsync = jest.fn();
const mockDeleteAsync = jest.fn();

jest.mock('expo-media-library', () => ({
  requestPermissionsAsync: (...args: any[]) => mockRequestPermissionsAsync(...args),
  saveToLibraryAsync: (...args: any[]) => mockSaveToLibraryAsync(...args),
}));

jest.mock('expo-file-system/legacy', () => ({
  cacheDirectory: 'file:///cache/',
  downloadAsync: (...args: any[]) => mockDownloadAsync(...args),
  deleteAsync: (...args: any[]) => mockDeleteAsync(...args),
}));

import { saveChatImageToLibrary } from '../chatImageSave';

describe('saveChatImageToLibrary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestPermissionsAsync.mockResolvedValue({ granted: true });
    mockDownloadAsync.mockResolvedValue({ uri: 'file:///cache/chat-image.jpg' });
  });

  it('downloads a protected remote image with auth headers before saving to Photos', async () => {
    mockDownloadAsync.mockResolvedValueOnce({ uri: 'file:///cache/chat-image.jpg', status: 200 });

    await saveChatImageToLibrary({
      uri: 'https://health.example/api/v1/upload/files/chat/7/meal.jpg',
      headers: { Authorization: 'Bearer token' },
    });

    expect(mockRequestPermissionsAsync).toHaveBeenCalledWith(true);
    expect(mockDownloadAsync).toHaveBeenCalledWith(
      'https://health.example/api/v1/upload/files/chat/7/meal.jpg',
      expect.stringMatching(/^file:\/\/\/cache\/chat-image-\d+\.jpg$/),
      { headers: { Authorization: 'Bearer token' } },
    );
    expect(mockSaveToLibraryAsync).toHaveBeenCalledWith('file:///cache/chat-image.jpg');
    expect(mockDeleteAsync).toHaveBeenCalledWith('file:///cache/chat-image.jpg', { idempotent: true });
  });

  it('does not save a failed remote download response as a photo', async () => {
    mockDownloadAsync.mockResolvedValueOnce({ uri: 'file:///cache/chat-image.jpg', status: 401 });

    await expect(saveChatImageToLibrary({
      uri: 'https://health.example/api/v1/upload/files/chat/7/meal.jpg',
      headers: { Authorization: 'Bearer expired' },
    })).rejects.toThrow('image_download_failed');

    expect(mockSaveToLibraryAsync).not.toHaveBeenCalled();
    expect(mockDeleteAsync).toHaveBeenCalledWith('file:///cache/chat-image.jpg', { idempotent: true });
  });

  it('saves a local image directly without downloading it again', async () => {
    await saveChatImageToLibrary({ uri: 'file:///tmp/meal.png' });

    expect(mockDownloadAsync).not.toHaveBeenCalled();
    expect(mockSaveToLibraryAsync).toHaveBeenCalledWith('file:///tmp/meal.png');
  });

  it('normalizes an iOS view-shot absolute path before saving it', async () => {
    await saveChatImageToLibrary({
      uri: '/private/var/mobile/Containers/Data/Application/app/tmp/diet-card.png',
    });

    expect(mockDownloadAsync).not.toHaveBeenCalled();
    expect(mockSaveToLibraryAsync).toHaveBeenCalledWith(
      'file:///private/var/mobile/Containers/Data/Application/app/tmp/diet-card.png',
    );
  });

  it('fails clearly when Photos permission is denied', async () => {
    mockRequestPermissionsAsync.mockResolvedValueOnce({ granted: false });

    await expect(saveChatImageToLibrary({ uri: 'file:///tmp/meal.png' }))
      .rejects.toThrow('photo_permission_denied');
    expect(mockSaveToLibraryAsync).not.toHaveBeenCalled();
  });
});
