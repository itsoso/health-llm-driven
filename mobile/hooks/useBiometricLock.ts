import { useState, useEffect, useCallback, useRef } from 'react';
import { AppState, type AppStateStatus, Platform } from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';

const BIOMETRIC_ENABLED_KEY = 'biometric_lock_enabled';

export function useBiometricLock(isAuthenticated: boolean) {
  const [isLocked, setIsLocked] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [isReady, setIsReady] = useState(Platform.OS === 'web');
  const [initializationFailed, setInitializationFailed] = useState(false);
  const appState = useRef(AppState.currentState);
  const wasBackground = useRef(false);

  const initialize = useCallback(async () => {
    if (Platform.OS === 'web') return;
    setIsReady(false);
    setInitializationFailed(false);
    try {
      const hasHardware = await LocalAuthentication.hasHardwareAsync();
      const isEnrolled = await LocalAuthentication.isEnrolledAsync();
      const stored = await SecureStore.getItemAsync(BIOMETRIC_ENABLED_KEY);
      setIsSupported(hasHardware && isEnrolled);
      const enabled = stored === 'true' && hasHardware && isEnrolled;
      setIsEnabled(enabled);
      setIsLocked(enabled);
      setIsReady(true);
    } catch {
      console.warn('[biometric] app lock initialization failed');
      setInitializationFailed(true);
    }
  }, []);

  useEffect(() => { void initialize(); }, [initialize]);

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
      promptMessage: '解锁小气候',
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

  return { isLocked, isEnabled, isSupported, isReady, initializationFailed,
    retryInitialization: initialize, authenticate, toggleEnabled };
}
