import api from './api';

export type DataConnectionStatus =
  | 'connected'
  | 'authorized'
  | 'syncing'
  | 'stale'
  | 'error'
  | 'disconnected'
  | 'revoked'
  | string;

export interface DataConnection {
  id?: number | string;
  provider?: string | null;
  source?: string | null;
  name?: string | null;
  status?: DataConnectionStatus | null;
  sync_enabled?: boolean | null;
  last_sync_at?: string | null;
  updated_at?: string | null;
}

function normalizeConnections(data: unknown): DataConnection[] {
  if (Array.isArray(data)) return data.filter((item): item is DataConnection => item != null && typeof item === 'object');
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.connections)) return normalizeConnections(obj.connections);
    if (Array.isArray(obj.items)) return normalizeConnections(obj.items);
    if (Array.isArray(obj.data)) return normalizeConnections(obj.data);
  }
  return [];
}

export async function fetchDataConnections(): Promise<DataConnection[]> {
  try {
    const { data } = await api.get('/data-connections/me');
    return normalizeConnections(data);
  } catch {
    return [];
  }
}

export function connectionStatusSummary(connections?: DataConnection[] | null): string {
  const items = Array.isArray(connections) ? connections : [];
  if (items.length === 0) return '未连接';
  const enabled = items.filter((item) => item.sync_enabled !== false);
  const active = enabled.filter((item) => {
    const status = String(item.status || '').toLowerCase();
    return ['connected', 'authorized', 'syncing'].includes(status);
  });
  if (active.length > 0) return `${active.length}/${items.length} 已连接`;
  if (enabled.length > 0) return `${enabled.length}/${items.length} 待同步`;
  return '已关闭';
}
