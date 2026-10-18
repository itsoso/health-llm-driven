import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Stack, router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { useAuth } from '../hooks/useAuth';
import { getAuthSessionSnapshot } from '../services/api';
import { dailyJourneyAPI, type DailyJourneyReview, type DailyJourneySession, type JourneyMode } from '../services/dailyJourney';
import { dailyJourneyCapture, type DailyJourneyCaptureSnapshot } from '../services/dailyJourneyCapture';
import { hasDailyJourneyNativeCapability } from '../config/releaseCapabilities';
import { journeyStyles as s } from '../components/journey/styles';
import { revaColors as C } from '../constants/revaTheme';

const MODES: Record<JourneyMode, string> = { unknown: '交通方式待确认', walking: '步行', cycling: '骑行', vehicle: '乘车' };
const STATUS: Record<string, string> = { idle: '尚未开始', starting: '正在准备定位', active: '正在记录', paused: '本机已暂停', ended: '记录已结束', interrupted: '采集已中断' };
function today() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
function shiftDate(value: string, days: number) {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
function time(value: string | undefined | null, zone: string) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return '时间未提供';
  try { return new Intl.DateTimeFormat('zh-CN', { timeZone: zone, hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)); }
  catch { return '时间不可用'; }
}
function expiryTime(value: string, zone: string) {
  try {
    return new Intl.DateTimeFormat('zh-CN', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
  } catch { return '到期时间不可用'; }
}
function Button({ text, onPress, disabled = false, secondary = false, label }: {
  text: string; onPress: () => void; disabled?: boolean; secondary?: boolean; label?: string;
}) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label ?? text} accessibilityState={{ disabled }} disabled={disabled}
    style={[secondary ? s.secondary : s.button, { minHeight: 44, justifyContent: 'center' }, disabled && s.disabled]} onPress={onPress}>
    <Text style={secondary ? s.link : s.buttonText}>{text}</Text>
  </Pressable>;
}
function Header() {
  return <View style={[s.between, styles.header]}>
    <Button text="← 返回" label="返回上一页" secondary onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)/chat')} />
    <Text style={s.heading}>一天的行程</Text><Text style={s.note}>私人记录</Text>
  </View>;
}

export default function DailyJourneyScreen() {
  const { user, token } = useAuth();
  const generation = getAuthSessionSnapshot().generation;
  if (!user || !token) return <SafeAreaView style={s.screen}><Header /><Text style={[s.body, { padding: 20 }]}>请先登录，再查看自己的行程。</Text></SafeAreaView>;
  return <DailyJourneyContent key={`${user.id}:${generation}`} token={token} generation={generation} />;
}

