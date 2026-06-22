import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import {
  scheduleEyeBreakReminders,
  cancelEyeBreakReminders,
  DEFAULT_EYE_BREAK_PREFS,
  type EyeBreakPrefs,
} from '../services/eyeBreakReminders';
import {
  loadEyeBreakPrefs,
  saveEyeBreakPrefs,
} from '../services/eyeBreakPrefs';

/**
 * useEyeBreakReminders —— 驱动 20-20-20 护眼提醒的滚动重排。
 *
 * - 启动时载入本地偏好，开启则排当日剩余 slot（见 eyeBreakReminders 的 64-cap 策略）。
 * - App 回到前台时重排：把已消耗掉的 slot 补回（这就是「滚动当日重排」，
 *   保证 pending 数始终远小于 iOS 64 上限）。
 * - updatePrefs：设置屏改配置后调用，持久化 + 立即重排（关闭则取消全部本类通知）。
 *
 * 无通知权限时 scheduleEyeBreakReminders 内部静默跳过（设置项仍可切，下次授权后生效）。
 */
export function useEyeBreakReminders(isAuthenticated: boolean) {
  const [prefs, setPrefs] = useState<EyeBreakPrefs>(DEFAULT_EYE_BREAK_PREFS);
  const [loaded, setLoaded] = useState(false);
  const prefsRef = useRef<EyeBreakPrefs>(DEFAULT_EYE_BREAK_PREFS);
  prefsRef.current = prefs;

  // 启动载入偏好。
  useEffect(() => {
    let alive = true;
    loadEyeBreakPrefs().then((p) => {
      if (!alive) return;
      setPrefs(p);
      setLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  // 偏好就绪 / 变化时重排（登录后才排，登出不主动排）。
  useEffect(() => {
    if (!loaded || !isAuthenticated) return;
    scheduleEyeBreakReminders(prefs).catch(() => {
      // 排程失败不影响 UI
    });
  }, [loaded, isAuthenticated, prefs]);

  // App 回前台 → 滚动重排（补回已消耗的 slot）。
  useEffect(() => {
    if (!isAuthenticated) return;
    const sub = AppState.addEventListener('change', (status: AppStateStatus) => {
      if (status !== 'active') return;
      if (!prefsRef.current.enabled) return;
      scheduleEyeBreakReminders(prefsRef.current).catch(() => {});
    });
    return () => sub.remove();
  }, [isAuthenticated]);

  const updatePrefs = useCallback(async (next: EyeBreakPrefs) => {
    setPrefs(next);
    await saveEyeBreakPrefs(next);
    // setPrefs 已触发上面的重排 effect；关闭时 scheduleEyeBreakReminders 内部走取消路径。
    if (!next.enabled) {
      await cancelEyeBreakReminders();
    }
  }, []);

  return { prefs, loaded, updatePrefs };
}
