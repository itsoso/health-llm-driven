import * as FileSystem from 'expo-file-system/legacy';
import * as MediaLibrary from 'expo-media-library';

export interface ChatImageSaveSource {
  uri: string;
  headers?: Record<string, string>;
}

function normalizeLocalFileUri(uri: string): string | null {
  if (/^(file|content|ph|assets-library):\/\//i.test(uri)) {
    return uri;
  }
  if (uri.startsWith('/')) {
    return `file://${uri}`;
  }
  return null;
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

  const localFileUri = normalizeLocalFileUri(uri);
  if (localFileUri) {
    await MediaLibrary.saveToLibraryAsync(localFileUri);
    return;
  }

  if (!FileSystem.cacheDirectory) {
    throw new Error('image_cache_unavailable');
  }

  const ext = extensionFromUri(uri);
  const localUri = `${FileSystem.cacheDirectory}chat-image-${Date.now()}.${ext}`;
  let cleanupUri = localUri;
  try {
    const download = await FileSystem.downloadAsync(uri, localUri, {
      headers: source.headers,
    });
    cleanupUri = download.uri || localUri;
    const status = typeof download.status === 'number' ? download.status : 200;
    if (status < 200 || status >= 300) {
      throw new Error('image_download_failed');
    }
    await MediaLibrary.saveToLibraryAsync(download.uri);
  } finally {
    try {
      await FileSystem.deleteAsync(cleanupUri, { idempotent: true });
    } catch (error) {
      if (__DEV__) console.warn('[chatImageSave] temporary file cleanup failed', error);
    }
  }
}
