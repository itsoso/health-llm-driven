/**
 * Medical Exams API client — 化验/体检记录列表 + 详情.
 *
 * P6 (2026-05-04): 用户已经有 16 份化验报告 (OpenClaw skill 上传), 但 mobile
 * 没有专门的化验列表页 — 上传完没法回看. 这是 dead-end.
 *
 * 这次只做查看 (上传仍走 chat → OpenClaw skill, 那是 OCR 工作量太大暂不重做),
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

// ========== 上传入口 (Iter 1 Day 2/3: /import 页) ==========

export interface MedicalExamPdfUploadResult {
  message: string;
  exam_id: number;
  patient_name?: string | null;
  exam_date: string;
  exam_type?: string | null;
  hospital_name?: string | null;
  items_count: number;
  conclusions_count?: number;
  category_summary?: Record<string, number>;
}

export interface MedicalExamImageUploadResult {
  message: string;
  exam_id: number;
  exam_date: string;
  exam_type?: string | null;
  hospital_name?: string | null;
  items_count: number;
  abnormal_count: number;
  conclusion?: string | null;
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
  return res.data;
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
  return res.data;
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
