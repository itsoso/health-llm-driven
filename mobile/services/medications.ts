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

// ──────────────────────────────────────────────────────────────
// 今日服药状态 + 打卡日志
// 后端未暴露 OpenAPI schema(types/api.generated.ts 暂无 Medication),
// 故此处手写 interface, 对齐 GET /medication/today/me 与 POST /medication/logs。
// ──────────────────────────────────────────────────────────────

export interface MedicationLogEntry {
  id: number;
  time: string | null; // "HH:MM"
  status: 'taken' | 'skipped' | 'delayed';
}

/** GET /medication/today/me 的单项 (见 medication_service.get_today_status) */
export interface MedicationTodayItem {
  medication_id: number;
  name: string;
  dosage: string | null;
  category: string | null;
  total_count: number | null; // = times_per_day, 可能为 null
  taken_count: number;
  skipped_count: number;
  last_taken_time: string | null; // 今日最后一次 taken 的 HH:MM
  last_taken_time_overall?: string | null;
  last_taken_date_overall?: string | null;
  reminder_times: string[]; // ["HH:MM", ...]
  logs: MedicationLogEntry[];
}

export interface MedicationLogResult {
  id: number;
  medication_id: number;
  taken_date: string;
  taken_time: string | null;
  status: string;
}

export interface LogMedicationInput {
  medication_id: number;
  taken_time: string; // "HH:MM"
  status: 'taken' | 'skipped';
  skip_reason?: string;
  actual_dosage?: string;
  notes?: string;
}

/** POST /medication/logs — 记录一次服药/跳过 */
export async function logMedication(input: LogMedicationInput): Promise<MedicationLogResult> {
  const resp = await api.post<MedicationLogResult>('/medication/logs', input);
  return resp.data;
}

/** DELETE /medication/logs/{id} — 撤销误点的打卡 */
export async function deleteMedicationLog(id: number): Promise<void> {
  await api.delete(`/medication/logs/${id}`);
}

// ──────────────────────────────────────────────────────────────
// 多药梳理 / 减药候选评审(deprescribing review)
// 后端 GET /medication/deprescribing-review/me(PR #154)。无 OpenAPI schema,手写对齐:
// 见 backend/app/services/deprescribing_review.py::review_medications。
// ⚠️ 全部 candidate 级提示,后端话术绝不出现"停药/减量"命令——UI 文案照搬,不改写。
// ──────────────────────────────────────────────────────────────

export type DeprescribingFlagCode =
  | 'polypharmacy'
  | 'duplicate_class'
  | 'long_term_candidate'
  | 'expired_still_active'
  | string;

export interface DeprescribingFlag {
  code: DeprescribingFlagCode;
  detail: string;
  suggestion: string;
}

export interface DeprescribingReview {
  active_count: number;
  is_polypharmacy: boolean;
  flags: DeprescribingFlag[];
  disclaimer: string;
}

export async function getDeprescribingReview(): Promise<DeprescribingReview> {
  const resp = await api.get<DeprescribingReview>('/medication/deprescribing-review/me');
  return resp.data;
}
