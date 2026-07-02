import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import HomeMedicationSummary from '../HomeMedicationSummary';
import type { MedicationTodayItem } from '../../../services/medications';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

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
  beforeEach(() => {
    mockPush.mockClear();
  });

  it('does not render when there are no active medication or supplement items', () => {
    const { toJSON } = render(<HomeMedicationSummary items={[]} />);
    expect(toJSON()).toBeNull();
  });

  it('does not render per-item rows or check-in buttons (compact summary only)', () => {
    const { queryByText, queryByLabelText } = render(
      <HomeMedicationSummary
        items={[
          item({ medication_id: 1, name: '二甲双胍', category: 'medication', taken_count: 0 }),
          item({
            medication_id: 2,
            name: 'Magnesium',
            category: 'supplement',
            total_count: 1,
            taken_count: 0,
          }),
        ]}
      />,
    );

    // 逐项名称、已服按钮均不再出现在首页
    expect(queryByText('二甲双胍')).toBeNull();
    expect(queryByText('Magnesium')).toBeNull();
    expect(queryByLabelText('记录已服用 二甲双胍')).toBeNull();
  });

  it('renders a compact summary row per category with pending count and taken/total badge', () => {
    const { getByText } = render(
      <HomeMedicationSummary
        items={[
          // 用药:3 条 → 1 条已服满(2/2)、2 条待服(0/1 + 0/1)
          //   → 项待服 = 2(项 = 条目,非剂次);badge taken 2 / total 4
          item({ medication_id: 1, name: '二甲双胍', category: 'medication', total_count: 2, taken_count: 2 }),
          item({ medication_id: 2, name: '降压药', category: 'medication', total_count: 1, taken_count: 0, reminder_times: [] }),
          item({ medication_id: 3, name: '阿司匹林', category: 'medication', total_count: 1, taken_count: 0, reminder_times: [] }),
          // 补剂:1 条待服(0/1)
          item({ medication_id: 4, name: 'Magnesium', category: 'supplement', total_count: 1, taken_count: 0, reminder_times: [] }),
        ]}
      />,
    );

    // 两条汇总行标题
    expect(getByText('用药')).toBeTruthy();
    expect(getByText('补剂')).toBeTruthy();

    // 待服数以「条目」计:用药 2 项、补剂 1 项(无未来提醒 → 不带下一剂)
    expect(getByText('2 项待服')).toBeTruthy();
    expect(getByText('1 项待服')).toBeTruthy();

    // 徽标 taken/total 以「剂次」计:用药 2/4;补剂 0/1
    expect(getByText('2/4 已服')).toBeTruthy();
    expect(getByText('0/1 已服')).toBeTruthy();
  });

  it('shows an all-done state when every dose in a category is taken', () => {
    const { getByText } = render(
      <HomeMedicationSummary
        items={[
          item({ medication_id: 1, name: '二甲双胍', category: 'medication', total_count: 2, taken_count: 2 }),
        ]}
      />,
    );

    expect(getByText('今日已全部服用')).toBeTruthy();
    expect(getByText('2/2 已服')).toBeTruthy();
  });

  it('navigates to /medications when a summary row is pressed', () => {
    const { getByText } = render(
      <HomeMedicationSummary
        items={[
          item({ medication_id: 1, name: '二甲双胍', category: 'medication', total_count: 1, taken_count: 0, reminder_times: [] }),
        ]}
      />,
    );

    fireEvent.press(getByText('用药'));
    expect(mockPush).toHaveBeenCalledWith('/medications');
  });

  it('derives "下一剂 HH:MM" from the earliest reminder time after now', () => {
    // 固定本地时间为 09:00 → 08:00 已过、20:00 为下一剂
    jest.useFakeTimers().setSystemTime(new Date(2026, 6, 2, 9, 0, 0));
    try {
      const { getByText } = render(
        <HomeMedicationSummary
          items={[
            item({
              medication_id: 1,
              name: '二甲双胍',
              category: 'medication',
              total_count: 2,
              taken_count: 0,
              reminder_times: ['08:00', '20:00'],
            }),
          ]}
        />,
      );

      // 1 条待服(项=条目);从其 reminder_times 派生下一剂 20:00
      expect(getByText('1 项待服 · 下一剂 20:00')).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it('omits the next-dose hint when no pending reminder time is in the future', () => {
    // 固定本地时间为 23:00 → 08:00 / 20:00 均已过,无未来剂次
    jest.useFakeTimers().setSystemTime(new Date(2026, 6, 2, 23, 0, 0));
    try {
      const { getByText, queryByText } = render(
        <HomeMedicationSummary
          items={[
            item({
              medication_id: 1,
              name: '二甲双胍',
              category: 'medication',
              total_count: 2,
              taken_count: 0,
              reminder_times: ['08:00', '20:00'],
            }),
          ]}
        />,
      );

      expect(getByText('1 项待服')).toBeTruthy();
      expect(queryByText(/下一剂/)).toBeNull();
    } finally {
      jest.useRealTimers();
    }
  });
});
