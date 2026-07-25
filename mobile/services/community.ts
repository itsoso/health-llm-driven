import api from './api';

export type CommunityReaction = 'support' | 'same_path' | 'learned';

export interface CommunityDietSnapshot {
  meal_type: string;
  record_date: string;
  food_items: string;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
}

export interface CommunityPost {
  id: number;
  anonymous_name: string;
  source_type: 'diet_record';
  snapshot: CommunityDietSnapshot;
  caption: string | null;
  status: 'active' | 'under_review' | 'deleted';
  reaction_counts: Record<CommunityReaction, number>;
  my_reaction: CommunityReaction | null;
  is_owner: boolean;
  created_at: string;
}

export async function listCommunityPosts({
  limit = 20,
  beforeId,
}: {
  limit?: number;
  beforeId?: number;
} = {}): Promise<CommunityPost[]> {
  const { data } = await api.get<{ items: CommunityPost[] }>('/community/posts', {
    params: {
      limit,
      ...(beforeId ? { before_id: beforeId } : {}),
    },
  });
  return data.items;
}

export async function getCommunityPostForDietRecord(
  recordId: number,
): Promise<CommunityPost | null> {
  try {
    const { data } = await api.get<CommunityPost>(
      `/community/posts/source/diet_record/${recordId}`,
    );
    return data;
  } catch (error: any) {
    if (error?.response?.status === 404) return null;
    throw error;
  }
}

export async function publishDietRecordToCommunity(
  recordId: number,
  caption: string,
  idempotencyKey: string,
): Promise<CommunityPost> {
  const { data } = await api.post<CommunityPost>('/community/posts', {
    source_type: 'diet_record',
    source_id: recordId,
    caption: caption.trim() || undefined,
    idempotency_key: idempotencyKey,
  });
  return data;
}

export async function setCommunityReaction(
  postId: number,
  reaction: CommunityReaction,
): Promise<CommunityPost> {
  const { data } = await api.put<CommunityPost>(`/community/posts/${postId}/reaction`, { reaction });
  return data;
}

export async function removeCommunityReaction(postId: number): Promise<CommunityPost> {
  const { data } = await api.delete<CommunityPost>(`/community/posts/${postId}/reaction`);
  return data;
}

export async function deleteCommunityPost(postId: number): Promise<void> {
  await api.delete(`/community/posts/${postId}`);
}

export async function reportCommunityPost(
  postId: number,
  reason: string,
): Promise<{ report_count: number; status: string }> {
  const { data } = await api.post<{ report_count: number; status: string }>(
    `/community/posts/${postId}/report`,
    { reason },
  );
  return data;
}
