import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { getGoals, updateGoalProgress, type GoalResponse, type GoalProgressUpdate, type GoalStatus } from '@/services/goals';

export function useGoals(status?: GoalStatus) {
  return useQuery<GoalResponse[]>({
    queryKey: ['goals', status],
    queryFn: () => getGoals(status),
    staleTime: 120_000,
  });
}

export function useUpdateGoalProgress() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, update }: { id: number; update: GoalProgressUpdate }) =>
      updateGoalProgress(id, update),
    onMutate: async ({ id, update }) => {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      await qc.cancelQueries({ queryKey: ['goals'] });
      const prev = qc.getQueryData<GoalResponse[]>(['goals']);
      if (prev) {
        qc.setQueryData<GoalResponse[]>(['goals'], old =>
          (old || []).map(g => g.id === id ? { ...g, current_value: update.value } : g),
        );
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['goals'], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['goals'] });
    },
  });
}
