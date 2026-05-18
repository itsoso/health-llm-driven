import api from './api';

export interface Medication {
  id: number;
  name: string;
  dosage: string | null;
  frequency: string | null;
  times_per_day: number | null;
  reminder_times: string[] | null;
  category: string | null;
  purpose: string | null;
  start_date: string | null;
  end_date: string | null;
  is_active: boolean;
  notes: string | null;
}

export async function listMedications(activeOnly = true): Promise<Medication[]> {
  const resp = await api.get<Medication[]>('/medication/medications/me', {
    params: { active_only: activeOnly },
  });
  return resp.data;
}

export async function getMedication(id: number): Promise<Medication> {
  const resp = await api.get<Medication>(`/medication/medications/${id}`);
  return resp.data;
}

export async function addMedication(data: Partial<Medication>): Promise<Medication> {
  const resp = await api.post<Medication>('/medication/medications', data);
  return resp.data;
}

export async function deactivateMedication(id: number): Promise<void> {
  await api.delete(`/medication/medications/${id}`);
}

/** 误操作回滚 — 恢复已停用的药品 */
export async function restoreMedication(id: number): Promise<void> {
  await api.post(`/medication/medications/${id}/restore`);
}

export async function updateMedication(id: number, data: Partial<Medication>): Promise<Medication> {
  const resp = await api.put<Medication>(`/medication/medications/${id}`, data);
  return resp.data;
}
