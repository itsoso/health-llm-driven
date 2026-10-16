import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useAuth } from '../../hooks/useAuth';
import { subscribeAuthSessionChange } from '../../services/api';
import { type SupplementSnapshot } from '../../services/supplementQuickCheckin';
import { archiveSupplementGroup, confirmSupplementGroup, loadSupplementGroups, saveSupplementGroup, type SupplementGroup, type SupplementGroupCatalog } from '../../services/supplementGroups';
import { revaColors as c, revaSemantic } from '../../constants/revaTheme';

type Props = { snapshot: SupplementSnapshot; disabled?: boolean; onBusyChange: (busy: boolean) => void; onRecorded: () => void; onUncertain?: () => void };
export default function SupplementGroupsPanel({ snapshot, disabled = false, onBusyChange, onRecorded, onUncertain }: Props) {
  const { user, token } = useAuth();
  const [catalog, setCatalog] = useState<SupplementGroupCatalog | null>(null);
  const [opened, setOpened] = useState<number | null>(null);
  const [editing, setEditing] = useState<SupplementGroup | 'new' | null>(null);
  const [name, setName] = useState('');
  const [members, setMembers] = useState<number[]>([]);
  const [archivePrompt, setArchivePrompt] = useState(false);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState(false);
  const [authChanged, setAuthChanged] = useState(false);
  const live = useRef(true), invalidAuth = useRef(false), operation = useRef(false), epoch = useRef(0);
  const busyCallback = useRef(onBusyChange); busyCallback.current = onBusyChange;
  const identity = `${user?.id ?? ''}:${token ?? ''}`;
  const identityRef = useRef(identity);
  if (identityRef.current !== identity) { invalidAuth.current = true; identityRef.current = identity; epoch.current += 1; }
  const scope = `${snapshot.userId}:${snapshot.date}:${snapshot.timezone}`;
  const scopeRef = useRef(scope);
  if (scopeRef.current !== scope) { epoch.current += 1; scopeRef.current = scope; }
  const guardFor = () => { const generation = epoch.current; return () => live.current && !invalidAuth.current && generation === epoch.current; };
  const load = useCallback(async () => {
    if (operation.current || invalidAuth.current) return;
    const generation = epoch.current;
    const current = () => live.current && !invalidAuth.current && generation === epoch.current;
    setLoading(true); setError(false);
    try {
      if (!token || user?.id !== snapshot.userId) throw new Error('supplement_group_auth_required');
      const next = await loadSupplementGroups(current);
      if (!current()) return;
      if (next.record_date !== snapshot.date || next.timezone !== snapshot.timezone) throw new Error('supplement_group_day_changed');
      setCatalog(next);
    } catch { if (current()) { setError(true); setCatalog(null); setMessage('暂时无法核对组合，请刷新或重新打开弹窗'); } }
    finally { if (current()) setLoading(false); }
  }, [token, user?.id, snapshot.userId, snapshot.date, snapshot.timezone]);
  useEffect(() => {
    live.current = true;
    setOpened(null); setEditing(null); setMembers([]); setArchivePrompt(false);
    const unsubscribe = subscribeAuthSessionChange(() => {
      invalidAuth.current = true; epoch.current += 1; setCatalog(null); setOpened(null); setEditing(null); setName(''); setMembers([]); setAuthChanged(true);
      operation.current = false; setBusy(false); busyCallback.current(false);
    });
    void load();
    return () => { live.current = false; epoch.current += 1; operation.current = false; busyCallback.current(false); unsubscribe(); };
  }, [load]);
  const beginEdit = (group: SupplementGroup | 'new') => {
    if (disabled || busy || unknown) return;
    setEditing(group); setOpened(null); setArchivePrompt(false); setMessage('');
    setName(group === 'new' ? '' : group.name);
    setMembers(group === 'new' ? [] : group.members.filter(m => m.available && snapshot.rows.some(r => r.supplement.id === m.supplement_id)).map(m => m.supplement_id));
  };
  const run = async (kind: 'confirm' | 'save' | 'archive', group?: SupplementGroup) => {
    if (disabled || operation.current || unknown || !catalog || invalidAuth.current) return;
    operation.current = true; setBusy(true); busyCallback.current(true); setMessage('');
    const current = guardFor();
    try {
      if (kind === 'confirm' && group) {
        const result = await confirmSupplementGroup(catalog, group, current);
        if (!current()) return;
        setCatalog(result.catalog); setOpened(null);
        const labels = { confirmed: '整组已记录', already: '该组合今天已有确认记录，保留首次确认内容', reconciled: '已核对，该组合今天已有确认记录', context_changed: '日期或组合内容已变化，请重新核对', uncertain: '结果尚未确认，请稍后核对；本次不会再次提交' };
        setMessage(labels[result.status]);
        if (result.status === 'uncertain') { setUnknown(true); onUncertain?.(); }
        onRecorded();
      } else {
        if (kind === 'save') await saveSupplementGroup(catalog, { name, supplement_ids: members }, current, editing === 'new' || editing === null ? undefined : editing);
        if (kind === 'archive' && group) await archiveSupplementGroup(catalog, group, current);
        if (!current()) return;
        setEditing(null); setArchivePrompt(false); setOpened(null);
        // Reload authoritative state; a refresh failure must not trigger a repeated mutation.
        const next = await loadSupplementGroups(current);
        if (!current()) return;
        setCatalog(next); setMessage(kind === 'save' ? '组合已保存，尚未记录服用' : '组合已归档，历史记录保留');
      }
    } catch (failure) {
      if (!current()) return;
      const stale = failure instanceof Error && failure.message === 'supplement_group_context_changed';
      if (!stale) { setUnknown(true); onUncertain?.(); }
      setOpened(null); setEditing(null); setArchivePrompt(false);
      setMessage(stale ? '日期或组合内容已变化，请重新核对' : '结果尚未确认，请稍后核对；本次不会再次提交');
      try { const next = await loadSupplementGroups(current); if (current()) setCatalog(next); }
      catch { if (current()) setError(true); }
    } finally { if (current()) { operation.current = false; setBusy(false); busyCallback.current(false); } }
  };
  if (authChanged || invalidAuth.current) return <Text style={s.caption}>登录状态已变化，请重新打开弹窗</Text>;
  const locked = disabled || busy || unknown || loading || error || (!!catalog && (catalog.record_date !== snapshot.date || catalog.timezone !== snapshot.timezone));
  const active = catalog?.groups.find(g => g.id === opened);
  return <View style={s.panel}>
    <View style={s.header}><Text style={s.title}>我的组合</Text><Pressable accessibilityRole="button" disabled={locked || (catalog?.groups.length ?? 0) >= 20} onPress={() => beginEdit('new')} style={s.smallButton}><Text style={[s.link, locked && s.dim]}>新建组合</Text></Pressable></View>
    <Text style={s.caption}>把常用补剂存成组合，每次核对后再确认已服。</Text>
    {loading && <ActivityIndicator color={c.green500} style={s.loader} />}
    {!!message && <Text accessibilityRole="alert" style={[s.message, (unknown || error) && s.warning]}>{message}</Text>}
    {busy && <Text style={s.caption}>正在核对并保存，请稍候…</Text>}
    {!loading && error && <Pressable disabled={busy} onPress={() => void load()} style={s.smallButton}><Text style={s.link}>刷新组合</Text></Pressable>}
    {!loading && !error && !editing && <View style={s.groups}>
      {catalog?.groups.length === 0 && <Text style={s.caption}>还没有组合，可以从已有清单中创建。</Text>}
      {catalog?.groups.map(group => <Pressable key={group.id} accessibilityRole="button" disabled={disabled || busy || unknown} onPress={() => { setOpened(opened === group.id ? null : group.id); setMessage(''); }} style={[s.group, opened === group.id && s.groupActive]}>
        <Text style={s.groupName}>{group.name}</Text><Text style={s.caption}>{group.members.length} 项{group.today_confirmation ? ' · 今日已确认' : ''}　›</Text>
      </Pressable>)}
    </View>}
    {active && !editing && !unknown && <View style={s.detail}>
      <Text style={s.subheading}>{active.today_confirmation ? '今日首次确认内容' : '核对本次已服的组合成员'}</Text>
      {active.today_confirmation && <Text style={s.caption}>{active.today_confirmation.name} · {active.today_confirmation.record_date}</Text>}
      {(active.today_confirmation?.members ?? active.members).map(m => <View key={m.supplement_id} style={s.member}><Text style={s.memberName}>{m.name}{'available' in m && !m.available ? '（已停用，需编辑）' : ''}</Text>{m.reference_dosage && <Text style={s.caption}>参考用量：{m.reference_dosage}</Text>}</View>)}
      <Text style={s.caption}>只记录已服状态，不将参考用量当作实际剂量。</Text>
      {active.today_confirmation ? <Text style={s.notice}>今日已确认；修改组合不会追加或改写这次记录。</Text> : <Pressable accessibilityRole="button" disabled={locked || active.members.some(m => !m.available)} onPress={() => void run('confirm', active)} style={[s.primary, (locked || active.members.some(m => !m.available)) && s.dim]}><Text style={s.primaryText}>确认整组已服 · {active.members.length} 项</Text></Pressable>}
      <Pressable disabled={locked} onPress={() => beginEdit(active)} style={s.smallButton}><Text style={s.link}>编辑组合</Text></Pressable>
    </View>}
    {editing && <View style={s.detail}>
      <Text style={s.subheading}>{editing === 'new' ? '新建组合' : '编辑组合'}</Text>
      <TextInput accessibilityLabel="组合名称" placeholder="例如：早餐后" value={name} maxLength={60} onChangeText={setName} editable={!locked} style={s.input} />
      <Text style={s.caption}>选择组合成员，保存不会记录服用。</Text>
      {snapshot.rows.length === 0 && <Text style={s.caption}>请先在对话中添加补剂清单。</Text>}
      {snapshot.rows.map(row => <Pressable key={row.supplement.id} accessibilityRole="checkbox" accessibilityLabel={`组合成员：${row.supplement.name}`} accessibilityState={{ checked: members.includes(row.supplement.id), disabled: locked }} disabled={locked} onPress={() => setMembers(ids => ids.includes(row.supplement.id) ? ids.filter(id => id !== row.supplement.id) : ids.length < 30 ? [...ids, row.supplement.id] : ids)} style={s.editorRow}>
        <Text style={[s.check, members.includes(row.supplement.id) && s.checked]}>{members.includes(row.supplement.id) ? '✓' : ''}</Text><Text style={s.memberName}>{row.supplement.name}</Text>
      </Pressable>)}
      <Pressable accessibilityRole="button" disabled={locked || !name.trim() || !members.length} onPress={() => void run('save')} style={[s.primary, (locked || !name.trim() || !members.length) && s.dim]}><Text style={s.primaryText}>保存组合，不记录服用</Text></Pressable>
      <View style={s.actions}><Pressable disabled={busy} onPress={() => { setEditing(null); setArchivePrompt(false); }} style={s.smallButton}><Text style={s.link}>取消编辑</Text></Pressable>{editing !== 'new' && <Pressable disabled={locked} onPress={() => setArchivePrompt(true)} style={s.smallButton}><Text style={s.caption}>归档组合</Text></Pressable>}</View>
      {archivePrompt && editing !== 'new' && <View style={s.archive}><Text style={s.caption}>归档后不再显示这个组合，已确认的历史记录会保留。</Text><Pressable disabled={locked} onPress={() => void run('archive', editing)} style={s.smallButton}><Text style={s.link}>确认归档</Text></Pressable></View>}
    </View>}
  </View>;
}
const s = StyleSheet.create({
  panel: { borderWidth: 1, borderColor: c.line, borderRadius: 18, backgroundColor: c.surface2, padding: 14, marginBottom: 10, gap: 10 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }, title: { fontSize: 17, fontWeight: '700', color: c.ink1 },
  caption: { fontSize: 12, lineHeight: 19, color: c.ink2 }, smallButton: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 4 }, link: { fontSize: 14, fontWeight: '600', color: c.green600 },
  groups: { gap: 8 }, group: { backgroundColor: c.surface, borderWidth: 1, borderColor: c.line, borderRadius: 12, padding: 12, gap: 3 }, groupActive: { borderColor: c.green500, backgroundColor: c.green50 }, groupName: { color: c.ink1, fontSize: 15, fontWeight: '600' },
  detail: { borderTopWidth: StyleSheet.hairlineWidth, borderColor: c.line, paddingTop: 12, gap: 12 }, subheading: { color: c.ink1, fontSize: 14, fontWeight: '600' }, member: { gap: 3 }, memberName: { color: c.ink1, fontSize: 14, lineHeight: 21, flexShrink: 1 },
  input: { minHeight: 44, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: c.lineStrong, color: c.ink1, backgroundColor: c.surface, fontSize: 15 },
  editorRow: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 10 }, check: { width: 23, height: 23, textAlign: 'center', lineHeight: 21, borderRadius: 6, borderWidth: 1, borderColor: c.lineStrong, color: c.greenOn }, checked: { backgroundColor: c.green500, borderColor: c.green500 },
  primary: { minHeight: 48, borderRadius: 12, backgroundColor: c.green500, alignItems: 'center', justifyContent: 'center', padding: 12 }, primaryText: { color: c.greenOn, fontWeight: '600', fontSize: 14 }, dim: { opacity: 0.45 },
  message: { color: c.green700, backgroundColor: c.green50, padding: 10, borderRadius: 10, fontSize: 13, lineHeight: 20 }, warning: { color: revaSemantic.caution.fg, backgroundColor: revaSemantic.caution.bg }, notice: { color: c.green700, fontSize: 13, lineHeight: 20 },
  loader: { padding: 12 }, actions: { flexDirection: 'row', justifyContent: 'space-between' }, archive: { padding: 10, backgroundColor: c.paper2, borderRadius: 10 },
});
