/**
 * 日历(Calendar v2 / C2)客户端。后端 /api/v1/calendar/*。
 * 多源管理(CalDAV / ICS)+ 详细事件读取(本人客户端,解密明细)。
 * 端点未进 api.generated.ts(契约漂移待补 CI 闸),此处手写镜像后端 schema
 * (backend/app/api/calendar.py · models/calendar_sync.py · services/caldav_sync.py)。
 *
 * 只读:create/edit/write-back 是 C3,本文件不含。
 */
import api from './api';

// ── 状态(旧单源端点,沿用)────────────────────────────────────────────────
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

/** 保存 CalDAV 凭据(旧单源端点;多源走 addCalendarSource)。 */
export async function saveCalendarCredentials(url: string, username: string, password: string): Promise<void> {
  await api.put('/calendar/credentials', { url, username, password });
}

// ── 多源管理(C1)────────────────────────────────────────────────────────
export type CalendarProvider = 'caldav' | 'ics';

/** 日历源(安全出参:绝不含凭据 / url / password)。镜像 _source_safe()。 */
export interface CalendarSource {
  id: number;
  provider: CalendarProvider;
  name: string;
  color?: string | null;
  writable: boolean;
  sync_enabled: boolean;
  last_sync_at?: string | null;
  last_error?: string | null;
}

export async function listCalendarSources(): Promise<CalendarSource[]> {
  const { data } = await api.get('/calendar/sources');
  return data;
}

/** 新增源:caldav 需 {name,url,username,password};ics 需 {name,url}。 */
export interface AddSourceInput {
  provider: CalendarProvider;
  name: string;
  url: string;
  color?: string | null;
  username?: string;
  password?: string;
}

export async function addCalendarSource(input: AddSourceInput): Promise<CalendarSource> {
  const { data } = await api.post('/calendar/sources', input);
  return data;
}

export interface UpdateSourceInput {
  name?: string;
  color?: string | null;
  sync_enabled?: boolean;
}

export async function updateCalendarSource(id: number, patch: UpdateSourceInput): Promise<CalendarSource> {
  const { data } = await api.put(`/calendar/sources/${id}`, patch);
  return data;
}

export async function deleteCalendarSource(id: number): Promise<void> {
  await api.delete(`/calendar/sources/${id}`);
}

// ── 同步(所有 sync_enabled 源,fail-soft per source)────────────────────────
/** 单源同步结果:成功 {synced} 或 fail-soft {error}。 */
export interface SourceSyncResult {
  synced?: number;
  error?: string;
}

/** sync_all_sources 返回 {sources:{[id]:{synced|error}}, count}。 */
export interface SyncResult {
  sources: Record<string, SourceSyncResult>;
  count: number;
}

export async function syncCalendar(): Promise<SyncResult> {
  const { data } = await api.post('/calendar/sync');
  return data;
}

// ── 事件明细(本人客户端,解密;LLM 路径绝不走这里)────────────────────────
/**
 * 一条日历事件(全量明细)。注意后端键是 start/end(非 start_time/end_time)。
 * 镜像 GET /calendar/events 出参。
 */
export interface CalendarEvent {
  id: number;
  source_id: number;
  uid: string;
  title: string;
  start: string | null; // ISO8601(北京时区)
  end: string | null;
  all_day: boolean;
  location: string;
  description: string;
  attendees: string[];
  status: string | null;
}

/** from/to 为 YYYY-MM-DD。缺省后端给 [今天-7d, 今天+30d]。 */
export async function getCalendarEvents(from?: string, to?: string): Promise<CalendarEvent[]> {
  const params: Record<string, string> = {};
  if (from) params.from = from;
  if (to) params.to = to;
  const { data } = await api.get('/calendar/events', { params });
  return data;
}
