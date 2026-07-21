import React from 'react';
import { render } from '@testing-library/react-native';

import { MedicationDraftCardView } from '../MedicationDraftCard';

describe('MedicationDraftCardView', () => {
  it('shows every medication in a batch with actual intake separated from observed strength', () => {
    const { getAllByText, getByText } = render(
      <MedicationDraftCardView
        items={[
          {
            medication_name: '伊托必利',
            actual_dosage: '一粒',
            observed_strength: '50mg',
          },
          {
            medication_name: '替普瑞酮',
            actual_dosage: '一粒',
          },
        ]}
        taken_at="2026-07-21T21:15:00-04:00"
        boundary="确认后一次写入全部服药记录；未确认前不会写入。"
      />,
    );

    expect(getByText('伊托必利')).toBeTruthy();
    expect(getByText('替普瑞酮')).toBeTruthy();
    expect(getAllByText('本次 一粒')).toHaveLength(2);
    expect(getByText('规格 50mg')).toBeTruthy();
    expect(getByText('21:15')).toBeTruthy();
    expect(getByText('确认后一次写入全部服药记录；未确认前不会写入。')).toBeTruthy();
  });

  it('renders a truthful expired terminal instead of leaving the draft pending', () => {
    const { getByText, queryByText } = render(
      <MedicationDraftCardView
        items={[{ medication_name: '伊托必利', actual_dosage: '一粒' }]}
        decision_status="expired"
      />,
    );

    expect(getByText('用药 · 已过期')).toBeTruthy();
    expect(getByText('确认已过期，这组记录没有写入；请重新发送完整用药记录。')).toBeTruthy();
    expect(queryByText('需核对')).toBeNull();
  });

  it('lets medication facts follow the user Dynamic Type setting', () => {
    const { getByText } = render(
      <MedicationDraftCardView
        items={[{ medication_name: '伊托必利', actual_dosage: '一粒' }]}
      />,
    );

    expect(getByText('伊托必利').props.maxFontSizeMultiplier).toBeUndefined();
    expect(getByText('本次 一粒').props.maxFontSizeMultiplier).toBeUndefined();
  });
});
