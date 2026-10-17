import React from 'react';
import { fireEvent, waitFor } from '@testing-library/react-native';
import { renderWithProviders } from '../../test-utils';
const mockTodayTaken = jest.fn();
const mockLoad = jest.fn(); const mockSubmit = jest.fn(); const mockPush = jest.fn();
let mockParams: Record<string, string> = { id: '7', date: '2026-10-16', time: '18:00' };
let mockAuth = { user: { id: 1 }, token: 'a' };
let mockInvalidate = () => {};
jest.mock('expo-router', () => ({ useRouter: () => ({ back: jest.fn(), push: mockPush }), useLocalSearchParams: () => mockParams }));
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => mockAuth }));
jest.mock('../../services/api', () => ({ subscribeAuthSessionChange: (fn: () => void) => { mockInvalidate = fn; return jest.fn(); } }));
jest.mock('../../services/medicationReminderLanding', () => ({ ...jest.requireActual('../../services/medicationReminderLanding'), confirmTodayMedicationTaken: (...a: any[]) => mockTodayTaken(...a), loadMedicationReminder: (...a: any[]) => mockLoad(...a), submitMedicationReminder: (...a: any[]) => mockSubmit(...a) }));
// Container tests focus on lifecycle/action behavior, pure view has separate real-layout tests.
jest.mock('../../components/medication/MedicationReminderView', () => {
  const { View, Text, Pressable } = require('react-native');
  return { __esModule: true, default: (p: any) => <View><Text>{p.context?.medication?.name ?? 'empty'}</Text><Text>{p.error}</Text><Text>{p.message}</Text><Pressable accessibilityLabel="taken" disabled={p.busy || !p.context?.actionable} onPress={p.onTaken} /><Pressable accessibilityLabel="today-taken" onPress={p.onConfirmTodayTaken} /><Pressable accessibilityLabel="date" onPress={p.onConfirmDate} /><Pressable accessibilityLabel="retry" onPress={p.onRetry} /></View> };
});
import MedicationReminderScreen from '../medication-reminder';
const context = () => ({ user_id: 1, timezone: 'Asia/Shanghai', today_date: '2026-10-16', date: '2026-10-16', time: '18:00', requires_date_confirmation: false, revision: 'abc', actionable: true, reason: null, medication: { id: 7, user_id: 1, name: '合成药品', dosage: '1粒', reminder_times: ['18:00'] }, log: null });
beforeEach(() => { jest.clearAllMocks(); mockAuth = { user: { id: 1 }, token: 'a' }; mockParams = { id: '7', date: '2026-10-16', time: '18:00' }; mockLoad.mockResolvedValue(context()); mockSubmit.mockResolvedValue({ status: 'saved', context: { ...context(), actionable: false, log: { id: 10, status: 'taken' } } }); });
it('opens read-only and prevents duplicate submissions', async () => {
  let resolve: (x: any) => void = () => {}; mockSubmit.mockImplementation(() => new Promise(r => { resolve = r; }));
  const s = renderWithProviders(<MedicationReminderScreen />);
  await waitFor(() => expect(s.getByText('合成药品')).toBeTruthy()); expect(mockSubmit).not.toHaveBeenCalled();
  fireEvent.press(s.getByLabelText('taken')); fireEvent.press(s.getByLabelText('taken'));
  expect(mockSubmit).toHaveBeenCalledTimes(1);
  resolve({ status: 'saved', context: { ...context(), actionable: false, log: { id: 10, status: 'taken' } } });
  await waitFor(() => expect(s.getByText('已记录本次已服用')).toBeTruthy());
});
it('requires explicit date selection for undated notifications', async () => {
  mockParams = { id: '7', time: '18:00' }; mockLoad.mockResolvedValue({ ...context(), actionable: false, requires_date_confirmation: true });
  const s = renderWithProviders(<MedicationReminderScreen />); await waitFor(() => expect(s.getByText('合成药品')).toBeTruthy());
  expect(mockLoad.mock.calls[0][1].date).toBeUndefined(); fireEvent.press(s.getByLabelText('date'));
  await waitFor(() => expect(mockLoad).toHaveBeenLastCalledWith(1, expect.objectContaining({ date: '2026-10-16', sourceTimezone: 'Asia/Shanghai' }), expect.any(Function)));
  expect(mockSubmit).not.toHaveBeenCalled();
});
it('does not render stale account response or let it write', async () => {
  let resolve: (x: any) => void = () => {}; mockLoad.mockImplementation(() => new Promise(r => { resolve = r; }));
  const s = renderWithProviders(<MedicationReminderScreen />); mockAuth = { user: { id: 2 }, token: 'b' }; s.rerender(<MedicationReminderScreen />);
  resolve(context()); await waitFor(() => expect(s.getByText('登录状态已变化，请重新打开提醒')).toBeTruthy());
  expect(s.queryByText('合成药品')).toBeNull(); expect(mockSubmit).not.toHaveBeenCalled();
});
it('keeps uncertain submission disabled after a read with no confirmed log', async () => {
  mockSubmit.mockResolvedValue({ status: 'uncertain', context: context() });
  const s = renderWithProviders(<MedicationReminderScreen />); await waitFor(() => expect(s.getByText('合成药品')).toBeTruthy());
  fireEvent.press(s.getByLabelText('taken')); await waitFor(() => expect(s.getByText('记录结果尚未确认，请刷新核对，避免重复记录')).toBeTruthy());
  fireEvent.press(s.getByLabelText('retry')); await waitFor(() => expect(mockLoad).toHaveBeenCalledTimes(2));
  fireEvent.press(s.getByLabelText('taken')); expect(mockSubmit).toHaveBeenCalledTimes(1);
});
it('does not query invalid or missing identity', async () => {
  mockParams = { invalid: '1' }; const s = renderWithProviders(<MedicationReminderScreen />);
  await waitFor(() => expect(s.getByText('这条提醒缺少有效的药品信息，请到用药管理核对')).toBeTruthy()); expect(mockLoad).not.toHaveBeenCalled();
});

it('explicit today intake locks rapid taps and displays persisted receipt', async () => {
  mockParams = { id: '7', time: '18:00' };
  mockLoad.mockResolvedValue({ ...context(), actionable: false, requires_date_confirmation: true, reason: 'date_confirmation_required' });
  let resolve: (x: any) => void = () => {};
  mockTodayTaken.mockImplementation(() => new Promise(r => { resolve = r; }));
  const s = renderWithProviders(<MedicationReminderScreen />);
  await waitFor(() => expect(s.getByText('合成药品')).toBeTruthy());
  expect(mockTodayTaken).not.toHaveBeenCalled();
  fireEvent.press(s.getByLabelText('today-taken')); fireEvent.press(s.getByLabelText('today-taken'));
  expect(mockTodayTaken).toHaveBeenCalledTimes(1);
  resolve({ status: 'saved', context: { ...context(), actionable: false, log: { id: 10, status: 'taken' } } });
  await waitFor(() => expect(s.getByText('已记录本次已服用')).toBeTruthy());
  fireEvent.press(s.getByLabelText('today-taken'));
  expect(mockTodayTaken).toHaveBeenCalledTimes(1);
});
