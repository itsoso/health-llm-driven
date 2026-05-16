import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { SupplementCardView } from '../SupplementCard';
import { EvidenceRefsRow } from '../EvidenceRefsRow';

describe('EvidenceRefsRow', () => {
  it('renders compact evidence entry on ordinary cards', () => {
    const screen = render(
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
    const loadClaim = jest.fn().mockResolvedValue({
      claim: {
        doc_id: 'claim:c_mthfr_c677t_hcy_folate_boundary',
        title: 'MTHFR C677T 与叶酸转化边界',
        evidence_level: 'B',
        confidence: 0.82,
        sources: ['dedao:qiuzilong-genetics-07'],
      },
      claim_boundary: '仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。',
    });

    const screen = render(
      <EvidenceRefsRow
        refs={['claim:c_mthfr_c677t_hcy_folate_boundary']}
        loadClaim={loadClaim}
      />,
    );

    fireEvent.press(screen.getByTestId('system-kb-evidence-chip'));

    await waitFor(() => {
      expect(loadClaim).toHaveBeenCalledWith('claim:c_mthfr_c677t_hcy_folate_boundary');
      expect(screen.getByText('MTHFR C677T 与叶酸转化边界')).toBeTruthy();
    });
    expect(screen.getByText('B级')).toBeTruthy();
    expect(screen.getByText('dedao:qiuzilong-genetics-07')).toBeTruthy();
    expect(screen.getByText(/不替代医生诊断/)).toBeTruthy();
  });
});
