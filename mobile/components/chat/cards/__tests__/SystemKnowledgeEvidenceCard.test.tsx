import React from 'react';
import { render } from '@testing-library/react-native';
import { renderCard, renderServerCards } from '../registry';

jest.mock('../../../../services/api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

describe('SystemKnowledgeEvidenceCard', () => {
  const descriptor = {
    type: 'system_knowledge_evidence',
    data: {
      entity: { title: 'MTHFR', entity_id: 'MTHFR' },
      claims: [
        {
          doc_id: 'claim:c_mthfr_c677t_hcy_folate_boundary',
          title: 'MTHFR C677T 与叶酸转化边界',
          evidence_level: 'B',
          confidence: 0.82,
          sources: ['dedao:qiuzilong-genetics-07', 'pubmed:19033271'],
          source_details: [
            {
              source: 'dedao:qiuzilong-genetics-07',
              label: '得到课程',
              display_name: '仇子龙·基因科学20讲 #07',
            },
            {
              source: 'pubmed:19033271',
              label: 'PubMed',
              display_name: 'PubMed 19033271',
            },
          ],
          metadata: { review_status: 'reviewed' },
        },
      ],
      contraindications: [
        {
          title: '叶酸补充不替代 B12 缺乏评估',
          summary: '贫血或神经症状时先做临床评估。',
          severity: 'medium',
        },
      ],
      claim_boundary: '仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。',
    },
  };

  it('renders reviewed evidence refs, sources, safety hits, and boundary', () => {
    const element = renderCard(descriptor);
    expect(element).not.toBeNull();

    const screen = render(element!);
    expect(screen.getByText('MTHFR')).toBeTruthy();
    expect(screen.getByText('B级')).toBeTruthy();
    expect(screen.getByText('MTHFR C677T 与叶酸转化边界')).toBeTruthy();
    expect(screen.getByText(/已审核/)).toBeTruthy();
    expect(screen.getByText(/claim:c_mthfr_c677t_hcy_folate_boundary/)).toBeTruthy();
    expect(screen.getByText(/仇子龙/)).toBeTruthy();
    expect(screen.getByText(/PubMed 19033271/)).toBeTruthy();
    expect(screen.getByText(/安全命中/)).toBeTruthy();
    expect(screen.getByText(/叶酸补充不替代 B12 缺乏评估/)).toBeTruthy();
    expect(screen.getByText(/不替代医生诊断/)).toBeTruthy();
  });

  it('accepts backend card descriptors', () => {
    expect(renderServerCards([descriptor]).map((card) => card.type)).toEqual([
      'system_knowledge_evidence',
    ]);
  });
});
