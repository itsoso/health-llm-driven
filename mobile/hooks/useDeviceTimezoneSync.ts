/**
 * App 启动 + 前台时静默上报设备时区 → 后端 detected_timezone (自动跟随地理位置).
 *
 * 设计原则 (对齐 useGPSAutoRefresh):
 * - 纯 JS (Intl), 无 native 依赖 → 可 OTA, 不需 EAS build
 * - 用户没手动锁定时, detected_timezone 即生效时区; 用药/随访等"今天"按它的日历日算
 * - 节流: tz 没变且 12h 内上报过就跳过 (省请求); tz 一变 (出差/跨时区) 立即上报
 * - 静默失败: 取不到时区 / 网络错都不打扰用户
 * - 上报成功且 tz 变了 → invalidate 生效时区相关 query, 设置页/首页同步
 */
import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQueryClient } from '@tanstack/react-query';
import { getDeviceTimezone, reportDeviceTimezone } from '../services/location';

const MIN_INTERVAL_MS = 12 * 60 * 60 * 1000; // 12h: tz 不变最多半天上报一次
const LAST_TZ_KEY = 'device_tz_last_reported';
const LAST_TS_KEY = 'device_tz_last_ts';

export function useDeviceTimezoneSync(enabled: boolean) {
  const qc = useQueryClient();
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    const trySync = async () => {
      if (inFlightRef.current) return;

      const tz = getDeviceTimezone();
      if (!tz) return;

      // 节流: tz 没变且 12h 内上报过 → 跳过. tz 一变立即上报 (出差跨时区).
      try {
        const lastTz = await AsyncStorage.getItem(LAST_TZ_KEY);
        const lastTs = await AsyncStorage.getItem(LAST_TS_KEY);
        const ageMs = lastTs ? Date.now() - Number(lastTs) : Infinity;
        if (tz === lastTz && ageMs < MIN_INTERVAL_MS) return;
      } catch {
        // AsyncStorage 读失败 → 当作要上报, 继续
      }

      inFlightRef.current = true;
      try {
        await reportDeviceTimezone(tz);
        await AsyncStorage.multiSet([
          [LAST_TZ_KEY, tz],
          [LAST_TS_KEY, String(Date.now())],
        ]);
        // 生效时区可能变了 (未锁定时) → 让设置页/相关 query 重新拉
        qc.invalidateQueries({ queryKey: ['effectiveTimezone'] });
        qc.invalidateQueries({ queryKey: ['profileLocation'] });
        if (__DEV__) console.log(`[TZ] reported device timezone: ${tz}`);
      } catch (e) {
        if (__DEV__) console.warn('[TZ] report failed:', e);
      } finally {
        inFlightRef.current = false;
      }
    };

    // 启动时跑一次, 之后每次 foreground 触发
    trySync();
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') trySync();
    });
    return () => sub.remove();
  }, [enabled, qc]);
}
