import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import Sheet from '../SupplementQuickCheckinSheet';
import { loadSupplementSnapshot, submitSupplementSelection } from '../../../services/supplementQuickCheckin';
let mockGroupProps: any;
jest.mock('../SupplementGroupsPanel', () => ({ __esModule: true, default: (props: any) => { mockGroupProps = props; return null; } }));
let mockAuthListener: (() => void) | undefined;
const mockPush = jest.fn();
const mockInvalidate = jest.fn().mockResolvedValue(undefined);
jest.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: mockInvalidate }) }));
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ token: 'test', user: { id: 7 } }) }));
jest.mock('../../../services/api', () => ({ subscribeAuthSessionChange: (fn: () => void) => { mockAuthListener = fn; return () => {}; } }));
jest.mock('../../../services/supplementQuickCheckin', () => ({ loadSupplementSnapshot: jest.fn(), submitSupplementSelection: jest.fn() }));
const load = loadSupplementSnapshot as jest.Mock;
const submit = submitSupplementSelection as jest.Mock;
const snapshot = { userId: 7, timezone: 'Asia/Shanghai', date: '2026-10-16', rows: [
  { supplement: { id: 1, name: '测试补剂 A', dosage: '1 粒', is_active: true }, record: null },
  { supplement: { id: 2, name: '测试补剂 B', is_active: true }, record: { id: 8, taken: true } },
] };
beforeEach(() => { jest.clearAllMocks(); load.mockResolvedValue(snapshot); submit.mockResolvedValue({ status: 'saved', snapshot }); });
test('default unchecked, taken disabled, cancel never writes', async () => {
  const close = jest.fn(); const ui = render(<Sheet onClose={close} />);
  const first = await ui.findByLabelText('测试补剂 A');
  expect(first.props.accessibilityState.checked).toBe(false);
  expect(ui.getByLabelText('测试补剂 B').props.accessibilityState.disabled).toBe(true);
  expect(ui.getByText('参考用量：1 粒')).toBeTruthy();
  fireEvent.press(ui.getByLabelText('关闭补剂打卡')); expect(close).toHaveBeenCalled(); expect(submit).not.toHaveBeenCalled();
});
test('one selected ID is submitted once; busy blocks double tap and close', async () => {
  let resolve: (v: any) => void = () => {};
  submit.mockImplementation(() => new Promise(r => { resolve = r; }));
  const close = jest.fn(); const record = jest.fn(); const ui = render(<Sheet onClose={close} onManualRecord={record} />);
  fireEvent.press(await ui.findByLabelText('测试补剂 A'));
  const button = ui.getByText('确认已服 · 1 项');
  fireEvent.press(button); fireEvent.press(button); fireEvent.press(ui.getByLabelText('关闭补剂打卡')); fireEvent.press(ui.getByText('填写本次数量和时间'));
  expect(submit).toHaveBeenCalledTimes(1); expect(submit.mock.calls[0][1]).toEqual([1]); expect(close).not.toHaveBeenCalled(); expect(record).not.toHaveBeenCalled();
  await act(async () => resolve({ status: 'saved', snapshot })); expect(ui.getByText('已记录本次勾选的已服状态')).toBeTruthy();
});
test('existing list also offers exact manual quantity and time without writing', async () => {
  const record = jest.fn(); const ui = render(<Sheet onClose={jest.fn()} onManualRecord={record} />);
  await ui.findByLabelText('测试补剂 A'); fireEvent.press(ui.getByText('填写本次数量和时间'));
  expect(record).toHaveBeenCalledTimes(1); expect(submit).not.toHaveBeenCalled();
});
test('empty state offers no-photo manual recording without writing and provides records route', async () => {
  load.mockResolvedValue({ ...snapshot, rows: [] }); const close = jest.fn(); const record = jest.fn(); const ui = render(<Sheet onClose={close} onManualRecord={record} />);
  await ui.findByText('暂无可勾选的补剂');
  expect(ui.getByText('无需拍照，填写完整名称、本次数量和服用时间。')).toBeTruthy();
  fireEvent.press(ui.getByText('手动记录本次'));
  expect(record).toHaveBeenCalledTimes(1); expect(submit).not.toHaveBeenCalled();
  fireEvent.press(ui.getByText('查看补剂记录'));
  expect(mockPush).toHaveBeenCalledWith('/(tabs)/record'); expect(close).toHaveBeenCalled();
});
test('load failure supports retry without write', async () => {
  load.mockRejectedValueOnce(new Error('network')); const ui = render(<Sheet onClose={jest.fn()} />);
  fireEvent.press(await ui.findByText('重新加载')); await ui.findByLabelText('测试补剂 A'); expect(submit).not.toHaveBeenCalled();
});
test('auth change clears old data and rejects stale load', async () => {
  let resolve: (v: any) => void = () => {}; load.mockImplementation(() => new Promise(r => { resolve = r; }));
  const ui = render(<Sheet onClose={jest.fn()} />);
  act(() => mockAuthListener?.()); await act(async () => resolve(snapshot));
  expect(ui.queryByLabelText('测试补剂 A')).toBeNull(); expect(ui.getByText('登录状态已变化，请关闭后重新打开')).toBeTruthy();
});
test('uncertain result cannot be resubmitted from same sheet', async () => {
  submit.mockResolvedValue({ status: 'uncertain', snapshot }); const ui = render(<Sheet onClose={jest.fn()} />);
  fireEvent.press(await ui.findByLabelText('测试补剂 A')); fireEvent.press(ui.getByText('确认已服 · 1 项'));
  await ui.findByText('提交结果尚未确认，请稍后到补剂记录核对，避免重复提交');
  expect(ui.getByLabelText('测试补剂 A').props.accessibilityState.disabled).toBe(true);
});
test('changed context clears selected rows and requires another explicit choice', async () => {
  submit.mockResolvedValue({ status: 'context_changed', snapshot: { ...snapshot, date: '2026-10-17' } });
  const ui = render(<Sheet onClose={jest.fn()} />); fireEvent.press(await ui.findByLabelText('测试补剂 A')); fireEvent.press(ui.getByText('确认已服 · 1 项'));
  await ui.findByText('日期、时区或补剂清单已变化，请重新勾选');
  expect(ui.getByLabelText('测试补剂 A').props.accessibilityState.checked).toBe(false); expect(ui.getByText('确认已服 · 0 项')).toBeTruthy();
});
test('auth switch during pending submit hides names and suppresses success', async () => {
  let resolve: (v: any) => void = () => {}; submit.mockImplementation(() => new Promise(r => { resolve = r; }));
  const ui = render(<Sheet onClose={jest.fn()} />); fireEvent.press(await ui.findByLabelText('测试补剂 A')); fireEvent.press(ui.getByText('确认已服 · 1 项'));
  act(() => mockAuthListener?.()); await act(async () => resolve({ status: 'saved', snapshot }));
  expect(ui.queryByLabelText('测试补剂 A')).toBeNull(); expect(ui.queryByText('已记录本次勾选的已服状态')).toBeNull(); expect(mockInvalidate).not.toHaveBeenCalled();
});
test('unmount invalidates in-flight guard', async () => {
  const ui = render(<Sheet onClose={jest.fn()} />); await ui.findByLabelText('测试补剂 A');
  const guard = load.mock.calls[0][1]; expect(guard()).toBe(true); ui.unmount(); expect(guard()).toBe(false);
});
test('strict effect remount does not get stuck loading', async () => {
  const ui = render(<React.StrictMode><Sheet onClose={jest.fn()} /></React.StrictMode>);
  expect(await ui.findByLabelText('测试补剂 A')).toBeTruthy();
});
test('group operation blocks closing and refreshes individual statuses only after unlocking', async () => {
  const close = jest.fn(); const ui = render(<Sheet onClose={close} />); await ui.findByLabelText('测试补剂 A');
  act(() => mockGroupProps.onBusyChange(true)); fireEvent.press(ui.getByLabelText('关闭补剂打卡')); expect(close).not.toHaveBeenCalled();
  act(() => mockGroupProps.onRecorded()); expect(load).toHaveBeenCalledTimes(1);
  await act(async () => mockGroupProps.onBusyChange(false)); expect(load).toHaveBeenCalledTimes(2);
});
test('unknown group write also disables individual submission in this sheet', async () => {
  const record = jest.fn(); const ui = render(<Sheet onClose={jest.fn()} onManualRecord={record} />); await ui.findByLabelText('测试补剂 A');
  act(() => mockGroupProps.onUncertain()); expect(ui.getByLabelText('测试补剂 A').props.accessibilityState.disabled).toBe(true);
  expect(ui.getByRole('button', { name: '填写本次数量和时间' }).props.accessibilityState.disabled).toBe(true);
  fireEvent.press(ui.getByText('填写本次数量和时间')); expect(record).not.toHaveBeenCalled();
});
