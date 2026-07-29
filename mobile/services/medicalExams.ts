/**
 * Medical Exams API client — 化验/体检记录列表 + 详情.
 *
 * P6 (2026-05-04): 用户已经有 16 份化验报告, 但 mobile
 * 没有专门的化验列表页 — 上传完没法回看. 这是 dead-end.
 *
 * 这次只做查看 (上传仍走 chat → Agent OCR 流程),
 * 但至少让用户能 1) 看历史时间线 2) 看异常项 3) 看趋势对比.
 */
import api from './api';

export interface MedicalExamItem {
  id: number;
  exam_id: number;
  category?: string | null;
  item_name: string;
  item_code?: string | null;
  value?: number | null;
  value_text?: string | null;
  unit?: string | null;
  reference_range?: string | null;
  is_abnormal?: 'normal' | 'high' | 'low' | 'abnormal' | string | null;
  notes?: string | null;
  source?: 'manual' | 'ocr' | 'pdf' | 'csv' | 'json' | string | null;
  manually_corrected_at?: string | null;
  original_value?: number | null;
  original_value_text?: string | null;
}

export interface MedicalExamItemUpdate {
  item_name?: string;
  value?: number | null;
  value_text?: string | null;
  unit?: string;
  reference_range?: string;
  is_abnormal?: 'normal' | 'high' | 'low' | 'abnormal' | string;
  notes?: string;
}

export interface MedicalExam {
  id: number;
  user_id: number;
  exam_date: string;
  exam_type?: string | null;
  hospital_name?: string | null;
  doctor_name?: string | null;
  overall_assessment?: string | null;
  conclusions?: any[] | null;
  notes?: string | null;
  items: MedicalExamItem[];
  created_at?: string | null;
}

export async function listMedicalExams(limit = 50): Promise<MedicalExam[]> {
  try {
    const res = await api.get<MedicalExam[]>(`/medical-exams/me?limit=${limit}`);
    return Array.isArray(res.data) ? res.data : [];
  } catch {
    return [];
  }
}

/**
 * 计算异常项数 — UI 用来显示"⚠️ 3 项异常".
 * 'normal' / null / 空字符串都算正常, 其他 (high/low/abnormal) 算异常.
 */
export function countAbnormal(exam: MedicalExam): number {
  if (!exam.items) return 0;
  return exam.items.filter(item => {
    const v = (item.is_abnormal || '').toLowerCase().trim();
    return v && v !== 'normal';
  }).length;
}

/**
 * 给两次 exam 找同 item_code 的指标, 返回变化对比.
 * 用于详情页"vs 上次" 反馈.
 */
export interface ExamComparison {
  item_name: string;
  item_code?: string;
  unit?: string;
  current_value: number;
  previous_value: number;
  delta: number;
  delta_pct: number;
  current_abnormal: boolean;
  previous_abnormal: boolean;
}

export function compareExams(current: MedicalExam, previous: MedicalExam): ExamComparison[] {
  if (!current.items?.length || !previous.items?.length) return [];

  const prevByCode: Record<string, MedicalExamItem> = {};
  for (const it of previous.items) {
    const key = (it.item_code || it.item_name || '').toLowerCase().trim();
    if (key && it.value != null) prevByCode[key] = it;
  }

  const out: ExamComparison[] = [];
  for (const cur of current.items) {
    if (cur.value == null) continue;
    const key = (cur.item_code || cur.item_name || '').toLowerCase().trim();
    const prev = prevByCode[key];
    if (!prev || prev.value == null) continue;
    const delta = cur.value - prev.value;
    const delta_pct = prev.value !== 0 ? (delta / prev.value) * 100 : 0;
    out.push({
      item_name: cur.item_name,
      item_code: cur.item_code || undefined,
      unit: cur.unit || undefined,
      current_value: cur.value,
      previous_value: prev.value,
      delta,
      delta_pct,
      current_abnormal: !!cur.is_abnormal && cur.is_abnormal !== 'normal',
      previous_abnormal: !!prev.is_abnormal && prev.is_abnormal !== 'normal',
    });
  }
  // 按 |delta_pct| 倒序 — 变化最大的先呈现
  out.sort((a, b) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct));
  return out;
}

