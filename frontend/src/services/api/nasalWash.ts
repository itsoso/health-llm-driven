import { api } from './client';

export interface NasalWashEvent {
  event_id?: string;
  time: string;
  type?: 'wash' | 'soak';
  count?: number;
  volume_ml?: number | null;
  solution?: string | null;
}

export interface NasalWashRequest {
  event_id: string;
  record_date: string;
  count: number;
  volume_ml?: number | null;
  solution?: string | null;
  type?: 'wash' | 'soak';
  time?: string;
}

export interface NasalWashCheckin {
  id: number;
  checkin_date: string;
  nasal_wash_count: number | null;
  nasal_wash_times: NasalWashEvent[] | null;
}

export function createNasalWashRequest(
  recordDate: string,
  options: Pick<NasalWashRequest, 'type' | 'time'> = {},
): NasalWashRequest {
  return { event_id: crypto.randomUUID(), record_date: recordDate, count: 1, ...options };
}

export async function recordNasalWash(request: NasalWashRequest): Promise<NasalWashCheckin> {
  const response = await api.post<NasalWashCheckin>('/checkin/nasal-wash', request).catch((error: unknown) => {
    if ((error as { response?: { status?: number } })?.response?.status === 422) {
      const rejection = new Error('记录内容未通过校验，请检查日期和时间后重新提交。');
      rejection.name = 'NasalWashValidationError';
      throw rejection;
    }
    throw error;
  });
  if (!response.data.nasal_wash_times?.some(event => event.event_id === request.event_id)) {
    throw new Error('记录未确认，请重试这条记录。');
  }
  return response.data;
}

export async function undoNasalWash(checkinId: number, eventId: string): Promise<NasalWashCheckin> {
  const response = await api.delete<NasalWashCheckin>(`/checkin/${checkinId}/nasal-wash/${eventId}`);
  return response.data;
}
