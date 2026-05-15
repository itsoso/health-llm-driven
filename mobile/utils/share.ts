import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';

const DEFAULT_SHARE_URL = 'https://executor.life';

interface SharePlainTextOptions {
  title?: string;
  message: string;
  url?: string;
}

export async function sharePlainText({ title, message, url = DEFAULT_SHARE_URL }: SharePlainTextOptions) {
  if (Platform.OS !== 'ios') {
    return Share.share({ title, message });
  }

  await Clipboard.setStringAsync(message).catch(() => {});
  const messageWithUrl = message.includes(url) ? message : `${message}\n\n${url}`;
  return Share.share({
    title,
    message: messageWithUrl,
    url,
  });
}
