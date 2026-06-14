import { useEffect, useRef } from 'react';
import { scheduleBehaviorLoopReminders } from '../services/behaviorLoopReminders';
import type { DailyOperatingPlan } from '../services/dailyPlan';
import type { InterventionCycle } from '../services/healthOs';

/**
 * 把「行为闭环」排成可操作本地通知（自动镜像到 Apple Watch）。
 * - plan / cycle 变化时重排（先 cancel 本类旧通知，再排新的）。
 * - 指纹去抖: 只看会影响通知内容/调度的字段（top action_key+title、cycle 状态/到期），
 *   避免 dashboard 每次刷新都重排。
 * - 无通知权限时 scheduleBehaviorLoopReminders 内部静默跳过（App 内卡片仍在）。
 */
export function useBehaviorLoopReminders(
  plan: DailyOperatingPlan | null | undefined,
  cycle: InterventionCycle | null | undefined,
  enabled: boolean,
) {
  const lastFingerprint = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    // plan 与 cycle 任一就绪即可调度；两者都未就绪（undefined）则等待。
    if (plan === undefined && cycle === undefined) return;

    const topAction = (plan?.actions ?? []).find((a) => Boolean(a?.title));
    const fingerprint = JSON.stringify([
      topAction?.action_key ?? null,
      topAction?.title ?? null,
      cycle?.id ?? null,
      cycle?.status ?? null,
      cycle?.planned_end_date ?? null,
    ]);
    if (fingerprint === lastFingerprint.current) return;
    lastFingerprint.current = fingerprint;

    scheduleBehaviorLoopReminders({ plan, cycle }).catch(() => {
      // 排程失败不影响 UI
    });
  }, [plan, cycle, enabled]);
}
