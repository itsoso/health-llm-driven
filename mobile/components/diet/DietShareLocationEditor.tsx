import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { revaColors as C } from '../../constants/revaTheme';
import { aiConsentRevision, subscribeAIConsentInvalidation } from '../../services/aiConsentState';
import { nearbyShareLocations, searchShareLocations, shareLocationErrorMessage, type SharePlaces } from '../../services/shareLocation';
import { DIET_SHARE_LOCATION_MAX_LENGTH, normalizeDietShareLocation } from './dietShareLocation';

type Props = { initialValue: string; recordDate?: string | null; onConfirm: (label: string) => void; onCancel: () => void };
function today() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }

/** Mounted only inside one composer editing session. No persisted consent or GPS. */
export function DietShareLocationEditor({ initialValue, recordDate, onConfirm, onCancel }: Props) {
  const [draft, setDraftState] = useState(initialValue);
  const latestDraft = useRef(initialValue);
  const [keyword, setKeyword] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [places, setPlaces] = useState<SharePlaces>({ items: [], suggested_id: null });
  const [hint, setHint] = useState('');
  const revision = useRef(aiConsentRevision()).current;
  const active = useRef(true);
  const foreground = useRef(AppState.currentState !== 'background');
  const permitted = useRef(false);
  const edited = useRef(Boolean(initialValue));
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const isToday = recordDate === today();

  function setDraft(value: string) { latestDraft.current = value; setDraftState(value); }
  function stop() { generation.current += 1; controller.current?.abort(); controller.current = null; }
  function alive() { return active.current && foreground.current && revision === aiConsentRevision(); }
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      // iOS's OS permission prompt briefly makes the app inactive. Do not
      // cancel that prompt; only a real background transition cancels work.
      if (state === 'background') {
        foreground.current = false; stop(); permitted.current = false;
        setConsent(false); setBusy(false); setPlaces({ items: [], suggested_id: null });
        setHint('已停止地点查询；继续查询需重新同意。手填仍可使用。');
      } else if (state === 'active') foreground.current = true;
    });
    const unsubscribe = subscribeAIConsentInvalidation(() => {
      active.current = false; stop(); setBusy(false); setConsent(false); permitted.current = false;
      setPlaces({ items: [], suggested_id: null }); setDraft(''); setKeyword('');
    });
    return () => { active.current = false; stop(); subscription.remove(); unsubscribe(); };
  }, []);

  async function lookup(mode: 'nearby' | 'search') {
    if (!alive() || !permitted.current) return;
    stop();
    const sequence = generation.current;
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError(''); setHint(''); setPlaces({ items: [], suggested_id: null });
    const assertActive = () => {
      if (!alive() || generation.current !== sequence || !permitted.current) throw new Error('share_location_cancelled');
    };
    const context = { consent: true, revision, signal: abort.signal, assertActive };
    try {
      const response = mode === 'nearby' ? await nearbyShareLocations(context) : await searchShareLocations(keyword, context);
      assertActive();
      setPlaces(response);
      const suggestion = response.items.find(item => item.id === response.suggested_id);
      if (mode === 'nearby' && suggestion && !edited.current) {
        setDraft(suggestion.label);
        setHint('已推荐附近地点，请核对。GPS 无法确定你具体在哪家店。');
      } else setHint(response.items.length ? '请选择实际地点；附近地点不代表你已到店。' : '未找到合适地点，可搜索城市＋店名或手动填写。');
    } catch (cause) {
      if (alive() && generation.current === sequence) setError(shareLocationErrorMessage(cause));
    } finally {
      if (active.current && generation.current === sequence) { setBusy(false); controller.current = null; }
    }
  }
  function edit(value: string) {
    stop(); edited.current = true; setBusy(false); setDraft(value); setHint('');
  }
  function allow() {
    if (!alive() || permitted.current) return;
    permitted.current = true; setConsent(true);
    if (isToday && !edited.current) void lookup('nearby');
  }
  function finish(confirm: boolean) {
    if (!alive() || (confirm && draft !== latestDraft.current)) return;
    stop(); active.current = false;
    if (confirm) onConfirm(normalizeDietShareLocation(draft)); else onCancel();
  }
  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      <Text style={styles.title}>分享地点（可选）</Text>
      <Text style={styles.help}>优先查找附近餐厅，确认后才公开到图片和文字。仅用于本次分享，不修改饮食记录或足迹。</Text>
      {!consent ? <View style={styles.notice}>
        <Text style={styles.label}>使用高德地点查询</Text>
        <Text style={styles.help}>同意后，小巴健康将经服务器向高德地图发送本次精确坐标（定位时）或搜索词（搜索时），用于查找地点。我们不保存这些查询内容。不授权也可手动填写，不会后台定位。</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="同意本次高德查询" onPress={allow} style={styles.primary}>
          <Text style={styles.primaryText}>{isToday && !edited.current ? '同意并查找当前位置' : '同意本次查询'}</Text>
        </Pressable>
      </View> : <View style={styles.notice}>
        <Text style={styles.label}>附近餐厅与地点 · 高德地图</Text>
        {!isToday && <Text style={styles.help}>这不是今天的记录或日期未知；当前位置不是这餐的历史位置，请核对后再使用。</Text>}
        <Pressable accessibilityRole="button" accessibilityLabel="使用当前位置查找餐厅" disabled={busy} onPress={() => { void lookup('nearby'); }} style={styles.secondary}>
          <Text style={styles.action}>{busy ? '正在查找…' : '使用当前位置查找餐厅'}</Text>
        </Pressable>
        <TextInput accessibilityLabel="搜索餐厅或地址" placeholder="城市＋餐厅、商场或地址" value={keyword} maxLength={80} style={styles.input}
          onChangeText={value => { stop(); setBusy(false); setKeyword(value); setPlaces({ items: [], suggested_id: null }); }}
          returnKeyType="search" onSubmitEditing={() => { void lookup('search'); }} />
        <Pressable accessibilityRole="button" accessibilityLabel="搜索地点" disabled={busy || !keyword.trim()} onPress={() => { void lookup('search'); }} style={styles.secondary}>
          <Text style={styles.action}>搜索地点</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="停止并撤回本次高德查询" onPress={() => {
          stop(); permitted.current = false; setConsent(false); setBusy(false); setError('');
          setPlaces({ items: [], suggested_id: null }); setKeyword('');
          if (!edited.current) setDraft('');
          setHint('本次查询授权已撤回。已发送的请求无法收回，仍可手动填写。');
        }} style={styles.secondary}><Text style={styles.action}>停止并撤回本次查询</Text></Pressable>
      </View>}
      {busy && <ActivityIndicator accessibilityLabel="正在查询地点" color={C.green600} />}
      {!!error && <Text accessibilityRole="alert" style={styles.help}>{error}</Text>}
      {!!hint && <Text style={styles.help}>{hint}</Text>}
      {places.items.map(item => <Pressable key={item.id} accessibilityRole="button" accessibilityLabel={`选择地点：${item.name}`} onPress={() => edit(item.label)} style={styles.candidate}>
        <Text style={styles.label}>{item.name}{draft === item.label ? ' ✓' : ''}</Text>
        {!!item.address && <Text style={styles.help}>{item.address}</Text>}
      </Pressable>)}
      <Text style={styles.label}>公开展示的地点（可手动修改）</Text>
      <TextInput accessibilityLabel="分享地点" placeholder="例如：杭州 · 湖边餐厅" placeholderTextColor={C.ink3} value={draft}
        onChangeText={edit} maxLength={DIET_SHARE_LOCATION_MAX_LENGTH} style={styles.input} returnKeyType="done" onSubmitEditing={() => finish(true)} />
      <Text style={styles.help}>默认只展示地点名称。不建议填写住址、房号；留空即不展示地点。</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="清除分享地点" onPress={() => edit('')} style={styles.secondary}><Text style={styles.action}>清除地点</Text></Pressable>
      <View style={styles.row}>
        <Pressable accessibilityRole="button" accessibilityLabel="取消地点编辑" onPress={() => finish(false)} style={[styles.secondary, styles.flex]}><Text style={styles.action}>取消</Text></Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="确认分享地点" onPress={() => finish(true)} style={[styles.primary, styles.flex]}><Text style={styles.primaryText}>确认展示</Text></Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 32, gap: 12 },
  title: { fontSize: 18, fontWeight: '800', color: C.ink1 },
  help: { fontSize: 13, lineHeight: 20, color: C.ink3 },
  label: { fontSize: 15, fontWeight: '600', color: C.ink1 },
  input: { width: '100%', minHeight: 48, borderWidth: 1, borderColor: C.line, borderRadius: 12, padding: 14, fontSize: 16, color: C.ink1, backgroundColor: C.surface2 },
  notice: { padding: 14, borderRadius: 16, backgroundColor: C.green50, gap: 12 },
  candidate: { padding: 14, borderRadius: 12, borderWidth: 1, borderColor: C.line, gap: 4 },
  primary: { minHeight: 48, padding: 14, alignItems: 'center', justifyContent: 'center', borderRadius: 14, backgroundColor: C.green600 },
  primaryText: { color: C.greenOn, fontWeight: '700', fontSize: 15 },
  secondary: { minHeight: 48, padding: 14, alignItems: 'center', justifyContent: 'center', borderRadius: 14, borderWidth: 1, borderColor: C.line },
  action: { color: C.green600, fontWeight: '700', fontSize: 15 },
  row: { flexDirection: 'row', gap: 12 }, flex: { flex: 1 },
});
