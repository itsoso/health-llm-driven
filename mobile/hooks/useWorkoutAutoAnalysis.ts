import { useEffect, useState } from 'react';
import { useAuth } from './useAuth';
import {
  getPostWorkoutAnalysis,
  type PostWorkoutAnalysisResponse,
  type WorkoutAnalysis,
  type WorkoutDetail,
} from '../services/workouts';

type WorkoutAnalysisSource = Pick<WorkoutDetail, 'id' | 'user_id' | 'ai_analysis' | 'post_workout_analysis'>;

function parseAnalysis(raw: string | null): WorkoutAnalysis | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as WorkoutAnalysis;
  } catch {
    return null;
  }
}

function parseStoredPostAnalysis(raw: string | null): PostWorkoutAnalysisResponse | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        (value as Record<string, unknown>).success !== true) return null;
    return value as PostWorkoutAnalysisResponse;
  } catch { return null; }
}

export function useWorkoutAutoAnalysis({
  workoutId,
  workout,
}: {
  workoutId: number;
  workout: WorkoutAnalysisSource | null | undefined;
}) {
  const { user, token } = useAuth();
  const [cacheReadError, setCacheReadError] = useState(false);
  const scope = `${user?.id ?? ''}:${token ?? ''}:${workoutId}`;
  const [loadedScope, setLoadedScope] = useState(scope);
  const [analysis, setAnalysis] = useState<WorkoutAnalysis | null>(null);
  const [postAnalysis, setPostAnalysis] = useState<PostWorkoutAnalysisResponse | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const sourceWorkoutId = workout?.id ?? 0;
  const sourceAnalysis = workout?.ai_analysis ?? null;
  const sourcePostAnalysis = workout?.post_workout_analysis ?? null;
  const hasWorkout = Boolean(user?.id && token && workout?.user_id === user.id && sourceWorkoutId === workoutId);

  useEffect(() => {
    let active = true;
    const cachedAnalysis = hasWorkout ? parseAnalysis(sourceAnalysis) : null;
    const storedPost = hasWorkout ? parseStoredPostAnalysis(sourcePostAnalysis) : null;
    setLoadedScope(scope);
    setCacheReadError(false);

    setAnalysis(cachedAnalysis);
    setPostAnalysis(storedPost);
    setFromCache(Boolean(cachedAnalysis || storedPost));

    if (!hasWorkout || !workoutId) {
      return () => {
        active = false;
      };
    }

    void getPostWorkoutAnalysis(workoutId, false, true)
      .then((result) => {
        if (!active) return;
        if (!result.success) {
          setCacheReadError(result.has_cache !== false || Boolean(storedPost));
          return;
        }
        setPostAnalysis(result);
        setFromCache(true);
      })
      .catch(() => {
        if (active) setCacheReadError(true); // Keep stored content; surface refresh failure.
      });

    return () => {
      active = false;
    };
  }, [hasWorkout, sourceAnalysis, sourcePostAnalysis, sourceWorkoutId, workoutId, scope]);

  return {
    analysis: hasWorkout && loadedScope === scope ? analysis : null,
    postAnalysis: hasWorkout && loadedScope === scope ? postAnalysis : null,
    cacheReadError: hasWorkout && loadedScope === scope && cacheReadError,
    setPostAnalysis,
    fromCache,
    setFromCache,
  };
}
