import React from 'react';
import { render } from '@testing-library/react-native';
import { SupplementDraftCardView } from '../SupplementDraftCard';

const batch = {
  items: [
    { supplement_name: 'NAC', actual_dosage: '2粒' },
    { supplement_name: '槲皮素', actual_dosage: '1粒' },
    { supplement_name: '维生素D3+K2', actual_dosage: '1粒' },
    { supplement_name: '鱼油', actual_dosage: '1粒' },
  ],
  taken_date: '2026-10-10',
  decision_status: 'pending',
};

describe('photo supplement confirmation preview', () => {
  it('shows every item and its explicit quantity with the frozen date', () => {
    const view = render(<SupplementDraftCardView {...batch} />);
    batch.items.forEach(item => expect(view.getByText(item.supplement_name)).toBeTruthy());
    expect(view.getByText('本次 2粒')).toBeTruthy();
    expect(view.getAllByText('本次 1粒')).toHaveLength(3);
    expect(view.getByText('记录日期 2026-10-10')).toBeTruthy();
    expect(view.getByText('补剂 · 待确认')).toBeTruthy();
  });

  it.each([
    ['executed', '已记录'], ['dismissed', '已取消'], ['expired', '已过期'],
  ])('renders %s without a pending confirmation claim', (decision_status, label) => {
    const view = render(<SupplementDraftCardView {...batch} decision_status={decision_status} />);
    expect(view.getByText(`补剂 · ${label}`)).toBeTruthy();
    expect(view.queryByText('补剂 · 待确认')).toBeNull();
    expect(view.getByText('NAC')).toBeTruthy();
  });

  it('does not silently hide additional items', () => {
    const items = [...batch.items, { supplement_name: '维生素C', actual_dosage: '1粒' }];
    const view = render(<SupplementDraftCardView {...batch} items={items} />);
    expect(view.getByText('维生素C')).toBeTruthy();
    expect(view.getAllByText('本次 1粒')).toHaveLength(4);
  });
});

it('shows inventory strength separately from explicit intake quantity', () => {
  const view = render(<SupplementDraftCardView {...batch} items={[
    { supplement_name: 'NAC', actual_dosage: '2粒', observed_strength: '600mg/粒' },
  ]} />);
  expect(view.getByText('规格 600mg/粒')).toBeTruthy();
  expect(view.getByText('本次 2粒')).toBeTruthy();
});
