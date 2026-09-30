import api from './api';

export interface FamilyMember {
  id: number;
  can_view: boolean;
  can_edit: boolean;
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

export interface FamilyMembership {
  member_id: number;
  group_id: number;
  group_name: string;
  is_owner: boolean;
}

export interface FamilyDashboard {
  memberships: FamilyMembership[];
  is_owner: boolean;
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

/** 家人端: 输入码加入. relationship: father/mother/spouse/daughter/son/child/sibling/other */
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

export const FAMILY_RELATIONSHIPS: Record<string, string> = {
  self: '我', father: '爸爸', mother: '妈妈', spouse: '配偶',
  daughter: '女儿', son: '儿子', child: '孩子', sibling: '兄弟姐妹', other: '其他',
};

export interface FamilyIllnessUpdate {
  id: number;
  update_date: string;
  status: string | null;
  severity: number | null;
  notes: string | null;
}

export interface FamilyIllnessEpisode {
  id: number;
  name: string;
  start_date: string;
  end_date: string | null;
  status: string;
  severity: number | null;
  notes: string | null;
  updates: FamilyIllnessUpdate[];
}

export interface FamilyMemberHealth {
  member: Pick<FamilyMember, 'user_id' | 'name' | 'nickname' | 'relationship_type'>;
  reports: (Omit<import('./medicalExams').MedicalExam, 'items'> & {
    items: (import('./medicalExams').MedicalExamItem & { display_value: string })[];
  })[];
  episodes: FamilyIllnessEpisode[];
  limit: number;
}

/** Uses the viewer's existing session; the server validates read sharing. */
export async function fetchFamilyMemberHealth(userId: number): Promise<FamilyMemberHealth> {
  return (await api.get<FamilyMemberHealth>(`/family/members/${userId}/health`)).data;
}

export async function updateFamilyRelationship(memberId: number, relationshipType: string, nickname?: string) {
  return (await api.patch(`/family/members/${memberId}/relationship`, {
    relationship_type: relationshipType, nickname,
  })).data;
}

/** A member can withdraw sharing by leaving their group. */
export async function leaveFamily(memberId: number): Promise<void> {
  await api.delete(`/family/members/${memberId}`);
}
