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
          title: 'MTHFR C677T 与叶酸转化边界',
          evidence_level: 'B',
          confidence: 0.82,
          sources: ['dedao:qiuzilong-genetics-07', 'pubmed:19033271'],
        },
      ],
      claim_boundary: '仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。',
    },
  };

  it('renders system knowledge evidence with sources and boundary', () => {
    const element = renderCard(descriptor);
    expect(element).not.toBeNull();

    const screen = render(element!);
    expect(screen.getByText('MTHFR')).toBeTruthy();
    expect(screen.getByText('B级')).toBeTruthy();
    expect(screen.getByText('MTHFR C677T 与叶酸转化边界')).toBeTruthy();
    expect(screen.getByText('dedao:qiuzilong-genetics-07')).toBeTruthy();
    expect(screen.getByText('pubmed:19033271')).toBeTruthy();
    expect(screen.getByText(/不替代医生诊断/)).toBeTruthy();
  });

  it('accepts backend card descriptors', () => {
    expect(renderServerCards([descriptor]).map((card) => card.type)).toEqual([
      'system_knowledge_evidence',
    ]);
  });
});
