import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as Sharing from 'expo-sharing';
import api from '../services/api';

interface SharePlainTextOptions {
  title?: string;
  message: string;
}

async function createTextSharePage(title: string | undefined, message: string) {
  const res = await api.post<{ share_url: string }>('/shared/create-text', {
    title,
    message,
  });
  return res.data.share_url;
}

export async function sharePlainText({ title, message }: SharePlainTextOptions) {
  const shareUrl = await createTextSharePage(title, message);
  await Clipboard.setStringAsync(message).catch(() => {});
  const shareMessage = title ? `${title}\n${shareUrl}` : shareUrl;

  if (Platform.OS === 'ios') {
    return Share.share({
      title,
      message: shareMessage,
      url: shareUrl,
    });
  }

  return Share.share({ title, message: shareMessage });
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
