import { publishDietRecordUpdate, subscribeDietRecordUpdates } from '../dietRecordUpdates';
import { aiConsentRevision, invalidateAIConsent } from '../aiConsentState';
import { updateDietRecord, recalculateDietRecordNutrition } from '../diet';
const mockPut = jest.fn();
const mockPost = jest.fn();
jest.mock('../api', () => ({ __esModule: true, default: {
  put: (...args: unknown[]) => mockPut(...args), post: (...args: unknown[]) => mockPost(...args),
} }));
const row = { id: 1175, user_id: 7, calories: 650, protein: 28, carbs: 70, fat: 24, fiber: null,
  food_items: '面和饮品', meal_type: 'breakfast' as const, record_date: '2026-10-14', updated_at: '2026-10-14T10:01:00Z' };

it('emits only the persisted PUT response and the recalculation response', async () => {
  const listener = jest.fn(); const stop = subscribeDietRecordUpdates(listener);
  try {
    mockPut.mockResolvedValueOnce({ data: row });
    await updateDietRecord(1175, { calories: 640 });
    expect(listener).toHaveBeenLastCalledWith({ record: row, revision: aiConsentRevision() });
    mockPost.mockResolvedValueOnce({ data: { ...row, calories: 700 } });
    await recalculateDietRecordNutrition(1175, { food_items: '面和饮品', expected_updated_at: null }, 'test-key');
    expect(listener.mock.calls[1][0].record.calories).toBe(700);
  } finally { stop(); }
});
it('does not emit a late response after the account/consent generation changes', async () => {
  let resolve!: (value: unknown) => void;
  mockPut.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  const listener = jest.fn(); const stop = subscribeDietRecordUpdates(listener);
  try {
    const pending = updateDietRecord(1175, { calories: 640 });
    invalidateAIConsent(); resolve({ data: row }); await pending;
    expect(listener).not.toHaveBeenCalled();
  } finally { stop(); }
});
it('ignores failed writes, mismatched IDs, invalid identity/version and removes listeners', async () => {
  const listener = jest.fn(); const stop = subscribeDietRecordUpdates(listener);
  mockPut.mockRejectedValueOnce(new Error('offline'));
  await expect(updateDietRecord(1175, { calories: 640 })).rejects.toThrow('offline');
  mockPut.mockResolvedValueOnce({ data: { ...row, id: 1176 } });
  await updateDietRecord(1175, { calories: 640 });
  for (const patch of [{ id: 0 }, { user_id: 0 }, { updated_at: null }, { updated_at: 'invalid' }]) {
    publishDietRecordUpdate({ ...row, ...patch }, aiConsentRevision());
  }
  stop(); publishDietRecordUpdate(row, aiConsentRevision());
  expect(listener).not.toHaveBeenCalled();
});
