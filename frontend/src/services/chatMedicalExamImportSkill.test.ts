import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api/medicalExams', () => ({
  importMedicalExamFile: vi.fn(),
}));

import { importMedicalExamFile } from './api/medicalExams';
import { executeMedicalExamImportSkillForFile } from './chatMedicalExamImportSkill';

const mockImportMedicalExamFile = importMedicalExamFile as unknown as ReturnType<typeof vi.fn>;

describe('web chat medical exam import skill', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('imports a report file and returns a dynamic result card plus follow-up prompt', async () => {
    mockImportMedicalExamFile.mockResolvedValueOnce({
      message: 'PDF 解析成功',
      source: 'pdf',
      reviewRequired: true,
      examId: 42,
      examDate: '2026-06-27',
      hospitalName: '三甲医院',
      itemsCount: 28,
      abnormalCount: 3,
      raw: {},
    });
    const file = new File(['pdf'], 'report.pdf', { type: 'application/pdf' });

    const result = await executeMedicalExamImportSkillForFile(file);

    expect(mockImportMedicalExamFile).toHaveBeenCalledWith(file);
    expect(result.skillId).toBe('medical_exam_import');
    expect(result.card).toMatchObject({
      type: 'medical_exam_import_result',
      data: {
        exam_id: 42,
        source: 'pdf',
        items_count: 28,
        abnormal_count: 3,
        review_required: true,
      },
    });
    expect(result.prompt).toContain('刚导入的体检报告');
    expect(result.context.safety_boundary).toContain('复核');
  });
});
