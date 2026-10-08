import React from 'react';
import { AppState, StyleSheet } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { DietShareLocationEditor } from '../DietShareLocationEditor';
import { getShareLocationAvailability, nearbyShareLocations, searchShareLocations } from '../../../services/shareLocation';
import { invalidateAIConsent } from '../../../services/aiConsentState';

jest.mock('../../../services/shareLocation', () => ({
  getShareLocationAvailability: jest.fn(), nearbyShareLocations: jest.fn(), searchShareLocations: jest.fn(),
  shareLocationErrorMessage: () => '查询失败，请手动填写',
}));
const results = { items: [{ id: 'p1', name: '示例餐厅', address: '示例路 1 号', label: '示例餐厅', distance_m: 20 }], suggested_id: 'p1' };
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
async function setup(recordDate: string | null = today(), initialValue = '') {
  const onConfirm = jest.fn(); const onCancel = jest.fn();
  const view = { ...render(<DietShareLocationEditor recordDate={recordDate} initialValue={initialValue} onConfirm={onConfirm} onCancel={onCancel} />), onConfirm, onCancel };
  await act(async () => {});
  return view;
}
function deferred() { let resolve!: (value: any) => void; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
beforeEach(() => { jest.clearAllMocks(); (getShareLocationAvailability as jest.Mock).mockResolvedValue(true); jest.spyOn(AppState, 'addEventListener').mockReturnValue({ remove: jest.fn() }); (nearbyShareLocations as jest.Mock).mockResolvedValue(results); (searchShareLocations as jest.Mock).mockResolvedValue({ ...results, suggested_id: null }); });

it('hides unavailable provider UI while retaining manual confirmation', async () => {
  (getShareLocationAvailability as jest.Mock).mockResolvedValue(false);
  const view = await setup();
  expect(view.queryByText('使用高德地点查询')).toBeNull();
  expect(view.queryByLabelText('使用当前位置查找餐厅')).toBeNull();
  expect(view.queryByLabelText('搜索餐厅或地址')).toBeNull();
  fireEvent.changeText(view.getByLabelText('分享地点'), '手填地点');
  fireEvent.press(view.getByLabelText('确认分享地点'));
  expect(view.onConfirm).toHaveBeenCalledWith('手填地点');
  expect(nearbyShareLocations).not.toHaveBeenCalled();
});

it.each(['identity', 'background', 'unmount', 'cancel'])('keeps pending readiness hidden and discards it after %s', async terminal => {
  let state!: (value: string) => void;
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, listener: any) => { state = listener; return { remove: jest.fn() }; });
  const pending = deferred(); (getShareLocationAvailability as jest.Mock).mockReturnValue(pending.promise);
  const view = await setup();
  expect(view.queryByLabelText('同意本次高德查询')).toBeNull();
  const signal = (getShareLocationAvailability as jest.Mock).mock.calls[0][0];
  if (terminal === 'identity') act(() => invalidateAIConsent(false));
  else if (terminal === 'background') act(() => state('background'));
  else if (terminal === 'cancel') fireEvent.press(view.getByLabelText('取消地点编辑'));
  else view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve(true));
  if (terminal !== 'unmount') expect(view.queryByLabelText('同意本次高德查询')).toBeNull();
  expect(nearbyShareLocations).not.toHaveBeenCalled();
});

