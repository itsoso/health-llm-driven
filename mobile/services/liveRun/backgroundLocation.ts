/**
 * Live Run 后台定位 — 基于 expo-task-manager + expo-location 的背景模式.
 *
 * 为什么需要:
 * - 前台 watchPositionAsync 切 App / 锁屏几秒就被 iOS suspend JS runtime,
 *   跑着跑着掏出手机发现距离停在 1.2km 三分钟前 → 断档的体验不能忍
 * - UIBackgroundModes: location 声明后 iOS 允许 App 在后台保持 location 订阅,
 *   TaskManager task 是这个模式下 callback 的合法载体
 *
 * 架构:
 * - 模块 load 时 TaskManager.defineTask 注册一个全局 task
 * - 收到 location 批量后 DeviceEventEmitter.emit 广播给订阅者
 * - useLiveRun 在 start 时 subscribe, stop 时 unsubscribe
 *
 * 注意:
 * - task handler 运行在非 React 环境, 直接 setState 会出问题; 只能 emit event
 * - App 被 swipe-kill 时 task 也死, 这是 Apple 的设计, 无解
 */
import * as TaskManager from 'expo-task-manager';
import * as Location from 'expo-location';
import { DeviceEventEmitter } from 'react-native';

export const LIVE_RUN_LOCATION_TASK = 'LIVE_RUN_LOCATION_TASK';
export const LIVE_RUN_LOCATION_EVENT = 'LiveRunLocation';

if (!TaskManager.isTaskDefined(LIVE_RUN_LOCATION_TASK)) {
  TaskManager.defineTask(LIVE_RUN_LOCATION_TASK, async ({ data, error }) => {
    if (error) {
      console.warn('[LiveRun bg-location] task error:', error);
      return;
    }
    if (!data) return;
    const { locations } = data as { locations: Location.LocationObject[] };
    if (!locations || !Array.isArray(locations)) return;
    for (const loc of locations) {
      DeviceEventEmitter.emit(LIVE_RUN_LOCATION_EVENT, loc);
    }
  });
}

/** 启动后台追踪. 返回 false 表示权限/启动失败, 调用方需 fallback. */
export async function startBackgroundTracking(): Promise<boolean> {
  try {
    const fg = await Location.requestForegroundPermissionsAsync();
    if (fg.status !== 'granted') return false;

    // Background 权限必须先有 foreground 才能请求
    const bg = await Location.requestBackgroundPermissionsAsync();
    const hasBg = bg.status === 'granted';
    // 没给 background 权限就降级, 只前台也能跑 (锁屏会断)

    const already = await Location.hasStartedLocationUpdatesAsync(LIVE_RUN_LOCATION_TASK);
    if (already) {
      await Location.stopLocationUpdatesAsync(LIVE_RUN_LOCATION_TASK);
    }

    await Location.startLocationUpdatesAsync(LIVE_RUN_LOCATION_TASK, {
      accuracy: Location.Accuracy.BestForNavigation,
      timeInterval: 1000,
      distanceInterval: 2,
      // 后台下 iOS 会显示蓝条 — 标题让用户知道 App 在用定位
      showsBackgroundLocationIndicator: true,
      activityType: Location.ActivityType.Fitness,
      foregroundService: {
        notificationTitle: '跑步进行中',
        notificationBody: '正在记录你的路线和配速',
        notificationColor: '#0A8F8F',
      },
      pausesUpdatesAutomatically: false,
    });
    return hasBg || true;
  } catch (e) {
    console.warn('[LiveRun bg-location] start failed:', e);
    return false;
  }
}

export async function stopBackgroundTracking(): Promise<void> {
  try {
    const running = await Location.hasStartedLocationUpdatesAsync(LIVE_RUN_LOCATION_TASK);
    if (running) {
      await Location.stopLocationUpdatesAsync(LIVE_RUN_LOCATION_TASK);
    }
  } catch (e) {
    console.warn('[LiveRun bg-location] stop failed:', e);
  }
}

export type LocationSubscription = { remove: () => void };

/** 订阅后台 task 广播的 location. */
export function subscribeLocation(cb: (loc: Location.LocationObject) => void): LocationSubscription {
  const sub = DeviceEventEmitter.addListener(LIVE_RUN_LOCATION_EVENT, cb);
  return { remove: () => sub.remove() };
}
