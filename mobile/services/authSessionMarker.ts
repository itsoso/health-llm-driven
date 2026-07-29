import AsyncStorage from '@react-native-async-storage/async-storage';

const PERSISTED_SESSION_MARKER_KEY = 'auth:persisted_session:v1';

/**
 * Non-sensitive recovery hint. The access token remains exclusively in the
 * native keychain; this marker only tells cold start to tolerate a temporarily
 * unavailable keychain instead of immediately routing to login.
 */
export async function hasPersistedSessionMarker(): Promise<boolean> {
  try {
    return await AsyncStorage.getItem(PERSISTED_SESSION_MARKER_KEY) === '1';
  } catch {
    return false;
  }
}

export async function markPersistedSession(): Promise<void> {
  try {
    await AsyncStorage.setItem(PERSISTED_SESSION_MARKER_KEY, '1');
  } catch (error) {
    console.warn('[auth] persisted-session marker write failed:', error);
  }
}

export async function clearPersistedSessionMarker(): Promise<void> {
  try {
    await AsyncStorage.removeItem(PERSISTED_SESSION_MARKER_KEY);
  } catch (error) {
    console.warn('[auth] persisted-session marker deletion failed:', error);
  }
}
