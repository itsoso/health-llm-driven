/* eslint-disable import/first */
import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockBack = jest.fn();
const mockGetKnowledgeEntity = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack }),
  useLocalSearchParams: () => ({ type: 'gene', id: 'MTHFR' }),
}));

jest.mock('../../services/systemKnowledge', () => ({
  getKnowledgeEntity: (...args: any[]) => mockGetKnowledgeEntity(...args),
}));

import KnowledgeEntityScreen from '../knowledge/entity';

function renderScreen() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <KnowledgeEntityScreen />
    </QueryClientProvider>,
  );
}

describe('KnowledgeEntityScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetKnowledgeEntity.mockResolvedValue({
      entity: {
        doc_id: 'entity:gene:MTHFR',
        doc_type: 'entity',
        entity_type: 'gene',
        entity_id: 'MTHFR',
        title: 'MTHFR',
        summary: '参与一碳代谢和叶酸转化。',
        body: 'C677T 会影响叶酸向 5-MTHF 的转化效率。',
        evidence_level: 'B',
        evidence_level_detail: {
          label: 'B级',
          description: '中等证据：适合做健康管理参考。',
        },
        source_details: [
          {
            source: 'dedao:qiuzilong-genetics-07',
            label: '得到课程',
            display_name: '仇子龙·基因科学20讲 #07',
          },
        ],
      },
      linked_claims: [
        {
          doc_id: 'claim:c_mthfr_c677t_hcy_folate_boundary',
          doc_type: 'claim',
          title: 'MTHFR C677T 与叶酸转化边界',
          summary: '优先关注同型半胱氨酸、B12 与活性叶酸。',
          evidence_level: 'B',
        },
      ],
      claim_boundary: '仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。',
    });
  });

  it('loads entity bundle from route params and renders claims and sources', async () => {
    const screen = renderScreen();

    await waitFor(() => {
      expect(screen.getByText('MTHFR')).toBeTruthy();
    });

    expect(mockGetKnowledgeEntity).toHaveBeenCalledWith('gene', 'MTHFR');
    expect(screen.getByText(/叶酸向 5-MTHF/)).toBeTruthy();
    expect(screen.getByText(/MTHFR C677T/)).toBeTruthy();
    expect(screen.getByText('得到课程')).toBeTruthy();
    expect(screen.getByText(/不替代医生诊断/)).toBeTruthy();
  });
});
