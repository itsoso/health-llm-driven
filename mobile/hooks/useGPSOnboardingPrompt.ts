/**
 * GPS 首次授权 prompt — 一次性, 主动询问.
 *
 * 设计: useGPSAutoRefresh 只会被动用现有权限 (从不弹). 没 onboarding 流的情况下,
 * 大部分用户从没去 /location 主动开过, GPS auto-refresh 等于零. 这个 hook 在用户
 * 第一次进入 tabs 时弹一次 modal, 用户选"允许"就立刻请求权限; 选"以后再说"永不再弹
 * (要补还是去 /location).
 *
 * 触发四条 AND:
 *   1. 已登录 (caller 决定)
 *   2. AsyncStorage 'gps_prompt_seen_v1' 未设置
 *   3. profile.use_manual_location === false (用户在 manual mode 不需要 GPS)
 *   4. Location.getForegroundPermissionsAsync() === 'undetermined' (从没问过)
 *
 * 弹起延迟 1s, 让 tabs 先渲染好.
 *
 * 不依赖 — 单纯返 {visible, onAllow, onLater}, 渲染 Modal 由 caller 控制.
 */
import { useEffect, useState, useCallback } from 'react';
import * as Location from 'expo-location';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../services/api';

const STORAGE_KEY = 'gps_prompt_seen_v1';
const SHOW_DELAY_MS = 1000;

export interface GPSOnboardingPromptState {
  visible: boolean;
  onAllow: () => Promise<{ granted: boolean }>;
  onLater: () => Promise<void>;
}

export function useGPSOnboardingPrompt(enabled: boolean): GPSOnboardingPromptState {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const checkAndShow = async () => {
      try {
        // (a) 已问过 → 永不再弹
        const seen = await AsyncStorage.getItem(STORAGE_KEY);
        if (seen) return;

        // (b) 权限不是 undetermined → 用户已经决定过, 别打扰
        const { status } = await Location.getForegroundPermissionsAsync();
        if (status !== 'undetermined') return;

        // (c) profile manual mode → 不需要 GPS
        try {
          const resp = await api.get('/v1/profile/me');
          if (resp.data?.use_manual_location) return;
        } catch {
          // profile 拉不到不算 fatal, 继续弹
        }

        if (cancelled) return;
        // 延迟 ~1s 让 tabs 先渲染稳定
        await new Promise(r => setTimeout(r, SHOW_DELAY_MS));
        if (cancelled) return;
        setVisible(true);
      } catch {
        // 全静默 — onboarding 不能拖垮 app
      }
    };

    checkAndShow();
    return () => { cancelled = true; };
  }, [enabled]);

  const onAllow = useCallback(async () => {
    setVisible(false);
    await AsyncStorage.setItem(STORAGE_KEY, '1');
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      return { granted: status === 'granted' };
    } catch {
      return { granted: false };
    }
  }, []);

  const onLater = useCallback(async () => {
    setVisible(false);
    await AsyncStorage.setItem(STORAGE_KEY, '1');
  }, []);

  return { visible, onAllow, onLater };
}
