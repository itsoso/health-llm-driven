import api from './api';

export type GoalType = 'weight' | 'exercise' | 'sleep' | 'nutrition' | 'habit' | 'health_metric' | 'custom';
export type GoalPeriod = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly';
export type GoalStatus = 'active' | 'completed' | 'paused' | 'abandoned';

export interface GoalResponse {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  goal_type: GoalType;
  period: GoalPeriod;
  target_value: number;
  current_value: number;
  unit: string;
  status: GoalStatus;
  start_date: string;
  end_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface GoalCreate {
  title: string;
  description?: string;
  goal_type: GoalType;
  period: GoalPeriod;
  target_value: number;
  current_value?: number;
  unit: string;
  start_date: string;
  end_date?: string;
}

export interface GoalProgressUpdate {
  value: number;
  notes?: string;
}

export interface GoalGuidance {
  goal_id: number;
  current_progress: number;
  target: number;
  suggestions: string[];
  on_track: boolean;
}

export async function getGoals(status?: GoalStatus): Promise<GoalResponse[]> {
  const { data } = await api.get<GoalResponse[]>('/goals/me', { params: status ? { status } : undefined });
  return data;
}

export async function createGoal(goal: GoalCreate): Promise<GoalResponse> {
  const { data } = await api.post<GoalResponse>('/goals/', goal);
  return data;
}

export async function updateGoalProgress(id: number, update: GoalProgressUpdate): Promise<GoalResponse> {
  const { data } = await api.post<GoalResponse>(`/goals/${id}/progress`, update);
  return data;
}

export async function deleteGoal(id: number): Promise<void> {
  await api.delete(`/goals/${id}`);
}

export async function generateGoalsFromAnalysis(): Promise<GoalResponse[]> {
  const { data } = await api.post<GoalResponse[]>('/goals/me/generate-from-analysis');
  return data;
}

export async function getGoalGuidance(id: number): Promise<GoalGuidance> {
  const { data } = await api.get<GoalGuidance>(`/goals/${id}/guidance`);
  return data;
}
