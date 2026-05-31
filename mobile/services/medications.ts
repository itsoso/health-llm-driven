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

/**
 * 一条用药安全告警 (SafetyGuardian DDI/DSI/PGx 相互作用)。
 * 形状对应后端 Alert.model_dump_for_api()。
 */
export interface MedicationSafetyAlert {
  rule_id: string;
  category: string; // ddi | dsi | pgx
  severity: { value: number; label: string; label_zh: string };
  title: string;
  message: string;
  action?: string | null;
  requires_medical_attention?: boolean;
}

/**
 * 新增药物的响应: 药品本体 + 即时安全检查命中的高危相互作用告警。
 * safety_alerts 为空数组表示无高危相互作用 (诚实的三态之一: 已保存且未命中)。
 */
export type MedicationCreateResult = Medication & {
  safety_alerts: MedicationSafetyAlert[];
};

export async function addMedication(data: Partial<Medication>): Promise<MedicationCreateResult> {
  const resp = await api.post<MedicationCreateResult>('/medication/medications', data);
  // 旧后端可能不带 safety_alerts; 兜底成空数组, 避免下游 .length 崩.
  return { ...resp.data, safety_alerts: resp.data.safety_alerts ?? [] };
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
