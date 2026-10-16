import api from '../api';
import { loadMedicationReminder, submitMedicationReminder } from '../medicationReminderLanding';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
const get = api.get as jest.Mock;
const post = api.post as jest.Mock;
const context = () => ({ user_id: 1, timezone: 'Asia/Shanghai', today_date: '2026-10-16', date: '2026-10-16', time: '18:00', requires_date_confirmation: false, revision: 'abc', actionable: true, reason: null, medication: { id: 7, user_id: 1, name: '药品甲', dosage: '1粒', frequency: '每日一次', is_active: true, reminder_times: ['18:00'], timing_label: null, times_per_day: 1, category: null, purpose: null, start_date: null, end_date: null, notes: null }, log: null });
const receipt = (status = 'taken') => ({ id: 10, medication_id: 7, taken_date: '2026-10-16', taken_time: '18:00', status });
beforeEach(() => { jest.resetAllMocks(); get.mockResolvedValue({ data: context() }); post.mockResolvedValue({ data: receipt() }); });
it('reads only requested owner slot; no write on read', async () => {
  await loadMedicationReminder(1, { id: 7, date: '2026-10-16', time: '18:00', sourceTimezone: 'Asia/Shanghai' }, () => true);
  expect(get).toHaveBeenCalledWith('/medication/medications/7/reminder', { params: { date: '2026-10-16', time: '18:00', source_timezone: 'Asia/Shanghai' } });
  expect(post).not.toHaveBeenCalled();
});
it.each([0, -1, NaN])('rejects invalid medication id %s', async id => {
  await expect(loadMedicationReminder(1, { id }, () => true)).rejects.toThrow(); expect(get).not.toHaveBeenCalled();
});
it('rejects wrong owner/slot data', async () => {
  get.mockResolvedValue({ data: { ...context(), user_id: 2 } });
  await expect(loadMedicationReminder(1, { id: 7 }, () => true)).rejects.toThrow();
  get.mockResolvedValue({ data: { ...context(), log: { ...receipt(), medication_id: 8 } } });
  await expect(loadMedicationReminder(1, { id: 7 }, () => true)).rejects.toThrow();
});
it('revalidates revision and submits a fixed slot without inferred dose', async () => {
  const result = await submitMedicationReminder(context(), 'taken', () => true);
  expect(post).toHaveBeenCalledWith('/medication/medications/7/reminder/log', { date: '2026-10-16', time: '18:00', timezone: 'Asia/Shanghai', expected_revision: 'abc', status: 'taken' });
  expect(result.status).toBe('saved'); expect(result.context.log?.status).toBe('taken');
});
it('does not submit changed medication or an unconfirmed date', async () => {
  get.mockResolvedValue({ data: { ...context(), revision: 'changed' } });
  expect((await submitMedicationReminder(context(), 'taken', () => true)).status).toBe('changed'); expect(post).not.toHaveBeenCalled();
  await expect(submitMedicationReminder({ ...context(), requires_date_confirmation: true }, 'taken', () => true)).rejects.toThrow();
});
it('does not duplicate already logged slot', async () => {
  get.mockResolvedValue({ data: { ...context(), actionable: false, log: receipt() } });
  expect((await submitMedicationReminder(context(), 'taken', () => true)).status).toBe('already'); expect(post).not.toHaveBeenCalled();
});
it('reconciles one ambiguous post without retrying write', async () => {
  get.mockResolvedValueOnce({ data: context() }).mockResolvedValueOnce({ data: { ...context(), log: receipt(), actionable: false } });
  post.mockRejectedValue(new Error('timeout'));
  expect((await submitMedicationReminder(context(), 'taken', () => true)).status).toBe('reconciled'); expect(post).toHaveBeenCalledTimes(1);
});
it('wrong receipt never becomes success; unresolved failure locks submission', async () => {
  post.mockResolvedValue({ data: { ...receipt(), taken_date: '2026-10-15' } });
  expect((await submitMedicationReminder(context(), 'taken', () => true)).status).toBe('uncertain'); expect(post).toHaveBeenCalledTimes(1);
});
it('shows persisted conflict instead of claiming requested status', async () => {
  post.mockResolvedValue({ data: receipt('taken') });
  expect((await submitMedicationReminder(context(), 'skipped', () => true)).status).toBe('conflict');
});
it('account changes prevent stale read and subsequent post', async () => {
  let active = true;
  get.mockImplementation(async () => { active = false; return { data: context() }; });
  await expect(submitMedicationReminder(context(), 'taken', () => active)).rejects.toThrow(); expect(post).not.toHaveBeenCalled();
});
