import React from 'react';
import { render } from '@testing-library/react-native';
import { MedicalReportCardSpec, MedicalReportCardView } from '../MedicalReportCard';

describe('MedicalReportCardSpec.match', () => {
  const make = (query: string) => ({
    query,
    query_lower: query.toLowerCase(),
    toolsUsed: new Set<string>(),
    data: {},
    api: {},
  });

  it('matches 体检 queries', () => {
    expect(MedicalReportCardSpec.match(make('我最近的体检报告'))).toBe(14);
    expect(MedicalReportCardSpec.match(make('化验结果'))).toBe(14);
    expect(MedicalReportCardSpec.match(make('有哪些异常指标'))).toBe(14);
  });

  it('does not match unrelated queries', () => {
    expect(MedicalReportCardSpec.match(make('今天天气'))).toBeNull();
    expect(MedicalReportCardSpec.match(make('我体重多少'))).toBeNull();
  });
});

describe('MedicalReportCardView', () => {
  it('renders abnormal items', () => {
    const { getByText } = render(
      <MedicalReportCardView
        report_date="2026-04-15"
        abnormal_count={2}
        abnormals={[
          { name: '总胆固醇', value: 6.2, unit: 'mmol/L', trend: 'up' },
          { name: '空腹血糖', value: 6.5, unit: 'mmol/L', trend: 'stable' },
        ]}
      />,
    );
    expect(getByText('体检报告')).toBeTruthy();
    expect(getByText('2 项异常')).toBeTruthy();
    expect(getByText('总胆固醇')).toBeTruthy();
    expect(getByText(/6\.2/)).toBeTruthy();
    expect(getByText('最近报告: 2026-04-15')).toBeTruthy();
  });

  it('renders all normal message when no abnormals', () => {
    const { getByText } = render(
      <MedicalReportCardView
        report_date="2026-04-10"
        abnormal_count={0}
        abnormals={[]}
      />,
    );
    expect(getByText('所有指标正常')).toBeTruthy();
  });

  it('limits display to 5 items', () => {
    const items = Array.from({ length: 8 }, (_, i) => ({
      name: `指标${i}`,
      value: i + 1,
      unit: 'U',
    }));
    const { queryByText } = render(
      <MedicalReportCardView abnormal_count={8} abnormals={items} />,
    );
    expect(queryByText('指标0')).toBeTruthy();
    expect(queryByText('指标4')).toBeTruthy();
    expect(queryByText('指标5')).toBeNull();
  });
});