type Editor = { id: string; kind: 'stop' | 'segment'; label: string; mode: JourneyMode };
function DailyJourneyContent({ token, generation }: { token: string; generation: number }) {
  const [snapshot, setSnapshot] = useState<DailyJourneyCaptureSnapshot>({ status: 'idle', session: null, pendingCount: 0, offline: false, error: null });
  const [date, setDate] = useState(today);
  const [sessions, setSessions] = useState<DailyJourneySession[]>([]);
  const [review, setReview] = useState<DailyJourneyReview | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [disclosure, setDisclosure] = useState(false);
  const [retentionDays, setRetentionDays] = useState<1 | 7>(7);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const actionLock = useRef(false);
  const readTicket = useRef(0);
  const reviewTicket = useRef(0);
  const captureReady = useRef(false);
  const nativeReady = hasDailyJourneyNativeCapability();
  const current = useCallback(() => {
    const auth = getAuthSessionSnapshot();
    return mounted.current && auth.generation === generation && auth.token === token;
  }, [generation, token]);
  const load = useCallback(async () => {
    const ticket = ++readTicket.current;
    if (!current()) return;
    setLoading(true);
    try {
      const result = await dailyJourneyAPI.list(date, token);
      if (current() && ticket === readTicket.current) setSessions(result.items);
    } catch {
      if (current() && ticket === readTicket.current) setError('暂时无法读取行程，请刷新重试。');
    } finally { if (current() && ticket === readTicket.current) setLoading(false); }
  }, [current, date, token]);
  useEffect(() => {
    mounted.current = true;
    const unsubscribe = dailyJourneyCapture.subscribe(() => { if (current() && captureReady.current) setSnapshot(dailyJourneyCapture.getSnapshot()); });
    void dailyJourneyCapture.initialize().then(() => {
      if (current()) { captureReady.current = true; setSnapshot(dailyJourneyCapture.getSnapshot()); }
    }).catch(() => { if (current()) setError('未能恢复本机采集状态，请重新打开此页面。'); });
    return () => { mounted.current = false; captureReady.current = false; readTicket.current += 1; reviewTicket.current += 1; unsubscribe(); };
  }, [current]);
  useEffect(() => {
    setSessions([]); setReview(null); setEditor(null); setError(''); reviewTicket.current += 1;
    void load();
  }, [load]);

  const act = async (operation: () => Promise<unknown>, failure = '操作未完成，请检查状态后重试。') => {
    if (actionLock.current || !current()) return;
    actionLock.current = true; setBusy(true); setError('');
    try {
      await operation();
      if (!current()) return;
      setSnapshot(dailyJourneyCapture.getSnapshot());
      await load();
    } catch { if (current()) setError(failure); }
    finally { actionLock.current = false; if (current()) setBusy(false); }
  };
  const openReview = async (session: DailyJourneySession) => {
    if (!current() || actionLock.current) return;
    const ticket = ++reviewTicket.current;
    setReview(null); setEditor(null); setError('');
    try {
      const result = await dailyJourneyAPI.review(session.id, token);
      if (current() && ticket === reviewTicket.current) setReview(result);
    } catch { if (current() && ticket === reviewTicket.current) setError('暂时无法读取复盘，行程可能已过保留期限，请刷新重试。'); }
  };
  const remove = (session: DailyJourneySession) => {
    if (!current() || actionLock.current) return;
    Alert.alert('删除这条行程？', '将停止该行程的采集，并删除本机和云端轨迹、停留及复盘。删除后无法恢复。', [
      { text: '取消', style: 'cancel' },
      { text: '删除行程', style: 'destructive', onPress: () => act(async () => {
        await dailyJourneyCapture.remove(session.id);
        if (!current()) return;
        const afterDelete = dailyJourneyCapture.getSnapshot();
        if (afterDelete.offline && afterDelete.session?.id === session.id) throw new Error('delete_sync_pending');
        reviewTicket.current += 1; setReview(null); setEditor(null);
      }, '删除未完成，请检查网络后重试，当前记录尚未确认删除。') },
    ]);
  };
  const saveAnnotation = () => {
    if (!editor || !review || !current()) return;
    const selected = editor; const selectedReview = review;
    if ([...selected.label.trim()].length > 80) { setError('地点或路线名称最多 80 字。'); return; }
    void act(async () => {
      await dailyJourneyAPI.annotate(selectedReview.session.id, {
        expected_version: selectedReview.session.version,
        annotations: [{ target_id: selected.id, label: selected.label.trim(), ...(selected.kind === 'segment' ? { mode: selected.mode } : {}) }],
      }, token);
      if (!current()) return;
      const updated = await dailyJourneyAPI.review(selectedReview.session.id, token);
      if (!current()) return;
      setReview(updated); setEditor(null);
    }, '更正未保存，行程状态可能已变化，请刷新复盘后重试。');
  };
  const hasOpenSession = snapshot.status === 'starting' || (Boolean(snapshot.session) && ['active', 'paused', 'interrupted'].includes(snapshot.status));
  const pending = snapshot.pendingCount > 0 || snapshot.offline || Boolean(snapshot.error);
  const changeDate = (delta: number) => {
    if (busy) return;
    readTicket.current += 1; reviewTicket.current += 1;
    setReview(null); setEditor(null); setDate(value => shiftDate(value, delta));
  };

  return <SafeAreaView style={s.screen} edges={['top', 'bottom']}>
    <Stack.Screen options={{ title: '一天的行程', headerShown: false }} /><Header />
    <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
      <View style={s.card}>
        <Text style={s.label}>今天 · {today()}</Text>
        <Text style={s.heading}>{STATUS[snapshot.status] ?? '采集状态待确认'}</Text>
        <Text style={s.body}>把走过的路，留给自己。</Text>
        <Text style={s.note}>主动开启后记录路线与停留，系统调度和信号可能造成缺失。不会推断健康状况。</Text>
        {!nativeReady && <Text style={s.note}>请安装支持后台定位的新版本 iOS 应用后开始记录；已有行程仍可查看和删除。</Text>}
        {nativeReady && !hasOpenSession && !disclosure && <Button text="记录今天行程" disabled={busy || !captureReady.current} onPress={() => setDisclosure(true)} />}
        {disclosure && <View style={styles.disclosure}>
          <Text style={s.body}>同意本次记录</Text>
          <Text style={s.note}>精确位置用于记录今天的路线、停留与估算里程；轨迹加密暂存本机并同步私人云端，仅本人可见。不会自动发送给 AI 或用于健康推断。</Text>
          <Text style={s.note}>锁屏和切换应用时仍会尝试采集。可随时暂停、结束或删除；今天结束后不保存新的位置，次日需要再次主动开启。</Text>
          <Text style={s.label}>轨迹与复盘保留期限</Text>
          <View style={s.row}>{([1, 7] as const).map(days => <Pressable key={days} accessibilityRole="radio" accessibilityState={{ selected: retentionDays === days }}
            disabled={busy} style={[s.secondary, retentionDays === days && s.selected]} onPress={() => setRetentionDays(days)}><Text style={s.link}>{days} 天{days === 7 ? '（默认）' : ''}</Text></Pressable>)}</View>
          <Button text="同意并开始记录" disabled={busy || !nativeReady || !captureReady.current} onPress={() => { void act(async () => {
            if (!hasDailyJourneyNativeCapability()) throw new Error('native_capability_unavailable');
            await dailyJourneyCapture.start({ retentionDays, consent: true });
            if (current()) setDisclosure(false);
          }, '未能开始记录，请检查定位授权和网络，再重试。'); }} />
          <Button text="暂不开启" secondary disabled={busy} onPress={() => setDisclosure(false)} />
        </View>}
        {hasOpenSession && <View style={s.row}>
          {snapshot.status === 'active' && <Button text="暂停记录" disabled={busy} onPress={() => { void act(() => dailyJourneyCapture.pause()); }} />}
          {nativeReady && ['paused', 'interrupted'].includes(snapshot.status) && <Button text="继续记录" disabled={busy} onPress={() => { void act(() => dailyJourneyCapture.resume()); }} />}
          {snapshot.status !== 'starting' && <Button text="结束今天记录" secondary disabled={busy} onPress={() => { void act(() => dailyJourneyCapture.end()); }} />}
        </View>}
        {!!snapshot.error && <Text accessibilityRole="alert" style={s.error}>{snapshot.error}</Text>}
        {snapshot.pendingCount > 0 && <Text style={s.note}>本机待同步：{snapshot.pendingCount} 个定位点</Text>}
        {pending && <View style={{ gap: 10 }}><Text style={s.note}>存在尚未同步的变更。当前本机状态不代表云端已确认，恢复网络后可重试。</Text>
          <Button text="重试同步" secondary disabled={busy} onPress={() => { void act(() => dailyJourneyCapture.flush()); }} /></View>}
      </View>
      {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
      {busy && <ActivityIndicator accessibilityLabel="正在处理行程" />}
      <View style={s.between}>
        <Button text="←" label="前一天" secondary disabled={busy} onPress={() => changeDate(-1)} />
        <Text style={s.heading}>{date}</Text>
        <Button text="→" label="后一天" secondary disabled={busy || date >= today()} onPress={() => changeDate(1)} />
      </View>
      <View style={s.between}><Text style={s.label}>当天的记录</Text><Button text="刷新行程" secondary disabled={busy || loading} onPress={() => { setError(''); void load(); }} /></View>
      {loading && <ActivityIndicator accessibilityLabel="正在读取行程" />}
      {!loading && !sessions.length && <View style={s.card}><Text style={s.body}>这一天暂无可查看的行程。</Text><Text style={s.note}>未开启记录、尚未同步或超过保留期限的轨迹不会显示。</Text></View>}
      {sessions.map(session => <View key={session.id} style={s.card}>
        <Text style={s.body}>{time(session.started_at, session.timezone)} — {session.ended_at ? time(session.ended_at, session.timezone) : '尚未结束'}</Text>
        <Text style={s.note}>{session.timezone} · {session.status === 'ended' ? '已结束' : session.status === 'paused' ? '云端已暂停' : '云端记录中'}</Text>
        <Text style={s.note}>到期时间：{expiryTime(session.expires_at, session.timezone)} · {session.retention_days} 天保留</Text>
        <View style={s.row}><Button text="查看复盘" secondary disabled={busy} onPress={() => { void openReview(session); }} />
          <Button text="删除行程" label={`删除行程 ${session.id}`} secondary disabled={busy} onPress={() => remove(session)} /></View>
      </View>)}
      {review && <View style={{ gap: 16 }}>
        <View style={s.card}><Text style={s.heading}>这段路的复盘</Text><Text style={s.body}>估算里程 {review.summary.distance_display}</Text>
          <Text style={s.body}>有效观测 {review.summary.observed_display}</Text><Text style={s.note}>{review.summary.note}</Text>
          <Text style={s.note}>时间按 {review.session.timezone} 显示；停留和交通方式来自定位估计，可自行更正。</Text></View>
        <JourneyMap review={review} />
        {review.gaps.map((gap, index) => <View key={`${gap.started_at}:${index}`} style={s.card}><Text style={s.body}>{gap.reason === 'pause' ? '暂停记录' : '定位中断'} · {time(gap.started_at, review.session.timezone)} — {time(gap.ended_at, review.session.timezone)}</Text><Text style={s.note}>这段时间未形成连续轨迹，不推断经过路线或停留。</Text></View>)}
        {review.segments.map(segment => <View key={segment.id} style={s.card}>
          <Text style={s.body}>{segment.label || '一段路线'}</Text><Text style={s.body}>{MODES[segment.mode]}（{segment.mode_source === 'user' ? '你已更正' : '估计'}）</Text>
          <Text style={s.note}>{time(segment.started_at, review.session.timezone)} — {time(segment.ended_at, review.session.timezone)} · {segment.distance_display}</Text>
          <Button text="更正路线与交通方式" secondary disabled={busy} onPress={() => setEditor({ id: segment.id, kind: 'segment', label: segment.label ?? '', mode: segment.mode })} />
        </View>)}
        {review.stops.map((stop, index) => <View key={stop.id} style={s.card}>
          <Text style={s.body}>{stop.label || `停留地点 ${index + 1}`}</Text><Text style={s.note}>{time(stop.started_at, review.session.timezone)} — {time(stop.ended_at, review.session.timezone)} · 估计停留 {stop.duration_display}</Text>
          <Button text="为停留地点命名" secondary disabled={busy} onPress={() => setEditor({ id: stop.id, kind: 'stop', label: stop.label ?? '', mode: 'unknown' })} />
        </View>)}
        {editor && <View style={s.card}><Text style={s.heading}>{editor.kind === 'stop' ? '地点名称' : '更正路线'}</Text>
          <TextInput accessibilityLabel="地点或路线名称" style={s.input} value={editor.label} maxLength={80} placeholder="输入你确认的名称（最多 80 字）" editable={!busy} onChangeText={label => setEditor({ ...editor, label })} />
          {editor.kind === 'segment' && <View style={s.row}>{(Object.keys(MODES) as JourneyMode[]).map(mode => <Pressable key={mode} accessibilityRole="radio" accessibilityState={{ selected: editor.mode === mode }} disabled={busy} onPress={() => setEditor({ ...editor, mode })} style={[s.secondary, editor.mode === mode && s.selected]}><Text style={s.link}>{MODES[mode]}</Text></Pressable>)}</View>}
          <Button text="保存更正" disabled={busy} onPress={saveAnnotation} /><Button text="取消更正" secondary disabled={busy} onPress={() => setEditor(null)} />
        </View>}
      </View>}
    </ScrollView>
  </SafeAreaView>;
}

function JourneyMap({ review }: { review: DailyJourneyReview }) {
  if (Platform.OS !== 'ios' || !review.points.length) return <View style={s.card}><Text style={s.note}>暂无可绘制的连续轨迹；可查看下方记录。</Text></View>;
  const points = new Map(review.points.map(point => [point.id, point]));
  const first = review.points[0];
  const bounds = review.points.reduce((value, point) => ({
    minLat: Math.min(value.minLat, point.latitude), maxLat: Math.max(value.maxLat, point.latitude),
    minLon: Math.min(value.minLon, point.longitude), maxLon: Math.max(value.maxLon, point.longitude),
  }), { minLat: first.latitude, maxLat: first.latitude, minLon: first.longitude, maxLon: first.longitude });
  return <View style={styles.mapContainer}><MapView testID="journey-review-map" style={styles.map} showsUserLocation={false} showsMyLocationButton={false}
    initialRegion={{ latitude: (bounds.minLat + bounds.maxLat) / 2, longitude: (bounds.minLon + bounds.maxLon) / 2, latitudeDelta: Math.min(180, Math.max(0.008, (bounds.maxLat - bounds.minLat) * 1.3)), longitudeDelta: Math.min(360, Math.max(0.008, (bounds.maxLon - bounds.minLon) * 1.3)) }}>
    {review.segments.map(segment => {
      const coordinates = segment.point_ids.flatMap(id => { const point = points.get(id); return point ? [{ latitude: point.latitude, longitude: point.longitude }] : []; });
      return coordinates.length === segment.point_ids.length && coordinates.length >= 2 ? <Polyline key={segment.id} testID={`journey-line-${segment.id}`} coordinates={coordinates} strokeColor={C.green500} strokeWidth={4} /> : null;
    })}
    {review.stops.map((stop, index) => <Marker key={stop.id} coordinate={{ latitude: stop.latitude, longitude: stop.longitude }} title={stop.label || `停留地点 ${index + 1}`} />)}
  </MapView><Text style={[s.note, { padding: 12 }]}>仅绘制有效连续片段；断档不连线。地图不请求当前位置。</Text></View>;
}
const styles = StyleSheet.create({
  header: { paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.line },
  disclosure: { gap: 12, paddingTop: 8 },
  mapContainer: { overflow: 'hidden', borderRadius: 20, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line },
  map: { height: 260, width: '100%' },
});
