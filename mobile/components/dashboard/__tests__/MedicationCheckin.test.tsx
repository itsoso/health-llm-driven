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
    // 总进度 badge
    expect(getByText('0/2')).toBeTruthy();
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

  it('已服满 total_count: 显示完成态, 不再渲染「已服」按钮', () => {
    const { queryByLabelText, getByText } = render(
      <MedicationCheckin items={[item({ taken_count: 2 })]} />,
    );
    expect(getByText('2/2 次')).toBeTruthy();
    expect(queryByLabelText('记录已服用 二甲双胍')).toBeNull();
  });
});