// ========== 上传入口 (canonical /medical-exams/import/*) ==========

export type MedicalExamImportSource = 'pdf' | 'image' | 'text';

export interface MedicalExamImportResult {
  message: string;
  source: MedicalExamImportSource;
  reviewRequired: boolean;

  // Backward-compatible snake_case fields from backend responses.
  exam_id: number;
  exam_date?: string | null;
  exam_type?: string | null;
  hospital_name?: string | null;
  items_count?: number | null;
  abnormal_count?: number | null;
  conclusions_count?: number | null;
  conclusion?: string | null;
  category_summary?: Record<string, number> | null;
  patient_name?: string | null;

  // UI-friendly camelCase fields used by multi-surface import cards.
  examId: number;
  examDate?: string | null;
  examType?: string | null;
  hospitalName?: string | null;
  itemsCount?: number | null;
  abnormalCount?: number | null;
  conclusionsCount?: number | null;
}

export type MedicalExamPdfUploadResult = MedicalExamImportResult;

export type MedicalExamImageUploadResult = MedicalExamImportResult;

export interface MedicalExamTextUploadOptions {
  exam_date?: string;
  hospital_name?: string;
  exam_type?: string;
}

export type MedicalExamTextUploadResult = MedicalExamImportResult;

export interface MedicalExamImportAsset {
  uri: string;
  name?: string | null;
  mimeType?: string | null;
}

export interface MedicalExamPreviewItem {
  category?: string | null;
  item_name: string;
  item_code?: string | null;
  value?: number | null;
  value_text?: string | null;
  unit?: string | null;
  reference_range?: string | null;
  result?: string | null;
  is_abnormal?: string | null;
  notes?: string | null;
}

export interface MedicalExamPreview {
  source: 'pdf' | 'image';
  fileName: string;
  patient_name?: string | null;
  patient_gender?: string | null;
  patient_age?: number | null;
  exam_number?: string | null;
  exam_date: string;
  exam_type?: string | null;
  body_system?: string | null;
  hospital_name?: string | null;
  doctor_name?: string | null;
  overall_assessment?: string | null;
  conclusions?: any[] | null;
  items: MedicalExamPreviewItem[];
}

export function normalizeMedicalExamImportResult(
  raw: Record<string, any>,
  source: MedicalExamImportSource,
): MedicalExamImportResult {
  const examId = Number(raw.exam_id ?? raw.examId ?? 0);
  const itemsCount = raw.items_count ?? raw.itemsCount ?? null;
  const abnormalCount = raw.abnormal_count ?? raw.abnormalCount ?? null;
  const conclusionsCount = raw.conclusions_count ?? raw.conclusionsCount ?? null;

  return {
    ...raw,
    message: raw.message ?? '体检报告导入成功',
    source,
    reviewRequired: true,
    exam_id: examId,
    examId,
    exam_date: raw.exam_date ?? raw.examDate ?? null,
    examDate: raw.exam_date ?? raw.examDate ?? null,
    exam_type: raw.exam_type ?? raw.examType ?? null,
    examType: raw.exam_type ?? raw.examType ?? null,
    hospital_name: raw.hospital_name ?? raw.hospitalName ?? null,
    hospitalName: raw.hospital_name ?? raw.hospitalName ?? null,
    items_count: itemsCount,
    itemsCount,
    abnormal_count: abnormalCount,
    abnormalCount,
    conclusions_count: conclusionsCount,
    conclusionsCount,
    conclusion: raw.conclusion ?? null,
    category_summary: raw.category_summary ?? null,
    patient_name: raw.patient_name ?? null,
  };
}

/**
 * 体检 PDF 上传 → /medical-exams/import/pdf (multipart).
 */
export async function uploadMedicalExamPdf(
  fileUri: string,
  fileName: string,
): Promise<MedicalExamPdfUploadResult> {
  const form = new FormData();
  // RN FormData 接受 { uri, name, type } 对象
  form.append('file', { uri: fileUri, name: fileName, type: 'application/pdf' } as any);
  const res = await api.post<MedicalExamPdfUploadResult>(
    '/medical-exams/import/pdf',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
  );
  return normalizeMedicalExamImportResult(res.data, 'pdf');
}

