import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SupplementCardView } from '../SupplementCard';
import { EvidenceRefsRow } from '../EvidenceRefsRow';

jest.mock('../../../../services/systemKnowledge', () => ({
  getKnowledgeClaim: jest.fn(),
  submitKnowledgeClaimFeedback: jest.fn(),
}));

const { getKnowledgeClaim, submitKnowledgeClaimFeedback } = jest.requireMock(
  '../../../../services/systemKnowledge',
);

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('EvidenceRefsRow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders compact evidence entry on ordinary cards', () => {
    const screen = renderWithQuery(
      <SupplementCardView
        checked={1}
        total={2}
        pending_names={['5-MTHF']}
        evidence_refs={[
          'claim:c_mthfr_c677t_hcy_folate_boundary',
          'claim:c_5mthf_b12_boundary',
        ]}
      />,
    );

    expect(screen.getByText('系统证据 2')).toBeTruthy();
  });

  it('opens claim details from system knowledge', async () => {
    getKnowledgeClaim.mockResolvedValue({
      claim: {
        doc_id: 'claim:c_mthfr_c677t_hcy_folate_boundary',
        title: 'MTHFR C677T 与叶酸转化边界',
        evidence_level: 'B',
        confidence: 0.82,
        sources: ['dedao:qiuzilong-genetics-07'],
      },
      claim_boundary: '仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。',
    });

    const screen = renderWithQuery(
      <EvidenceRefsRow refs={['claim:c_mthfr_c677t_hcy_folate_boundary']} />,
    );

    fireEvent.press(screen.getByTestId('system-kb-evidence-chip'));

    await waitFor(() => {
      expect(getKnowledgeClaim).toHaveBeenCalledWith(
        'claim:c_mthfr_c677t_hcy_folate_boundary',
      );
      expect(screen.getByText('MTHFR C677T 与叶酸转化边界')).toBeTruthy();
    });
    expect(screen.getByText('B级')).toBeTruthy();
    expect(screen.getByText(/dedao:qiuzilong-genetics-07/)).toBeTruthy();
    expect(screen.getByText(/不替代医生诊断/)).toBeTruthy();
  });

  it('submits disagree feedback for a claim', async () => {
    getKnowledgeClaim.mockResolvedValue({
      claim: {
        doc_id: 'claim:c_mthfr_c677t_hcy_folate_boundary',
        title: 'MTHFR C677T 与叶酸转化边界',
        evidence_level: 'B',
        confidence: 0.82,
      },
    });
    submitKnowledgeClaimFeedback.mockResolvedValue({ ok: true });

    const screen = renderWithQuery(
      <EvidenceRefsRow refs={['claim:c_mthfr_c677t_hcy_folate_boundary']} />,
    );

    fireEvent.press(screen.getByTestId('system-kb-evidence-chip'));

    await waitFor(() => {
      expect(screen.getByText('这条证据不对')).toBeTruthy();
    });

    fireEvent.press(screen.getByTestId('claim-feedback-button'));

    await waitFor(() => {
      expect(submitKnowledgeClaimFeedback).toHaveBeenCalledWith(
        'claim:c_mthfr_c677t_hcy_folate_boundary',
        '用户在移动端反馈这条系统知识库证据不适用',
      );
      expect(screen.getByText('已记录反馈')).toBeTruthy();
    });
  });
});
