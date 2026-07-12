import * as FileSystem from 'expo-file-system/legacy';
import * as MediaLibrary from 'expo-media-library';

type SaveChatImageOptions = {
  authToken?: string | null;
  index?: number;
  now?: number;
};

export async function saveChatImageToLibrary(
  uri: string,
  options: SaveChatImageOptions = {},
): Promise<{ localUri: string }> {
  const sourceUri = String(uri || '').trim();
  if (!sourceUri) {
    throw new Error('chat_image_empty_uri');
  }

  const permission = await MediaLibrary.requestPermissionsAsync();
  if (!permission.granted) {
    throw new Error('photo_library_permission_denied');
  }

  const localUri = await materializeImageUri(sourceUri, options);
  await MediaLibrary.createAssetAsync(localUri);
  return { localUri };
}

async function materializeImageUri(
  uri: string,
  options: SaveChatImageOptions,
): Promise<string> {
  if (/^file:/i.test(uri)) {
    return uri;
  }

  const target = buildCacheTarget(uri, options);
  if (/^data:image\//i.test(uri)) {
    const comma = uri.indexOf(',');
    if (comma < 0) throw new Error('chat_image_invalid_data_uri');
    const base64 = uri.slice(comma + 1);
    await FileSystem.writeAsStringAsync(target, base64, {
      encoding: FileSystem.EncodingType.Base64,
    });
    return target;
  }

  if (/^https?:\/\//i.test(uri)) {
    const headers = options.authToken
      ? { Authorization: `Bearer ${options.authToken}` }
      : undefined;
    const downloaded = await FileSystem.downloadAsync(
      uri,
      target,
      headers ? { headers } : undefined,
    );
    return downloaded.uri;
  }

  throw new Error('chat_image_unsupported_uri');
}

function buildCacheTarget(uri: string, options: SaveChatImageOptions): string {
  const cacheDirectory = FileSystem.cacheDirectory;
  if (!cacheDirectory) {
    throw new Error('chat_image_cache_unavailable');
  }
  const now = options.now ?? Date.now();
  const index = options.index ?? 0;
  return `${cacheDirectory}reva-chat-image-${now}-${index}.${imageExtension(uri)}`;
}

function imageExtension(uri: string): string {
  const match = uri
    .split('?')[0]
    .split('#')[0]
    .match(/\.([a-zA-Z0-9]{2,5})$/);
  const ext = match?.[1]?.toLowerCase();
  if (ext === 'jpeg' || ext === 'jpg') return 'jpg';
  if (ext === 'png' || ext === 'webp' || ext === 'heic') return ext;
  const dataMatch = uri.match(/^data:image\/([a-zA-Z0-9.+-]+);/i);
  const dataExt = dataMatch?.[1]?.toLowerCase();
  if (dataExt === 'jpeg') return 'jpg';
  if (dataExt === 'png' || dataExt === 'webp') return dataExt;
  return 'jpg';
}
