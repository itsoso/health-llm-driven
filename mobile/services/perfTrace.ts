/**
 * Cold-start 性能埋点 (2026-05-29).
 *
 * 目标: 测"app 启动 → 首页 critical query 全部到位"的时间。
 *
 * 用法:
 *   - mobile/app/_layout.tsx 顶层 import 一次, 自动 markAppLaunch()
 *   - 首页 useHomeColdStartTrace({ twin, safety, dailyPlan, dashboard })
 *
 * 触发条件:
 *   - 每次进程启动后, **首页**第一次被装载时计时
 *   - 4 个 critical query 全部 success / data 就绪 → emit 一次 home_cold_start_perf
 *   - 5 秒内没全到位也 emit (timeout 兜底, 标记 incomplete=true)
 *   - 整个进程生命周期只 emit 一次, 后续重进首页不重复发
 */

import { useEffect, useRef } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { emitClientEvent } from './clientEvents';

const _appLaunchEpoch = Date.now();
let _coldStartEmitted = false;

export function getAppLaunchEpoch(): number {
  return _appLaunchEpoch;
}

export function msSinceLaunch(): number {
  return Date.now() - _appLaunchEpoch;
}

interface CriticalQueries {
  twin: UseQueryResult<unknown>;
  safety: UseQueryResult<unknown>;
  dailyPlan: UseQueryResult<unknown>;
  dashboard: UseQueryResult<unknown>;
}

const TIMEOUT_MS = 5000;

export function useHomeColdStartTrace(q: CriticalQueries) {
  const sawSuccessAt = useRef<Record<string, number>>({});

  // 各 query 首次进入 success 时记录耗时, 不依赖渲染顺序
  useEffect(() => {
    if (_coldStartEmitted) return;
    const now = msSinceLaunch();
    if (q.twin.isSuccess && !sawSuccessAt.current.twin) sawSuccessAt.current.twin = now;
    if (q.safety.isSuccess && !sawSuccessAt.current.safety) sawSuccessAt.current.safety = now;
    if (q.dailyPlan.isSuccess && !sawSuccessAt.current.dailyPlan) sawSuccessAt.current.dailyPlan = now;
    if (q.dashboard.isSuccess && !sawSuccessAt.current.dashboard) sawSuccessAt.current.dashboard = now;
  }, [q.twin.isSuccess, q.safety.isSuccess, q.dailyPlan.isSuccess, q.dashboard.isSuccess]);

  // 全到位 OR 超时 → emit
  useEffect(() => {
    if (_coldStartEmitted) return;
    const allDone =
      q.twin.isSuccess && q.safety.isSuccess && q.dailyPlan.isSuccess && q.dashboard.isSuccess;
    if (allDone) {
      _emit({ ...sawSuccessAt.current, incomplete: false });
    }
  }, [q.twin.isSuccess, q.safety.isSuccess, q.dailyPlan.isSuccess, q.dashboard.isSuccess]);

  // 5s 兜底: 不管谁还没回都先 emit
  useEffect(() => {
    if (_coldStartEmitted) return;
    const t = setTimeout(() => {
      if (_coldStartEmitted) return;
      _emit({ ...sawSuccessAt.current, incomplete: true });
    }, TIMEOUT_MS);
    return () => clearTimeout(t);
  }, []);
}

function _emit(payload: Record<string, unknown>) {
  if (_coldStartEmitted) return;
  _coldStartEmitted = true;
  const fullPayload = {
    ...payload,
    emitted_at_ms: msSinceLaunch(),
  };
  if (__DEV__) {
    // eslint-disable-next-line no-console
    console.log('[perf.home.cold_start]', fullPayload);
  }
  // 后端 /client-events 会落盘到 client_events 表, 可用 SQL 聚合统计
  emitClientEvent('home_cold_start_perf' as any, fullPayload);
}
