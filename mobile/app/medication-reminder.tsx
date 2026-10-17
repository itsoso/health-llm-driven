import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../hooks/useAuth';
import { subscribeAuthSessionChange } from '../services/api';
import { confirmTodayMedicationTaken, loadMedicationReminder, submitMedicationReminder, isReminderDate, isReminderTime, type MedicationReminderContext, type MedicationReminderTarget } from '../services/medicationReminderLanding';
import MedicationReminderView from '../components/medication/MedicationReminderView';

export default function MedicationReminderScreen() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, token } = useAuth();
  const idText = typeof params.id === 'string' ? params.id : '';
  const id = /^[1-9]\d*$/.test(idText) ? Number(idText) : NaN;
  const invalid = Boolean(params.invalid) || !Number.isSafeInteger(id) || (params.date !== undefined && !isReminderDate(params.date)) || (params.time !== undefined && !isReminderTime(params.time)) || (params.sourceTimezone !== undefined && typeof params.sourceTimezone !== 'string');
  const routeKey = JSON.stringify([idText, params.date, params.time, params.sourceTimezone, invalid]);
  const identity = `${user?.id ?? ''}:${token ?? ''}`;
  const identityRef = useRef(identity);
  const invalidSession = useRef(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const busyRef = useRef(false);
  const uncertainRef = useRef(false);
  const targetRef = useRef<MedicationReminderTarget>({ id });
  const contextRef = useRef<MedicationReminderContext | null>(null);
  const [context, setContext] = useState<MedicationReminderContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  if (identityRef.current !== identity) {
    identityRef.current = identity; invalidSession.current = true; generation.current += 1;
  }
  const store = (value: MedicationReminderContext) => { contextRef.current = value; setContext(value); };
  const refresh = useCallback(async (nextTarget?: MedicationReminderTarget) => {
    if (busyRef.current || invalidSession.current) return;
    if (nextTarget) targetRef.current = nextTarget;
    const epoch = ++generation.current;
    const current = () => mounted.current && !invalidSession.current && generation.current === epoch;
    setLoading(true); setError(null);
    if (invalid || !user?.id || !token) {
      setLoading(false); setError(invalid ? '这条提醒缺少有效的药品信息，请到用药管理核对' : '请先登录后查看用药提醒'); return;
    }
    try {
      const next = await loadMedicationReminder(user.id, targetRef.current, current);
      if (!current()) return;
      store(next);
      if (next.log) uncertainRef.current = false;
    } catch {
      if (current()) { contextRef.current = null; setContext(null); setError('暂时无法读取这次提醒，请检查网络后重试'); }
    } finally {
      if (current()) setLoading(false);
    }
  }, [invalid, user?.id, token]);
  useEffect(() => {
    mounted.current = true;
    const invalidate = () => {
      invalidSession.current = true; generation.current += 1;
      contextRef.current = null; setContext(null); setLoading(false); setBusy(false);
      setError('登录状态已变化，请重新打开提醒'); setMessage(null);
    };
    const unsubscribe = subscribeAuthSessionChange(invalidate);
    if (invalidSession.current) invalidate();
    else {
      contextRef.current = null; setContext(null); setMessage(null); uncertainRef.current = false; busyRef.current = false; setBusy(false);
      void refresh({ id, date: typeof params.date === 'string' ? params.date : undefined, time: typeof params.time === 'string' ? params.time : undefined, sourceTimezone: typeof params.sourceTimezone === 'string' ? params.sourceTimezone : undefined });
    }
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void refresh(); });
    return () => { mounted.current = false; generation.current += 1; unsubscribe(); listener.remove(); };
    // routeKey includes all route primitive fields.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey, refresh]);
  const submit = async (status: 'taken' | 'skipped', confirmToday = false) => {
    const original = contextRef.current;
    if (!original || original.log || loading || busyRef.current || uncertainRef.current || invalidSession.current) return;
    if (confirmToday ? !original.requires_date_confirmation || !original.time : !original.actionable || original.requires_date_confirmation) return;
    busyRef.current = true; setBusy(true); setError(null); setMessage(null);
    const epoch = generation.current;
    const current = () => mounted.current && !invalidSession.current && epoch === generation.current;
    try {
      const result = confirmToday
        ? await confirmTodayMedicationTaken(original, current)
        : await submitMedicationReminder(original, status, current);
      if (!current()) return;
      store(result.context);
      if (!result.context.requires_date_confirmation) targetRef.current = { id: result.context.medication.id, date: result.context.date, time: result.context.time ?? undefined, sourceTimezone: result.context.timezone };
      uncertainRef.current = result.status === 'uncertain';
      const messages = {
        saved: status === 'taken' ? '已记录本次已服用' : '已记录本次未服用',
        already: '这次提醒已有记录，无需重复操作',
        changed: '用药信息或日期已变化，请核对后再确认',
        reconciled: '已核对到本次记录，无需重复操作',
        conflict: '本次已有不同的记录，已显示服务器保存的状态',
        uncertain: '记录结果尚未确认，请刷新核对，避免重复记录',
      };
      setMessage(messages[result.status]);
      if (result.context.log) {
        void Promise.all([['medications'], ['medicationToday'], ['timeline'], ['agenda']].map(queryKey => queryClient.invalidateQueries({ queryKey, refetchType: 'none' }))).catch(() => {
          if (current()) setMessage(`${messages[result.status]}。其他页面可能需要刷新。`);
        });
      }
    } catch {
      if (current()) setError('暂时无法核对用药状态，请刷新后重试');
    } finally {
      if (current()) { busyRef.current = false; setBusy(false); }
    }
  };
  const visibleContext = invalidSession.current ? null : context && uncertainRef.current ? { ...context, actionable: false, requires_date_confirmation: false } : context;
  return <MedicationReminderView
    context={visibleContext} loading={loading} busy={busy} error={error} message={message}
    onBack={() => router.back()} onManage={() => router.push('/medications')}
    onRetry={() => { void refresh(); }}
    onConfirmDate={() => {
      const current = contextRef.current;
      if (!current || busyRef.current || invalidSession.current) return;
      void refresh({ ...targetRef.current, date: current.today_date, sourceTimezone: current.timezone });
    }}
    onSelectTime={time => {
      if (!isReminderTime(time) || busyRef.current || invalidSession.current) return;
      void refresh({ ...targetRef.current, time });
    }}
    onConfirmTodayTaken={() => { void submit('taken', true); }}
    onTaken={() => { void submit('taken'); }} onSkipped={() => { void submit('skipped'); }}
  />;
}
