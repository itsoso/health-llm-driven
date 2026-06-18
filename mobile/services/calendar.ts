/**
 * CalDAV 日历连接客户端。后端 /api/v1/calendar/*。
 * 用户在 App 自填 CalDAV 地址/账号/应用专用密码 → 后端加密存 + 同步忙碌块 → 时点求解器避开会议。
 * 端点未进 api.generated.ts(契约漂移待补 CI 闸),此处手写镜像后端 schema。
 */
import api from './api';

export interface CalendarStatus {
  connected: boolean;
  sync_enabled?: boolean;
  last_sync_at?: string | null;
  last_error?: string | null;
  busy_today?: number;
}

export async function getCalendarStatus(): Promise<CalendarStatus> {
  const { data } = await api.get('/calendar/status');
  return data;
}

/** 保存 CalDAV 凭据(用户自填;地址须 https)。后端加密存。 */
export async function saveCalendarCredentials(url: string, username: string, password: string): Promise<void> {
  await api.put('/calendar/credentials', { url, username, password });
}

/** 立即同步今日忙碌块。返回 {synced} 或抛(后端 422)。 */
export async function syncCalendar(): Promise<{ synced?: number; skipped?: string }> {
  const { data } = await api.post('/calendar/sync');
  return data;
}
