import React from 'react';
import { act, fireEvent, waitFor } from '@testing-library/react-native';
import { renderWithProviders } from '../../test-utils';
const mockLoad = jest.fn(); const mockPush = jest.fn();
let mockParams: Record<string, string>;
let mockAuth = { user: { id: 1 }, token: 'a' };
let mockInvalidate = () => {};
jest.mock('expo-router', () => ({
  useRouter: () => ({ back: jest.fn(), push: mockPush }), useLocalSearchParams: () => mockParams,
  useFocusEffect: (fn: any) => require('react').useEffect(fn, [fn]),
}));
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => mockAuth }));
jest.mock('../../services/api', () => ({ subscribeAuthSessionChange: (fn: () => void) => { mockInvalidate = fn; return jest.fn(); } }));
jest.mock('../../services/medicationReminderLanding', () => ({ loadMedicationReminder: (...args: any[]) => mockLoad(...args) }));
import Screen from '../medication-reminders';
const context = (id: number) => ({ medication: { id, name: `合成药品${id}`, dosage: '合成剂量' }, log: null });
beforeEach(() => {
  jest.clearAllMocks(); mockAuth = { user: { id: 1 }, token: 'a' };
  mockParams = { ids: '7,8', date: '2026-10-24', time: '18:00', sourceTimezone: 'Asia/Shanghai' };
  mockLoad.mockImplementation(async (_owner, target) => context(target.id));
});
it('reads every exact occurrence and opens explicit individual confirmation without writing', async () => {
  const s = renderWithProviders(<Screen />);
  await waitFor(() => expect(s.getByText('合成药品8')).toBeTruthy());
  expect(mockLoad).toHaveBeenCalledTimes(2);
  expect(mockLoad).toHaveBeenCalledWith(1, { id: 7, date: '2026-10-24', time: '18:00', sourceTimezone: 'Asia/Shanghai' }, expect.any(Function));
  expect(mockPush).not.toHaveBeenCalled();
  fireEvent.press(s.getByLabelText('查看第 2 项提醒'));
  expect(mockPush).toHaveBeenCalledWith('/medication-reminder?id=8&date=2026-10-24&time=18%3A00&sourceTimezone=Asia%2FShanghai');
});
it('retains a failed item, allowing a successful item to be viewed', async () => {
  mockLoad.mockImplementation(async (_owner, target) => { if (target.id === 7) throw Error('unavailable'); return context(8); });
  const s = renderWithProviders(<Screen />);
  await waitFor(() => expect(s.getByText('合成药品8')).toBeTruthy());
  expect(s.getByText('第 1 项提醒')).toBeTruthy();
  expect(s.queryByLabelText('查看第 1 项提醒')).toBeNull();
});
it('rejects any malformed group before querying', async () => {
  mockParams.ids = '7,bad';
  const s = renderWithProviders(<Screen />);
  await waitFor(() => expect(s.getByText('这条提醒信息不完整，请到用药管理核对')).toBeTruthy());
  expect(mockLoad).not.toHaveBeenCalled();
});
it('never resolves a missing date to today', async () => {
  delete mockParams.date;
  renderWithProviders(<Screen />);
  await waitFor(() => expect(mockLoad).toHaveBeenCalledTimes(2));
  expect(mockLoad.mock.calls[0][1].date).toBeUndefined();
});
it('rejects stale reads and stops querying after account switch', async () => {
  let resolve!: (value: any) => void;
  mockLoad.mockImplementation(() => new Promise(r => { resolve = r; }));
  const s = renderWithProviders(<Screen />);
  mockAuth = { user: { id: 2 }, token: 'b' }; s.rerender(<Screen />);
  await act(async () => resolve(context(7)));
  expect(s.queryByText('合成药品7')).toBeNull();
  expect(s.getByText('登录状态已变化，请重新打开提醒')).toBeTruthy();
  expect(mockLoad).toHaveBeenCalledTimes(1);
});
it('clears names and disables row navigation when session is invalidated', async () => {
  const s = renderWithProviders(<Screen />);
  await waitFor(() => expect(s.getByText('合成药品8')).toBeTruthy());
  act(() => mockInvalidate());
  expect(s.queryByText('合成药品8')).toBeNull();
  expect(s.queryByLabelText('查看第 2 项提醒')).toBeNull();
});

it.each([
  { requires_date_confirmation: true, reason: 'date_confirmation_required', label: '日期待确认' },
  { requires_date_confirmation: false, reason: 'timezone_mismatch', label: '时区需核对' },
])('does not attach an existing log to an unconfirmed occurrence: $reason', async fields => {
  mockParams.ids = '7';
  mockLoad.mockResolvedValue({ ...context(7), ...fields, log: { status: 'taken' } });
  const s = renderWithProviders(<Screen />);
  await waitFor(() => expect(s.getByText('合成药品7')).toBeTruthy());
  expect(s.getByText(fields.label)).toBeTruthy();
  expect(s.queryByText('已记录服用')).toBeNull();
  expect(s.queryByText('查看记录 →')).toBeNull();
  expect(s.getByText('查看并核对 →')).toBeTruthy();
});
