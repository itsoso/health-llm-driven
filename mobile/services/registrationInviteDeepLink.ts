import * as Linking from 'expo-linking';
import { useCallback, useEffect, useRef, useState } from 'react';

const APP_INVITE_SCHEMES = new Set(['health:', 'mobile:']);
const LINK_TOKEN_PATTERN = /^[A-Za-z0-9_-]{22,128}$/;

/**
 * Extract only the opaque invitation credential from an app-owned invite URL.
 * The full URL is deliberately never returned so callers cannot accidentally
 * persist or log phone/query metadata alongside the credential.
 */
export function parseRegistrationInviteToken(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (!APP_INVITE_SCHEMES.has(parsed.protocol)) return null;
    if (parsed.username || parsed.password || parsed.port || parsed.hash) return null;
    if (parsed.hostname !== 'invite' || (parsed.pathname !== '' && parsed.pathname !== '/')) {
      return null;
    }
    if (Array.from(parsed.searchParams.keys()).some((key) => key !== 'token')) return null;
    const values = parsed.searchParams.getAll('token');
    if (values.length !== 1 || !LINK_TOKEN_PATTERN.test(values[0])) return null;
    return values[0];
  } catch {
    return null;
  }
}

export async function getInitialRegistrationInviteToken(): Promise<string | null> {
  const initialUrl = await Linking.getInitialURL();
  return parseRegistrationInviteToken(initialUrl);
}

export function subscribeToRegistrationInviteLinks(
  onToken: (token: string) => void,
): () => void {
  const subscription = Linking.addEventListener('url', ({ url }) => {
    const token = parseRegistrationInviteToken(url);
    if (token) onToken(token);
  });
  return () => subscription.remove();
}

/** Keeps the invite credential process-local; no storage or logging occurs. */
export function useRegistrationInviteDeepLink(): {
  token: string | null;
  clear: () => void;
} {
  const [token, setToken] = useState<string | null>(null);
  const runtimeVersion = useRef(0);

  useEffect(() => {
    let active = true;
    const initialVersion = runtimeVersion.current;
    void getInitialRegistrationInviteToken()
      .then((initialToken) => {
        if (active && initialToken && runtimeVersion.current === initialVersion) {
          setToken(initialToken);
        }
      })
      .catch(() => {
        if (active) console.warn('[RegistrationInvite] initial URL unavailable');
      });
    const unsubscribe = subscribeToRegistrationInviteLinks((nextToken) => {
      runtimeVersion.current += 1;
      setToken(nextToken);
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const clear = useCallback(() => {
    runtimeVersion.current += 1;
    setToken(null);
  }, []);

  return { token, clear };
}
