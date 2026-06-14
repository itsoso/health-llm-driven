import { api } from './client';

export interface DailyPlanAction {
  action_key?: string | null;
  domain?: string | null;
  title: string;
  why?: string | null;
  when?: string | null;
}

export interface DailyPlanActionProgress {
  completed_count?: number;
  handled_count?: number;
  remaining_count?: number;
  completed_action_keys?: string[];
  terminal_action_keys?: string[];
}

export interface DailyOperatingPlan {
  id?: number | null;
  plan_date: string;
  primary_goal?: string | null;
  status?: string | null;
  state_summary: Record<string, unknown> & {
    action_progress?: DailyPlanActionProgress | null;
  };
  actions: DailyPlanAction[];
}

export function formatDailyPlanActionProgress(progress?: DailyPlanActionProgress | null): string | null {
  if (!progress) return null;
  const completedCount = Number.isFinite(progress.completed_count) ? progress.completed_count ?? 0 : 0;
  const handledCount = Number.isFinite(progress.handled_count) ? progress.handled_count ?? 0 : completedCount;
  const remainingCount = Number.isFinite(progress.remaining_count) ? progress.remaining_count ?? 0 : 0;
  const otherHandled = Math.max(0, handledCount - completedCount);
  return otherHandled > 0
    ? `今日闭环 ${completedCount} 完成 · ${otherHandled} 已处理 · ${remainingCount} 待做`
    : `今日闭环 ${completedCount} 完成 · ${remainingCount} 待做`;
}

export const dailyPlanApi = {
  async getMine(): Promise<DailyOperatingPlan> {
    const { data } = await api.get<DailyOperatingPlan>('/daily-plan/me');
    return {
      ...data,
      actions: Array.isArray(data.actions) ? data.actions : [],
      state_summary: data.state_summary ?? {},
    };
  },
};
