import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import api from '../services/api';

interface SharePlainTextOptions {
  title?: string;
  message: string;
}

interface TextSharePage {
  share_token: string;
  share_url: string;
}

async function createTextSharePage(title: string | undefined, message: string): Promise<TextSharePage> {
  const res = await api.post<TextSharePage>('/shared/create-text', {
    title,
    message,
  });
  return res.data;
}

async function revokeTextSharePage(shareToken: string): Promise<void> {
  await api.delete(`/shared/${encodeURIComponent(shareToken)}`);
}

export async function sharePlainText({ title, message }: SharePlainTextOptions) {
  const { share_token: shareToken, share_url: shareUrl } = await createTextSharePage(title, message);
  await Clipboard.setStringAsync(message).catch(() => {});
  const shareMessage = title ? `${title}\n${shareUrl}` : shareUrl;

  let result: Awaited<ReturnType<typeof Share.share>>;
  try {
    result = Platform.OS === 'ios'
      ? await Share.share({ title, message: shareMessage, url: shareUrl })
      : await Share.share({ title, message: shareMessage });
  } catch (error) {
    try {
      await revokeTextSharePage(shareToken);
    } catch (cleanupError) {
      if (__DEV__) console.warn('[share] failed to revoke abandoned share page', cleanupError);
    }
    throw error;
  }

  if (result.action === Share.dismissedAction) {
    await revokeTextSharePage(shareToken);
  }
  return result;
}

export async function sharePlainCaption({ title, message }: SharePlainTextOptions) {
  await Clipboard.setStringAsync(message).catch(() => {});
  return Share.share({ title, message });
}

export type SocialShareTarget = 'wechat' | 'xiaohongshu';
export type VideoShareTarget = SocialShareTarget;
export type ImageShareTarget = SocialShareTarget | 'more';

interface ShareImageOptions {
  target?: ImageShareTarget;
  cacheKey?: string;
  headers?: Record<string, string>;
  mimeType?: string;
  dialogTitle?: string;
}

interface ImageFormat {
  extension: string;
  mimeType: string;
  uti: string;
}

function imageFormat(uri: string, requestedMimeType?: string): ImageFormat {
  const mimeType = String(requestedMimeType || '').trim().toLowerCase();
  if (mimeType === 'image/png') return { extension: 'png', mimeType, uti: 'public.png' };
  if (mimeType === 'image/gif') return { extension: 'gif', mimeType, uti: 'com.compuserve.gif' };
  if (mimeType === 'image/heic' || mimeType === 'image/heif') {
    return { extension: 'heic', mimeType: 'image/heic', uti: 'public.heic' };
  }
  if (mimeType === 'image/webp') return { extension: 'webp', mimeType, uti: 'org.webmproject.webp' };
  if (mimeType === 'image/jpeg' || mimeType === 'image/jpg') {
    return { extension: 'jpg', mimeType: 'image/jpeg', uti: 'public.jpeg' };
  }

  const path = uri.split('?')[0]?.toLowerCase() || '';
  if (path.endsWith('.png')) return { extension: 'png', mimeType: 'image/png', uti: 'public.png' };
  if (path.endsWith('.gif')) return { extension: 'gif', mimeType: 'image/gif', uti: 'com.compuserve.gif' };
  if (path.endsWith('.heic') || path.endsWith('.heif')) {
    return { extension: 'heic', mimeType: 'image/heic', uti: 'public.heic' };
  }
  if (path.endsWith('.webp')) return { extension: 'webp', mimeType: 'image/webp', uti: 'org.webmproject.webp' };
  return { extension: 'jpg', mimeType: 'image/jpeg', uti: 'public.jpeg' };
}

function imageDialogTitle(target?: ImageShareTarget): string {
  if (target === 'wechat') return '分享到微信';
  if (target === 'xiaohongshu') return '分享到小红书';
  return '分享图片';
}

