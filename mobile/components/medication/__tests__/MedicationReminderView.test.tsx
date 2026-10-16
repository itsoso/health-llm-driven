import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import MedicationReminderView, { type MedicationReminderViewProps } from '../MedicationReminderView';
import type { MedicationReminderContext } from '../../../services/medicationReminderLanding';

const context: MedicationReminderContext = {
  user_id: 7, timezone: 'Asia/Shanghai', today_date: '2026-10-16',
  date: '2026-10-16', time: '18:00', requires_date_confirmation: false,
  medication: { id: 2, name: '测试药品', dosage: '1 片', frequency: '每日一次',
    is_active: true, reminder_times: ['18:00'], timing_label: '晚餐后', user_id: 7 },
  log: null, actionable: true, reason: null, revision: 'revision',
};
const props = (override: Partial<MedicationReminderViewProps> = {}): MedicationReminderViewProps => ({
  context, loading: false, busy: false, error: null, message: null,
  onBack: jest.fn(), onManage: jest.fn(), onRetry: jest.fn(), onConfirmDate: jest.fn(),
  onTaken: jest.fn(), onSkipped: jest.fn(), ...override,
});

it('shows the exact slot and stored instructions; opening never records a dose', () => {
  const p = props();
  const screen = render(<MedicationReminderView {...p} />);
  for (const text of ['18:00', '2026-10-16', 'Asia/Shanghai', '测试药品', '1 片', '晚餐后']) {
    expect(screen.getByText(text)).toBeTruthy();
  }
  expect(p.onTaken).not.toHaveBeenCalled();
  fireEvent.press(screen.getByRole('button', { name: '确认已服用' }));
  expect(p.onTaken).toHaveBeenCalledTimes(1);
  fireEvent.press(screen.getByRole('button', { name: '记录本次未服用' }));
  expect(p.onSkipped).toHaveBeenCalledTimes(1);
});

it('requires explicit date confirmation for an undated reminder', () => {
  const p = props({ context: { ...context, requires_date_confirmation: true, actionable: false, reason: 'date_confirmation_required' } });
  const screen = render(<MedicationReminderView {...p} />);
  expect(screen.queryByText('确认已服用')).toBeNull();
  expect(screen.getByText('提醒日期待确认')).toBeTruthy();
  fireEvent.press(screen.getByRole('button', { name: '查看今天这次提醒' }));
  expect(p.onConfirmDate).toHaveBeenCalledTimes(1);
});

it.each(['taken', 'skipped'] as const)('shows persisted %s without recording controls', (status) => {
  const screen = render(<MedicationReminderView {...props({ context: { ...context,
    log: { id: 9, medication_id: 2, taken_date: context.date, taken_time: '18:00', status },
  } })} />);
  expect(screen.getByText(status === 'taken' ? '已记录 · 已服用' : '已记录 · 本次未服用')).toBeTruthy();
  expect(screen.queryByText('确认已服用')).toBeNull();
  expect(screen.queryByText('记录本次未服用')).toBeNull();
});

it.each(['inactive', 'schedule_changed', 'invalid_medication_name', 'future_occurrence'])('blocks quick actions for %s', (reason) => {
  const screen = render(<MedicationReminderView {...props({ context: { ...context, actionable: false, reason } })} />);
  expect(screen.queryByText('确认已服用')).toBeNull();
  expect(screen.getByRole('button', { name: '查看用药管理' })).toBeTruthy();
});

it('disables both writes while saving', () => {
  const p = props({ busy: true });
  const screen = render(<MedicationReminderView {...p} />);
  fireEvent.press(screen.getByRole('button', { name: '确认已服用' }));
  fireEvent.press(screen.getByRole('button', { name: '记录本次未服用' }));
  expect(p.onTaken).not.toHaveBeenCalled();
  expect(p.onSkipped).not.toHaveBeenCalled();
});

it('shows a retry instead of a write on error, even with stale actionable context', () => {
  const p = props({ error: '暂时无法核对这次提醒' });
  const screen = render(<MedicationReminderView {...p} />);
  expect(screen.getByText(p.error!)).toBeTruthy();
  expect(screen.queryByText('确认已服用')).toBeNull();
  fireEvent.press(screen.getByRole('button', { name: '重新核对' }));
  expect(p.onRetry).toHaveBeenCalledTimes(1);
});

it('does not expose previous dose controls while loading', () => {
  const screen = render(<MedicationReminderView {...props({ loading: true })} />);
  expect(screen.queryByText('确认已服用')).toBeNull();
  expect(screen.queryByText('测试药品')).toBeNull();
});

it('offers valid stored schedule slots only; choosing one does not record a dose', () => {
  const onSelectTime = jest.fn();
  const p = props({ onSelectTime, context: { ...context, time: null, actionable: false, reason: 'time_required',
    medication: { ...context.medication, reminder_times: ['08:00', '18:00', '25:00', '9:30', '18:00'] },
  } });
  const screen = render(<MedicationReminderView {...p} />);
  fireEvent.press(screen.getByRole('button', { name: '查看 18:00 这次提醒' }));
  expect(onSelectTime).toHaveBeenCalledWith('18:00');
  expect(p.onTaken).not.toHaveBeenCalled();
  expect(screen.queryByText('25:00')).toBeNull();
  expect(screen.queryByText('9:30')).toBeNull();
});

it('provides read-only retry for an uncertain outcome without exposing another write', () => {
  const p = props({ context: { ...context, actionable: false }, message: '保存结果尚未确认，请重新核对。' });
  const screen = render(<MedicationReminderView {...p} />);
  expect(screen.queryByText('确认已服用')).toBeNull();
  fireEvent.press(screen.getByRole('button', { name: '重新核对' }));
  expect(p.onRetry).toHaveBeenCalledTimes(1);
});