it('does not query without consent; after consent defaults a candidate in draft only', async () => {
  const view = await setup();
  expect(nearbyShareLocations).not.toHaveBeenCalled();
  expect(StyleSheet.flatten(view.getByLabelText('分享地点').props.style).width).toBe('100%');
  fireEvent.press(view.getByLabelText('同意本次高德查询'));
  await waitFor(() => expect(view.getByLabelText('分享地点').props.value).toBe('示例餐厅'));
  expect(view.getByText('示例路 1 号')).toBeTruthy();
  expect(view.onConfirm).not.toHaveBeenCalled();
  fireEvent.press(view.getByLabelText('确认分享地点'));
  expect(view.onConfirm).toHaveBeenCalledWith('示例餐厅');
});
it.each(['2020-01-01', null])('does not locate an old or undated meal automatically: %s', async date => {
  const view = await setup(date);
  fireEvent.press(view.getByLabelText('同意本次高德查询'));
  await act(async () => {});
  expect(nearbyShareLocations).not.toHaveBeenCalled();
  expect(view.getByText(/不是这餐的历史位置/)).toBeTruthy();
  fireEvent.press(view.getByLabelText('使用当前位置查找餐厅'));
  await waitFor(() => expect(nearbyShareLocations).toHaveBeenCalledTimes(1));
});
it('retains manual editing and clear even when a late response arrives', async () => {
  const pending = deferred(); (nearbyShareLocations as jest.Mock).mockReturnValue(pending.promise);
  const view = await setup();
  fireEvent.press(view.getByLabelText('同意本次高德查询'));
  fireEvent.changeText(view.getByLabelText('分享地点'), '手填地点');
  await act(async () => pending.resolve(results));
  expect(view.getByLabelText('分享地点').props.value).toBe('手填地点');
  fireEvent.press(view.getByLabelText('清除分享地点'));
  fireEvent.press(view.getByLabelText('确认分享地点'));
  expect(view.onConfirm).toHaveBeenCalledWith('');
});
it('searches without GPS and only applies a selected search result', async () => {
  const view = await setup('2020-01-01');
  fireEvent.press(view.getByLabelText('同意本次高德查询'));
  fireEvent.changeText(view.getByLabelText('搜索餐厅或地址'), '示例');
  expect(searchShareLocations).not.toHaveBeenCalled();
  fireEvent.press(view.getByLabelText('搜索地点'));
  await waitFor(() => expect(view.getByText('示例路 1 号')).toBeTruthy());
  expect(view.getByLabelText('分享地点').props.value).toBe('');
  fireEvent.press(view.getByLabelText('选择地点：示例餐厅'));
  expect(view.getByLabelText('分享地点').props.value).toBe('示例餐厅');
});
it('never replaces an already confirmed label when consenting', async () => {
  const view = await setup(today(), '原地点');
  fireEvent.press(view.getByLabelText('同意本次高德查询'));
  await act(async () => {});
  expect(nearbyShareLocations).not.toHaveBeenCalled();
  expect(view.getByLabelText('分享地点').props.value).toBe('原地点');
});
it('aborts and discards pending work when backgrounded or unmounted', async () => {
  let state!: (value: string) => void;
  const sub = jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, listener: any) => { state = listener; return { remove: jest.fn() }; });
  const pending = deferred(); (nearbyShareLocations as jest.Mock).mockReturnValue(pending.promise);
  const view = await setup(); fireEvent.press(view.getByLabelText('同意本次高德查询'));
  const context = (nearbyShareLocations as jest.Mock).mock.calls[0][0];
  act(() => state('background'));
  expect(context.signal.aborted).toBe(true);
  await act(async () => pending.resolve(results));
  expect(view.getByLabelText('分享地点').props.value).toBe('');
  view.unmount(); sub.mockRestore();
});
it('rejects queued confirm after authentication invalidation', async () => {
  const view = await setup();
  let node = view.getByLabelText('确认分享地点');
  while (typeof node.props.onPress !== 'function' && node.parent) node = node.parent;
  const queued = node.props.onPress;
  act(() => invalidateAIConsent(false));
  act(() => queued());
  expect(view.onConfirm).not.toHaveBeenCalled();
});
it('offers manual fallback on failure and supports cancellation without saving', async () => {
  (nearbyShareLocations as jest.Mock).mockRejectedValue(new Error('failure'));
  const view = await setup(); fireEvent.press(view.getByLabelText('同意本次高德查询'));
  await waitFor(() => expect(view.getByText('查询失败，请手动填写')).toBeTruthy());
  expect(view.queryByLabelText('使用当前位置查找餐厅')).toBeNull();
  expect(view.queryByLabelText('搜索地点')).toBeNull();
  fireEvent.changeText(view.getByLabelText('分享地点'), '仍可手填');
  fireEvent.press(view.getByLabelText('取消地点编辑'));
  expect(view.onCancel).toHaveBeenCalledTimes(1);
  expect(view.onConfirm).not.toHaveBeenCalled();
});
it('withdraws query consent and prevents a late result from returning', async () => {
  const pending = deferred(); (nearbyShareLocations as jest.Mock).mockReturnValue(pending.promise);
  const view = await setup(); fireEvent.press(view.getByLabelText('同意本次高德查询'));
  const context = (nearbyShareLocations as jest.Mock).mock.calls[0][0];
  fireEvent.press(view.getByLabelText('停止并撤回本次高德查询'));
  expect(context.signal.aborted).toBe(true);
  await act(async () => pending.resolve(results));
  expect(view.getByLabelText('同意本次高德查询')).toBeTruthy();
  expect(view.queryByText('示例路 1 号')).toBeNull();
  fireEvent.changeText(view.getByLabelText('分享地点'), '手动公开名称');
  fireEvent.press(view.getByLabelText('确认分享地点'));
  expect(view.onConfirm).toHaveBeenCalledWith('手动公开名称');
});
it('rejects a queued confirmation from before the public label was edited', async () => {
  const view = await setup(today(), '旧地点');
  let node = view.getByLabelText('确认分享地点');
  while (typeof node.props.onPress !== 'function' && node.parent) node = node.parent;
  const queued = node.props.onPress;
  fireEvent.changeText(view.getByLabelText('分享地点'), '新地点');
  act(() => queued());
  expect(view.onConfirm).not.toHaveBeenCalled();
  fireEvent.press(view.getByLabelText('确认分享地点'));
  expect(view.onConfirm).toHaveBeenCalledWith('新地点');
});

