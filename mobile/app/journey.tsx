import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, Pressable, ScrollView, ActivityIndicator, Alert, Modal } from 'react-native';
import { Stack, router, useFocusEffect } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../hooks/useAuth';
import { revaColors as C } from '../constants/revaTheme';
import { JourneyKind, JourneyPlace, JourneySource, JourneyExportSelection, journeyAPI, journeyToday, journeySessionRevision, assertJourneySession, shiftJourneyMonth, exportSelection, JOURNEY_LABELS } from '../services/journey';
import JourneyConstellation from '../components/journey/JourneyConstellation';
import JourneyEditor from '../components/journey/JourneyEditor';
import JourneyExportPanel from '../components/journey/JourneyExportPanel';
import { journeyStyles as s } from '../components/journey/styles';
import JourneyThumbnail from '../components/journey/JourneyThumbnail';

export default function JourneyScreen() {
  const { user, token } = useAuth();
  if (!user || !token) return <View style={s.screen}><Text style={s.body}>请先登录，再查看自己的足迹。</Text></View>;
  // A new authentication token remounts the whole private page and its cleanup scopes.
  return <JourneyContent key={`${user.id}:${journeySessionRevision()}`} token={token} />;
}

function JourneyContent({ token }: { token: string }) {
  const [revision] = useState(journeySessionRevision);
  const [timezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai');
  const [month, setMonth] = useState(() => journeyToday().slice(0, 7));
  const [places, setPlaces] = useState<JourneyPlace[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<JourneyKind>('diet');
  const [sources, setSources] = useState<JourneySource[]>([]);
  const [sourceTotal, setSourceTotal] = useState(0);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [editor, setEditor] = useState<JourneySource | null>(null);
  const [selected, setSelected] = useState<Record<number, string[]>>({});
  const [exportItems, setExportItems] = useState<JourneyExportSelection[] | null>(null);
  const generation = useRef(0);
  const sourceGeneration = useRef(0);
  const mounted = useRef(true);
  const monthLock = useRef(false);
  const sourceLock = useRef(false);
  const mutationLock = useRef(false);
  const reloadOnFocus = useRef<() => void>(() => {});
  const valid = () => { assertJourneySession(revision); if (!mounted.current) throw new Error('页面已关闭'); };
  useEffect(() => () => { mounted.current = false; generation.current += 1; sourceGeneration.current += 1; }, []);
  const load = async (append = false) => {
    if (append && monthLock.current) return;
    monthLock.current = true;
    const ticket = ++generation.current;
    setBusy(true); setError('');
    try {
      valid();
      const page = await journeyAPI.month(month, append ? places.length : 0, revision);
      valid(); if (ticket !== generation.current) return;
      setPlaces(previous => append ? [...previous, ...page.items.filter(item => !previous.some(old => old.id === item.id))] : page.items);
      setTotal(page.total);
    } catch { if (mounted.current && ticket === generation.current) setError('暂时无法加载足迹，请重试。'); }
    finally { if (mounted.current && ticket === generation.current) { monthLock.current = false; setBusy(false); } }
  };
  const loadSources = async (append = false) => {
    if (append && sourceLock.current) return;
    sourceLock.current = true;
    const ticket = ++sourceGeneration.current;
    setSourceBusy(true); setSourceError('');
    try {
      valid();
      const page = await journeyAPI.sources(kind, month, timezone, append ? sources.length : 0, revision);
      valid(); if (ticket !== sourceGeneration.current) return;
      setSources(previous => append ? [...previous, ...page.items.filter(item => !previous.some(old => old.source_id === item.source_id))] : page.items);
      setSourceTotal(page.total);
    } catch { if (mounted.current && ticket === sourceGeneration.current) setSourceError('记录未能加载，请检查网络后重试。'); }
    finally { if (mounted.current && ticket === sourceGeneration.current) { sourceLock.current = false; setSourceBusy(false); } }
  };
  reloadOnFocus.current = () => { void load(); if (adding) void loadSources(); };
  useFocusEffect(useCallback(() => {
    mounted.current = true;
    reloadOnFocus.current();
    return () => {
      mounted.current = false; generation.current += 1; sourceGeneration.current += 1;
      monthLock.current = false; sourceLock.current = false;
      setBusy(false); setSourceBusy(false); setEditor(null); setExportItems(null);
    };
  }, []));
  useEffect(() => {
    setPlaces([]); setTotal(0); setSelected({}); setExportItems(null); setEditor(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);
  useEffect(() => {
    sourceGeneration.current += 1; setSources([]); setSourceTotal(0); setEditor(null);
    if (adding) void loadSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, month, adding]);
  const switchMonth = (delta: number) => {
    generation.current += 1; sourceGeneration.current += 1;
    setExportItems(null); setEditor(null); setSelected({});
    setMonth(value => shiftJourneyMonth(value, delta));
  };
  const toggle = (place: JourneyPlace) => {
    setExportItems(null);
    setSelected(previous => {
      const next = { ...previous };
      if (Object.prototype.hasOwnProperty.call(next, place.id)) delete next[place.id];
      else if (Object.keys(next).length < 30) next[place.id] = [];
      else Alert.alert('每次最多选择 30 个片段', '请取消一些选择后继续。');
      return next;
    });
  };
  const remove = (place: JourneyPlace) => Alert.alert('删除这条地点？', '只删除足迹地点，不删除原记录。已分享或存入相册的图片无法撤回。', [
    { text: '取消', style: 'cancel' }, { text: '删除地点', style: 'destructive', onPress: async () => {
      if (mutationLock.current) return;
      mutationLock.current = true;
      try {
        valid(); await journeyAPI.remove(place, revision); valid();
        setExportItems(null); setSelected({}); await load();
      } catch (failure: any) {
        if (mounted.current) { setExportItems(null); setSelected({}); setError(failure?.response?.status === 409 ? '该地点已被修改，请刷新并核对最新内容后再删除。' : '删除未完成，请刷新后重试。'); }
      } finally { mutationLock.current = false; }
    } },
  ]);
  const editPlace = (place: JourneyPlace) => {
    setEditor({ kind: place.kind, source_id: place.source_id, title: place.title, suggested_date: place.local_date, date_basis: place.kind === 'chat_photo' ? 'message' : 'record', images: place.images, image_status: place.image_status, place });
    setExportItems(null);
  };
  const closeEditor = () => setEditor(null);
  const count = Object.keys(selected).length;
  return <SafeAreaView style={s.screen} edges={['bottom']}>
    <Stack.Screen options={{ title: '这一路', headerStyle: { backgroundColor: C.paper }, headerTintColor: C.ink1 }} />
    <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
      <View style={s.between}>
        <Pressable onPress={() => switchMonth(-1)} accessibilityLabel="上个月" style={s.secondary}><Text style={s.link}>←</Text></Pressable>
        <Text style={s.heading}>{month}</Text>
        <Pressable onPress={() => switchMonth(1)} accessibilityLabel="下个月" style={s.secondary}><Text style={s.link}>→</Text></Pressable>
      </View>
      <JourneyConstellation month={month} cities={[...new Set(places.map(place => place.city))]} count={places.length} partial />
      <Text style={s.note}>共 {total} 个片段 · 已加载 {places.length} 个。城市来自你确认的记录地点，不是连续定位轨迹。</Text>
      <View style={s.row}><Pressable style={s.button} onPress={() => setAdding(value => !value)}><Text style={s.buttonText}>{adding ? '收起记录选择' : '＋ 为记录添加地点'}</Text></Pressable><Pressable style={s.secondary} disabled={busy} onPress={() => { setSelected({}); setExportItems(null); void load(); }}><Text style={s.link}>刷新</Text></Pressable></View>
      {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
      {busy && <ActivityIndicator />}
      {!busy && !error && !total && <View style={s.card}><Text style={s.heading}>这一页，等你留下风景。</Text><Text style={s.body}>选一条饮食、生活片段或聊天照片，添加城市。不开定位，也可以开始。</Text></View>}
      {adding && <View style={s.card}>
        <Text style={s.heading}>从已有记录开始</Text>
        <View style={s.row}>{(Object.keys(JOURNEY_LABELS) as JourneyKind[]).map(tab => <Pressable key={tab} onPress={() => setKind(tab)} style={[s.secondary, kind === tab && s.selected]} accessibilityRole="tab" accessibilityState={{ selected: kind === tab }}><Text style={s.link}>{JOURNEY_LABELS[tab]}</Text></Pressable>)}</View>
        <Text style={s.note}>按所选月份查找原记录；添加时可核对并更正发生日期。</Text>
        {sourceBusy && <ActivityIndicator />}
        {!!sourceError && <><Text style={s.error}>{sourceError}</Text><Pressable onPress={() => loadSources()}><Text style={s.link}>重试读取记录</Text></Pressable></>}
        {sources.map(source => <Pressable key={`${source.kind}:${source.source_id}`} disabled={source.kind === 'chat_photo' && source.image_status !== 'ready'} style={s.card} onPress={() => setEditor(source)}>
          <Text style={s.body}>{source.title}</Text><Text style={s.note}>{source.suggested_date} · {source.place ? `已添加：${source.place.city} · 点击编辑` : '添加城市'}</Text>
          {source.date_basis === 'message' && <Text style={s.note}>日期为消息时间，请核对照片实际日期</Text>}
          {source.image_status === 'unavailable' && <Text style={s.error}>照片不可用{source.kind === 'chat_photo' ? '，暂不能添加' : '，仍可无图添加地点'}</Text>}
        </Pressable>)}
        <Text style={s.note}>已加载 {sources.length} / {sourceTotal} 条原记录</Text>
        {sources.length < sourceTotal && <Pressable disabled={sourceBusy} onPress={() => loadSources(true)} style={s.secondary}><Text style={s.link}>加载更多记录（剩余 {sourceTotal - sources.length}）</Text></Pressable>}
        {!sourceBusy && !sourceError && !sourceTotal && <Text style={s.note}>本月还没有这类记录。</Text>}
        <Pressable onPress={() => router.navigate('/(tabs)/chat')} style={s.secondary}><Text style={s.link}>去聊天拍照或记录新片段 →</Text></Pressable>
      </View>}
      <Text style={s.heading}>我的月度片段</Text>
      <Text style={s.note}>分享默认不选任何片段或照片。仅选中的内容进入预览，不含下面的记录原文。</Text>
      {places.map(place => {
        const checked = Object.prototype.hasOwnProperty.call(selected, place.id);
        return <View key={place.id} style={[s.card, checked && s.selected]}>
          <Pressable onPress={() => toggle(place)} accessibilityRole="checkbox" accessibilityState={{ checked }} accessibilityLabel={`选择片段 ${place.local_date} ${place.city}`}>
            <Text style={s.note}>{place.local_date} · {JOURNEY_LABELS[place.kind]} · {checked ? '已选分享' : '不分享'}</Text><Text style={s.heading}>{place.city}</Text>
          </Pressable>
          <Text style={s.body}>{place.title}</Text>
          {place.image_status === 'unavailable' && <Text style={s.error}>原照片暂不可用，可只分享城市和日期。</Text>}
          {checked && place.images.length > 0 && <View style={{ gap: 10 }}><Text style={s.note}>照片需单独选择；请先检查其中的隐私。</Text>{place.images.map((image, index) => <Pressable key={image.key} style={s.secondary} accessibilityRole="checkbox" accessibilityState={{ checked: selected[place.id].includes(image.key) }} onPress={() => { setExportItems(null); setSelected(previous => ({ ...previous, [place.id]: previous[place.id].includes(image.key) ? previous[place.id].filter(key => key !== image.key) : [...previous[place.id], image.key] })); }}><JourneyThumbnail image={image} token={token} /><Text style={s.link}>{selected[place.id].includes(image.key) ? '☑' : '□'} 照片 {index + 1}</Text></Pressable>)}</View>}
          <View style={s.row}><Pressable onPress={() => editPlace(place)}><Text style={s.link}>编辑城市与日期</Text></Pressable><Pressable onPress={() => remove(place)}><Text style={s.note}>删除地点</Text></Pressable></View>
        </View>;
      })}
      {places.length < total && <Pressable disabled={busy} style={s.secondary} onPress={() => load(true)}><Text style={s.link}>加载更多片段（剩余 {total - places.length}）</Text></Pressable>}
      <Pressable disabled={!count} style={[s.button, !count && s.disabled]} onPress={() => { try { valid(); setExportItems(exportSelection(places, selected)); } catch { setError('无法创建预览，请重新登录或减少选择。'); } }}><Text style={s.buttonText}>预览我的长图 · 已选 {count} / 30</Text></Pressable>
    </ScrollView>
    <Modal visible={!!editor} animationType="slide" onRequestClose={closeEditor}>
      <SafeAreaView style={s.screen}><ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">{editor && <JourneyEditor key={`${editor.kind}:${editor.source_id}:${editor.place?.version || 0}`} source={editor} timezone={timezone} revision={revision} onClose={closeEditor} onSaved={() => { setEditor(null); setSelected({}); void load(); if (adding) void loadSources(); }} onReload={() => { setEditor(null); setSelected({}); void load(); if (adding) void loadSources(); }} />}</ScrollView></SafeAreaView>
    </Modal>
    <Modal visible={!!exportItems} animationType="slide" onRequestClose={() => setExportItems(null)}><SafeAreaView style={s.screen}><ScrollView contentContainerStyle={[s.content, { paddingHorizontal: 0 }]}>{exportItems && <JourneyExportPanel selection={exportItems} token={token} revision={revision} onClose={() => setExportItems(null)} />}</ScrollView></SafeAreaView></Modal>
  </SafeAreaView>;
}
