import api from './api';

export interface ActionCard {
  id: number;
  title: string;
  content: string;
  card_type: string;
  status: string;
  priority: number;
  created_at: string;
  source?: string;
}

export async function getActiveCards(): Promise<ActionCard[]> {
  const { data } = await api.get<ActionCard[]>(
    '/action-cards/me?status=active&limit=20',
  );
  return data;
}

export async function completeCard(id: number): Promise<ActionCard> {
  const { data } = await api.patch<ActionCard>(`/action-cards/${id}`, {
    status: 'completed',
  });
  return data;
}
