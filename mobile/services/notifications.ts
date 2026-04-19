import api from './api';

export interface NotificationSettings {
  enabled: boolean;
  morning_briefing_enabled: boolean;
  morning_briefing_time: string;
  reminder_enabled: boolean;
  health_alert_enabled: boolean;
  ai_advice_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  wechat_enabled: boolean;
  wechat_bound: boolean;
  ios_push_enabled: boolean;
  ios_bound: boolean;
}

export interface NotificationSettingsUpdate {
  enabled?: boolean;
  morning_briefing_enabled?: boolean;
  morning_briefing_time?: string;
  reminder_enabled?: boolean;
  health_alert_enabled?: boolean;
  ai_advice_enabled?: boolean;
  quiet_hours_start?: string;
  quiet_hours_end?: string;
  ios_push_enabled?: boolean;
}

export interface Reminder {
  id: number;
  reminder_type: string;
  name: string;
  reminder_times: string[];
  days_of_week: number[];
  message: string | null;
  enabled: boolean;
}

export interface ReminderTemplate {
  type: string;
  name: string;
  default_times: string[];
  default_message: string;
}

export interface ReminderCreate {
  reminder_type: string;
  name: string;
  reminder_times: string[];
  days_of_week?: number[];
  message?: string;
}

export interface ReminderUpdate {
  name?: string;
  reminder_times?: string[];
  days_of_week?: number[];
  message?: string;
  enabled?: boolean;
}

export interface NotificationLog {
  id: number;
  notification_type: string;
  channel: string;
  title: string;
  content: string;
  status: string;
  sent_at: string | null;
  created_at: string | null;
}

export async function bindIOSToken(deviceToken: string): Promise<void> {
  await api.post('/notification/bind/ios', { device_token: deviceToken });
}

export async function unbindIOS(): Promise<void> {
  await api.delete('/notification/unbind/ios');
}

export async function getSettings(): Promise<NotificationSettings> {
  const { data } = await api.get<NotificationSettings>('/notification/settings');
  return data;
}

export async function updateSettings(
  updates: NotificationSettingsUpdate,
): Promise<void> {
  await api.put('/notification/settings', updates);
}

export async function getReminders(): Promise<Reminder[]> {
  const { data } = await api.get<{ reminders: Reminder[] }>(
    '/notification/reminders',
  );
  return data.reminders;
}

export async function getReminderTemplates(): Promise<ReminderTemplate[]> {
  const { data } = await api.get<{ templates: ReminderTemplate[] }>(
    '/notification/reminders/templates',
  );
  return data.templates;
}

export async function createReminder(
  reminder: ReminderCreate,
): Promise<Reminder> {
  const { data } = await api.post<{ reminder: Reminder }>(
    '/notification/reminders',
    reminder,
  );
  return data.reminder;
}

export async function updateReminder(
  id: number,
  updates: ReminderUpdate,
): Promise<void> {
  await api.put(`/notification/reminders/${id}`, updates);
}

export async function deleteReminder(id: number): Promise<void> {
  await api.delete(`/notification/reminders/${id}`);
}

export async function getLogs(
  limit = 50,
  notificationType?: string,
): Promise<NotificationLog[]> {
  const params: Record<string, any> = { limit };
  if (notificationType) params.notification_type = notificationType;
  const { data } = await api.get<{ logs: NotificationLog[] }>(
    '/notification/logs',
    { params },
  );
  return data.logs;
}

export async function sendTestPush(
  title = '测试推送',
  content = '这是一条测试推送消息',
): Promise<void> {
  await api.post('/notification/test', { title, content, channel: 'ios_apns' });
}
