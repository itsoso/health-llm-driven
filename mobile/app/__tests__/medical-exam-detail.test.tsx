import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockRefetch = jest.fn();
let mockDetail: any;
let mockGate = 'unlocked';
const mockUseQuery = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ back: jest.fn(), push: jest.fn() }), useLocalSearchParams: () => ({ id: '501' }) }));
jest.mock('../../hooks/useRouteBiometricGate', () => ({ useRouteBiometricGate: () => ({ status: mockGate, retry: jest.fn() }) }));
jest.mock('@tanstack/react-query', () => ({
  useQuery: (options: any) => mockUseQuery(options),
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));
import MedicalExamDetailScreen from '../medical-exam-detail';

describe('owned report detail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGate = 'unlocked';
    mockDetail = { data: { id: 501, exam_date: '2020-01-01', items: [], overall_assessment: '合成摘要'.repeat(300) + '完整末尾' } };
    mockUseQuery.mockImplementation((options: any) => options.queryKey[0] === 'medical-exam'
      ? { refetch: mockRefetch, ...mockDetail }
      : { data: [], isLoading: false });
  });
  it('renders an older complete report even when absent from the recent list', () => {
    const view = render(<MedicalExamDetailScreen />);
    expect(view.getByText(mockDetail.data.overall_assessment)).toBeTruthy();
    expect(view.getByText(/不是原始影像/)).toBeTruthy();
    expect(view.queryByText('记录不存在或已被删除')).toBeNull();
  });
  it('shows load failure with retry instead of claiming deletion', () => {
    mockDetail = { isError: true };
    const view = render(<MedicalExamDetailScreen />);
    expect(view.getByText('报告加载失败，请重试')).toBeTruthy();
    fireEvent.press(view.getByText('重试'));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });
  it('does not enable owned report reads before biometric unlock', () => {
    mockGate = 'locked';
    render(<MedicalExamDetailScreen />);
    const detail = mockUseQuery.mock.calls.find(([options]) => options.queryKey[0] === 'medical-exam')[0];
    expect(detail.enabled).toBe(false);
  });
});
