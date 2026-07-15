import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
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
