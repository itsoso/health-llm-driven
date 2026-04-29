import api from './client';

export interface ActivityCategoryStats {
  category: string;
  total_minutes: number;
  count: number;
  percentage: number;
}

export interface ActivityStatsData {
  total_records: number;
  total_active_minutes: number;
  category_distribution: ActivityCategoryStats[];
}

export interface ActivityStatusData {
  id: number;
  user_id: number;
  status_text: string;
  category: string;
  start_time: string;
  estimated_duration_minutes: number | null;
  estimated_end_time: string | null;
  actual_end_time: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
}

export interface ActivityTimelineItem {
  id: number;
  status_text: string;
  category: string;
  start_time: string;
  end_time: string | null;
  duration_minutes: number | null;
  is_active: boolean;
}

export const activityStatusApi = {
  createRecord: (data: { status_text: string; category: string; estimated_duration_minutes?: number; notes?: string }) =>
    api.post<ActivityStatusData>('/activity-status/records', data),
  getCurrentStatus: () =>
    api.get<ActivityStatusData | null>('/activity-status/records/me/current'),
  endRecord: (recordId: number) =>
    api.put<ActivityStatusData>(`/activity-status/records/${recordId}/end`),
  getTodayTimeline: () =>
    api.get<ActivityTimelineItem[]>('/activity-status/records/me/today'),
  getMyRecords: (params?: { start_date?: string; end_date?: string; limit?: number }) =>
    api.get<ActivityStatusData[]>('/activity-status/records/me', { params }),
  getRecord: (recordId: number) =>
    api.get<ActivityStatusData>(`/activity-status/records/${recordId}`),
  deleteRecord: (recordId: number) =>
    api.delete(`/activity-status/records/${recordId}`),
  getStats: (days: number = 7) =>
    api.get<ActivityStatsData>(`/activity-status/stats/me?days=${days}`),
};
