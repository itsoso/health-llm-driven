import api from './api';

// 处方识别 + 原研药查询(后端 /prescriptions/*)。
export interface Originator {
  generic: string;       // 通用名
  brand: string;         // 原研药品牌
  manufacturer: string;  // 原研厂家
}
export interface PrescriptionDrug {
  raw_name: string | null;       // 处方原始药名
  generic_name: string | null;   // 规整后的通用名
  dosage: string | null;
  frequency: string | null;
  originator: Originator | null; // 命中的原研药;未命中为 null
  has_originator: boolean;
}
export interface PrescriptionRecognizeResult {
  items: PrescriptionDrug[];
  matched_originators: number;
  note: string;
}

/** 上传处方图片 → 识别药品 + 原研药(供用户确认,不入库)。 */
export async function recognizePrescription(
  fileUri: string,
  fileName = 'prescription.jpg',
  mimeType = 'image/jpeg',
): Promise<PrescriptionRecognizeResult> {
  const form = new FormData();
  form.append('file', { uri: fileUri, name: fileName, type: mimeType } as any);
  const res = await api.post<PrescriptionRecognizeResult>(
    '/prescriptions/recognize',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 },
  );
  return res.data;
}

/** 单条按药名查原研药。 */
export async function lookupOriginator(name: string): Promise<{ originator: Originator | null; has_originator: boolean }> {
  const res = await api.get<{ originator: Originator | null; has_originator: boolean }>(
    '/prescriptions/originator',
    { params: { name } },
  );
  return res.data;
}

// ── 纯 helper(可单测)──

/** 命中原研药的条目优先排前(方便展示"有原研可换")。 */
export function sortByOriginator(items: PrescriptionDrug[] | null | undefined): PrescriptionDrug[] {
  return [...(items ?? [])].sort((a, b) => Number(b.has_originator) - Number(a.has_originator));
}

/** 一句话摘要:N 种药,M 种有原研。 */
export function summarize(result: PrescriptionRecognizeResult | null | undefined): string {
  const n = result?.items?.length ?? 0;
  const m = result?.matched_originators ?? 0;
  if (n === 0) return '未识别到药品';
  return `识别 ${n} 种药,其中 ${m} 种找到对应原研药`;
}
