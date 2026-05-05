import api from './api';

export interface TimelineEvent {
  id: string;
  source: 'workout' | 'alert' | 'sleep' | 'medication' | 'exam' | string;
  title: string;
  subtitle: string | null;
  icon: string;            // Ionicons name
  color: string;           // hex
  occurred_at: string;     // ISO datetime
  deep_link: string | null;
  severity: 'info' | 'warning' | 'critical' | null;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  days: number;
  count: number;
}

export async function fetchTimeline(days = 30, limit = 40): Promise<TimelineResponse> {
  const resp = await api.get<TimelineResponse>('/v1/timeline', {
    params: { days, limit },
  });
  return resp.data;
}
