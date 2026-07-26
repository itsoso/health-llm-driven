/**
 * Genetic Data API client — 基因档案上传 (TXT / PDF).
 *
 * 后端 /genetic/profiles/upload-txt 和 /upload-pdf 都走 JSON body,
 * 不是 multipart — TXT 传 txt_content 字符串, PDF 传 pdf_base64.
 */
import * as FileSystem from 'expo-file-system/legacy';
import api from './api';
import { todayStr } from '../utils/dietDate';

export interface GeneticTxtUploadResult {
  id: number;
  matched_count: number;
  variants: { gene: string; genotype: string; result: string; risk: string }[];
  message: string;
  import_job?: GeneticImportJob;
  coverage?: GeneticImportCoverage;
}

export interface GeneticPdfUploadResult {
  id: number;
  status: string;
  message: string;
}

export async function uploadGeneticTxt(
  fileUri: string,
  opts: { test_provider?: string; test_date?: string; notes?: string } = {},
): Promise<GeneticTxtUploadResult> {
  const txt_content = await FileSystem.readAsStringAsync(fileUri, {
    encoding: FileSystem.EncodingType.UTF8,
  });
  const today = todayStr();
  const res = await api.post<GeneticTxtUploadResult>('/genetic/profiles/upload-txt', {
    test_provider: opts.test_provider || '自助上传',
    test_date: opts.test_date || today,
    txt_content,
    notes: opts.notes,
  });
  return res.data;
}

export async function uploadGeneticPdf(
  fileUri: string,
  opts: { test_provider?: string; test_date?: string; notes?: string } = {},
): Promise<GeneticPdfUploadResult> {
  const pdf_base64 = await FileSystem.readAsStringAsync(fileUri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  const today = todayStr();
  const res = await api.post<GeneticPdfUploadResult>('/genetic/profiles/upload-pdf', {
    test_provider: opts.test_provider || '自助上传',
    test_date: opts.test_date || today,
    pdf_base64,
    notes: opts.notes,
  }, { timeout: 120_000 });
  return res.data;
}

export interface GeneticProfileStatus {
  id: number;
  status: 'queued' | 'processing' | 'done' | 'failed' | string;
  variant_count: number;
  notes: string;
  import_job?: GeneticImportJob | null;
  coverage?: GeneticImportCoverage | null;
}

export interface GeneticImportJob {
  status?: string | null;
  matched_count?: number | null;
  unmapped_count?: number | null;
  missing_count?: number | null;
  error_message?: string | null;
}

export interface GeneticImportCoverage {
  known_total?: number | null;
  present?: number | null;
  missing?: number | null;
  missing_by_reason?: Record<string, number> | null;
  missing_by_rsids?: Record<string, string> | null;
}

export async function getGeneticProfileStatus(profileId: number): Promise<GeneticProfileStatus> {
  const res = await api.get<GeneticProfileStatus>(`/genetic/profiles/${profileId}/status`);
  return res.data;
}

/**
 * 轮询基因档案状态直到完成或超时.
 * 默认每 6 秒轮一次, 最长 3 分钟.
 */
export async function pollGeneticProfileStatus(
  profileId: number,
  opts: { intervalMs?: number; maxMs?: number; onTick?: (s: GeneticProfileStatus) => void } = {},
): Promise<GeneticProfileStatus> {
  const interval = opts.intervalMs ?? 6000;
  const maxMs = opts.maxMs ?? 180_000;
  const start = Date.now();
  let last: GeneticProfileStatus | null = null;
  while (Date.now() - start < maxMs) {
    try {
      last = await getGeneticProfileStatus(profileId);
      opts.onTick?.(last);
      if (!['queued', 'processing', 'running', 'started'].includes((last.status || '').toLowerCase())) {
        return last;
      }
    } catch {
      // 网络瞬断忽略, 继续轮
    }
    await new Promise(r => setTimeout(r, interval));
  }
  return last ?? { id: profileId, status: 'processing', variant_count: 0, notes: '超时' };
}
