import { reconcileRecordedDietCards } from '../recordedDietCardSync';

const old = { type: 'diet_draft', data: { card_id: 'meal-a', recorded: true, record_id: 1175, food_items: '面和饮品', calories: null, protein: null, updated_at: '2026-10-14T10:00:00Z', photo_url: '/private/photo' } };
const fresh = { type: 'diet_draft', data: { card_id: 'meal-b', recorded: true, record_id: 1175, food_items: '面和饮品', calories: 650, protein: 28, carbs: 70, fat: 24, fiber: null, updated_at: '2026-10-14T10:01:00Z' } };
const message = (id: string, card: any) => ({ id, role: 'assistant' as const, content: '', cardType: card.type, cardData: card.data });

it('refreshes an earlier saved meal from a newer durable projection of the same record', () => {
  const result = reconcileRecordedDietCards([message('old', old), message('new', fresh)]);
  expect(result[0].cardData).toMatchObject({ calories: 650, protein: 28, fiber: null, photo_url: '/private/photo' });
  expect(old.data.calories).toBeNull();
});
it('accepts explicit null as missing, never zero or the previous estimate', () => {
  const result = reconcileRecordedDietCards([message('old', fresh), message('new', { ...fresh, data: { ...fresh.data, calories: null, updated_at: '2026-10-14T10:02:00Z' } })]);
  expect(result[0].cardData.calories).toBeNull();
});
it.each([
  { recorded: false }, { record_id: 1176 }, { updated_at: '2026-10-14T09:59:00Z' }, { updated_at: 'bad' }, { calories: '650' },
])('does not project an unconfirmed, unrelated, stale or invalid source: %j', patch => {
  const result = reconcileRecordedDietCards([message('old', old), message('new', { ...fresh, data: { ...fresh.data, ...patch } })]);
  expect(result[0].cardData.calories).toBeNull();
});
it('refreshes saved diet cards nested in groups and never unconfirmed drafts', () => {
  const draft = { ...old, data: { ...old.data, recorded: false } };
  const result = reconcileRecordedDietCards([message('group', {type: 'cards_group', data: { cards: [old, draft] }}), message('new', fresh)]);
  expect(result[0].cardData.cards[0].data.calories).toBe(650);
  expect(result[0].cardData.cards[1].data.calories).toBeNull();
});
it('does not cross explicit owners or override an equal/unknown revision', () => {
  for (const data of [{ ...old.data, user_id: 2 }, { ...old.data, updated_at: fresh.data.updated_at }, { ...old.data, updated_at: undefined }]) {
    const result = reconcileRecordedDietCards([message('old', { ...old, data }), message('new', fresh)]);
    expect(result[0].cardData.calories).toBeNull();
  }
});
it('never revives an unavailable record or consumes it as a saved source', () => {
  const unavailable = { ...old, data: { ...old.data, record_unavailable: true } };
  expect(reconcileRecordedDietCards([message('old', unavailable), message('new', fresh)])[0].cardData.calories).toBeNull();
});
it('updates a persisted never-edited row with an explicit null revision after its first successful edit', () => {
  const result = reconcileRecordedDietCards([
    message('old', { ...old, data: { ...old.data, user_id: 7, updated_at: null } }),
    message('new', { ...fresh, data: { ...fresh.data, user_id: 7 } }),
  ]);
  expect(result[0].cardData.calories).toBe(650);
  expect(result[0].cardData.updated_at).toBe(fresh.data.updated_at);
});

it('preserves authoritative edit seed precision while refreshing the display card', () => {
  const seed = { record_id: 1175, calories: 650.1234, protein: null, carbs: 70, fat: 24, fiber: null,
    updated_at: fresh.data.updated_at };
  const source = { ...fresh, data: { ...fresh.data, calories: 650.12, adjust_record: seed } };
  const target = { ...old, data: { ...old.data, adjust_record: { record_id: 1175, calories: null } } };
  const result = reconcileRecordedDietCards([message('old', target), message('new', source)]);
  expect(result[0].cardData.calories).toBe(650.12);
  expect(result[0].cardData.adjust_record.calories).toBe(650.1234);
});
