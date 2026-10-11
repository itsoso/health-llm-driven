import type { Router } from 'expo-router';

/** Stack pages keep their caller; a direct link must still have a visible exit. */
export function backOrChat(router: Pick<Router, 'canGoBack' | 'back' | 'replace'>) {
  if (router.canGoBack()) router.back();
  else router.replace('/(tabs)/chat');
}
