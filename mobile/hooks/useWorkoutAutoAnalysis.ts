import { useEffect, useState } from 'react';
import {
  getPostWorkoutAnalysis,
  type PostWorkoutAnalysisResponse,
  type WorkoutAnalysis,
  type WorkoutDetail,
} from '../services/workouts';

type WorkoutAnalysisSource = Pick<WorkoutDetail, 'id' | 'ai_analysis'>;

function parseAnalysis(raw: string | null): WorkoutAnalysis | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as WorkoutAnalysis;
  } catch {
    return null;
  }
}

export function useWorkoutAutoAnalysis({
  workoutId,
  workout,
}: {
  workoutId: number;
  workout: WorkoutAnalysisSource | null | undefined;
}) {
  const [analysis, setAnalysis] = useState<WorkoutAnalysis | null>(null);
  const [postAnalysis, setPostAnalysis] = useState<PostWorkoutAnalysisResponse | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const sourceWorkoutId = workout?.id ?? 0;
  const sourceAnalysis = workout?.ai_analysis ?? null;
  const hasWorkout = Boolean(workout);

  useEffect(() => {
    let active = true;
    const cachedAnalysis = parseAnalysis(sourceAnalysis);

    setAnalysis(cachedAnalysis);
    setPostAnalysis(null);
    setFromCache(Boolean(cachedAnalysis));

    if (!hasWorkout || !workoutId) {
      return () => {
        active = false;
      };
    }

    void getPostWorkoutAnalysis(workoutId, false, true)
      .then((result) => {
        if (!active || !result.success) return;
        setPostAnalysis(result);
        setFromCache(true);
      })
      .catch(() => {
        // The detail remains usable with its stored analysis when refresh fails.
      });

    return () => {
      active = false;
    };
  }, [hasWorkout, sourceAnalysis, sourceWorkoutId, workoutId]);

  return {
    analysis,
    postAnalysis,
    setPostAnalysis,
    fromCache,
    setFromCache,
  };
}
