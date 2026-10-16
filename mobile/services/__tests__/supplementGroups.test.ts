import { loadSupplementGroups, confirmSupplementGroup, saveSupplementGroup, archiveSupplementGroup } from '../supplementGroups';
import api from '../api';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() } }));
const get = api.get as jest.Mock, post = api.post as jest.Mock, put = api.put as jest.Mock, remove = api.delete as jest.Mock;
const group = { id: 1, name: '早餐组合', revision: 'r1', members: [{ supplement_id: 3, name: '测试补剂', reference_dosage: '1 粒', available: true }], today_confirmation: null };
const catalog = { record_date: '2026-10-16', timezone: 'Asia/Shanghai', groups: [group] };
const receipt = { event_id: 6, group_id: 1, name: '早餐组合', revision: 'r1', record_date: catalog.record_date, source: 'manual_group', members: [{ supplement_id: 3, name: '测试补剂', reference_dosage: '1 粒', record_id: 9, already_taken: false }] };
beforeEach(() => { jest.clearAllMocks(); get.mockResolvedValue({ data: catalog }); });
test('saving a combination never confirms intake', async () => {
  post.mockResolvedValue({ data: group }); await saveSupplementGroup(catalog, { name: '早餐组合', supplement_ids: [3] }, () => true);
  expect(post).toHaveBeenCalledWith('/supplements/groups', { name: '早餐组合', supplement_ids: [3] }); expect(post).toHaveBeenCalledTimes(1);
});
test('update and archive bind revision', async () => {
  put.mockResolvedValue({ data: group }); remove.mockResolvedValue({ data: { archived: true } });
  await saveSupplementGroup(catalog, { name: '早餐组合', supplement_ids: [3] }, () => true, group);
  expect(put).toHaveBeenCalledWith('/supplements/groups/1', { name: '早餐组合', supplement_ids: [3], revision: 'r1' });
  await archiveSupplementGroup(catalog, group, () => true); expect(remove).toHaveBeenCalledWith('/supplements/groups/1', { params: { revision: 'r1' } });
});
test('explicit confirmation uses one POST and validates the event', async () => {
  post.mockResolvedValue({ data: receipt }); const result = await confirmSupplementGroup(catalog, group, () => true);
  expect(result.status).toBe('confirmed'); expect(post).toHaveBeenCalledWith('/supplements/groups/1/confirm', { revision: 'r1', record_date: catalog.record_date, confirmed: true });
});
test.each(['revision', 'record_date', 'timezone'])('changed %s blocks stale confirmation', async field => {
  get.mockResolvedValue({ data: field === 'revision' ? { ...catalog, groups: [{ ...group, revision: 'r2' }] } : { ...catalog, [field]: field === 'record_date' ? '2026-10-17' : 'Asia/Tokyo' } });
  expect((await confirmSupplementGroup(catalog, group, () => true)).status).toBe('context_changed'); expect(post).not.toHaveBeenCalled();
});
test('previous confirmation does not add newly edited members', async () => {
  get.mockResolvedValue({ data: { ...catalog, groups: [{ ...group, revision: 'r2', today_confirmation: receipt }] } });
  expect((await confirmSupplementGroup(catalog, group, () => true)).status).toBe('already'); expect(post).not.toHaveBeenCalled();
});
test('timeout reads back immutable event without retry', async () => {
  post.mockRejectedValue(new Error('timeout')); get.mockResolvedValueOnce({ data: catalog }).mockResolvedValueOnce({ data: { ...catalog, groups: [{ ...group, today_confirmation: receipt }] } });
  expect((await confirmSupplementGroup(catalog, group, () => true)).status).toBe('reconciled'); expect(post).toHaveBeenCalledTimes(1);
});
test('wrong receipt and no event remains unknown', async () => {
  post.mockResolvedValue({ data: { ...receipt, group_id: 8 } }); expect((await confirmSupplementGroup(catalog, group, () => true)).status).toBe('uncertain'); expect(post).toHaveBeenCalledTimes(1);
});
test('auth change during fresh load prohibits dispatch', async () => {
  let current = true; get.mockImplementation(async () => { current = false; return { data: catalog }; });
  await expect(confirmSupplementGroup(catalog, group, () => current)).rejects.toThrow(); expect(post).not.toHaveBeenCalled();
});
test('inactive member cannot be confirmed', async () => {
  get.mockResolvedValue({ data: { ...catalog, groups: [{ ...group, members: [{ ...group.members[0], available: false }] }] } });
  expect((await confirmSupplementGroup(catalog, group, () => true)).status).toBe('context_changed'); expect(post).not.toHaveBeenCalled();
});
test('invalid response cannot masquerade as an empty list', async () => { get.mockResolvedValue({ data: {} }); await expect(loadSupplementGroups(() => true)).rejects.toThrow(); });
test('save rejects mismatched name or membership receipt', async () => {
  post.mockResolvedValue({ data: { ...group, name: '错误组合' } });
  await expect(saveSupplementGroup(catalog, { name: group.name, supplement_ids: [3] }, () => true)).rejects.toThrow('invalid_save_receipt'); expect(post).toHaveBeenCalledTimes(1);
});
test('create never dispatches when account day changed', async () => {
  get.mockResolvedValue({ data: { ...catalog, record_date: '2026-10-17' } });
  await expect(saveSupplementGroup(catalog, { name: group.name, supplement_ids: [3] }, () => true)).rejects.toThrow('context_changed'); expect(post).not.toHaveBeenCalled();
});
test('auth switch during POST suppresses receipt and readback', async () => {
 let active = true; post.mockImplementation(async () => { active = false; return { data: receipt }; });
 await expect(confirmSupplementGroup(catalog, group, () => active)).rejects.toThrow('session_changed'); expect(get).toHaveBeenCalledTimes(1); expect(post).toHaveBeenCalledTimes(1);
});
test('unknown confirmation does not fabricate a result when readback is unavailable', async () => {
 get.mockResolvedValueOnce({ data: catalog }).mockRejectedValueOnce(new Error('offline')); post.mockRejectedValue(new Error('timeout'));
 expect((await confirmSupplementGroup(catalog, group, () => true)).status).toBe('uncertain'); expect(post).toHaveBeenCalledTimes(1);
});
