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
  const resp = await api.get<FamilyDashboard>('/family/dashboard');
  return resp.data;
}

// ────── G Phase 2: 邀请码 ──────

export interface InviteCode {
  code: string;
  expires_in_seconds: number;
  group_name: string;
}

/** 主人端: 拿邀请码 (30min TTL, 同一组内 30min 内复用) */
export async function createFamilyInvitation(): Promise<InviteCode> {
  const resp = await api.post<InviteCode>('/family/invitation/create');
  return resp.data;
}

export interface InviteAcceptResp {
  message: string;
  group_name: string;
  member_id: number;
  relationship_type?: string;
}

/** 家人端: 输入码加入. relationship: father/mother/spouse/child/sibling/other */
export async function acceptFamilyInvitation(
  code: string,
  relationshipType: string,
  nickname?: string,
): Promise<InviteAcceptResp> {
  const resp = await api.post<InviteAcceptResp>('/family/invitation/accept', {
    code,
    relationship_type: relationshipType,
    nickname,
  });
  return resp.data;
}

/** 创建家庭组 (主人没创建过组时调一次) */
export async function createFamilyGroup(name: string): Promise<{ id: number; name: string }> {
  const resp = await api.post<{ id: number; name: string }>('/family/groups', { name });
  return resp.data;
}
