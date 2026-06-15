/**
 * 统一健康议程 service —— 消费后端 /agenda(R1)。
 * 协议待办 + 到期复查聚成一条 today;双轨完成经 /agenda/complete 路由写真实业务记录。
 *
 * 注:后端 /agenda、/protocols 端点尚未进 mobile/types/api.generated.ts(待 npm run generate-types)。
 * 本文件先手写最小契约,字段对齐 backend/app/services/agenda_service.py。
 */
import api from './api';

export interface AgendaSource {
  object_type: string; // health_protocol / health_problem
  object_id: number;
}

export interface AgendaItem {
  type: string; // hydration/medication/diet/checkup/...
  title: string;
  status: string; // pending/completed/skipped/due/overdue
  time_window?: string;
  priority: number;
  can_default_complete?: boolean;
  detail?: string;
  responsible?: string;
  next_due?: string;
  // 训练决策灯(type === 'training', status === 'info')专属字段
  light?: 'green' | 'yellow' | 'red';
  zone?: string;
  readiness_score?: number | null;
  confidence?: number;
  source: AgendaSource;
}

export interface AgendaToday {
  agenda_date: string;
  count: number;
  items: AgendaItem[];
}

export async function getAgendaToday(): Promise<AgendaToday> {
  const resp = await api.get<AgendaToday>('/agenda/today');
  return resp.data;
}

/** 统一完成:按 source 路由(协议→双轨写真实记录)。track 默认协议轨。 */
export async function completeAgendaItem(
  source: AgendaSource,
  track: 'protocol' | 'manual' = 'protocol',
): Promise<unknown> {
  const resp = await api.post('/agenda/complete', {
    object_type: source.object_type,
    object_id: source.object_id,
    track,
  });
  return resp.data;
}

/** 跳过(仅协议来源),带失败原因(R14)。 */
export async function skipProtocol(protocolId: number, reason?: string): Promise<unknown> {
  const resp = await api.post(`/protocols/${protocolId}/skip`, { reason: reason ?? null });
  return resp.data;
}

/** 该 agenda item 是否可由协议轨「一键完成」(协议来源且未完成)。 */
export function isProtocolActionable(item: AgendaItem): boolean {
  return item.source.object_type === 'health_protocol' && item.status === 'pending';
}

/** 一键试用:seed 一个 2000ml 温水杯协议 + 登记胃溃疡(Hp-),让议程立刻有内容。 */
export async function seedDemo(): Promise<void> {
  await api.post('/protocols/seed/water-cup');
  await api.post('/problems/seed/gastric-ulcer-hp-neg');
}
