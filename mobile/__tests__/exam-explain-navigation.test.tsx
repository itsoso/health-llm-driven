import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockRouter = {
  back: jest.fn(), push: jest.fn(), dismissTo: jest.fn(), canGoBack: jest.fn(() => true),
};
let mockQuery: any;

jest.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ id: '7' }),
  useRouter: () => mockRouter,
  Stack: { Screen: () => null },
}));
jest.mock('@tanstack/react-query', () => ({ useQuery: () => mockQuery }));
jest.mock('../services/examExplain', () => ({ fetchExamExplain: jest.fn() }));

import ExamExplainScreen from '../app/exam-explain/[id]';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createExamExplainAgentContext, serializeAgentContext } from '../utils/agentContext';

const report = {
  exam: { id: 7, exam_type: '测试体检', exam_date: '2026-09-01' },
  abnormal_items: [{ item_name: '测试指标', value: 2, value_text: null, unit: null,
    reference_range: '3–5', is_abnormal: 'low', gene_links: [] }],
  explanation: { summary: '测试报告解读', actions: [], recheck_window_days: 0, see_doctor_specialty: null },
  trends: {}, related_cards: [], user_gene_hits: [],
};

describe('exam explanation navigation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRouter.canGoBack.mockReturnValue(true);
    mockQuery = { data: report, isLoading: false, error: null };
  });

  it.each(['loading', 'error', 'success'])('provides a visible main-screen exit in %s state', (state) => {
    if (state === 'loading') mockQuery = { isLoading: true };
    if (state === 'error') mockQuery = { error: new Error('测试加载失败') };
    const screen = render(<ExamExplainScreen />);
    expect(screen.getByText('AI 体检解读')).toBeTruthy();
    fireEvent.press(screen.getByLabelText('返回主屏幕'));
    expect(mockRouter.dismissTo).toHaveBeenCalledWith('/(tabs)/chat');
    expect(mockRouter.push).not.toHaveBeenCalled();
  });

  it('goes back to the previous report screen when history exists', () => {
    fireEvent.press(render(<ExamExplainScreen />).getByLabelText('返回上一页'));
    expect(mockRouter.back).toHaveBeenCalledTimes(1);
    expect(mockRouter.dismissTo).not.toHaveBeenCalled();
  });

  it('falls back to main chat for a direct report deep link without history', () => {
    mockRouter.canGoBack.mockReturnValue(false);
    fireEvent.press(render(<ExamExplainScreen />).getByLabelText('返回上一页'));
    expect(mockRouter.dismissTo).toHaveBeenCalledWith('/(tabs)/chat');
    expect(mockRouter.back).not.toHaveBeenCalled();
  });

  it('unwinds modal history and carries the report and original read-only prompt into main chat', () => {
    fireEvent.press(render(<ExamExplainScreen />).getByLabelText('跟小巴讨论这些异常项'));
    expect(mockRouter.dismissTo).toHaveBeenCalledWith({
      pathname: '/(tabs)/chat',
      params: {
        prompt: '请基于这次体检异常解读，帮我按优先级梳理风险、行动、复查安排和需要向医生确认的问题。不要替代诊断或用药建议。',
        context: serializeAgentContext(createExamExplainAgentContext(report)),
        badge: '体检异常 1 项', newChat: '1', contextEntry: '1',
      },
    });
    expect(mockRouter.push).not.toHaveBeenCalled();
  });

  it('preserves push navigation for existing feedback-link consumers without opt-in', () => {
    fireEvent.press(render(<AgentFeedbackLink label="普通讨论" prompt="分析" context={{ from: 'test' }} badge="测试" />).getByLabelText('普通讨论'));
    expect(mockRouter.push).toHaveBeenCalledTimes(1);
    expect(mockRouter.dismissTo).not.toHaveBeenCalled();
  });
});
