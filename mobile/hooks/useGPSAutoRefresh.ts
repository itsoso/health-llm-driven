/**
 * App foreground 时静默刷新 GPS 城市.
 *
 * 设计原则:
 * - 只在"已授权"时跑, 绝不主动弹权限 (用户第一次授权通过 /location 手动触发)
 * - 节流: 默认 30 分钟; 但每次 foreground 都会先取一次低精度坐标看是否
 *   显著漂移 (>50km), 漂移大就破节流强制刷 — 防"北京飞杭州 2h + 节流卡住"
 * - 静默失败: 定位不了 / 网络错 / 反查失败都不打扰用户
 * - 城市变化时才 invalidate 天气 cache, 减少无谓 refetch
 *
 * 解决的 badcase:
 *   1. (2026-05-08) 用户从杭州到北京后, profile.detected_city 还是"杭州",
 *      计划提醒 / 天气卡全部错位. 以前只有手动去 /location 页点 GPS 才刷.
 *   2. (2026-05-10) 第一次修复后仍有 case: 节流 4h 锁死, 用户飞行落地后
 *      节流没过期, 必须手动保存. 现在按坐标距离破节流, 30min + 50km 触发刷新.
 */
import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import * as Location from 'expo-location';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQueryClient } from '@tanstack/react-query';
import { updateGPSLocation, reverseGeocodeOnDevice } from '../services/location';
import { writeGPSRefreshStatus, type GPSRefreshStatus } from '../services/gpsRefreshStatus';
import { queryKeys } from '../applib/queryKeys';

const MIN_INTERVAL_MS = 30 * 60 * 1000;  // 30min 节流
const FORCE_REFRESH_KM = 50;             // 坐标漂移 >50km 直接破节流
const LAST_TS_KEY = 'gps_last_refresh_ts';
const LAST_CITY_KEY = 'gps_last_city';
const LAST_LAT_KEY = 'gps_last_lat';
const LAST_LON_KEY = 'gps_last_lon';

// Haversine: 球面两点距离 (km)
function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

export function useGPSAutoRefresh(enabled: boolean) {
  const qc = useQueryClient();
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    const recordStatus = async (status: GPSRefreshStatus) => {
      try {
        await writeGPSRefreshStatus(status);
      } catch (e) {
        if (__DEV__) console.warn('[GPS] refresh status persistence failed:', e);
      }
    };

    const tryRefresh = async () => {
      if (inFlightRef.current) return;

      // 1. 只在已授权情况下跑, 不主动弹权限
      try {
        const { status } = await Location.getForegroundPermissionsAsync();
        if (status !== 'granted') {
          await recordStatus({ state: 'permission_required' });
          return;
        }
      } catch {
        await recordStatus({ state: 'error', errorKind: 'permission_check' });
        return;
      }

      // 2. 先拿一次坐标 (最低精度, 城市级 50km 阈值够用) — 用于判断漂移
      let pos: Location.LocationObject;
      try {
        pos = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Lowest,
        });
      } catch (e) {
        if (__DEV__) console.warn('[GPS] getCurrentPosition failed:', e);
        await recordStatus({ state: 'error', errorKind: 'location' });
        return;
      }

      // 3. 节流判断: 30min 内且坐标没怎么动, 跳过. 漂移 >50km 直接破节流.
      try {
        const lastTs = await AsyncStorage.getItem(LAST_TS_KEY);
        const lastLatStr = await AsyncStorage.getItem(LAST_LAT_KEY);
        const lastLonStr = await AsyncStorage.getItem(LAST_LON_KEY);
        const ageMs = lastTs ? Date.now() - Number(lastTs) : Infinity;

        if (ageMs < MIN_INTERVAL_MS && lastLatStr && lastLonStr) {
          const drift = distanceKm(
            Number(lastLatStr), Number(lastLonStr),
            pos.coords.latitude, pos.coords.longitude,
          );
          if (drift < FORCE_REFRESH_KM) {
            if (__DEV__) console.log(`[GPS] 节流跳过: age=${Math.round(ageMs / 60000)}min drift=${drift.toFixed(1)}km`);
            await recordStatus({ state: 'ready' });
            return;
          }
          if (__DEV__) console.log(`[GPS] 漂移破节流: drift=${drift.toFixed(1)}km`);
        }
      } catch {
        // 旁路: AsyncStorage 读失败 → 当作没节流, 继续刷新.
      }

      await recordStatus({ state: 'refreshing' });

      // 4. 客户端先反查 city (CLGeocoder 离线可用), 给 backend hint 让它跳过 qweather.
      //    失败不阻断 — backend 会自己用 qweather 兜底, 或没 city 也能正常存 lat/lon.
      const hint = await reverseGeocodeOnDevice(pos.coords.latitude, pos.coords.longitude);

      // 5. 真去后端反查 + 更新 detected_city
      inFlightRef.current = true;
      try {
        const loc = await updateGPSLocation(pos.coords.latitude, pos.coords.longitude, hint);
        await AsyncStorage.multiSet([
          [LAST_TS_KEY, String(Date.now())],
          [LAST_LAT_KEY, String(pos.coords.latitude)],
          [LAST_LON_KEY, String(pos.coords.longitude)],
        ]);

        // GPS 反查成功 → 一律清天气/AQI/dashboard cache. 后端已清 server-side
        // cache, 这里同步清 React Query, 否则 stale UI 会继续显示旧城市数据.
        // 不依赖 city 变化判断 — 即使 city 字符串没变 (北京→朝阳→北京), 经纬度
        // 也已变, 后端 forecast 数据可能更新.
        qc.invalidateQueries({ queryKey: ['profileLocation'] });
        qc.invalidateQueries({ queryKey: ['effectiveLocation'] });
        qc.invalidateQueries({ queryKey: queryKeys.profile });
        qc.invalidateQueries({ queryKey: ['weather'] });
        qc.invalidateQueries({ queryKey: ['weatherForecast'] });
        qc.invalidateQueries({ queryKey: ['airQuality'] });
        qc.invalidateQueries({ queryKey: ['environment'] });
        qc.invalidateQueries({ queryKey: ['dashboard'] });

        if (loc.city) {
          const prevCity = await AsyncStorage.getItem(LAST_CITY_KEY);
          if (prevCity !== loc.city) {
            await AsyncStorage.setItem(LAST_CITY_KEY, loc.city);
            if (__DEV__) console.log(`[GPS] 城市更新: ${prevCity || '(空)'} → ${loc.city}`);
          }
        }
        await recordStatus({ state: 'ready', lastSuccessAt: Date.now() });
      } catch (e) {
        if (__DEV__) console.warn('[GPS] auto-refresh failed:', e);
        await recordStatus({ state: 'error', errorKind: 'network_or_server' });
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
