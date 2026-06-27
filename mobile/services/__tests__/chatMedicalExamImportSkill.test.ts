/* eslint-disable import/first */
jest.mock('../medicalExams', () => ({
  uploadMedicalExamPdf: jest.fn(),
  uploadMedicalExamImage: jest.fn(),
}));

import { uploadMedicalExamPdf, uploadMedicalExamImage } from '../medicalExams';
import {
  CHAT_MEDICAL_EXAM_IMPORT_SKILL,
  buildMedicalExamImportResultCard,
  executeMedicalExamImportSkillForDocumentAsset,
} from '../chatMedicalExamImportSkill';

const mockUploadPdf = uploadMedicalExamPdf as jest.Mock;
const mockUploadImage = uploadMedicalExamImage as jest.Mock;

describe('chat medical exam import runtime skill', () => {
  beforeEach(() => jest.clearAllMocks());

  it('declares the runtime skill contract used by Chat', () => {
    expect(CHAT_MEDICAL_EXAM_IMPORT_SKILL).toMatchObject({
      id: 'medical_exam_import',
      writeScope: 'medical_exam',
      requiresUserAction: true,
    });
  });

  it('routes PDF assets to the canonical medical exam PDF importer', async () => {
    mockUploadPdf.mockResolvedValueOnce({
      examId: 42,
      exam_id: 42,
      itemsCount: 28,
      items_count: 28,
      reviewRequired: true,
      source: 'pdf',
      message: '导入成功',
    });

    const out = await executeMedicalExamImportSkillForDocumentAsset({
      uri: 'file:///tmp/report.pdf',
      name: 'report.pdf',
      mimeType: 'application/pdf',
    });

    expect(mockUploadPdf).toHaveBeenCalledWith('file:///tmp/report.pdf', 'report.pdf');
    expect(out.card.type).toBe('medical_exam_import_result');
    expect(out.card.data).toMatchObject({
      exam_id: 42,
      items_count: 28,
      source: 'pdf',
      review_required: true,
    });
  });

  it('routes image assets to the canonical medical exam image importer', async () => {
    mockUploadImage.mockResolvedValueOnce({
      examId: 77,
      exam_id: 77,
      itemsCount: 9,
      items_count: 9,
      abnormalCount: 2,
      abnormal_count: 2,
      reviewRequired: true,
      source: 'image',
      message: '图片 OCR 导入成功',
    });

    const out = await executeMedicalExamImportSkillForDocumentAsset({
      uri: 'file:///tmp/report.png',
      name: 'report.png',
      mimeType: 'image/png',
    });

    expect(mockUploadImage).toHaveBeenCalledWith('file:///tmp/report.png', 'report.png', 'image/png');
    expect(out.card.data).toMatchObject({
      exam_id: 77,
      items_count: 9,
      abnormal_count: 2,
      source: 'image',
    });
  });

  it('builds a review-first dynamic card payload', () => {
    const card = buildMedicalExamImportResultCard({
      examId: 91,
      exam_id: 91,
      examDate: '2026-06-27',
      exam_date: '2026-06-27',
      hospitalName: '三甲医院',
      hospital_name: '三甲医院',
      itemsCount: 12,
      items_count: 12,
      abnormalCount: 3,
      abnormal_count: 3,
      reviewRequired: true,
      source: 'text',
      message: '文本导入成功',
    });

    expect(card).toEqual({
      type: 'medical_exam_import_result',
      data: expect.objectContaining({
        exam_id: 91,
        exam_date: '2026-06-27',
        hospital_name: '三甲医院',
        items_count: 12,
        abnormal_count: 3,
        review_required: true,
        safety_note: expect.stringContaining('复核'),
      }),
    });
  });
});
