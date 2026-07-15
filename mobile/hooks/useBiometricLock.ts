import { useState, useEffect, useCallback, useRef } from 'react';
import { AppState, type AppStateStatus, Platform } from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';

const BIOMETRIC_ENABLED_KEY = 'biometric_lock_enabled';

export function useBiometricLock(isAuthenticated: boolean) {
  const [isLocked, setIsLocked] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const appState = useRef(AppState.currentState);
  const wasBackground = useRef(false);

  useEffect(() => {
    if (Platform.OS === 'web') return;
    (async () => {
      const hasHardware = await LocalAuthentication.hasHardwareAsync();
      const isEnrolled = await LocalAuthentication.isEnrolledAsync();
      setIsSupported(hasHardware && isEnrolled);

      try {
        const stored = await SecureStore.getItemAsync(BIOMETRIC_ENABLED_KEY);
        if (stored === 'true' && hasHardware && isEnrolled) {
          setIsEnabled(true);
          setIsLocked(true);
        }
      } catch (e) {
        if (__DEV__) console.warn('[biometric] SecureStore read failed:', e);
      }
    })();
  }, []);

  useEffect(() => {
    if (!isAuthenticated || !isEnabled) return;

    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (appState.current.match(/inactive|background/) && next === 'active') {
        if (wasBackground.current) {
          setIsLocked(true);
        }
      }
      wasBackground.current = next === 'background';
      appState.current = next;
    });
    return () => sub.remove();
  }, [isAuthenticated, isEnabled]);

  const authenticate = useCallback(async () => {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: '解锁小巴',
      fallbackLabel: '使用密码',
      disableDeviceFallback: false,
    });
    if (result.success) setIsLocked(false);
    return result.success;
  }, []);

  const toggleEnabled = useCallback(async () => {
    if (!isSupported) return;
    const newVal = !isEnabled;
    if (newVal) {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: '启用 Face ID 保护',
        fallbackLabel: '使用密码',
        disableDeviceFallback: false,
      });
      if (!result.success) return;
    }
    setIsEnabled(newVal);
    setIsLocked(false);
    await SecureStore.setItemAsync(BIOMETRIC_ENABLED_KEY, String(newVal));
  }, [isSupported, isEnabled]);

  return { isLocked, isEnabled, isSupported, authenticate, toggleEnabled };
}
