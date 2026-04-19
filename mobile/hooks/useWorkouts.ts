import { useQuery } from '@tanstack/react-query';
import { getWorkouts, getWorkoutStats, getWorkoutDetail, type WorkoutSummary, type WorkoutStats, type WorkoutDetail } from '@/services/workouts';

export function useWorkoutList(limit = 20) {
  return useQuery<WorkoutSummary[]>({
    queryKey: ['workouts', limit],
    queryFn: () => getWorkouts(limit),
    staleTime: 120_000,
  });
}

export function useWorkoutStats(days = 30) {
  return useQuery<WorkoutStats>({
    queryKey: ['workoutStats', days],
    queryFn: () => getWorkoutStats(days),
    staleTime: 120_000,
  });
}

export function useWorkoutDetail(id: number) {
  return useQuery<WorkoutDetail>({
    queryKey: ['workout', id],
    queryFn: () => getWorkoutDetail(id),
    enabled: id > 0,
    staleTime: 300_000,
  });
}
