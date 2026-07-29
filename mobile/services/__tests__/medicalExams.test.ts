/* eslint-disable import/first */
jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '../api';
import {
  listMedicalExams,
  countAbnormal,
  compareExams,
  relativeExamDate,
  normalizeMedicalExamImportResult,
  uploadMedicalExamPdf,
  uploadMedicalExamImage,
  uploadMedicalExamText,
  previewMedicalExamAsset,
  confirmMedicalExamPreview,
  type MedicalExam,
} from '../medicalExams';

const mockGet = api.get as jest.Mock;
const mockPost = api.post as jest.Mock;

const makeExam = (overrides: Partial<MedicalExam> = {}): MedicalExam => ({
  id: 1,
  user_id: 1,
  exam_date: '2026-04-01',
  items: [],
  ...overrides,
});

describe('listMedicalExams', () => {
  beforeEach(() => jest.clearAllMocks());

  it('returns array on success', async () => {
    mockGet.mockResolvedValueOnce({ data: [makeExam(), makeExam({ id: 2 })] });
    const out = await listMedicalExams();
    expect(out).toHaveLength(2);
    expect(mockGet).toHaveBeenCalledWith('/medical-exams/me?limit=50');
  });

  it('passes limit override', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    await listMedicalExams(10);
    expect(mockGet).toHaveBeenCalledWith('/medical-exams/me?limit=10');
  });

  it('returns empty on error (no throw)', async () => {
    mockGet.mockRejectedValueOnce(new Error('500'));
    expect(await listMedicalExams()).toEqual([]);
  });

  it('returns empty when shape is wrong', async () => {
    mockGet.mockResolvedValueOnce({ data: { not: 'array' } });
    expect(await listMedicalExams()).toEqual([]);
  });
});

describe('uploadMedicalExamText', () => {
  beforeEach(() => jest.clearAllMocks());

  it('posts text fallback to the persistent medical-exams import endpoint', async () => {
    mockPost.mockResolvedValueOnce({
      data: { message: '导入成功', exam_id: 12, exam_date: '2026-05-11', items_count: 6 },
    });

    const out = await uploadMedicalExamText('ALT 31 U/L，肌酐 71 μmol/L', {
      exam_date: '2026-05-11',
      hospital_name: '手工录入',
    });

    expect(out.exam_id).toBe(12);
    expect(mockPost).toHaveBeenCalledWith('/medical-exams/import/text', {
      text: 'ALT 31 U/L，肌酐 71 μmol/L',
      exam_date: '2026-05-11',
      hospital_name: '手工录入',
    });
  });
});

describe('medical exam import uploads', () => {
  beforeEach(() => jest.clearAllMocks());

  it('normalizes PDF import responses for review-first UI', () => {
    const out = normalizeMedicalExamImportResult({
      message: 'PDF解析并导入成功',
      exam_id: 42,
      exam_date: '2026-06-18',
      hospital_name: '三甲医院',
      items_count: 28,
      conclusions_count: 2,
    }, 'pdf');

    expect(out).toMatchObject({
      source: 'pdf',
      exam_id: 42,
      examId: 42,
      examDate: '2026-06-18',
      hospitalName: '三甲医院',
      items_count: 28,
      itemsCount: 28,
      conclusionsCount: 2,
      reviewRequired: true,
    });
  });

  it('posts PDFs to the canonical medical-exams endpoint and returns normalized result', async () => {
    mockPost.mockResolvedValueOnce({
      data: { message: '导入成功', exam_id: 42, exam_date: '2026-06-18', items_count: 28 },
    });

    const out = await uploadMedicalExamPdf('file:///tmp/report.pdf', 'report.pdf');

    expect(out.examId).toBe(42);
    expect(out.itemsCount).toBe(28);
    expect(out.reviewRequired).toBe(true);
    expect(mockPost).toHaveBeenCalledWith(
      '/medical-exams/import/pdf',
      expect.any(FormData),
      expect.objectContaining({ timeout: 120_000 }),
    );
  });

  it('posts report images to the canonical medical-exams endpoint and preserves abnormal count', async () => {
    mockPost.mockResolvedValueOnce({
      data: { message: '图片 OCR 导入成功', exam_id: 77, items_count: 9, abnormal_count: 2 },
    });

    const out = await uploadMedicalExamImage('file:///tmp/report.png', 'report.png', 'image/png');

    expect(out.examId).toBe(77);
    expect(out.itemsCount).toBe(9);
    expect(out.abnormalCount).toBe(2);
    expect(mockPost).toHaveBeenCalledWith(
      '/medical-exams/import/image',
      expect.any(FormData),
      expect.objectContaining({ timeout: 120_000 }),
    );
  });
});