export async function shareImage(uri: string, options: ShareImageOptions = {}) {
  const sourceUri = String(uri || '').trim();
  if (!sourceUri) throw new Error('image_uri_missing');

  const available = await Sharing.isAvailableAsync();
  if (!available) throw new Error('image_sharing_unavailable');

  const format = imageFormat(sourceUri, options.mimeType);
  const isRemote = /^https?:\/\//i.test(sourceUri);
  const isBareAbsolutePath = sourceUri.startsWith('/');
  if (!isRemote && !isBareAbsolutePath && !/^file:\/\//i.test(sourceUri)) {
    throw new Error('image_share_requires_file_or_https');
  }

  let localUri = isBareAbsolutePath ? `file://${sourceUri}` : sourceUri;
  let cleanup = false;
  if (isRemote) {
    if (!FileSystem.cacheDirectory) throw new Error('image_share_cache_unavailable');
    localUri = `${FileSystem.cacheDirectory}reva-shared-image-${safeCacheKey(options.cacheKey)}.${format.extension}`;
    let download;
    try {
      download = options.headers
        ? await FileSystem.downloadAsync(sourceUri, localUri, { headers: options.headers })
        : await FileSystem.downloadAsync(sourceUri, localUri);
    } catch (error) {
      await FileSystem.deleteAsync(localUri, { idempotent: true }).catch(() => {});
      throw error;
    }
    const status = typeof download.status === 'number' ? download.status : 200;
    if (status < 200 || status >= 300) {
      await FileSystem.deleteAsync(localUri, { idempotent: true }).catch(() => {});
      throw new Error('image_share_download_failed');
    }
    localUri = download.uri || localUri;
    cleanup = true;
  }

  try {
    return await Sharing.shareAsync(localUri, {
      dialogTitle: options.dialogTitle || imageDialogTitle(options.target),
      mimeType: format.mimeType,
      UTI: format.uti,
    });
  } finally {
    if (cleanup) {
      await FileSystem.deleteAsync(localUri, { idempotent: true }).catch((error) => {
        if (__DEV__) console.warn('[share] temporary image cleanup failed', error);
      });
    }
  }
}

export async function shareLocalImage(uri: string) {
  return shareImage(uri, {
    dialogTitle: '分享饮食打卡截图',
    mimeType: 'image/png',
  });
}

interface ShareRemoteVideoOptions {
  target: VideoShareTarget;
  cacheKey?: string;
}

function safeCacheKey(value: string | undefined): string {
  const normalized = String(value || '')
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized.slice(0, 64) || String(Date.now());
}

export async function shareRemoteVideo(
  uri: string,
  options: ShareRemoteVideoOptions,
) {
  const sourceUri = String(uri || '').trim();
  if (!/^(https?:\/\/|file:\/\/)/i.test(sourceUri)) {
    throw new Error('video_share_requires_file_or_https');
  }

  const available = await Sharing.isAvailableAsync();
  if (!available) throw new Error('video_sharing_unavailable');

  const isLocal = /^file:\/\//i.test(sourceUri);
  let localUri = sourceUri;
  let cleanup = false;
  if (!isLocal) {
    if (!FileSystem.cacheDirectory) throw new Error('video_share_cache_unavailable');
    localUri = `${FileSystem.cacheDirectory}reva-aigc-video-${safeCacheKey(options.cacheKey)}.mp4`;
    let download;
    try {
      download = await FileSystem.downloadAsync(sourceUri, localUri);
    } catch (error) {
      await FileSystem.deleteAsync(localUri, { idempotent: true }).catch(() => {});
      throw error;
    }
    const status = typeof download.status === 'number' ? download.status : 200;
    if (status < 200 || status >= 300) {
      await FileSystem.deleteAsync(localUri, { idempotent: true }).catch(() => {});
      throw new Error('video_share_download_failed');
    }
    localUri = download.uri || localUri;
    cleanup = true;
  }

  try {
    return await Sharing.shareAsync(localUri, {
      dialogTitle: options.target === 'wechat' ? '分享到微信' : '分享到小红书',
      mimeType: 'video/mp4',
      UTI: 'public.mpeg-4',
    });
  } finally {
    if (cleanup) {
      await FileSystem.deleteAsync(localUri, { idempotent: true }).catch((error) => {
        if (__DEV__) console.warn('[share] temporary video cleanup failed', error);
      });
    }
  }
}
