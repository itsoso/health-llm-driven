import { api } from './client';

export type MedicalExamImportSource = 'pdf' | 'image' | 'text';

export interface MedicalExamImportResult {
  message: string;
  source: MedicalExamImportSource;
  reviewRequired: boolean;
  examId: number;
  examDate?: string | null;
  examType?: string | null;
  hospitalName?: string | null;
  itemsCount?: number | null;
  abnormalCount?: number | null;
  conclusionsCount?: number | null;
  conclusion?: string | null;
  raw: Record<string, any>;
}

export interface MedicalExamTextImportOptions {
  exam_date?: string;
  exam_type?: string;
  hospital_name?: string;
}

export function normalizeMedicalExamImportResult(
  raw: Record<string, any>,
  source: MedicalExamImportSource,
): MedicalExamImportResult {
  return {
    message: raw.message ?? '体检报告导入成功',
    source,
    reviewRequired: true,
    examId: Number(raw.exam_id ?? raw.examId ?? 0),
    examDate: raw.exam_date ?? raw.examDate ?? null,
    examType: raw.exam_type ?? raw.examType ?? null,
    hospitalName: raw.hospital_name ?? raw.hospitalName ?? null,
    itemsCount: raw.items_count ?? raw.itemsCount ?? null,
    abnormalCount: raw.abnormal_count ?? raw.abnormalCount ?? null,
    conclusionsCount: raw.conclusions_count ?? raw.conclusionsCount ?? null,
    conclusion: raw.conclusion ?? null,
    raw,
  };
}

export function medicalExamImportSourceForFile(file: File): Exclude<MedicalExamImportSource, 'text'> {
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  if (type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf';
  if (type.startsWith('image/') || /\.(jpg|jpeg|png|heic|webp)$/.test(name)) return 'image';
  throw new Error('请选择 PDF、JPG、PNG、HEIC 或 WebP 格式的体检报告');
}

export async function importMedicalExamFile(file: File): Promise<MedicalExamImportResult> {
  const source = medicalExamImportSourceForFile(file);
  const formData = new FormData();
  formData.append('file', file);
  const endpoint = source === 'pdf'
    ? '/medical-exams/import/pdf'
    : '/medical-exams/import/image';
  const res = await api.post(endpoint, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  });
  return normalizeMedicalExamImportResult(res.data, source);
}

export async function importMedicalExamText(
  text: string,
  options: MedicalExamTextImportOptions = {},
): Promise<MedicalExamImportResult> {
  const res = await api.post('/medical-exams/import/text', {
    text,
    ...options,
  });
  return normalizeMedicalExamImportResult(res.data, 'text');
}
