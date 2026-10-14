import React, { useMemo, useState } from 'react';
import { Image, type ImageProps } from 'expo-image';
import { BASE_URL } from '../../services/api';
import type { ChatImageSource } from '../../utils/chatImageSource';

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
  const showPreview = uri !== source.uri && failedPreview !== uri;
  return (
    <Image
      source={showPreview ? { ...source, uri } : source}
      style={style}
      contentFit="cover"
      recyclingKey={source.uri}
      onError={showPreview ? () => setFailedPreview(uri) : undefined}
    />
  );
}
