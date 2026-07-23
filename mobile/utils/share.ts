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

export async function shareLocalImage(uri: string) {
  const imageUri = String(uri || '').trim();
  if (!/^file:\/\//i.test(imageUri)) throw new Error('image_share_requires_local_file');

  const available = await Sharing.isAvailableAsync();
  if (!available) throw new Error('image_sharing_unavailable');

  return Sharing.shareAsync(imageUri, {
    dialogTitle: '分享饮食打卡截图',
    mimeType: 'image/png',
    UTI: 'public.png',
  });
}

export type VideoShareTarget = 'wechat' | 'xiaohongshu';

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
