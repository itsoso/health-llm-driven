/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('../../../services/medications', () => ({
  __esModule: true,
  logMedication: jest.fn(),
}));

import { logMedication } from '../../../services/medications';
import MedicationCheckin from '../MedicationCheckin';
import type { MedicationTodayItem } from '../../../services/medications';

const mockLog = logMedication as jest.Mock;

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

beforeEach(() => {
  jest.clearAllMocks();
});

describe('MedicationCheckin', () => {
  it('空态: 无在服药品时整卡不渲染', () => {
    const { toJSON: a } = render(<MedicationCheckin items={[]} />);
    expect(a()).toBeNull();
    const { toJSON: b } = render(<MedicationCheckin items={null} />);
    expect(b()).toBeNull();
  });

  it('渲染今日清单: 名称 / 剂量 / 进度 / 提醒时段', () => {
    const { getByText } = render(<MedicationCheckin items={[item({})]} />);
    expect(getByText('二甲双胍')).toBeTruthy();
    expect(getByText('0.5g')).toBeTruthy();
    expect(getByText('0/2 次')).toBeTruthy();
    expect(getByText('08:00 · 20:00')).toBeTruthy();
    // 折叠汇总: 总进度 badge + 待服汇总
    expect(getByText('0/2 已服')).toBeTruthy();
    expect(getByText('1 项待服')).toBeTruthy();
  });

  it('首页折叠: 默认只显示待服(≤3), 其余收进「查看全部」', () => {
    const items = [
      item({ medication_id: 1, name: '药A' }),
      item({ medication_id: 2, name: '药B' }),
      item({ medication_id: 3, name: '药C' }),
      item({ medication_id: 4, name: '药D' }),
      item({ medication_id: 5, name: '药E', taken_count: 2 }), // 已服满 → 折叠态不显示
    ];
    const { getByText, queryByText } = render(<MedicationCheckin items={items} />);
    // 待服只显示前 3 条
    expect(getByText('药A')).toBeTruthy();
    expect(getByText('药B')).toBeTruthy();
    expect(getByText('药C')).toBeTruthy();
    expect(queryByText('药D')).toBeNull();
    expect(queryByText('药E')).toBeNull();
    // 「查看全部 (5)」展开后显示全部
    fireEvent.press(getByText('查看全部 (5)'));
    expect(getByText('药D')).toBeTruthy();
    expect(getByText('药E')).toBeTruthy();
  });

  it('点「已服」乐观更新进度 + 调 logMedication(taken)', async () => {
    mockLog.mockResolvedValue({ id: 99 });
    const onChanged = jest.fn();
    const { getByLabelText, getByText } = render(
      <MedicationCheckin items={[item({})]} onChanged={onChanged} />,
    );

    fireEvent.press(getByLabelText('记录已服用 二甲双胍'));

    // 乐观: 进度立刻 0/2 → 1/2
    await waitFor(() => expect(getByText('1/2 次')).toBeTruthy());

    expect(mockLog).toHaveBeenCalledWith(
      expect.objectContaining({ medication_id: 1, status: 'taken' }),
    );
    // taken_time 是 HH:MM
    expect(mockLog.mock.calls[0][0].taken_time).toMatch(/^\d{2}:\d{2}$/);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('打卡失败回滚乐观进度', async () => {
    mockLog.mockRejectedValue(new Error('network'));
    const { getByLabelText, getByText } = render(<MedicationCheckin items={[item({})]} />);

    fireEvent.press(getByLabelText('记录已服用 二甲双胍'));

    // 回滚后仍是 0/2
    await waitFor(() => expect(getByText('0/2 次')).toBeTruthy());
  });

  it('全部已服满: 折叠态显示「全部完成」汇总, 展开后是完成态且无「已服」按钮', () => {
    const { queryByLabelText, getByText, queryByText } = render(
      <MedicationCheckin items={[item({ taken_count: 2 })]} />,
    );
    // 折叠态: 无待服 → 显示全部完成汇总, 不平铺药行
    expect(getByText('今日已全部服用')).toBeTruthy();
    expect(getByText('今日用药已全部完成')).toBeTruthy();
    expect(queryByText('2/2 次')).toBeNull();
    // 展开后看到完成态行, 仍无「已服」按钮
    fireEvent.press(getByText('今日用药已全部完成'));
    expect(getByText('2/2 次')).toBeTruthy();
    expect(queryByLabelText('记录已服用 二甲双胍')).toBeNull();
  });
});
