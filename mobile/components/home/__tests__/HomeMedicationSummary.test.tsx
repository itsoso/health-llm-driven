import React from 'react';
import { render } from '@testing-library/react-native';

import HomeMedicationSummary from '../HomeMedicationSummary';
import type { MedicationTodayItem } from '../../../services/medications';

const item = (over: Partial<MedicationTodayItem>): MedicationTodayItem => ({
  medication_id: 1,
  name: '二甲双胍',
  dosage: '0.5g',
  category: null,
  total_count: 2,
  taken_count: 0,
  skipped_count: 0,
  last_taken_time: null,
  reminder_times: ['08:00', '20:00'],
  logs: [],
  ...over,
});

describe('HomeMedicationSummary', () => {
  it('does not render when there are no active medication or supplement items', () => {
    const { toJSON } = render(<HomeMedicationSummary items={[]} />);
    expect(toJSON()).toBeNull();
  });

  it('renders one combined compact summary when medication and supplement are done', () => {
    const { getByText, queryByText, getByLabelText } = render(
      <HomeMedicationSummary
        items={[
          item({ medication_id: 1, name: '二甲双胍', category: 'medication', taken_count: 2 }),
          item({ medication_id: 2, name: 'Magnesium', category: 'supplement', total_count: 1, taken_count: 1 }),
        ]}
      />,
    );

    expect(getByLabelText('今日用药补剂摘要')).toBeTruthy();
    expect(getByText('用药 / 补剂')).toBeTruthy();
    expect(getByText('今日已全部完成')).toBeTruthy();
    expect(getByText('用药 2/2')).toBeTruthy();
    expect(getByText('补剂 1/1')).toBeTruthy();
    expect(queryByText('今日用药')).toBeNull();
    expect(queryByText('今日补剂')).toBeNull();
  });

  it('keeps only pending categories expanded and summarizes completed categories', () => {
    const { getByText, queryByText } = render(
      <HomeMedicationSummary
        items={[
          item({ medication_id: 1, name: '二甲双胍', category: 'medication', taken_count: 2 }),
          item({ medication_id: 2, name: 'Magnesium', category: 'supplement', total_count: 1, taken_count: 0 }),
        ]}
      />,
    );

    expect(getByText('补剂')).toBeTruthy();
    expect(getByText('Magnesium')).toBeTruthy();
    expect(getByText('用药 2/2')).toBeTruthy();
    expect(queryByText('今日用药')).toBeNull();
  });
});