describe('review-first medical exam import', () => {
  beforeEach(() => jest.clearAllMocks());

  it('previews an image without calling a persistent import endpoint', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        filename: 'report.jpg',
        parsed_data: {
          report_date: '2026-07-29',
          report_type: 'biochemistry',
          institution: '测试医院',
          items: [{ name: '丙氨酸氨基转移酶', name_en: 'ALT', value: 25, unit: 'U/L' }],
        },
      },
    });

    const preview = await previewMedicalExamAsset({
      uri: 'file:///tmp/report.jpg',
      name: 'report.jpg',
      mimeType: 'image/jpeg',
    });

    expect(preview.items[0]).toMatchObject({ item_name: '丙氨酸氨基转移酶', item_code: 'ALT' });
    expect(mockPost).toHaveBeenCalledWith(
      '/medical-exams/parse-image-preview',
      expect.any(FormData),
      expect.objectContaining({ timeout: 120_000 }),
    );
    expect(mockPost).not.toHaveBeenCalledWith(
      '/medical-exams/import/image',
      expect.anything(),
      expect.anything(),
    );
  });

  it('normalizes OCR date and numeric strings before confirmation', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        filename: 'report.jpg',
        parsed_data: {
          report_date: '2026年7月9日',
          conclusion: '建议结合临床复核',
          items: [
            {
              name: '丙氨酸氨基转移酶',
              value: '25.6',
              reference_low: 0,
              reference_high: 40,
              is_abnormal: false,
            },
          ],
        },
      },
    });

    const preview = await previewMedicalExamAsset({
      uri: 'file:///tmp/report.jpg',
      name: 'report.jpg',
      mimeType: 'image/jpeg',
    });

    expect(preview.exam_date).toBe('2026-07-09');
    expect(preview.items[0]).toMatchObject({
      value: 25.6,
      value_text: null,
      reference_range: '0-40',
      is_abnormal: 'normal',
    });
  });

  it('rejects an empty parser response before showing a save action', async () => {
    mockPost.mockResolvedValueOnce({
      data: { filename: 'blank.pdf', parsed_data: { items: [] } },
    });

    await expect(previewMedicalExamAsset({
      uri: 'file:///tmp/blank.pdf',
      name: 'blank.pdf',
      mimeType: 'application/pdf',
    })).rejects.toThrow('未识别到可保存的体检内容');
  });

  it('confirms a preview with a stable idempotency key', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        id: 88,
        user_id: 3,
        exam_date: '2026-07-29',
        exam_type: 'biochemistry',
        hospital_name: '测试医院',
        conclusions: [],
        items: [
          { id: 1, exam_id: 88, item_name: 'ALT', value: 25, is_abnormal: 'normal' },
        ],
      },
    });

    const result = await confirmMedicalExamPreview({
      source: 'image',
      fileName: 'report.jpg',
      exam_date: '2026-07-29',
      exam_type: 'biochemistry',
      hospital_name: '测试医院',
      conclusions: [],
      items: [{ item_name: 'ALT', value: 25, is_abnormal: 'normal' }],
    }, 'medical-confirm-stable-key');

    expect(result).toMatchObject({ examId: 88, itemsCount: 1, source: 'image' });
    expect(mockPost).toHaveBeenCalledWith(
      '/medical-exams/',
      expect.objectContaining({ exam_date: '2026-07-29', items: expect.any(Array) }),
      { headers: { 'Idempotency-Key': 'medical-confirm-stable-key' } },
    );
  });
});

describe('countAbnormal', () => {
  it('counts only non-normal items', () => {
    const exam = makeExam({
      items: [
        { id: 1, exam_id: 1, item_name: 'LDL', value: 4.5, is_abnormal: 'high' },
        { id: 2, exam_id: 1, item_name: 'HDL', value: 1.2, is_abnormal: 'normal' },
        { id: 3, exam_id: 1, item_name: 'TC', value: 5.5, is_abnormal: 'abnormal' },
        { id: 4, exam_id: 1, item_name: 'TG', value: 1.1, is_abnormal: null },
        { id: 5, exam_id: 1, item_name: 'ALT', value: 25, is_abnormal: 'low' },
      ],
    });
    expect(countAbnormal(exam)).toBe(3); // LDL high, TC abnormal, ALT low
  });

  it('returns 0 for empty items', () => {
    expect(countAbnormal(makeExam())).toBe(0);
  });

  it('treats empty string is_abnormal as normal', () => {
    const exam = makeExam({
      items: [{ id: 1, exam_id: 1, item_name: 'X', value: 1, is_abnormal: '' }],
    });
    expect(countAbnormal(exam)).toBe(0);
  });

  it('case-insensitive normal check', () => {
    const exam = makeExam({
      items: [{ id: 1, exam_id: 1, item_name: 'X', value: 1, is_abnormal: 'NORMAL' }],
    });
    expect(countAbnormal(exam)).toBe(0);
  });
});

