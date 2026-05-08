/**
 * App foreground 时静默刷新 GPS 城市.
 *
 * 设计原则:
 * - 只在"已授权"时跑, 绝不主动弹权限 (用户第一次授权通过 /location 手动触发)
 * - 节流 4h: 跨城最早 4 小时后才重新定位
 * - 静默失败: 定位不了 / 网络错 / 反查失败都不打扰用户
 * - 城市变化时才 invalidate 天气 cache, 减少无谓 refetch
 *
 * 解决的 badcase (2026-05-08):
 *   用户从杭州到北京后, profile.detected_city 还是"杭州",
 *   计划提醒 / 天气卡全部错位. 以前只有手动去 /location 页点 GPS 才刷.
 */
import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import * as Location from 'expo-location';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQueryClient } from '@tanstack/react-query';
import { updateGPSLocation } from '../services/location';

const MIN_INTERVAL_MS = 4 * 60 * 60 * 1000;  // 4h
const LAST_TS_KEY = 'gps_last_refresh_ts';
const LAST_CITY_KEY = 'gps_last_city';

export function useGPSAutoRefresh(enabled: boolean) {
  const qc = useQueryClient();
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    const tryRefresh = async () => {
      if (inFlightRef.current) return;

      // 1. 节流: 4h 内刷过就跳过
      try {
        const lastTs = await AsyncStorage.getItem(LAST_TS_KEY);
        if (lastTs && Date.now() - Number(lastTs) < MIN_INTERVAL_MS) return;
      } catch {}

      // 2. 只在已授权情况下跑, 不主动弹权限
      try {
        const { status } = await Location.getForegroundPermissionsAsync();
        if (status !== 'granted') return;
      } catch {
        return;
      }

      inFlightRef.current = true;
      try {
        const pos = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Low,  // 500m 足够城市级
        });
        const loc = await updateGPSLocation(pos.coords.latitude, pos.coords.longitude);
        await AsyncStorage.setItem(LAST_TS_KEY, String(Date.now()));

        if (loc.city) {
          // 城市变了才 invalidate (减少无谓 refetch)
          const prevCity = await AsyncStorage.getItem(LAST_CITY_KEY);
          if (prevCity !== loc.city) {
            await AsyncStorage.setItem(LAST_CITY_KEY, loc.city);
            qc.invalidateQueries({ queryKey: ['profileLocation'] });
            qc.invalidateQueries({ queryKey: ['weather'] });
            qc.invalidateQueries({ queryKey: ['weatherForecast'] });
            qc.invalidateQueries({ queryKey: ['airQuality'] });
            qc.invalidateQueries({ queryKey: ['environment'] });
            qc.invalidateQueries({ queryKey: ['dashboard'] });
            if (__DEV__) console.log(`[GPS] 城市更新: ${prevCity || '(空)'} → ${loc.city}`);
          }
        }
      } catch (e) {
        if (__DEV__) console.warn('[GPS] auto-refresh failed:', e);
      } finally {
        inFlightRef.current = false;
      }
    };

    // 启动时跑一次, 之后每次 foreground 触发
    tryRefresh();
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') tryRefresh();
    });
    return () => sub.remove();
  }, [enabled, qc]);
}
