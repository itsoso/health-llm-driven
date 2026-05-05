import api from './api';

export interface FamilyMember {
  user_id: number;
  name: string | null;
  nickname: string | null;
  relationship_type: string;
  is_managed: boolean;
  latest_weight: number | null;
  today_steps: number | null;
  sleep_score: number | null;
  resting_hr: number | null;
  today_water_ml: number;
  unread_alerts: number;
}

export interface FamilyDashboard {
  group_name: string | null;
  members: FamilyMember[];
}

export async function fetchFamilyDashboard(): Promise<FamilyDashboard> {
  const resp = await api.get<FamilyDashboard>('/v1/family/dashboard');
  return resp.data;
}
