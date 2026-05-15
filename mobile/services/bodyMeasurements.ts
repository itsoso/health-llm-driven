import api from './api';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export interface WeightRecord {
  id?: number;
  record_date: string;
  weight: number;
  body_fat_percentage?: number | null;
  muscle_mass?: number | null;
  notes?: string | null;
}

export interface WaistRecord {
  id?: number;
  record_date: string;
  waist_cm: number;
  source?: string | null;
  notes?: string | null;
}

export interface BodyMeasurementInput {
  recordDate?: string;
  weightKg?: number | null;
  waistCm?: number | null;
  notes?: string | null;
}

export async function getLatestBodyMeasurements(): Promise<{
  weight?: WeightRecord | null;
  waist?: WaistRecord | null;
}> {
  const [weightResp, waistResp] = await Promise.all([
    api.get<WeightRecord[]>('/weight/records/me', { params: { limit: 1 } }).catch(() => ({ data: [] as WeightRecord[] })),
    api.get<WaistRecord | null>('/waist/records/me/latest').catch(() => ({ data: null })),
  ]);
  return {
    weight: Array.isArray(weightResp.data) ? weightResp.data[0] ?? null : null,
    waist: waistResp.data ?? null,
  };
}

export async function saveBodyMeasurements(input: BodyMeasurementInput): Promise<void> {
  const recordDate = input.recordDate ?? today();
  const tasks: Promise<unknown>[] = [];
  if (input.weightKg != null) {
    tasks.push(api.post('/weight/records', {
      record_date: recordDate,
      weight: input.weightKg,
      notes: input.notes || undefined,
    }));
  }
  if (input.waistCm != null) {
    tasks.push(api.post('/waist/records', {
      record_date: recordDate,
      waist_cm: input.waistCm,
      source: 'manual',
      notes: input.notes || undefined,
    }));
  }
  await Promise.all(tasks);
}

export function parseOptionalMeasurement(raw: string): number | null {
  const normalized = raw.trim().replace(',', '.');
  if (!normalized) return null;
  const value = Number(normalized);
  if (!Number.isFinite(value)) return NaN;
  return Math.round(value * 10) / 10;
}
