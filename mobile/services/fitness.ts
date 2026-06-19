/**
 * 健身编排 + 动作指导客户端 (P2 · proactive-planning PRD §3.C).
 *
 * C1 周健身计划 (T2):MovementCoach 按目标 + ACWR 生成难/易/休 → 你一键确认排期。
 * C2 动作图文指导 (T0/T1):分解步骤 + 常见错误 + 伤病红线(降级就医),hedged 教练内容。
 *
 * 后端 = backend/app/api/fitness.py (并行开发中)。下面的接口手写,**字段名 + 类型严格对齐
 * 钉死的契约**(过往 sleep_hours vs total_sleep_minutes / float vs int 静默坏过)。
 *
 * TODO(P2): reconcile with generated types post-merge —— 后端 OpenAPI 就绪后跑
 * `npm run generate-types`,用 `components['schemas'][...]` 替换本文件手写 interface 并 diff。
 */
import api from './api';

// ── C1 周健身计划 ─────────────────────────────────────────────────────────────

export type FitnessDayType = 'hard' | 'easy' | 'rest';
export type WeeklyPlanStatus = 'proposed' | 'confirmed';

export interface FitnessWorkout {
  name: string;
  exercise_key: string; // links to C2; "" if none
  duration_min: number; // integer
  intensity_note: string;
}

export interface FitnessPlanDay {
  date: string; // "YYYY-MM-DD"
  weekday: string; // "周一"
  day_type: FitnessDayType;
  workout: FitnessWorkout | null; // null when rest
  rationale: string;
}

export interface WeeklyFitnessPlan {
  plan_id: number | null;
  status: WeeklyPlanStatus | null;
  week_start: string; // "YYYY-MM-DD"
  goal: string;
  acwr: number | null;
  readiness_note: string;
  days: FitnessPlanDay[]; // length 7
  disclaimer: string;
}

export interface ConfirmWeeklyPlanResult {
  confirmed: true;
  plan_id: number;
  scheduled_count: number;
}

export interface DismissWeeklyPlanResult {
  dismissed: true;
}

export async function getWeeklyFitnessPlan(): Promise<WeeklyFitnessPlan> {
  const { data } = await api.get<WeeklyFitnessPlan>('/fitness/weekly-plan');
  return data;
}

export async function confirmWeeklyFitnessPlan(
  planId: number,
): Promise<ConfirmWeeklyPlanResult> {
  const { data } = await api.post<ConfirmWeeklyPlanResult>(
    '/fitness/weekly-plan/confirm',
    { plan_id: planId },
  );
  return data;
}

export async function dismissWeeklyFitnessPlan(
  planId: number,
): Promise<DismissWeeklyPlanResult> {
  const { data } = await api.post<DismissWeeklyPlanResult>(
    '/fitness/weekly-plan/dismiss',
    { plan_id: planId },
  );
  return data;
}

// ── C2 动作图文指导 ────────────────────────────────────────────────────────────

export interface ExerciseGuideListItem {
  exercise_key: string;
  name: string;
}

export interface ExerciseGuide {
  exercise_key: string;
  name: string;
  steps: string[];
  common_mistakes: string[];
  injury_red_lines: string[];
  safety_note: string;
}

export async function getExerciseGuideList(): Promise<ExerciseGuideListItem[]> {
  const { data } = await api.get<{ exercises: ExerciseGuideListItem[] }>(
    '/fitness/exercise-guide',
  );
  return data?.exercises ?? [];
}

export async function getExerciseGuide(
  exerciseKey: string,
): Promise<ExerciseGuide> {
  const { data } = await api.get<ExerciseGuide>(
    `/fitness/exercise-guide/${encodeURIComponent(exerciseKey)}`,
  );
  return data;
}
