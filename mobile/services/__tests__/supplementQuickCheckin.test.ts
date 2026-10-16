import { loadSupplementSnapshot, submitSupplementSelection } from '../supplementQuickCheckin';
import api from '../api';
import { getEffectiveTimezone } from '../location';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('../location', () => ({ getEffectiveTimezone: jest.fn() }));
const get = api.get as jest.Mock;
const post = api.post as jest.Mock;
const tz = getEffectiveTimezone as jest.Mock;
const row = (id = 1, taken = false) => ({ supplement: { id, user_id: 7, name: '测试补剂', dosage: '1 粒', is_active: true }, record: taken ? { id: 91, user_id: 7, supplement_id: id, record_date: '2026-10-16', taken: true } : null });
const guard = () => true;
beforeEach(() => { jest.useFakeTimers().setSystemTime(new Date('2026-10-16T02:00:00Z')); jest.clearAllMocks(); tz.mockResolvedValue({ timezone: 'Asia/Shanghai' }); get.mockResolvedValue({ data: [row()] }); });
afterEach(() => jest.useRealTimers());
test('loads account timezone and validates ownership without writing', async () => {
  const s = await loadSupplementSnapshot(7, guard);
  expect(s.date).toBe('2026-10-16'); expect(post).not.toHaveBeenCalled();
  get.mockResolvedValue({ data: [ { ...row(), supplement: { ...row().supplement, user_id: 8 } } ] });
  await expect(loadSupplementSnapshot(7, guard)).rejects.toThrow();
});
test('does not use device day and rejects invalid timezone', async () => {
  tz.mockResolvedValue({ timezone: 'America/Los_Angeles' });
  const s = await loadSupplementSnapshot(7, guard); expect(s.date).toBe('2026-10-15');
  tz.mockResolvedValue({ timezone: 'invalid' }); await expect(loadSupplementSnapshot(7, guard)).rejects.toThrow();
});
test('posts only explicitly selected untaken IDs and validates receipt', async () => {
  get.mockResolvedValue({ data: [row(), row(2, true)] });
  const s = await loadSupplementSnapshot(7, guard);
  post.mockResolvedValue({ data: { results: [{ supplement_id: 1, record_id: 92, record_date: s.date, taken: true }] } });
  expect((await submitSupplementSelection(s, [1, 2], guard)).status).toBe('saved');
  expect(post).toHaveBeenCalledWith('/supplements/records/batch', { record_date: s.date, checkins: [{ supplement_id: 1, taken: true }] });
});
test('empty selection writes nothing', async () => {
  const s = await loadSupplementSnapshot(7, guard); await expect(submitSupplementSelection(s, [], guard)).rejects.toThrow(); expect(post).not.toHaveBeenCalled();
});
test('refresh removes already recorded items without writing', async () => {
  const s = await loadSupplementSnapshot(7, guard); get.mockResolvedValue({ data: [row(1, true)] });
  expect((await submitSupplementSelection(s, [1], guard)).status).toBe('already'); expect(post).not.toHaveBeenCalled();
});
test('changed date or timezone clears context and does not write', async () => {
  const s = await loadSupplementSnapshot(7, guard); tz.mockResolvedValue({ timezone: 'Asia/Tokyo' });
  expect((await submitSupplementSelection(s, [1], guard)).status).toBe('context_changed'); expect(post).not.toHaveBeenCalled();
});
test('auth change during refresh prevents next request and writing', async () => {
  const s = await loadSupplementSnapshot(7, guard); let current = true;
  tz.mockImplementation(async () => { current = false; return { timezone: 'Asia/Shanghai' }; });
  await expect(submitSupplementSelection(s, [1], () => current)).rejects.toThrow(); expect(post).not.toHaveBeenCalled();
});
test('timeout reads back and never retries post', async () => {
  const s = await loadSupplementSnapshot(7, guard); post.mockRejectedValue(new Error('timeout'));
  get.mockResolvedValueOnce({ data: [row()] }).mockResolvedValueOnce({ data: [row(1, true)] });
  expect((await submitSupplementSelection(s, [1], guard)).status).toBe('reconciled'); expect(post).toHaveBeenCalledTimes(1);
});
test('invalid receipt remains uncertain when readback does not prove write', async () => {
  const s = await loadSupplementSnapshot(7, guard);
  post.mockResolvedValue({ data: { results: [{ supplement_id: 99, record_id: 92, record_date: s.date, taken: true }] } });
  expect((await submitSupplementSelection(s, [1], guard)).status).toBe('uncertain'); expect(post).toHaveBeenCalledTimes(1);
});
test('account switch after post suppresses receipt and readback', async () => {
  const s = await loadSupplementSnapshot(7, guard); let current = true;
  post.mockImplementation(async () => { current = false; return { data: { results: [] } }; });
  await expect(submitSupplementSelection(s, [1], () => current)).rejects.toThrow(); expect(get).toHaveBeenCalledTimes(2);
});
test('midnight during preflight fetch reloads without posting yesterday', async () => {
  const s = await loadSupplementSnapshot(7, guard);
  get.mockImplementationOnce(async () => { jest.setSystemTime(new Date('2026-10-16T16:00:01Z')); return { data: [row()] }; });
  const result = await submitSupplementSelection(s, [1], guard);
  expect(result.status).toBe('context_changed'); expect(result.snapshot.date).toBe('2026-10-17'); expect(post).not.toHaveBeenCalled();
});
test('removed or changed definition requires fresh selection', async () => {
  const s = await loadSupplementSnapshot(7, guard);
  get.mockResolvedValue({ data: [{ ...row(), supplement: { ...row().supplement, dosage: '新参考用量' } }] });
  expect((await submitSupplementSelection(s, [1], guard)).status).toBe('context_changed'); expect(post).not.toHaveBeenCalled();
});
test('readback failure is unknown, not a claimed failed write', async () => {
  const s = await loadSupplementSnapshot(7, guard); post.mockRejectedValue(new Error('timeout'));
  get.mockResolvedValueOnce({ data: [row()] }).mockRejectedValueOnce(new Error('offline'));
  expect((await submitSupplementSelection(s, [1], guard)).status).toBe('uncertain'); expect(post).toHaveBeenCalledTimes(1);
});
test('duplicate receipt IDs are not accepted as a complete write', async () => {
  get.mockResolvedValue({ data: [row(), row(2)] }); const s = await loadSupplementSnapshot(7, guard);
  const receipt = { supplement_id: 1, record_id: 92, record_date: s.date, taken: true };
  post.mockResolvedValue({ data: { results: [receipt, receipt] } });
  expect((await submitSupplementSelection(s, [1, 2], guard)).status).toBe('uncertain');
});