/**
 * 体检照片上传 → /medical-exams/import/image (multipart, 走 vision OCR).
 */
export async function uploadMedicalExamImage(
  fileUri: string,
  fileName: string,
  mimeType: string = 'image/jpeg',
): Promise<MedicalExamImageUploadResult> {
  const form = new FormData();
  form.append('file', { uri: fileUri, name: fileName, type: mimeType } as any);
  const res = await api.post<MedicalExamImageUploadResult>(
    '/medical-exams/import/image',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
  );
  return normalizeMedicalExamImportResult(res.data, 'image');
}

/**
 * 手工贴文字 → /medical-exams/import/text.
 * 这是 OCR 失败后的持久化兜底路径,不能再走 parse-preview.
 */
export async function uploadMedicalExamText(
  text: string,
  options: MedicalExamTextUploadOptions = {},
): Promise<MedicalExamTextUploadResult> {
  const res = await api.post<MedicalExamTextUploadResult>('/medical-exams/import/text', {
    text,
    ...options,
  });
  return normalizeMedicalExamImportResult(res.data, 'text');
}

function assetExtension(asset: MedicalExamImportAsset): string {
  const name = (asset.name ?? '').toLowerCase();
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot + 1) : '';
}

function isPdfAsset(asset: MedicalExamImportAsset): boolean {
  return asset.mimeType?.toLowerCase() === 'application/pdf' || assetExtension(asset) === 'pdf';
}

