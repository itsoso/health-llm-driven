import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import Panel from '../SupplementGroupsPanel';
import { loadSupplementGroups, saveSupplementGroup, archiveSupplementGroup, confirmSupplementGroup } from '../../../services/supplementGroups';
let mockAuth: (() => void) | undefined;
jest.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ token: 'test', user: { id: 7 } }) }));
jest.mock('../../../services/api', () => ({ subscribeAuthSessionChange: (fn: () => void) => { mockAuth = fn; return () => {}; } }));
jest.mock('../../../services/supplementGroups', () => ({ loadSupplementGroups: jest.fn(), saveSupplementGroup: jest.fn(), archiveSupplementGroup: jest.fn(), confirmSupplementGroup: jest.fn() }));
const load = loadSupplementGroups as jest.Mock, save = saveSupplementGroup as jest.Mock, archive = archiveSupplementGroup as jest.Mock, confirm = confirmSupplementGroup as jest.Mock;
const group = { id: 1, name: '早餐组合', revision: 'r1', members: [{ supplement_id: 3, name: '测试补剂', reference_dosage: '1 粒', available: true }], today_confirmation: null };
const catalog = { record_date: '2026-10-16', timezone: 'Asia/Shanghai', groups: [group] };
const snapshot: any = { date: catalog.record_date, timezone: catalog.timezone, userId: 7, rows: [{ supplement: { id: 3, name: '测试补剂', dosage: '1 粒' }, record: null }] };
const props = { snapshot, onBusyChange: jest.fn(), onRecorded: jest.fn() };
beforeEach(() => { jest.clearAllMocks(); load.mockResolvedValue(catalog); save.mockResolvedValue(group); archive.mockResolvedValue(undefined); confirm.mockResolvedValue({ status: 'confirmed', catalog }); });
test('opening a group only previews, explicit confirmation writes once', async () => {
 const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合')); expect(confirm).not.toHaveBeenCalled();
 fireEvent.press(ui.getByText('确认整组已服 · 1 项')); await ui.findByText('整组已记录'); expect(confirm).toHaveBeenCalledTimes(1);
});
test('create saves members without intake', async () => {
 const ui = render(<Panel {...props} />); await ui.findByText('早餐组合'); fireEvent.press(ui.getByText('新建组合')); fireEvent.changeText(ui.getByLabelText('组合名称'), '晨间组合');
 fireEvent.press(ui.getByLabelText('组合成员：测试补剂')); fireEvent.press(ui.getByText('保存组合，不记录服用'));
 await ui.findByText('组合已保存，尚未记录服用'); expect(save).toHaveBeenCalledTimes(1); expect(confirm).not.toHaveBeenCalled();
});
test('unknown result locks writes without claiming failure', async () => {
 confirm.mockResolvedValue({ status: 'uncertain', catalog }); const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合')); fireEvent.press(ui.getByText('确认整组已服 · 1 项'));
 await ui.findByText('结果尚未确认，请稍后核对；本次不会再次提交'); expect(ui.queryByText('确认整组已服 · 1 项')).toBeNull();
});
test('auth switch clears member names while pending', async () => {
 let resolve: (v: any) => void = () => {}; load.mockImplementation(() => new Promise(r => { resolve = r; })); const ui = render(<Panel {...props} />);
 act(() => mockAuth?.()); await act(async () => resolve(catalog)); expect(ui.queryByText('早餐组合')).toBeNull();
});
test('editing and archiving require separate explicit actions', async () => {
 const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合')); fireEvent.press(ui.getByText('编辑组合')); expect(save).not.toHaveBeenCalled();
 fireEvent.press(ui.getByText('归档组合')); expect(archive).not.toHaveBeenCalled(); fireEvent.press(ui.getByText('确认归档')); await ui.findByText('组合已归档，历史记录保留'); expect(archive).toHaveBeenCalledTimes(1); expect(confirm).not.toHaveBeenCalled();
});
test('ambiguous save reloads read-only and cannot auto-create a duplicate', async () => {
 save.mockRejectedValue(new Error('timeout')); const ui = render(<Panel {...props} />); await ui.findByText('早餐组合'); fireEvent.press(ui.getByText('新建组合'));
 fireEvent.changeText(ui.getByLabelText('组合名称'), '晨间组合'); fireEvent.press(ui.getByLabelText('组合成员：测试补剂')); fireEvent.press(ui.getByText('保存组合，不记录服用'));
 await ui.findByText('结果尚未确认，请稍后核对；本次不会再次提交'); expect(save).toHaveBeenCalledTimes(1); expect(load).toHaveBeenCalledTimes(2); expect(confirm).not.toHaveBeenCalled();
});
test('date transition clears old confirmation preview', async () => {
 const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合'));
 load.mockResolvedValue({ ...catalog, record_date: '2026-10-17' }); ui.rerender(<Panel {...props} snapshot={{ ...snapshot, date: '2026-10-17' }} />);
 await ui.findByText('早餐组合'); expect(ui.queryByText('确认整组已服 · 1 项')).toBeNull(); expect(confirm).not.toHaveBeenCalled();
});
test('double tap cannot dispatch a second confirmation', async () => {
 let resolve: (v: any) => void = () => {}; confirm.mockImplementation(() => new Promise(r => { resolve = r; }));
 const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合')); const button = ui.getByText('确认整组已服 · 1 项'); fireEvent.press(button); fireEvent.press(button);
 expect(confirm).toHaveBeenCalledTimes(1); expect(props.onBusyChange).toHaveBeenCalledWith(true);
 await act(async () => resolve({ status: 'confirmed', catalog })); expect(props.onBusyChange).toHaveBeenLastCalledWith(false);
});
test('account switch during confirmation suppresses success and old details', async () => {
 let resolve: (v: any) => void = () => {}; confirm.mockImplementation(() => new Promise(r => { resolve = r; }));
 const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合')); fireEvent.press(ui.getByText('确认整组已服 · 1 项'));
 act(() => mockAuth?.()); await act(async () => resolve({ status: 'confirmed', catalog })); expect(ui.queryByText('早餐组合')).toBeNull(); expect(props.onRecorded).not.toHaveBeenCalled();
});
test('already confirmed group displays immutable original snapshot with no confirmation action', async () => {
 const event = { event_id: 9, group_id: 1, name: '原组合名称', revision: 'old', record_date: catalog.record_date, source: 'manual_group', members: [{ supplement_id: 3, name: '原成员名称', reference_dosage: '原参考用量', record_id: 7, already_taken: false }] };
 load.mockResolvedValue({ ...catalog, groups: [{ ...group, today_confirmation: event }] });
 const ui = render(<Panel {...props} />); fireEvent.press(await ui.findByText('早餐组合')); expect(ui.getByText('原组合名称 · 2026-10-16')).toBeTruthy(); expect(ui.getByText('原成员名称')).toBeTruthy(); expect(ui.queryByText('确认整组已服 · 1 项')).toBeNull();
});