it.each(['cancel', 'unmount', 'identity'])('discards a pending query after %s', async terminal => {
  const pending = deferred(); (nearbyShareLocations as jest.Mock).mockReturnValue(pending.promise);
  const view = await setup(); fireEvent.press(view.getByLabelText('同意本次高德查询'));
  const context = (nearbyShareLocations as jest.Mock).mock.calls[0][0];
  if (terminal === 'cancel') fireEvent.press(view.getByLabelText('取消地点编辑'));
  else if (terminal === 'unmount') view.unmount();
  else act(() => invalidateAIConsent(false));
  expect(context.signal.aborted).toBe(true);
  expect(() => context.assertActive()).toThrow();
  await act(async () => pending.resolve(results));
  expect(view.onConfirm).not.toHaveBeenCalled();
  if (terminal !== 'unmount') expect(view.queryByText('示例路 1 号')).toBeNull();
});

it('keeps the query active through the iOS permission prompt but requires new consent after backgrounding', async () => {
  let state!: (value: string) => void;
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, listener: any) => { state = listener; return { remove: jest.fn() }; });
  const pending = deferred(); (nearbyShareLocations as jest.Mock).mockReturnValue(pending.promise);
  const view = await setup(); fireEvent.press(view.getByLabelText('同意本次高德查询'));
  const context = (nearbyShareLocations as jest.Mock).mock.calls[0][0];
  act(() => state('inactive'));
  expect(context.signal.aborted).toBe(false);
  act(() => state('active'));
  await act(async () => pending.resolve(results));
  expect(view.getByLabelText('分享地点').props.value).toBe('示例餐厅');
  act(() => state('background'));
  await act(async () => state('active'));
  expect(view.getByLabelText('同意本次高德查询')).toBeTruthy();
  expect(nearbyShareLocations).toHaveBeenCalledTimes(1);
  expect(view.onConfirm).not.toHaveBeenCalled();
});
