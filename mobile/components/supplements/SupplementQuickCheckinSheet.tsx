import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, KeyboardAvoidingView, Platform, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { recordMutationQueryKeys } from '../../applib/queryKeys';
import { useAuth } from '../../hooks/useAuth';
import { subscribeAuthSessionChange } from '../../services/api';
import { loadSupplementSnapshot, submitSupplementSelection, type SupplementSnapshot } from '../../services/supplementQuickCheckin';
import SupplementGroupsPanel from './SupplementGroupsPanel';
import { revaColors as colors, revaSemantic } from '../../constants/revaTheme';

/** Mounted only while open. No defaults, model calls, or implicit dosage writes. */
export default function SupplementQuickCheckinSheet({ onClose }: { onClose: () => void }) {
  const { user, token } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const insets = useSafeAreaInsets();
  const [snapshot, setSnapshot] = useState<SupplementSnapshot | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [loadError, setLoadError] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [sessionChanged, setSessionChanged] = useState(false);
  const epoch = useRef(0);
  const mounted = useRef(true);
  const busyRef = useRef(false);
  const loadingRef = useRef(false);
  const invalidSession = useRef(false);
  const snapshotRef = useRef<SupplementSnapshot | null>(null);
  const groupRefreshRequested = useRef(false);
  const identity = `${user?.id ?? ''}:${token ?? ''}`;
  const identityRef = useRef(identity);
  // Invalidate synchronously during a new auth render, before pending promises resume.
  if (identityRef.current !== identity) {
    identityRef.current = identity;
    invalidSession.current = true;
    epoch.current += 1;
  }
  const saveSnapshot = (next: SupplementSnapshot) => { snapshotRef.current = next; setSnapshot(next); };
  const refresh = useCallback(async (background = false) => {
    if (invalidSession.current || busyRef.current || loadingRef.current) return;
    const generation = epoch.current;
    const current = () => mounted.current && !invalidSession.current && generation === epoch.current;
    if (!user?.id || !token) {
      setLoading(false); setLoadError(true); setMessage('请先登录后再记录补剂'); return;
    }
    loadingRef.current = true;
    if (!background) setLoading(true);
    try {
      const next = await loadSupplementSnapshot(user.id, current);
      if (!current()) return;
      const previous = snapshotRef.current;
      const changed = previous && (next.date !== previous.date || next.timezone !== previous.timezone);
      saveSnapshot(next);
      setLoadError(false);
      if (changed) {
        setSelected([]); setMessage('日期或时区已变化，请重新勾选');
      } else {
        setSelected(ids => ids.filter(id => next.rows.some(row => row.supplement.id === id && !row.record?.taken)));
        if (!background) setMessage('');
      }
    } catch {
      if (current()) {
        setLoadError(true); setMessage('暂时无法加载补剂，请检查网络后重试');
        // Do not leave stale selections actionable after a failed refresh.
        setSelected([]);
      }
    } finally {
      if (generation === epoch.current) loadingRef.current = false;
      if (current()) setLoading(false);
    }
  }, [user?.id, token]);
  useEffect(() => {
    mounted.current = true;
    const invalidate = () => {
      invalidSession.current = true; epoch.current += 1;
      snapshotRef.current = null; setSnapshot(null); setSelected([]);
      setSessionChanged(true); setLoading(false); setBusy(false);
      busyRef.current = false; loadingRef.current = false;
    };
    const unsubscribe = subscribeAuthSessionChange(invalidate);
    if (invalidSession.current) invalidate();
    else void refresh();
    const timer = setInterval(() => { if (AppState.currentState === 'active') void refresh(true); }, 60000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void refresh(true); });
    return () => { mounted.current = false; epoch.current += 1; loadingRef.current = false; unsubscribe(); clearInterval(timer); listener.remove(); };
  }, [refresh]);
  const handleGroupBusy = useCallback((value: boolean) => {
    busyRef.current = value; setBusy(value);
    if (!value && groupRefreshRequested.current) {
      groupRefreshRequested.current = false;
      void refresh(true);
    }
  }, [refresh]);
  const handleGroupRecorded = () => {
    groupRefreshRequested.current = true;
    setSelected([]);
    void Promise.all([...recordMutationQueryKeys, ['supplements']].map(queryKey =>
      queryClient.invalidateQueries({ queryKey, refetchType: 'none' }),
    )).catch(() => { if (mounted.current && !invalidSession.current) setMessage('记录页面可能需要手动刷新'); });
  };
  const close = () => { if (!busyRef.current) onClose(); };
  const submit = async () => {
    if (busyRef.current || loadingRef.current || uncertain || loadError || invalidSession.current || !snapshot || !selected.length) return;
    busyRef.current = true; setBusy(true); setMessage('');
    const generation = epoch.current;
    const current = () => mounted.current && !invalidSession.current && generation === epoch.current;
    try {
      const result = await submitSupplementSelection(snapshot, selected, current);
      if (!current()) return;
      saveSnapshot(result.snapshot); setSelected([]);
      const messages = {
        saved: '已记录本次勾选的已服状态',
        already: '所选补剂今天已有已服记录，无需重复记录',
        reconciled: '已核对，所选补剂今天已有已服记录',
        context_changed: '日期、时区或补剂清单已变化，请重新勾选',
        uncertain: '提交结果尚未确认，请稍后到补剂记录核对，避免重复提交',
      };
      setMessage(messages[result.status]);
      if (result.status === 'uncertain') setUncertain(true);
      // Mark related screens stale without fetching unrelated health data here.
      if (result.status !== 'context_changed') {
        void Promise.all([...recordMutationQueryKeys, ['supplements']].map(queryKey =>
          queryClient.invalidateQueries({ queryKey, refetchType: 'none' }),
        )).catch(() => {
          if (current()) setMessage(`${messages[result.status]}。其他页面可能需要手动刷新。`);
        });
      }
    } catch {
      if (current()) { setMessage('暂时无法核对当前清单，请重新加载后再试'); setSelected([]); setLoadError(true); }
    } finally {
      if (current()) { busyRef.current = false; setBusy(false); }
    }
  };
  const disabled = busy || loading || loadError || uncertain || sessionChanged || invalidSession.current;
  const manage = () => { if (!busyRef.current) { onClose(); router.push('/(tabs)/record'); } };
  return (
    <Modal transparent animationType="slide" visible onRequestClose={close}>
      <KeyboardAvoidingView style={styles.overlay} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <Pressable style={StyleSheet.absoluteFill} onPress={close} accessibilityLabel="收起补剂打卡" disabled={busy} />
        <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]} accessibilityViewIsModal>
          <View style={styles.handle} />
          <View style={styles.heading}>
            <View style={styles.headingText}>
              <Text style={styles.title}>补剂打卡</Text>
              <Text style={styles.subtitle}>{snapshot ? `${snapshot.date} · ${snapshot.timezone}` : '勾选本次已经服用的补剂'}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel="关闭补剂打卡" accessibilityState={{ disabled: busy }} disabled={busy} onPress={close} style={styles.close}><Text style={styles.closeText}>×</Text></Pressable>
          </View>
          <View style={styles.notice}><Text style={styles.noticeText}>只记录已服状态，不记录本次剂量。常规用量仅供核对，不是服用建议。</Text></View>
          <ScrollView style={styles.list} contentContainerStyle={styles.listContent} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
            {sessionChanged || invalidSession.current ? <Text style={styles.empty}>登录状态已变化，请关闭后重新打开</Text> : loading ? <View style={styles.loading}><ActivityIndicator color={colors.green500} /><Text style={styles.subtitle}>正在加载我的补剂…</Text></View> : <>
              {snapshot && !loadError && <SupplementGroupsPanel snapshot={snapshot} disabled={disabled} onBusyChange={handleGroupBusy} onRecorded={handleGroupRecorded} onUncertain={() => setUncertain(true)} />}
              {!!message && <Text accessibilityRole="alert" style={[styles.message, uncertain || loadError ? styles.warning : null]}>{message}</Text>}
              {loadError ? <Pressable accessibilityRole="button" onPress={() => void refresh()} style={styles.secondary}><Text style={styles.linkText}>重新加载</Text></Pressable> : <>
                {snapshot?.rows.length === 0 && <View style={styles.emptyBlock}><Text style={styles.emptyTitle}>暂无可勾选的补剂</Text><Text style={styles.subtitle}>请先在对话中添加补剂清单，再回来打卡。</Text></View>}
                {snapshot?.rows.map(row => {
                  const taken = row.record?.taken === true;
                  const checked = selected.includes(row.supplement.id);
                  return <Pressable key={row.supplement.id} accessibilityRole="checkbox" accessibilityLabel={row.supplement.name}
                    accessibilityState={{ checked: taken || checked, disabled: taken || disabled }} disabled={taken || disabled}
                    onPress={() => setSelected(ids => ids.includes(row.supplement.id) ? ids.filter(id => id !== row.supplement.id) : [...ids, row.supplement.id])}
                    style={[styles.row, checked && styles.rowSelected, taken && styles.rowTaken]}>
                    <View style={[styles.checkbox, (checked || taken) && styles.checkboxSelected]}><Text style={styles.check}>{checked || taken ? '✓' : ''}</Text></View>
                    <View style={styles.rowBody}><Text style={styles.name}>{row.supplement.name}</Text>{!!row.supplement.dosage && <Text style={styles.reference}>参考用量：{row.supplement.dosage}</Text>}</View>
                    {taken && <Text style={styles.taken}>今日已服</Text>}
                  </Pressable>;
                })}
              </>}
              <Pressable accessibilityRole="button" disabled={busy} onPress={manage} style={styles.manage}><Text style={styles.linkText}>查看补剂记录</Text></Pressable>
            </>}
          </ScrollView>
          <View style={styles.footer}>
            <Text style={styles.footerHint}>仅勾选你已服用的项目，不会自动全选</Text>
            <Pressable accessibilityRole="button" accessibilityState={{ disabled: disabled || !selected.length }} disabled={disabled || !selected.length} onPress={() => void submit()} style={[styles.primary, (disabled || !selected.length) && styles.primaryDisabled]}>
              {busy && <ActivityIndicator color={colors.greenOn} />}
              <Text style={styles.primaryText}>{busy ? '正在核对并记录…' : `确认已服 · ${selected.length} 项`}</Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(22,32,27,0.32)' },
  sheet: { width: '100%', maxWidth: 640, alignSelf: 'center', maxHeight: '88%', backgroundColor: colors.paper, borderTopLeftRadius: 28, borderTopRightRadius: 28 },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.lineStrong, alignSelf: 'center', marginTop: 10, marginBottom: 14 },
  heading: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, gap: 12 },
  headingText: { flex: 1 }, title: { fontSize: 23, fontWeight: '700', color: colors.ink1 },
  subtitle: { fontSize: 13, color: colors.ink2, lineHeight: 20, marginTop: 5 },
  close: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center', borderRadius: 22, backgroundColor: colors.paper2 },
  closeText: { fontSize: 28, color: colors.ink2 },
  notice: { margin: 20, marginBottom: 8, backgroundColor: colors.green50, padding: 12, borderRadius: 12 },
  noticeText: { fontSize: 13, lineHeight: 20, color: colors.green700 },
  list: { flexShrink: 1 }, listContent: { paddingHorizontal: 20, paddingBottom: 8, gap: 10 },
  loading: { padding: 28, alignItems: 'center', gap: 10 },
  row: { minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: 16, padding: 14 },
  rowSelected: { borderColor: colors.green500, backgroundColor: colors.green50 }, rowTaken: { backgroundColor: colors.paper2 },
  rowBody: { flex: 1 }, name: { fontSize: 16, lineHeight: 23, fontWeight: '600', color: colors.ink1 }, reference: { fontSize: 12, lineHeight: 18, color: colors.ink2, marginTop: 4 },
  checkbox: { width: 24, height: 24, borderRadius: 7, borderWidth: 1.5, borderColor: colors.lineStrong, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  checkboxSelected: { backgroundColor: colors.green500, borderColor: colors.green500 }, check: { fontSize: 17, fontWeight: '700', color: colors.greenOn },
  taken: { fontSize: 12, color: colors.green600 }, empty: { padding: 20, color: colors.ink2, lineHeight: 22 },
  emptyBlock: { paddingVertical: 24, alignItems: 'center' }, emptyTitle: { fontSize: 17, color: colors.ink1, fontWeight: '600' },
  message: { padding: 12, borderRadius: 12, color: colors.green700, backgroundColor: colors.green50, fontSize: 14, lineHeight: 21 },
  warning: { color: revaSemantic.caution.fg, backgroundColor: revaSemantic.caution.bg },
  secondary: { padding: 14, alignItems: 'center' }, manage: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 4 }, linkText: { color: colors.green600, fontSize: 14, fontWeight: '600' },
  footer: { paddingHorizontal: 20, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.line },
  footerHint: { textAlign: 'center', fontSize: 12, color: colors.ink2, marginBottom: 10 },
  primary: { minHeight: 52, borderRadius: 16, backgroundColor: colors.green500, justifyContent: 'center', alignItems: 'center', flexDirection: 'row', gap: 8 },
  primaryDisabled: { opacity: 0.45 }, primaryText: { color: colors.greenOn, fontSize: 16, fontWeight: '700' },
});
