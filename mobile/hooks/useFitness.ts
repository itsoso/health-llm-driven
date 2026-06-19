/**
 * React Query hooks for 健身编排 + 动作指导 (P2 · proactive-planning PRD §3.C).
 *
 * C1 confirm/dismiss 镜像 WriteIntentCard 的交互(busy + 成功 haptic + 失效查询);
 * 这里只管数据 + mutation,haptic 留在屏幕里触发(与 WriteIntentCard 一致)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  confirmWeeklyFitnessPlan,
  dismissWeeklyFitnessPlan,
  getExerciseGuide,
  getExerciseGuideList,
  getWeeklyFitnessPlan,
  type ExerciseGuide,
  type ExerciseGuideListItem,
  type WeeklyFitnessPlan,
} from '../services/fitness';

export const WEEKLY_FITNESS_PLAN_KEY = ['fitness', 'weekly-plan'] as const;

export function useWeeklyFitnessPlan() {
  return useQuery<WeeklyFitnessPlan>({
    queryKey: WEEKLY_FITNESS_PLAN_KEY,
    queryFn: getWeeklyFitnessPlan,
    staleTime: 5 * 60 * 1000,
  });
}

export function useConfirmWeeklyFitnessPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: number) => confirmWeeklyFitnessPlan(planId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: WEEKLY_FITNESS_PLAN_KEY });
      // 确认后落时间线 → 失效今日/日程相关缓存,让首页时间线刷新。
      qc.invalidateQueries({ queryKey: ['schedule'] });
      qc.invalidateQueries({ queryKey: ['today-timeline'] });
    },
  });
}

export function useDismissWeeklyFitnessPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: number) => dismissWeeklyFitnessPlan(planId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: WEEKLY_FITNESS_PLAN_KEY });
    },
  });
}

export function useExerciseGuideList() {
  return useQuery<ExerciseGuideListItem[]>({
    queryKey: ['fitness', 'exercise-guide'],
    queryFn: getExerciseGuideList,
    staleTime: 30 * 60 * 1000,
  });
}

export function useExerciseGuide(exerciseKey: string | null) {
  return useQuery<ExerciseGuide>({
    queryKey: ['fitness', 'exercise-guide', exerciseKey],
    queryFn: () => getExerciseGuide(exerciseKey as string),
    enabled: !!exerciseKey,
    staleTime: 30 * 60 * 1000,
  });
}
