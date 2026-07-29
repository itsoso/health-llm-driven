import api from './api';
import { todayStr } from '../utils/dietDate';

export type GoalType = 'diet' | 'exercise' | 'sleep' | 'water' | 'supplement' | 'outdoor' | 'weight' | 'other';
export type GoalPeriod = 'daily' | 'weekly' | 'monthly' | 'yearly';
export type GoalStatus = 'active' | 'completed' | 'paused' | 'cancelled';

export interface GoalResponse {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  goal_type: GoalType;
  goal_period: GoalPeriod;
  target_value: number | null;
  target_unit: string | null;
  current_value: number | null;
  status: GoalStatus;
  start_date: string;
  end_date: string | null;
  implementation_steps: string | null;
  priority: number | null;
  notes: string | null;
}

export interface GoalCreate {
  title: string;
  description?: string;
  goal_type: GoalType;
  goal_period: GoalPeriod;
  target_value?: number;
  target_unit?: string;
  start_date: string;
  end_date?: string;
  implementation_steps?: string;
  priority?: number;
  notes?: string;
}

export interface GoalGuidance {
  suggestions: string[];
  [key: string]: any;
}

export async function getGoals(status?: GoalStatus): Promise<GoalResponse[]> {
  const { data } = await api.get<GoalResponse[]>('/goals/me', { params: status ? { status } : undefined });
  return data;
}

export async function createGoal(goal: GoalCreate): Promise<GoalResponse> {
  const { data } = await api.post<GoalResponse>('/goals/', goal);
  return data;
}

export async function updateGoalProgress(id: number, progressValue: number): Promise<any> {
  const today = todayStr();
  const { data } = await api.post(`/goals/${id}/progress`, null, {
    params: { progress_date: today, progress_value: progressValue },
  });
  return data;
}

export async function generateGoalsFromAnalysis(): Promise<GoalResponse[]> {
  const { data } = await api.post<GoalResponse[]>('/goals/me/generate-from-analysis');
  return data;
}

export async function getGoalGuidance(goalType: string, description: string, targetValue?: number): Promise<GoalGuidance> {
  const { data } = await api.post<GoalGuidance>('/goals/guidance', {
    goal_type: goalType,
    goal_description: description,
    target_value: targetValue,
  });
  return data;
}
