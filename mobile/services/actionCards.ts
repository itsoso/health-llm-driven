import api from './api';
import type { SafetyAlert } from './safety';

export interface ActionCard {
  id: number;
  title: string;
  content: string;
  card_type: string;
  status: string;
  priority: number;
  created_at: string;
  expires_at?: string | null;
  completed_at?: string | null;
  checklist?: Array<{ item: string; done: boolean }>;
  latest_assessment?: {
    score?: number;
    summary?: string;
    evidence?: string[];
    adjustments?: string[];
  } | null;
  source_type?: string;
  source_id?: string | null;
}

export interface ActionCardCreateInput {
  title: string;
  content: string;
  card_type?: string;
  color?: string;
  source_type?: string;
  source_id?: string | null;
  priority?: number;
  expires_at?: string | null;
}

export type ActionCockpitItem =
  | { type: 'alert'; item: SafetyAlert }
  | { type: 'card'; item: ActionCard };

export interface ActionCockpitSection {
  title: '需要立即处理' | '正在执行' | '等待验证' | '日常提示';
  data: ActionCockpitItem[];
}

function getSeverityKey(severity: unknown): string {
  return typeof severity === 'string' ? severity : (severity as { label?: string } | undefined)?.label ?? 'info';
}

export function getActionCardProgress(card: ActionCard): { completed: number; total: number } | null {
  if (!Array.isArray(card.checklist) || card.checklist.length === 0) return null;
  return {
    completed: card.checklist.filter(item => item.done).length,
    total: card.checklist.length,
  };
}

export function getActionCardVerificationLabel(card: ActionCard): string | null {
  if (card.latest_assessment?.score != null) {
    return `已评估 ${card.latest_assessment.score}/10`;
  }
  if (card.expires_at) {
    return `待验证 ${card.expires_at.slice(0, 10)}`;
  }
  return null;
}

export function buildActionCockpitSections(
  alerts: SafetyAlert[] = [],
  cards: ActionCard[] = [],
): ActionCockpitSection[] {
  const sortedAlerts = [...alerts].sort((a, b) => {
    const order = ['critical', 'high', 'medium', 'low', 'info'];
    return order.indexOf(getSeverityKey(a.severity)) - order.indexOf(getSeverityKey(b.severity));
  });

  const immediateAlerts = sortedAlerts.filter(alert => ['critical', 'high'].includes(getSeverityKey(alert.severity)));
  const dailyAlerts = sortedAlerts.filter(alert => !['critical', 'high'].includes(getSeverityKey(alert.severity)));
  const verificationCards = cards.filter(card => card.latest_assessment || card.expires_at);
  const activeCards = cards.filter(card => !card.latest_assessment && !card.expires_at);

  return [
    { title: '需要立即处理' as const, data: immediateAlerts.map(item => ({ type: 'alert' as const, item })) },
    { title: '正在执行' as const, data: activeCards.map(item => ({ type: 'card' as const, item })) },
    { title: '等待验证' as const, data: verificationCards.map(item => ({ type: 'card' as const, item })) },
    { title: '日常提示' as const, data: dailyAlerts.map(item => ({ type: 'alert' as const, item })) },
  ].filter(section => section.data.length > 0);
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

export async function createActionCard(input: ActionCardCreateInput): Promise<ActionCard> {
  const { data } = await api.post<ActionCard>('/action-cards', input);
  return data;
}