describe('compareExams', () => {
  it('returns delta + delta_pct for items in both exams', () => {
    const prev = makeExam({
      id: 1, exam_date: '2025-10-01',
      items: [
        { id: 1, exam_id: 1, item_name: 'LDL', item_code: 'LDL', value: 3.5, unit: 'mmol/L' },
        { id: 2, exam_id: 1, item_name: 'HDL', item_code: 'HDL', value: 1.4, unit: 'mmol/L' },
      ],
    });
    const cur = makeExam({
      id: 2, exam_date: '2026-04-01',
      items: [
        { id: 3, exam_id: 2, item_name: 'LDL', item_code: 'LDL', value: 4.1, unit: 'mmol/L', is_abnormal: 'high' },
        { id: 4, exam_id: 2, item_name: 'HDL', item_code: 'HDL', value: 1.3, unit: 'mmol/L' },
      ],
    });
    const out = compareExams(cur, prev);
    expect(out).toHaveLength(2);
    // LDL 变化更大, 应排第一
    expect(out[0].item_name).toBe('LDL');
    expect(out[0].current_value).toBe(4.1);
    expect(out[0].previous_value).toBe(3.5);
    expect(out[0].delta).toBeCloseTo(0.6, 1);
    expect(out[0].delta_pct).toBeCloseTo(17.14, 1);
    expect(out[0].current_abnormal).toBe(true);
    expect(out[0].previous_abnormal).toBe(false);
  });

  it('skips items missing in either exam', () => {
    const prev = makeExam({
      items: [{ id: 1, exam_id: 1, item_name: 'LDL', item_code: 'LDL', value: 3.5 }],
    });
    const cur = makeExam({
      items: [
        { id: 2, exam_id: 2, item_name: 'LDL', item_code: 'LDL', value: 4.1 },
        { id: 3, exam_id: 2, item_name: 'HbA1c', item_code: 'HBA1C', value: 5.8 },
      ],
    });
    const out = compareExams(cur, prev);
    expect(out).toHaveLength(1);
    expect(out[0].item_name).toBe('LDL');
  });

  it('handles 0 previous value safely (no /0 NaN)', () => {
    const prev = makeExam({
      items: [{ id: 1, exam_id: 1, item_name: 'X', item_code: 'X', value: 0 }],
    });
    const cur = makeExam({
      items: [{ id: 2, exam_id: 2, item_name: 'X', item_code: 'X', value: 5 }],
    });
    const out = compareExams(cur, prev);
    expect(out[0].delta).toBe(5);
    expect(out[0].delta_pct).toBe(0); // explicit fallback, not NaN
  });

  it('returns empty for empty inputs', () => {
    expect(compareExams(makeExam(), makeExam())).toEqual([]);
  });

  it('matches by item_name when item_code missing', () => {
    const prev = makeExam({
      items: [{ id: 1, exam_id: 1, item_name: 'LDL 胆固醇', value: 3.5 }],
    });
    const cur = makeExam({
      items: [{ id: 2, exam_id: 2, item_name: 'LDL 胆固醇', value: 4.0 }],
    });
    const out = compareExams(cur, prev);
    expect(out).toHaveLength(1);
  });
});

describe('relativeExamDate', () => {
  const NOW = new Date('2026-05-04');

  it('formats < 7 days as "N 天前"', () => {
    expect(relativeExamDate('2026-05-01', NOW)).toBe('3 天前');
    expect(relativeExamDate('2026-05-04', NOW)).toBe('0 天前');
  });

  it('formats 7-29 days as "N 周前"', () => {
    expect(relativeExamDate('2026-04-15', NOW)).toBe('2 周前');
  });

  it('formats < 1 year as "N 个月前"', () => {
    expect(relativeExamDate('2025-10-01', NOW)).toBe('7 个月前');
  });

  it('formats >= 1 year as "N 年前"', () => {
    expect(relativeExamDate('2024-01-01', NOW)).toBe('2 年前');
  });

  it('returns raw on invalid date', () => {
    expect(relativeExamDate('not-a-date', NOW)).toBe('not-a-date');
  });
});
