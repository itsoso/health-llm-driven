import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { Image, type ImageProps } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { BASE_URL } from '../../services/api';
import type { ChatImageSource } from '../../utils/chatImageSource';
import { revaColors as C, revaFonts } from '../../constants/revaTheme';

/** Only our private chat/diet routes support previews; preserve the signed URL. */
function previewUri(uri: string): string {
  try {
    const url = new URL(uri);
    if (url.origin !== new URL(BASE_URL).origin
      || !/^\/api\/v\d+\/upload\/files\/(chat|diet)\//.test(url.pathname)) return uri;
    url.searchParams.set('variant', 'preview');
    return url.toString();
  } catch {
    // Local drafts and opaque image URIs must retain their original source.
    return uri;
  }
}

export function ChatMessageImage({ source, style }: {
  source: ChatImageSource;
  style: ImageProps['style'];
}) {
  const uri = useMemo(() => previewUri(source.uri), [source.uri]);
  const [failedPreview, setFailedPreview] = useState<string | null>(null);
  const [failedOriginal, setFailedOriginal] = useState<string | null>(null);
  const [retryAttempt, setRetryAttempt] = useState({ uri: source.uri, count: 0 });
  const showPreview = uri !== source.uri && failedPreview !== uri;
  const retryCount = retryAttempt.uri === source.uri ? retryAttempt.count : 0;
  if (failedOriginal === source.uri) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="图片暂时无法加载，轻触重试"
        onPress={() => {
          setFailedPreview(null);
          setFailedOriginal(null);
          setRetryAttempt((current) => ({
            uri: source.uri,
            count: current.uri === source.uri ? current.count + 1 : 1,
          }));
        }}
        style={[style as any, styles.failure]}
      >
        <Ionicons name="image-outline" size={21} color={C.greenOn} />
        <Text maxFontSizeMultiplier={1.1} style={styles.failureTitle}>图片暂时无法加载</Text>
        <Text maxFontSizeMultiplier={1.1} style={styles.failureHint}>轻触重试</Text>
      </Pressable>
    );
  }
  return (
    <Image
      source={showPreview ? { ...source, uri } : source}
      style={style}
      contentFit="cover"
      recyclingKey={retryCount > 0 ? `${source.uri}:${retryCount}` : source.uri}
      onError={showPreview
        ? () => setFailedPreview(uri)
        : () => setFailedOriginal(source.uri)}
    />
  );
}

const styles = StyleSheet.create({
  failure: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingHorizontal: 10,
    backgroundColor: C.green600,
  },
  failureTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    color: C.greenOn,
    textAlign: 'center',
  },
  failureHint: {
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 14,
    color: 'rgba(255,255,255,0.78)',
  },
});
