import api from './api';
import type { Medication, MedicationLogResult } from './medications';

export type MedicationReminderTarget = { id: number; date?: string; time?: string; sourceTimezone?: string };
export type MedicationReminderContext = {
  user_id: number;
  timezone: string;
  today_date: string;
  date: string;
  time: string | null;
  requires_date_confirmation: boolean;
  revision: string;
  medication: Pick<Medication, 'id' | 'name' | 'dosage' | 'frequency' | 'is_active' | 'reminder_times' | 'safety_alerts'> & { user_id: number; timing_label?: string | null };
  log: MedicationLogResult | null;
  actionable: boolean;
  reason: string | null;
};
type CurrentSession = () => boolean;
const validId = (id: unknown): id is number => Number.isSafeInteger(id) && Number(id) > 0;
export const isReminderDate = (value: unknown): value is string => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};
export const isReminderTime = (value: unknown): value is string => typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
function assertCurrent(current: CurrentSession) {
  if (!current()) throw new Error('medication_reminder_session_changed');
}
function exactReceipt(log: MedicationLogResult, context: MedicationReminderContext) {
  return log && validId(log.id) && log.medication_id === context.medication.id && log.taken_date === context.date && log.taken_time === context.time && ['taken', 'skipped', 'delayed'].includes(log.status);
}
export async function loadMedicationReminder(userId: number, target: MedicationReminderTarget, current: CurrentSession): Promise<MedicationReminderContext> {
  assertCurrent(current);
  if (!validId(userId) || !validId(target.id) || (target.date !== undefined && !isReminderDate(target.date)) || (target.time !== undefined && !isReminderTime(target.time))) throw new Error('medication_reminder_invalid_target');
  const { data } = await api.get<MedicationReminderContext>(`/medication/medications/${target.id}/reminder`, { params: { date: target.date, time: target.time, source_timezone: target.sourceTimezone } });
  assertCurrent(current);
  if (!data || data.user_id !== userId || data.medication?.user_id !== userId || data.medication.id !== target.id || typeof data.medication.name !== 'string' || !data.medication.name.trim() || !isReminderDate(data.date) || !isReminderDate(data.today_date) || (data.time !== null && !isReminderTime(data.time)) || (target.date && data.date !== target.date) || (target.time && data.time !== target.time) || !data.timezone || !data.revision || typeof data.actionable !== 'boolean' || typeof data.requires_date_confirmation !== 'boolean' || (data.log && !exactReceipt(data.log, data))) throw new Error('medication_reminder_invalid_readback');
  return data;
}
export type MedicationReminderSubmitResult = { status: 'saved' | 'already' | 'changed' | 'reconciled' | 'conflict' | 'uncertain'; context: MedicationReminderContext };
export async function submitMedicationReminder(original: MedicationReminderContext, status: 'taken' | 'skipped', current: CurrentSession): Promise<MedicationReminderSubmitResult> {
  assertCurrent(current);
  if (!original.actionable || original.requires_date_confirmation || !original.time || original.log) throw new Error('medication_reminder_not_actionable');
  const target = { id: original.medication.id, date: original.date, time: original.time, sourceTimezone: original.timezone };
  const fresh = await loadMedicationReminder(original.user_id, target, current);
  if (fresh.log) return { status: 'already', context: fresh };
  if (!fresh.actionable || fresh.requires_date_confirmation || fresh.timezone !== original.timezone || fresh.revision !== original.revision || fresh.today_date !== original.today_date) return { status: 'changed', context: fresh };
  try {
    assertCurrent(current);
    const { data } = await api.post<MedicationLogResult>(`/medication/medications/${target.id}/reminder/log`, { date: fresh.date, time: fresh.time, timezone: fresh.timezone, expected_revision: fresh.revision, status });
    assertCurrent(current);
    if (!exactReceipt(data, fresh)) throw new Error('medication_reminder_invalid_receipt');
    return { status: data.status === status ? 'saved' : 'conflict', context: { ...fresh, actionable: false, reason: 'already_recorded', log: data } };
  } catch {
    assertCurrent(current);
    // An uncertain response may already have committed. Re-read once, never retry POST.
    try {
      const reconciled = await loadMedicationReminder(original.user_id, target, current);
      return { status: reconciled.log ? (reconciled.log.status === status ? 'reconciled' : 'conflict') : 'uncertain', context: reconciled };
    } catch {
      assertCurrent(current);
      return { status: 'uncertain', context: fresh };
    }
  }
}

/** Explicit user confirmation of both the displayed account-local date and actual intake. */
export async function confirmTodayMedicationTaken(original: MedicationReminderContext, current: CurrentSession): Promise<MedicationReminderSubmitResult> {
  if (!original.requires_date_confirmation || original.reason !== 'date_confirmation_required' || !original.time || original.log || !isReminderDate(original.today_date)) {
    throw new Error('medication_reminder_date_confirmation_unavailable');
  }
  // Only resolve the missing date. The normal submit path must still re-read the
  // owner, schedule, revision, local day and actionability before any POST.
  return submitMedicationReminder({ ...original, date: original.today_date, requires_date_confirmation: false, actionable: true }, 'taken', current);
}
