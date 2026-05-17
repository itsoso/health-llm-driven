/**
 * iOS BackgroundFetch — best-effort 后台位置刷新.
 *
 * 这是 plan 的 L2 通道 (锦上添花). 主保障是后端 `get_fresh_city` (L1, Celery
 * 任务读 city 时自动用 last_ip 重跑 IP geo). 这里希望 iOS 调度 app 后台运行
 * 一次, 拿 GPS + 反查后写入 detected_*, 让早晨推送拿到 GPS 精度的城市.
 *
 * 关于 iOS 调度的现实预期:
 * - Apple 不保证间隔. 最小是 15 分钟, 实际经常几小时, Low Power Mode 直接停.
 * - 用户行为模式决定调度优先级 — 高频用 app 的用户更容易被调度.
 * - 这意味着: 这个任务"经常不跑"是正常的, 不是 bug. L1 服务端 fallback 兜底.
 *
 * 设计原则:
 * - 全静默: 失败/无权限/无定位都安静 return, 不弹通知, 不打扰用户.
 * - 25s 超时: iOS 给 30s, 留 5s buffer 给清理.
 * - 失败不报错, 返 NoData; iOS 会下调调度频率以省电.
 */
import * as TaskManager from 'expo-task-manager';
import * as BackgroundFetch from 'expo-background-fetch';
import * as Location from 'expo-location';
import { updateGPSLocation, reverseGeocodeOnDevice } from './location';

export const BACKGROUND_LOCATION_TASK = 'BACKGROUND_LOCATION_REFRESH';

// 注册任务定义 — module load 时就跑, 必须在 React 树挂载之前.
// 包 try/catch 防热重载重复 define 时炸.
try {
  TaskManager.defineTask(BACKGROUND_LOCATION_TASK, async () => {
    try {
      // 权限检查 — 用户可能在系统设置撤销, 静默退出.
      const { status } = await Location.getForegroundPermissionsAsync();
      if (status !== 'granted') return BackgroundFetch.BackgroundFetchResult.NoData;

      // iOS 给的总时间约 30s. 整个流程留 25s buffer.
      // getCurrentPositionAsync 最久的一步, 用最低精度尽快返回.
      const positionPromise = Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Lowest,
      });
      const timeout = new Promise<null>(resolve => setTimeout(() => resolve(null), 20_000));
      const pos = (await Promise.race([positionPromise, timeout])) as Location.LocationObject | null;
      if (!pos) return BackgroundFetch.BackgroundFetchResult.NoData;

      const hint = await reverseGeocodeOnDevice(pos.coords.latitude, pos.coords.longitude);
      await updateGPSLocation(pos.coords.latitude, pos.coords.longitude, hint);
      return BackgroundFetch.BackgroundFetchResult.NewData;
    } catch {
      return BackgroundFetch.BackgroundFetchResult.Failed;
    }
  });
} catch {
  // 热重载二次 define 会抛 'Task ... is already defined'; 忽略.
}

/**
 * App 启动 + 已认证后调一次. 幂等 — 已注册会 noop.
 *
 * iOS 上 minimumInterval 是建议值, 实际由 iOS 决定. 给 60min 让 iOS 知道我们不急.
 * Android 不接 (UIBackgroundModes 只对 iOS 生效, Android 走另一套 — 这次不做).
 */
export async function registerBackgroundLocationTask(): Promise<void> {
  try {
    // 权限没拿到不注册 — 注册了也跑不通, 反而占 iOS 调度配额.
    const { status } = await Location.getForegroundPermissionsAsync();
    if (status !== 'granted') return;

    const isRegistered = await TaskManager.isTaskRegisteredAsync(BACKGROUND_LOCATION_TASK);
    if (isRegistered) return;

    await BackgroundFetch.registerTaskAsync(BACKGROUND_LOCATION_TASK, {
      minimumInterval: 60 * 60, // 1h 建议值
      stopOnTerminate: false,   // app 被杀也继续 (iOS 上无效, 此处为兼容)
      startOnBoot: false,
    });
  } catch {
    // 静默 — 后台 fetch 完全是 best-effort, 注册失败不影响 app 正常用.
  }
}
