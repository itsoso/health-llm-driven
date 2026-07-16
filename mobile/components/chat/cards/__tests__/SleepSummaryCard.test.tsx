import React from 'react';
import { render } from '@testing-library/react-native';
import { SleepSummaryCardView } from '../SleepSummaryCard';

// 契约 fixture = 后端 build_sleep_summary 的 descriptor.data(字段逐一对齐)。
const data = {
  range_label: '近3天',
  nights: [
    { date: '2026-07-12', score: 82, duration_h: 7.4, deep_min: 98 },
    { date: '2026-07-11', score: 79, duration_h: 7.3, deep_min: 92 },
  ],
  averages: { score: 80, duration_h: 7.4, deep_min: 95 },
  duration: { current_h: 7.4, target_h: 8 },
  observations: [
    { severity: 'normal', label: '睡眠时长充足', detail: '平均 7.4h,一般建议 7–9h。' },
    { severity: 'caution', label: '深睡偏少', detail: '平均 40 分钟。' },
  ],
};

describe('SleepSummaryCardView', () => {
  it('renders header, nights (MM-DD), averages, observations, duration bar', () => {
    const { getByText } = render(<SleepSummaryCardView data={data} />);
    expect(getByText('睡眠概览')).toBeTruthy();
    expect(getByText('北京时间 · 近3天')).toBeTruthy();
    expect(getByText('07-12')).toBeTruthy();     // ISO → MM-DD
    expect(getByText('07-11')).toBeTruthy();
    expect(getByText('近期平均')).toBeTruthy();
    expect(getByText('睡眠时长充足')).toBeTruthy();
    expect(getByText('深睡偏少')).toBeTruthy();
    expect(getByText('7.4/8h')).toBeTruthy();     // 进度条 valueText
  });

  it('degrades gracefully: empty nights / missing fields / undefined do not crash', () => {
    expect(() => render(<SleepSummaryCardView data={{ nights: [], averages: {}, observations: [] }} />)).not.toThrow();
    expect(() => render(<SleepSummaryCardView data={{}} />)).not.toThrow();
    expect(() => render(<SleepSummaryCardView data={undefined} />)).not.toThrow();
    expect(() =>
      render(<SleepSummaryCardView data={{ nights: [{ date: '2026-07-10' }], averages: {} }} />),
    ).not.toThrow();
  });
});
