export interface ChatImageSource {
  uri: string;
  headers?: { Authorization: string };
}

export function isProtectedChatImageUri(uri: string): boolean {
  return /^https?:\/\/[^/]+\/api\/v\d+\/upload\/files\/(?:chat|diet|medical|other)\//i
    .test(String(uri || ''));
}

export function buildChatImageSource(
  uri: string,
  authToken?: string | null,
): ChatImageSource | undefined {
  const normalized = String(uri || '').trim();
  if (!normalized) return undefined;
  if (!isProtectedChatImageUri(normalized)) return { uri: normalized };
  if (!authToken) return undefined;
  return {
    uri: normalized,
    headers: { Authorization: `Bearer ${authToken}` },
  };
}
