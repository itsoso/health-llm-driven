/**
 * Route-level Face ID gate — for sensitive screens (lab reports, genetic data).
 *
 * Diff vs useBiometricLock (App-wide):
 *  - 入页就锁; 走完一次 auth 才进入页面.
 *  - 若用户没开 BIOMETRIC_ENABLED_KEY 全局开关 → 直接 unlocked (不强制).
 *  - 不监听 AppState — 该页本身的 lifecycle 已经会重 mount.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Platform } from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';

const BIOMETRIC_ENABLED_KEY = 'biometric_lock_enabled';

export function useRouteBiometricGate(promptMessage: string = '解锁查看敏感数据') {
  const [status, setStatus] = useState<'checking' | 'locked' | 'unlocked'>('checking');
  const triggered = useRef(false);

  const tryAuth = useCallback(async () => {
    const res = await LocalAuthentication.authenticateAsync({
      promptMessage,
      fallbackLabel: '使用密码',
      disableDeviceFallback: false,
    });
    if (res.success) setStatus('unlocked');
    return res.success;
  }, [promptMessage]);

  useEffect(() => {
    if (Platform.OS === 'web') {
      setStatus('unlocked');
      return;
    }
    (async () => {
      try {
        const enabled = await SecureStore.getItemAsync(BIOMETRIC_ENABLED_KEY);
        if (enabled !== 'true') {
          setStatus('unlocked');
          return;
        }
        const hasHw = await LocalAuthentication.hasHardwareAsync();
        const enrolled = await LocalAuthentication.isEnrolledAsync();
        if (!hasHw || !enrolled) {
          setStatus('unlocked');
          return;
        }
        setStatus('locked');
        if (!triggered.current) {
          triggered.current = true;
          await tryAuth();
        }
      } catch {
        setStatus('unlocked');
      }
    })();
  }, [tryAuth]);

  return { status, retry: tryAuth };
}
