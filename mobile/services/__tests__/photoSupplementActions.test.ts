const mockConfirm = jest.fn();
const mockDismiss = jest.fn();
jest.mock('../api', () => ({ __esModule: true, default: {} }));
jest.mock('../writeIntents', () => ({
  confirmWriteIntent: (...args: unknown[]) => mockConfirm(...args),
  dismissWriteIntent: (...args: unknown[]) => mockDismiss(...args),
}));
import { dispatchChatCardAction } from '../chatCardActions';

const action = {
  id: 'photo-supplement-confirm:42', action: 'write_intent.confirm', label: '确认记录',
  endpoint: '/write-intents/42/confirm', requires_manual_confirm: true,
  payload: { write_intent_id: 42 }, capability_id: 'supplement_draft.v1',
  required_receipt: true, autonomy_tier: 'manual_confirm', policy_reason: 'manual_confirm_write',
};
const context = { cardType: 'supplement_draft', cardData: {
  write_intent_id: 42, taken_date: '2026-10-10',
  items: [{ supplement_id: 7, actual_dosage: '2粒' }, { supplement_id: 8, actual_dosage: '1粒' }],
} };
const receipts = () => [7, 8].map((id, i) => ({
  operation_id: `write_intent:photo_supplement_intake:42:${id}`, resource_id: String(id),
  resource_type: 'supplement_record', status: 'verified', verified: true, action: 'create',
  completed_at: '2026-10-10T10:00:00Z', supplement_id: id, record_date: '2026-10-10',
  taken: true, actual_dosage: i === 0 ? '2粒' : '1粒',
}));
beforeEach(() => jest.clearAllMocks());
it.each(['expired', 'dismissed'])('returns %s without claiming a write', async status => {
  mockConfirm.mockResolvedValue({ status });
  expect(await dispatchChatCardAction(action, undefined, context)).toEqual({ status, decision_status: status });
});
it('accepts all matching receipts', async () => {
  mockConfirm.mockResolvedValue({ status: 'executed', write_receipts: receipts() });
  expect((await dispatchChatCardAction(action, undefined, context)).write_receipts).toHaveLength(2);
});
it.each(['missing', 'partial', 'dose', 'date', 'intent', 'resource', 'duplicate'])('rejects %s receipts', async mode => {
  const rows = receipts();
  if (mode === 'dose') rows[0].actual_dosage = '1粒';
  if (mode === 'date') rows[0].record_date = '2026-10-11';
  if (mode === 'intent') rows[0].operation_id = 'write_intent:photo_supplement_intake:43:7';
  if (mode === 'resource') rows[0].resource_type = 'medication_log';
  if (mode === 'duplicate') rows[1] = rows[0];
  mockConfirm.mockResolvedValue({ status: 'executed', write_receipts: mode === 'missing' ? [] : mode === 'partial' ? rows.slice(0, 1) : rows });
  await expect(dispatchChatCardAction(action, undefined, context)).rejects.toThrow();
});
it('requires complete card context before sending', async () => {
  await expect(dispatchChatCardAction(action)).rejects.toThrow();
  expect(mockConfirm).not.toHaveBeenCalled();
});
it('returns verified execution when confirmation wins a dismissal race', async () => {
  mockDismiss.mockResolvedValue({ status: 'executed', write_receipts: receipts() });
  const result = await dispatchChatCardAction({ ...action, action: 'write_intent.dismiss', endpoint: '/write-intents/42/dismiss' }, undefined, context);
  expect(result.status).toBe('completed');
  expect(result.write_receipts).toHaveLength(2);
});
