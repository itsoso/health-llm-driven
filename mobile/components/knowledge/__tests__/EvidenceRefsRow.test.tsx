import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EvidenceRefsRow } from '../EvidenceRefsRow';

jest.mock('../../../services/systemKnowledge', () => ({
  getKnowledgeClaim: jest.fn(),
  submitKnowledgeClaimFeedback: jest.fn(),
}));

const { getKnowledgeClaim } = jest.requireMock('../../../services/systemKnowledge');

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('knowledge EvidenceRefsRow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('normalizes claim refs and opens the shared claim sheet', async () => {
    getKnowledgeClaim.mockResolvedValue({
      claim: {
        doc_id: 'claim:c_recovery_low_reduce_intensity',
        title: '恢复不足时降低运动强度',
        evidence_level: 'B',
        confidence: 0.8,
        sources: ['system-kb:recovery'],
      },
      claim_boundary: '用于健康管理建议，不替代医生诊断。',
    });

    const screen = renderWithQuery(
      <EvidenceRefsRow
        refs={[
          'claim:c_recovery_low_reduce_intensity',
          { claim_id: 'claim:c_recovery_low_reduce_intensity' },
          { doc_id: 'entity:gene:MTHFR' },
        ]}
        testID="action-evidence-chip"
      />,
    );

    expect(screen.getByTestId('action-evidence-chip')).toBeTruthy();
    expect(screen.getByText('系统证据 1')).toBeTruthy();

    fireEvent.press(screen.getByTestId('action-evidence-chip'));

    await waitFor(() => {
      expect(getKnowledgeClaim).toHaveBeenCalledWith('claim:c_recovery_low_reduce_intensity');
      expect(screen.getByText('恢复不足时降低运动强度')).toBeTruthy();
    });
  });
});
