import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useAuth } from '../hooks/useAuth';
import { subscribeAuthSessionChange } from '../services/api';
import { loadMedicationReminder, type MedicationReminderContext } from '../services/medicationReminderLanding';
import { resolveNotificationRoute } from '../services/notificationRoutes';
import { revaColors as C } from '../constants/revaTheme';

type Row = { id: number; context: MedicationReminderContext | null };
function needsOccurrenceCheck(context: MedicationReminderContext): boolean {
  return context.requires_date_confirmation || context.reason === 'timezone_mismatch';
}
function rowStatus(context: MedicationReminderContext): string {
  if (context.requires_date_confirmation) return '日期待确认';
  if (context.reason === 'timezone_mismatch') return '时区需核对';
  return context.log ? ({ taken: '已记录服用', skipped: '已记录未服用', delayed: '已推迟' }[context.log.status] ?? '已有记录') : '待核对';
}

/** A notification group is a list of occurrences, never a bulk intake instruction. */
export default function MedicationRemindersScreen() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const { user, token } = useAuth();
  const payload = { reminder_type: 'medication', medication_ids: typeof params.ids === 'string' ? params.ids.split(',') : [], scheduled_date: params.date, scheduled_time: params.time, scheduled_timezone: params.sourceTimezone };
  const route = resolveNotificationRoute(payload)!;
  const invalid = route.includes('invalid=');
  const target = new URLSearchParams(route.split('?')[1]);
  const ids = invalid ? [] : (target.get('ids') ?? target.get('id') ?? '').split(',').map(Number);
  const key = JSON.stringify([route, user?.id, token]);
  const activeKey = useRef(key);
  activeKey.current = key;
  const epoch = useRef(0);
  const invalidSession = useRef(false);
  const identity = `${user?.id ?? ''}:${token ?? ''}`;
  const identityRef = useRef(identity);
  if (identityRef.current !== identity) {
    identityRef.current = identity; invalidSession.current = true; epoch.current += 1;
  }
  const [state, setState] = useState<{ key: string; rows: Row[]; loading: boolean; error: string | null }>({ key, rows: [], loading: true, error: null });
  useEffect(() => subscribeAuthSessionChange(() => {
    invalidSession.current = true;
    epoch.current += 1;
    setState({ key: activeKey.current, rows: [], loading: false, error: '登录状态已变化，请重新打开提醒' });
  }), []);
  const refresh = useCallback(async () => {
    const run = ++epoch.current;
    const current = () => run === epoch.current && activeKey.current === key && !invalidSession.current;
    if (invalidSession.current || invalid || !user?.id || !token) {
      setState({ key, rows: [], loading: false, error: invalidSession.current ? '登录状态已变化，请重新打开提醒' : invalid ? '这条提醒信息不完整，请到用药管理核对' : '请先登录后查看用药提醒' });
      return;
    }
    setState({ key, rows: [], loading: true, error: null });
    const rows: Row[] = [];
    // Sequential, bounded by the payload cap. Never fan out unbounded requests.
    for (const id of ids) {
      if (!current()) return;
      let context: MedicationReminderContext | null = null;
      try {
        context = await loadMedicationReminder(user.id, { id, date: target.get('date') ?? undefined, time: target.get('time') ?? undefined, sourceTimezone: target.get('sourceTimezone') ?? undefined }, current);
      } catch { context = null; /* A failed read renders an explicit unavailable row. */ }
      if (!current()) return;
      rows.push({ id, context });
      setState({ key, rows: [...rows], loading: rows.length < ids.length, error: null });
    }
    // All route and identity primitives are encoded in key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useFocusEffect(useCallback(() => { void refresh(); return () => { epoch.current += 1; }; }, [refresh]));
  const visible = state.key === key && !invalidSession.current;
  const rows = visible ? state.rows : [];
  return <SafeAreaView style={styles.screen}>
    <View style={styles.header}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={styles.back}><Text style={styles.title}>‹</Text></Pressable><Text style={styles.title}>用药提醒</Text></View>
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.hero}><Text style={styles.label}>本次提醒</Text><Text style={styles.time}>{target.get('time') ?? '时间待确认'}</Text><Text style={styles.body}>{target.get('date') ?? '日期待确认'}</Text><Text style={styles.note}>{target.get('sourceTimezone') ?? '请在详情核对提醒时区'}</Text><Text style={styles.body}>逐项核对后，记录实际服用情况</Text></View>
      {state.key === key && state.error ? <Text accessibilityRole="alert" style={styles.body}>{state.error}</Text> : null}
      {rows.map((row, index) => <View key={row.id} style={styles.card}>
        <Text style={styles.title}>{row.context?.medication.name ?? `第 ${index + 1} 项提醒`}</Text>
        {row.context ? <><Text style={styles.body}>{row.context.medication.dosage || '剂量未填写'}</Text><Text style={styles.label}>{rowStatus(row.context)}</Text></> : <Text style={styles.body}>暂时无法读取，请刷新重试或到用药管理核对</Text>}
        {row.context && <Pressable accessibilityRole="button" accessibilityLabel={`查看第 ${index + 1} 项提醒`} style={styles.button} onPress={() => {
          if (activeKey.current !== key || invalidSession.current) return;
          router.push(resolveNotificationRoute({ ...payload, medication_ids: [row.id] }) as any);
        }}><Text style={styles.buttonText}>{needsOccurrenceCheck(row.context) ? '查看并核对' : row.context.log ? '查看记录' : '查看并记录'} →</Text></Pressable>}
      </View>)}
      {visible && state.loading && <ActivityIndicator accessibilityLabel="正在读取提醒" color={C.green600} />}
      <Pressable accessibilityRole="button" onPress={() => { void refresh(); }} style={styles.button}><Text style={styles.buttonText}>刷新核对</Text></Pressable>
      <Pressable accessibilityRole="button" onPress={() => router.push('/medications')} style={styles.button}><Text style={styles.buttonText}>查看用药管理</Text></Pressable>
      <Text style={styles.note}>仅记录实际服用情况，不调整用药方案</Text>
    </ScrollView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.paper }, header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, gap: 12 }, back: { padding: 12 },
  content: { padding: 20, gap: 16, paddingBottom: 40 }, hero: { backgroundColor: C.green50, padding: 24, borderRadius: 24, gap: 10 },
  title: { fontSize: 21, fontWeight: '600', color: C.ink1 }, time: { fontSize: 42, fontWeight: '600', color: C.green700 },
  label: { fontSize: 16, fontWeight: '600', color: C.green600 }, body: { fontSize: 17, color: C.ink2, lineHeight: 26 }, note: { fontSize: 14, color: C.ink2, lineHeight: 22 },
  card: { backgroundColor: C.surface, padding: 22, borderRadius: 22, gap: 12 }, button: { minHeight: 48, justifyContent: 'center', padding: 12, backgroundColor: C.green50, borderRadius: 14 }, buttonText: { fontSize: 17, color: C.green700, fontWeight: '600' },
});
