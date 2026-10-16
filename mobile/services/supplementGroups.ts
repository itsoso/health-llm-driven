import api from './api';

import type { components } from '../types/api.generated';
export type GroupMember = components['schemas']['SupplementGroupMember'];
export type GroupConfirmation = components['schemas']['SupplementGroupConfirmation'];
export type SupplementGroup = components['schemas']['SupplementGroupResponse'];
export type SupplementGroupCatalog = components['schemas']['SupplementGroupListResponse'];
export type GroupInput = components['schemas']['SupplementGroupCreate'];
type Guard = () => boolean;
const positive = (n: unknown): n is number => typeof n === 'number' && Number.isSafeInteger(n) && n > 0;
const text = (s: unknown): s is string => typeof s === 'string' && s.trim().length > 0;
function current(guard: Guard) { if (!guard()) throw new Error('supplement_group_session_changed'); }
function validConfirmation(value: any): value is GroupConfirmation {
  return !!value && positive(value.event_id) && positive(value.group_id) && text(value.name) && text(value.revision) && /^\d{4}-\d{2}-\d{2}$/.test(value.record_date) && value.source === 'manual_group' &&
    Array.isArray(value.members) && value.members.length > 0 && new Set(value.members.map((m: any) => m.supplement_id)).size === value.members.length &&
    value.members.every((m: any) => positive(m.supplement_id) && text(m.name) && (m.reference_dosage === null || typeof m.reference_dosage === 'string') && positive(m.record_id) && typeof m.already_taken === 'boolean');
}
function validGroup(value: any): value is SupplementGroup {
  return !!value && positive(value.id) && text(value.name) && text(value.revision) && Array.isArray(value.members) && value.members.length > 0 && value.members.length <= 30 &&
    new Set(value.members.map((m: any) => m.supplement_id)).size === value.members.length &&
    value.members.every((m: any) => positive(m.supplement_id) && text(m.name) && (m.reference_dosage === null || typeof m.reference_dosage === 'string') && typeof m.available === 'boolean') &&
    (value.today_confirmation === null || (validConfirmation(value.today_confirmation) && value.today_confirmation.group_id === value.id));
}
export async function loadSupplementGroups(guard: Guard): Promise<SupplementGroupCatalog> {
  current(guard); const { data } = await api.get<SupplementGroupCatalog>('/supplements/groups'); current(guard);
  if (!data || !/^\d{4}-\d{2}-\d{2}$/.test(data.record_date) || !text(data.timezone) || !Array.isArray(data.groups) || !data.groups.every(validGroup) ||
    new Set(data.groups.map(g => g.id)).size !== data.groups.length || data.groups.some(g => g.today_confirmation && g.today_confirmation.record_date !== data.record_date)) throw new Error('supplement_group_invalid_catalog');
  // Reject invalid IANA values instead of substituting a device timezone.
  new Intl.DateTimeFormat('en-US', { timeZone: data.timezone }).format();
  return data;
}
function sameDay(a: SupplementGroupCatalog, b: SupplementGroupCatalog) { return a.record_date === b.record_date && a.timezone === b.timezone; }
async function freshForEdit(catalog: SupplementGroupCatalog, guard: Guard, group?: SupplementGroup) {
  const fresh = await loadSupplementGroups(guard);
  if (!sameDay(catalog, fresh) || (group && !fresh.groups.some(g => g.id === group.id && g.revision === group.revision))) throw new Error('supplement_group_context_changed');
  return fresh;
}
export async function saveSupplementGroup(catalog: SupplementGroupCatalog, input: GroupInput, guard: Guard, group?: SupplementGroup): Promise<SupplementGroup> {
  if (!text(input.name) || input.name.trim().length > 60 || !input.supplement_ids.length || input.supplement_ids.length > 30 || input.supplement_ids.some(id => !positive(id)) || new Set(input.supplement_ids).size !== input.supplement_ids.length) throw new Error('supplement_group_invalid_input');
  await freshForEdit(catalog, guard, group); current(guard);
  const payload = { name: input.name.trim(), supplement_ids: input.supplement_ids };
  const { data } = group ? await api.put<SupplementGroup>(`/supplements/groups/${group.id}`, { ...payload, revision: group.revision }) : await api.post<SupplementGroup>('/supplements/groups', payload);
  current(guard); if (!validGroup(data) || (group && data.id !== group.id) || data.name !== payload.name || data.members.length !== payload.supplement_ids.length || !data.members.every(m => payload.supplement_ids.includes(m.supplement_id))) throw new Error('supplement_group_invalid_save_receipt'); return data;
}
export async function archiveSupplementGroup(catalog: SupplementGroupCatalog, group: SupplementGroup, guard: Guard): Promise<void> {
  await freshForEdit(catalog, guard, group); current(guard);
  const { data } = await api.delete(`/supplements/groups/${group.id}`, { params: { revision: group.revision } });
  current(guard); if (data?.archived !== true) throw new Error('supplement_group_invalid_archive_receipt');
}
function matches(receipt: GroupConfirmation, group: SupplementGroup, date: string) {
  return validConfirmation(receipt) && receipt.group_id === group.id && receipt.revision === group.revision && receipt.record_date === date &&
    receipt.members.length === group.members.length && receipt.members.every(m => group.members.some(expected => expected.supplement_id === m.supplement_id && expected.name === m.name && expected.reference_dosage === m.reference_dosage));
}
export async function confirmSupplementGroup(catalog: SupplementGroupCatalog, group: SupplementGroup, guard: Guard): Promise<{ status: 'confirmed' | 'already' | 'reconciled' | 'context_changed' | 'uncertain'; catalog: SupplementGroupCatalog }> {
  const fresh = await loadSupplementGroups(guard); current(guard);
  const latest = fresh.groups.find(g => g.id === group.id);
  if (!sameDay(catalog, fresh)) return { status: 'context_changed', catalog: fresh };
  if (latest?.today_confirmation) return { status: 'already', catalog: fresh };
  if (!latest || latest.revision !== group.revision || latest.members.some(m => !m.available)) return { status: 'context_changed', catalog: fresh };
  try {
    current(guard);
    const { data } = await api.post<GroupConfirmation>(`/supplements/groups/${group.id}/confirm`, { revision: group.revision, record_date: fresh.record_date, confirmed: true });
    current(guard); if (!matches(data, group, fresh.record_date)) throw new Error('supplement_group_invalid_confirmation');
    return { status: 'confirmed', catalog: { ...fresh, groups: fresh.groups.map(g => g.id === group.id ? { ...g, today_confirmation: data } : g) } };
  } catch {
    current(guard);
    try {
      const readback = await loadSupplementGroups(guard);
      const receipt = readback.groups.find(g => g.id === group.id)?.today_confirmation;
      return { status: receipt && matches(receipt, group, fresh.record_date) ? 'reconciled' : 'uncertain', catalog: readback };
    } catch { current(guard); return { status: 'uncertain', catalog: fresh }; }
  }
}
