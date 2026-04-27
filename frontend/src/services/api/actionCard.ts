import api from './client';

export interface ActionCard {
  id: number;
  title: string;
  content: string;
  card_type: 'plan' | 'insight' | 'recommendation' | 'note' | 'guide';
  color: string | null;
  source_type: 'conversation' | 'orchestrator' | 'manual';
  source_id: string | null;
  status: 'active' | 'completed' | 'archived';
  priority: number;
  expires_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  // 信任循环字段
  metric_key?: string | null;
  baseline_value?: string | null;
  target_value?: string | null;
  verification_days?: number | null;
  creator_specialist?: string | null;
  check_back_date?: string | null;
  actual_value?: string | null;
  accuracy_score?: number | null;
  graded_at?: string | null;
  grading_notes?: string | null;
}

export const getMyActionCards = async (
  status: string = 'active',
  limit: number = 20
): Promise<ActionCard[]> => {
  const res = await api.get('/action-cards/me', { params: { status, limit } });
  return res.data;
};

export const createActionCard = async (data: {
  title: string;
  content: string;
  card_type?: string;
  color?: string;
  source_type?: string;
  source_id?: string;
  priority?: number;
}): Promise<ActionCard> => {
  const res = await api.post('/action-cards', data);
  return res.data;
};

export const pinMessageToCard = async (data: {
  content: string;
  source_id?: string;
  card_type?: string;
}): Promise<ActionCard> => {
  const res = await api.post('/action-cards/from-message', data);
  return res.data;
};

export const updateActionCard = async (
  cardId: number,
  data: {
    title?: string;
    status?: string;
    priority?: number;
    is_visible?: boolean;
    color?: string;
  }
): Promise<ActionCard> => {
  const res = await api.patch(`/action-cards/${cardId}`, data);
  return res.data;
};

export const archiveActionCard = async (cardId: number): Promise<void> => {
  await api.delete(`/action-cards/${cardId}`);
};
