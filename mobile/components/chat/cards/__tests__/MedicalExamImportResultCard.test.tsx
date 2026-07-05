import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import { MedicalExamImportResultCardSpec, MedicalExamImportResultCardView } from '../MedicalExamImportResultCard';

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('MedicalExamImportResultCard', () => {
  beforeEach(() => jest.clearAllMocks());

  it('is server/local only and does not match free-text queries', () => {
    expect(MedicalExamImportResultCardSpec.type).toBe('medical_exam_import_result');
    expect(MedicalExamImportResultCardSpec.match({
      query: '体检报告',
      query_lower: '体检报告',
      toolsUsed: new Set(),
      data: {},
      api: {},
    })).toBeNull();
  });

  it('renders the import summary and review warning', () => {
    const { getAllByText, getByText } = render(
      <MedicalExamImportResultCardView
        exam_id={42}
        exam_date="2026-06-18"
        hospital_name="三甲医院"
        items_count={28}
        abnormal_count={3}
        source="pdf"
        review_required
        safety_note="OCR/AI 解析结果需要复核后再用于判断。"
      />,
    );

    expect(getByText('体检报告已导入')).toBeTruthy();
    expect(getByText('28 项指标')).toBeTruthy();
    expect(getAllByText('3 项异常').length).toBeGreaterThan(0);
    expect(getByText(/OCR\/AI 解析结果需要复核/)).toBeTruthy();
  });

  it('can navigate to medical exams and ask Reva with context', () => {
    const { getByLabelText } = render(
      <MedicalExamImportResultCardView
        exam_id={42}
        items_count={28}
        abnormal_count={3}
        source="pdf"
        review_required
        safety_note="OCR/AI 解析结果需要复核后再用于判断。"
      />,
    );

    fireEvent.press(getByLabelText('查看体检记录'));
    expect(mockPush).toHaveBeenCalledWith('/medical-exams');

    fireEvent.press(getByLabelText('让小巴解读这次导入'));
    expect(mockPush).toHaveBeenCalledWith(expect.objectContaining({
      pathname: '/(tabs)/chat',
      params: expect.objectContaining({
        badge: '体检导入结果',
        prompt: expect.stringContaining('刚导入的体检报告'),
      }),
    }));
  });
});