function numericValue(raw: unknown): number | null {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw !== 'string') return null;
  const value = raw.trim();
  if (!/^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizePreviewItem(raw: Record<string, any>): MedicalExamPreviewItem | null {
  const itemName = String(raw.item_name ?? raw.name ?? '').trim();
  if (!itemName) return null;
  const low = raw.reference_low;
  const high = raw.reference_high;
  const referenceRange = raw.reference_range
    ?? (low != null && high != null ? `${low}-${high}` : null);
  const value = numericValue(raw.value);
  const abnormal = typeof raw.is_abnormal === 'string'
    ? (raw.is_abnormal.trim() || 'normal')
    : (raw.is_abnormal === true ? 'abnormal' : 'normal');
  return {
    category: raw.category ?? null,
    item_name: itemName,
    item_code: raw.item_code ?? raw.name_en ?? null,
    value,
    value_text: raw.value_text ?? (value == null && raw.value != null ? String(raw.value) : null),
    unit: raw.unit ?? null,
    reference_range: referenceRange,
    result: raw.result ?? null,
    is_abnormal: abnormal,
    notes: raw.notes ?? null,
  };
}

function todayLocal(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function normalizeExamDate(raw: unknown): string {
  const text = String(raw ?? '').trim();
  const separated = text.match(/^(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?$/);
  const compact = text.match(/^(\d{4})(\d{2})(\d{2})$/);
  const match = separated ?? compact;
  if (!match) return todayLocal();
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() + 1 !== month
    || parsed.getUTCDate() !== day
  ) {
    return todayLocal();
  }
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function normalizeMedicalExamPreview(
  raw: Record<string, any>,
  source: 'pdf' | 'image',
  fileName: string,
): MedicalExamPreview {
  const items = (Array.isArray(raw.items) ? raw.items : [])
    .map(item => normalizePreviewItem(item))
    .filter((item): item is MedicalExamPreviewItem => item != null);
  const overallAssessment = raw.overall_assessment ?? raw.conclusion ?? null;
  return {
    source,
    fileName,
    patient_name: raw.patient_name ?? null,
    patient_gender: raw.patient_gender ?? null,
    patient_age: raw.patient_age ?? null,
    exam_number: raw.exam_number ?? null,
    exam_date: normalizeExamDate(raw.exam_date ?? raw.report_date),
    exam_type: raw.exam_type ?? raw.report_type ?? 'other',
    body_system: raw.body_system ?? null,
    hospital_name: raw.hospital_name ?? raw.institution ?? null,
    doctor_name: raw.doctor_name ?? null,
    overall_assessment: overallAssessment,
    conclusions: Array.isArray(raw.conclusions) ? raw.conclusions : null,
    items,
  };
}

/**
 * Parse a selected report without persistence. The returned preview is the
 * only input accepted by the explicit confirmation step below.
 */
export async function previewMedicalExamAsset(
  asset: MedicalExamImportAsset,
): Promise<MedicalExamPreview> {
  const pdf = isPdfAsset(asset);
  const source = pdf ? 'pdf' : 'image';
  const fileName = asset.name?.trim() || (pdf ? 'medical-exam.pdf' : 'medical-exam.jpg');
  const mimeType = asset.mimeType || (pdf ? 'application/pdf' : 'image/jpeg');
  const form = new FormData();
  form.append('file', { uri: asset.uri, name: fileName, type: mimeType } as any);
  const endpoint = pdf
    ? '/medical-exams/parse-pdf-preview'
    : '/medical-exams/parse-image-preview';
  const response = await api.post(
    endpoint,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
  );
  const preview = normalizeMedicalExamPreview(
    response.data?.parsed_data ?? {},
    source,
    fileName,
  );
  if (
    preview.items.length === 0
    && !preview.overall_assessment
    && (preview.conclusions?.length ?? 0) === 0
  ) {
    throw new Error('未识别到可保存的体检内容，请更换更清晰或完整的报告。');
  }
  return preview;
}

/**
 * Persist an already-reviewed preview. Reusing the key is safe and returns the
 * original owner-scoped report instead of creating duplicate health records.
 */
export async function confirmMedicalExamPreview(
  preview: MedicalExamPreview,
  idempotencyKey: string,
): Promise<MedicalExamImportResult> {
  const response = await api.post<MedicalExam>(
    '/medical-exams/',
    {
      patient_name: preview.patient_name,
      patient_gender: preview.patient_gender,
      patient_age: preview.patient_age,
      exam_number: preview.exam_number,
      exam_date: preview.exam_date,
      exam_type: preview.exam_type,
      body_system: preview.body_system,
      hospital_name: preview.hospital_name,
      doctor_name: preview.doctor_name,
      overall_assessment: preview.overall_assessment,
      conclusions: preview.conclusions,
      notes: `经用户确认导入: ${preview.fileName}`,
      items: preview.items,
    },
    { headers: { 'Idempotency-Key': idempotencyKey } },
  );
  const exam = response.data;
  const abnormalCount = (exam.items ?? []).filter(item => {
    const status = String(item.is_abnormal ?? '').toLowerCase();
    return status !== '' && status !== 'normal';
  }).length;
  return normalizeMedicalExamImportResult({
    message: '体检报告已保存',
    exam_id: exam.id,
    exam_date: exam.exam_date,
    exam_type: exam.exam_type,
    hospital_name: exam.hospital_name,
    items_count: exam.items?.length ?? 0,
    abnormal_count: abnormalCount,
    conclusions_count: exam.conclusions?.length ?? 0,
    conclusion: exam.overall_assessment,
  }, preview.source);
}

/**
 * 把 exam_date 'YYYY-MM-DD' 转成"6 月 / 3 个月前 / 2 年前" 这种相对时间.
 */
export function relativeExamDate(dateStr: string, now: Date = new Date()): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const days = Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 7) return `${days} 天前`;
  if (days < 30) return `${Math.floor(days / 7)} 周前`;
  if (days < 365) return `${Math.floor(days / 30)} 个月前`;
  const years = Math.floor(days / 365);
  return `${years} 年前`;
}

/**
 * Calibrate UI — 用户手工校正单条 item.
 * 后端 PATCH /medical-exams/items/{id} 会同步写 medical_indicators + invalidate Twin.
 */
export async function updateMedicalExamItem(
  itemId: number,
  patch: MedicalExamItemUpdate,
): Promise<MedicalExamItem> {
  const res = await api.patch<MedicalExamItem>(`/medical-exams/items/${itemId}`, patch);
  return res.data;
}
