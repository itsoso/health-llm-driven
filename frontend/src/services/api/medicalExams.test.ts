import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('./client', () => ({
  api: {
    post: vi.fn(),
  },
}));

import { api } from './client';
import {
  importMedicalExamFile,
  importMedicalExamText,
  normalizeMedicalExamImportResult,
} from './medicalExams';

const mockPost = api.post as unknown as ReturnType<typeof vi.fn>;

describe('medical exam import API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes backend import responses for review-first UI', () => {
    const out = normalizeMedicalExamImportResult({
      message: 'PDF解析并导入成功',
      exam_id: 42,
      exam_date: '2026-06-18',
      hospital_name: '三甲医院',
      items_count: 28,
      abnormal_count: 3,
    }, 'pdf');

    expect(out).toMatchObject({
      source: 'pdf',
      examId: 42,
      examDate: '2026-06-18',
      hospitalName: '三甲医院',
      itemsCount: 28,
      abnormalCount: 3,
      reviewRequired: true,
    });
  });

  it('imports PDFs through the canonical medical exam endpoint', async () => {
    mockPost.mockResolvedValueOnce({
      data: { message: '导入成功', exam_id: 42, items_count: 28 },
    });
    const file = new File(['pdf'], 'report.pdf', { type: 'application/pdf' });

    const out = await importMedicalExamFile(file);

    expect(out.examId).toBe(42);
    expect(out.itemsCount).toBe(28);
    expect(mockPost).toHaveBeenCalledWith(
      '/medical-exams/import/pdf',
      expect.any(FormData),
      expect.objectContaining({ timeout: 120_000 }),
    );
  });

  it('imports report images through the canonical medical exam endpoint', async () => {
    mockPost.mockResolvedValueOnce({
      data: { message: '图片 OCR 导入成功', exam_id: 77, items_count: 9, abnormal_count: 2 },
    });
    const file = new File(['png'], 'report.png', { type: 'image/png' });

    const out = await importMedicalExamFile(file);

    expect(out.source).toBe('image');
    expect(out.abnormalCount).toBe(2);
    expect(mockPost).toHaveBeenCalledWith(
      '/medical-exams/import/image',
      expect.any(FormData),
      expect.objectContaining({ timeout: 120_000 }),
    );
  });

  it('imports pasted text as a persistent medical exam record', async () => {
    mockPost.mockResolvedValueOnce({
      data: { message: '文本导入成功', exam_id: 91, exam_date: '2026-06-27', items_count: 4 },
    });

    const out = await importMedicalExamText('LDL 3.8 mmol/L', { hospital_name: '手工贴文字' });

    expect(out.examId).toBe(91);
    expect(out.source).toBe('text');
    expect(mockPost).toHaveBeenCalledWith('/medical-exams/import/text', {
      text: 'LDL 3.8 mmol/L',
      hospital_name: '手工贴文字',
    });
  });
});
