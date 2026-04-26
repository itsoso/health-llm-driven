import { getActiveCards } from './actionCards';
import { listConsultations } from './consultations';
import { buildDataPrompts, fetchDataHealthStatus } from './dataHealth';
import { getTodayCoachFocus, type TodayCoachFocus } from './todayCoach';

export interface AgentAgendaItem {
  id: string;
  title: string;
  subtitle?: string;
  route?: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}

export interface AgentAgendaSection {
  key: 'watching' | 'waiting' | 'missing_data';
  title: string;
  items: AgentAgendaItem[];
}

export interface AgentAgenda {
  date: string;
  focus: TodayCoachFocus;
  sections: AgentAgendaSection[];
}

export async function getAgentAgenda(today: string): Promise<AgentAgenda> {
  const [focus, cards, consultations, dataHealth] = await Promise.all([
    getTodayCoachFocus(today),
    getActiveCards().catch(() => []),
    listConsultations(10).catch(() => []),
    fetchDataHealthStatus().catch(() => null),
  ]);

  const watching: AgentAgendaItem[] = cards
    .filter(card => !card.expires_at && !card.latest_assessment)
    .slice(0, 3)
    .map(card => ({
      id: `card-${card.id}`,
      title: card.title,
      subtitle: '正在执行',
      route: '/(tabs)/alerts',
    }));

  const waiting: AgentAgendaItem[] = [
    ...cards
      .filter(card => card.expires_at || card.latest_assessment)
      .slice(0, 3)
      .map(card => ({
        id: `verify-card-${card.id}`,
        title: card.title,
        subtitle: card.expires_at ? `验证 ${card.expires_at.slice(0, 10)}` : '已有评估',
        route: '/(tabs)/alerts',
        tone: 'warn' as const,
      })),
    ...consultations
      .filter(item => item.pending_count > 0 || item.verification_scheduled_at)
      .slice(0, 2)
      .map(item => ({
        id: `consult-${item.id}`,
        title: item.title,
        subtitle: item.verification_scheduled_at
          ? `预测复盘 ${item.verification_scheduled_at.slice(0, 10)}`
          : `${item.pending_count} 条待确认`,
        route: `/consultations/${item.id}`,
        tone: 'warn' as const,
      })),
  ];

  const missingData: AgentAgendaItem[] = buildDataPrompts(dataHealth)
    .slice(0, 3)
    .map(prompt => ({
      id: `data-${prompt.key}`,
      title: prompt.title,
      subtitle: prompt.body,
      route: prompt.route,
      tone: prompt.severity === 'blocking' ? 'bad' : 'warn',
    }));

  return {
    date: today,
    focus,
    sections: [
      { key: 'watching' as const, title: 'Agent 正在观察', items: watching },
      { key: 'waiting' as const, title: '等待验证', items: waiting },
      { key: 'missing_data' as const, title: '需要补证据', items: missingData },
    ].filter(section => section.items.length > 0),
  };
}
