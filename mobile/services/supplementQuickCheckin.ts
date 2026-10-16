import api from './api';
import { getEffectiveTimezone } from './location';
import type { components } from '../types/api.generated';

type SupplementRow = components['schemas']['SupplementWithRecord'];
export type SupplementSnapshot = { userId: number; timezone: string; date: string; rows: SupplementRow[] };
type CurrentSession = () => boolean;
export type SupplementSubmitResult = {
  status: 'saved' | 'already' | 'context_changed' | 'reconciled' | 'uncertain';
  snapshot: SupplementSnapshot;
};
function assertCurrent(current: CurrentSession): void {
  if (!current()) throw new Error('supplement_session_changed');
}
function dateInTimezone(timezone: string): string {
  // Invalid or unavailable account timezones fail closed; never use device day.
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)?.value).join('-');
}
async function readRows(userId: number, date: string, current: CurrentSession): Promise<SupplementRow[]> {
  assertCurrent(current);
  const { data } = await api.get<SupplementRow[]>(`/supplements/me/date/${date}`);
  assertCurrent(current);
  const ids = new Set<number>();
  if (!Array.isArray(data) || !data.every(row => {
    const s = row?.supplement;
    const r = row?.record;
    if (!s || !Number.isInteger(s.id) || s.id <= 0 || s.user_id !== userId || typeof s.name !== 'string' || !s.name.trim() || ids.has(s.id)) return false;
    ids.add(s.id);
    return !r || (Number.isInteger(r.id) && r.id > 0 && r.user_id === userId && r.supplement_id === s.id && r.record_date === date && typeof r.taken === 'boolean');
  })) throw new Error('supplement_invalid_readback');
  return data.filter(row => row.supplement.is_active === true);
}
export async function loadSupplementSnapshot(userId: number, current: CurrentSession): Promise<SupplementSnapshot> {
  assertCurrent(current);
  if (!Number.isInteger(userId) || userId <= 0) throw new Error('supplement_auth_required');
  const effective = await getEffectiveTimezone();
  assertCurrent(current);
  if (!effective?.timezone) throw new Error('supplement_timezone_required');
  const date = dateInTimezone(effective.timezone);
  const rows = await readRows(userId, date, current);
  return { userId, timezone: effective.timezone, date, rows };
}
export async function submitSupplementSelection(
  original: SupplementSnapshot, selected: number[], current: CurrentSession,
): Promise<SupplementSubmitResult> {
  assertCurrent(current);
  const ids = [...new Set(selected)];
  if (!ids.length || ids.some(id => !original.rows.some(row => row.supplement.id === id))) throw new Error('supplement_invalid_selection');
  const fresh = await loadSupplementSnapshot(original.userId, current);
  assertCurrent(current);
  if (fresh.date !== original.date || fresh.timezone !== original.timezone || ids.some(id => {
    const old = original.rows.find(row => row.supplement.id === id)?.supplement;
    const next = fresh.rows.find(row => row.supplement.id === id)?.supplement;
    return !next || old?.name !== next.name || old?.dosage !== next.dosage;
  })) return { status: 'context_changed', snapshot: fresh };
  const pending = ids.filter(id => !fresh.rows.find(row => row.supplement.id === id)?.record?.taken);
  if (!pending.length) return { status: 'already', snapshot: fresh };
  // Refresh could straddle midnight. Do not dispatch an old-day write.
  if (dateInTimezone(fresh.timezone) !== fresh.date) return { status: 'context_changed', snapshot: await loadSupplementSnapshot(original.userId, current) };
  try {
    assertCurrent(current);
    const { data } = await api.post<components['schemas']['SupplementBatchCheckinResponse']>('/supplements/records/batch', {
      record_date: fresh.date,
      checkins: pending.map(supplement_id => ({ supplement_id, taken: true })),
    });
    assertCurrent(current);
    const results = data?.results;
    if (!Array.isArray(results) || results.length !== pending.length || new Set(results.map(r => r.supplement_id)).size !== pending.length ||
      !results.every(r => pending.includes(r.supplement_id) && Number.isInteger(r.record_id) && r.record_id > 0 && r.record_date === fresh.date && r.taken === true)) {
      throw new Error('supplement_invalid_receipt');
    }
    return { status: 'saved', snapshot: { ...fresh, rows: fresh.rows.map(row => {
      const receipt = results.find(r => r.supplement_id === row.supplement.id);
      return receipt ? { ...row, record: { ...row.record, id: receipt.record_id, user_id: fresh.userId, supplement_id: receipt.supplement_id, record_date: fresh.date, taken: true } } : row;
    }) } };
  } catch {
    assertCurrent(current);
    // A timeout/invalid receipt is not a failed write. Reconcile once, never retry POST.
    try {
      const rows = await readRows(fresh.userId, fresh.date, current);
      return { status: pending.every(id => rows.some(row => row.supplement.id === id && row.record?.taken === true)) ? 'reconciled' : 'uncertain', snapshot: { ...fresh, rows } };
    } catch {
      assertCurrent(current);
      return { status: 'uncertain', snapshot: fresh };
    }
  }
}
