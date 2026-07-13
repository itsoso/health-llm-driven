import * as FileSystem from 'expo-file-system/legacy';
import * as MediaLibrary from 'expo-media-library';

export interface ChatImageSaveSource {
  uri: string;
  headers?: Record<string, string>;
}

function isLocalFileUri(uri: string): boolean {
  return /^(file|content|ph|assets-library):\/\//i.test(uri);
}

function extensionFromUri(uri: string): string {
  const path = uri.split('?')[0] || '';
  const match = path.match(/\.([a-z0-9]{2,5})$/i);
  return match ? match[1].toLowerCase() : 'jpg';
}

async function ensurePhotoWritePermission(): Promise<void> {
  const permission = await MediaLibrary.requestPermissionsAsync(true);
  if (!permission.granted) {
    throw new Error('photo_permission_denied');
  }
}

export async function saveChatImageToLibrary(source: ChatImageSaveSource): Promise<void> {
  const uri = String(source.uri || '').trim();
  if (!uri) throw new Error('image_uri_missing');

  await ensurePhotoWritePermission();

  if (isLocalFileUri(uri)) {
    await MediaLibrary.saveToLibraryAsync(uri);
    return;
  }

  if (!FileSystem.cacheDirectory) {
    throw new Error('image_cache_unavailable');
  }

  const ext = extensionFromUri(uri);
  const localUri = `${FileSystem.cacheDirectory}chat-image-${Date.now()}.${ext}`;
  const download = await FileSystem.downloadAsync(uri, localUri, {
    headers: source.headers,
  });
  const status = typeof download.status === 'number' ? download.status : 200;
  if (status < 200 || status >= 300) {
    throw new Error('image_download_failed');
  }
  await MediaLibrary.saveToLibraryAsync(download.uri);
}
