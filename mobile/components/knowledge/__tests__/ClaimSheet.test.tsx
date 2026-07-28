import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClaimSheet } from '../ClaimSheet';

jest.mock('../../../services/systemKnowledge', () => ({
  getKnowledgeClaim: jest.fn(),
  submitKnowledgeClaimFeedback: jest.fn(),
}));

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const { getKnowledgeClaim, submitKnowledgeClaimFeedback } = jest.requireMock(
  '../../../services/systemKnowledge',
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

function makeBundle(claimId: string) {
  return {
    claim: {
      doc_id: claimId,
      doc_type: 'claim',
      title: `Claim ${claimId}`,
      summary: '叶酸代谢与同型半胱氨酸的边界说明',
      evidence_level: 'B',
      evidence_level_detail: {
        level: 'B',
        label: 'B级',
        description: '中等证据：来自人群研究、临床观察或有来源的专家课程。',
      },
      confidence: 0.82,
      sources: ['dedao:qiuzilong-genetics-07', 'pubmed:19033271'],
      source_details: [
        {
          source: 'dedao:qiuzilong-genetics-07',
          kind: 'course',
          label: '得到课程',
          trust_tier: 'expert_course',
          display_name: '仇子龙·基因科学20讲 #07',
        },
        {
          source: 'pubmed:19033271',
          kind: 'research',
          label: 'PubMed',
          trust_tier: 'clinical_research',
          display_name: 'PubMed 19033271',
        },
      ],
    },
    neighbors: [
      {
        doc_id: 'entity:gene/MTHFR',
        doc_type: 'entity',
        entity_type: 'gene',
        entity_id: 'MTHFR',
        title: 'MTHFR',
        summary: '影响叶酸代谢',
        evidence_level: 'A',
      },
    ],
    claim_boundary: '仅用于健康管理，不替代医生诊断、治疗或用药决策。',
  };
}

describe('ClaimSheet', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPush.mockClear();
  });

  it('returns null when hidden', () => {
    const screen = renderWithQuery(
      <ClaimSheet visible={false} onClose={() => {}} claimIds={['claim:foo']} />,
    );
    expect(screen.toJSON()).toBeNull();
  });

  it('deduplicates claim ids before loading evidence details', async () => {
    getKnowledgeClaim.mockResolvedValue(makeBundle('claim:c_mthfr_folate'));

    const screen = renderWithQuery(
      <ClaimSheet
        visible
        onClose={() => {}}
        claimIds={[
          'claim:c_mthfr_folate',
          'claim:c_mthfr_folate',
          'claim:c_mthfr_folate',
        ]}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Claim claim:c_mthfr_folate')).toBeTruthy();
    });
    expect(getKnowledgeClaim).toHaveBeenCalledTimes(1);
  });

  it('renders claim detail, neighbor entity, sources, and feedback', async () => {
    getKnowledgeClaim.mockResolvedValue(makeBundle('claim:c_mthfr_folate'));
    submitKnowledgeClaimFeedback.mockResolvedValue({ ok: true });

    const screen = renderWithQuery(
      <ClaimSheet
        visible
        onClose={() => {}}
        claimIds={['claim:c_mthfr_folate']}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Claim claim:c_mthfr_folate')).toBeTruthy();
    });
    expect(screen.getByText('B级')).toBeTruthy();
    expect(screen.getByText(/中等证据/)).toBeTruthy();
    expect(screen.getByText('置信度 82%')).toBeTruthy();
    expect(screen.getByText(/叶酸代谢与同型半胱氨酸/)).toBeTruthy();
    expect(screen.getByText('MTHFR')).toBeTruthy();
    expect(screen.getByText('得到课程')).toBeTruthy();
    expect(screen.getByText('PubMed')).toBeTruthy();
    expect(screen.getByText(/仇子龙/)).toBeTruthy();

    fireEvent.press(screen.getByTestId('claim-feedback-button'));

    await waitFor(() => {
      expect(submitKnowledgeClaimFeedback).toHaveBeenCalledWith(
        'claim:c_mthfr_folate',
        expect.stringContaining('用户'),
      );
      expect(screen.getByText('已记录反馈')).toBeTruthy();
    });
  });

  it('opens the entity deep-link page from a related entity', async () => {
    getKnowledgeClaim.mockResolvedValue(makeBundle('claim:c_mthfr_folate'));
    const onClose = jest.fn();

    const screen = renderWithQuery(
      <ClaimSheet
        visible
        onClose={onClose}
        claimIds={['claim:c_mthfr_folate']}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('MTHFR')).toBeTruthy();
    });

    fireEvent.press(screen.getByTestId('knowledge-entity-card-entity:gene/MTHFR'));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mockPush).toHaveBeenCalledWith({
      pathname: '/knowledge/entity',
      params: { type: 'gene', id: 'MTHFR' },
    });
  });
});
