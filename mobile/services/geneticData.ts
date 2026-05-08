/**
 * Genetic Data API client — 基因档案上传 (TXT / PDF).
 *
 * 后端 /genetic-data/profiles/upload-txt 和 /upload-pdf 都走 JSON body,
 * 不是 multipart — TXT 传 txt_content 字符串, PDF 传 pdf_base64.
 */
import * as FileSystem from 'expo-file-system/legacy';
import api from './api';

export interface GeneticTxtUploadResult {
  id: number;
  matched_count: number;
  variants: Array<{ gene: string; genotype: string; result: string; risk: string }>;
  message: string;
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
  const today = new Date().toISOString().slice(0, 10);
  const res = await api.post<GeneticTxtUploadResult>('/genetic-data/profiles/upload-txt', {
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
  const today = new Date().toISOString().slice(0, 10);
  const res = await api.post<GeneticPdfUploadResult>('/genetic-data/profiles/upload-pdf', {
    test_provider: opts.test_provider || '自助上传',
    test_date: opts.test_date || today,
    pdf_base64,
    notes: opts.notes,
  }, { timeout: 120_000 });
  return res.data;
}
