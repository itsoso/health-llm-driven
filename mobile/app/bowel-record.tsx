import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import { uuid } from 'expo-modules-core';
import { useAuth } from '../hooks/useAuth';
import { aiConsentRevision, subscribeAIConsentInvalidation } from '../services/aiConsentState';
import { bowelPhotoUrl, createBowelRecord, getBowelRecord, listBowelRecords, uploadBowelPhoto, type BowelRecord, type BowelSession } from '../services/excretion';
import { todayStr } from '../utils/dietDate';
import { revaColors as C, revaRadii, revaFonts } from '../constants/revaTheme';

const STOOLS = ['硬颗粒', '结块条状', '条状有裂纹', '光滑软条', '软块', '糊状', '水样'];
const COLORS = [['brown', '棕色'], ['yellow', '黄色'], ['green', '绿色'], ['black', '黑色'], ['red', '红色'], ['pale', '浅色']];
const localTime = () => `${String(new Date().getHours()).padStart(2, '0')}:${String(new Date().getMinutes()).padStart(2, '0')}`;
function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const parsed = new Date(y, m - 1, d);
  return parsed.getFullYear() === y && parsed.getMonth() === m - 1 && parsed.getDate() === d;
}

export default function BowelRecordScreen() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();
  const revision = useSyncExternalStore(subscribeAIConsentInvalidation, aiConsentRevision, aiConsentRevision);
  if (isLoading || !user || !token) return <SafeAreaView style={styles.safe}>
    <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="关闭排便记录"><Text style={styles.label}>关闭</Text></Pressable>
    <Text style={styles.label}>{isLoading ? '正在加载账号…' : '请登录后记录排便。'}</Text>
  </SafeAreaView>;
  return <BowelForm key={`${user.id}:${revision}`} session={{ owner: user.id, revision }} />;
}

function BowelForm({ session }: { session: BowelSession }) {
  const router = useRouter();
  const [date, setDate] = useState(todayStr);
  const [time, setTime] = useState(localTime);
  const [stool, setStool] = useState<number>();
  const [color, setColor] = useState<string>();
  const [blood, setBlood] = useState<boolean>();
  const [pain, setPain] = useState<number>();
  const [notes, setNotes] = useState('');
  const [photo, setPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const photoKey = useRef<string | undefined>(undefined);
  const requestId = useRef<string | undefined>(undefined);
  const active = useRef(true);
  const busy = useRef(false);
  const pickerBusy = useRef(false);
  const historyGeneration = useRef(0);
  const [saving, setSaving] = useState(false);
  const [picking, setPicking] = useState(false);
  const [message, setMessage] = useState('');
  const [records, setRecords] = useState<BowelRecord[]>([]);
  const [historyError, setHistoryError] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [visiblePhoto, setVisiblePhoto] = useState<{ id: number; url: string } | null>(null);
  const [loadingPhoto, setLoadingPhoto] = useState<number | null>(null);
  const current = () => active.current && session.revision === aiConsentRevision();
  useEffect(() => () => { active.current = false; photoKey.current = undefined; }, []);

  useEffect(() => {
    let live = true;
    const generation = ++historyGeneration.current;
    setRecords([]);
    setVisiblePhoto(null);
    setLoadingHistory(false);
    setHistoryError(false);
    if (!validDate(date)) return;
    setLoadingHistory(true);
    setHistoryError(false);
    listBowelRecords(session, date).then(result => {
      if (live && current() && generation === historyGeneration.current) setRecords(result);
    }).catch(() => {
      if (live && current() && generation === historyGeneration.current) setHistoryError(true);
    }).finally(() => { if (live && current() && generation === historyGeneration.current) setLoadingHistory(false); });
    return () => { live = false; };
  }, [date, session.owner, session.revision]);

  const pickPhoto = async (camera: boolean) => {
    if (busy.current || pickerBusy.current) return;
    pickerBusy.current = true;
    setPicking(true);
    try {
      if (camera) {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!current()) return;
        if (!permission.granted) { Alert.alert('相机未授权', '可在系统设置允许相机，或从相册选择照片。'); return; }
      }
      const result = camera
        ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7, exif: false })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7, exif: false, allowsMultipleSelection: false });
      if (!current() || result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      // Re-encode the pixels so location/EXIF data and original filenames are not uploaded.
      const sanitized = await ImageManipulator.manipulateAsync(asset.uri,
        asset.width > 1280 ? [{ resize: { width: 1280 } }] : [],
        { compress: 0.8, format: ImageManipulator.SaveFormat.JPEG });
      if (!current()) return;
      photoKey.current = undefined;
      setPhoto({ ...asset, uri: sanitized.uri, mimeType: 'image/jpeg', fileName: 'bowel.jpg' });
    } catch {
      if (current()) Alert.alert('照片未添加', '请重试拍照，或从相册选择照片。');
    } finally { pickerBusy.current = false; if (current()) setPicking(false); }
  };

  const save = async () => {
    if (busy.current || pickerBusy.current || !current()) return;
    if (!validDate(date) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) {
      setMessage('请填写有效日期和时间。'); return;
    }
    busy.current = true;
    setSaving(true);
    setMessage('');
    try {
      requestId.current ??= uuid.v4();
      if (photo && !photoKey.current) photoKey.current = await uploadBowelPhoto(session, photo);
      if (!current()) return;
      const record = await createBowelRecord(session, {
        type: 'bowel', record_date: date, record_time: `${time}:00`, stool_type: stool,
        color, blood_present: blood, pain_level: pain, notes: notes.trim() || undefined,
        photo_key: photoKey.current, client_request_id: requestId.current,
      });
      if (!current()) return;
      historyGeneration.current += 1;
      setLoadingHistory(false);
      setHistoryError(false);
      setRecords(existing => [record, ...existing.filter(item => item.id !== record.id)]);
      setMessage('排便记录已保存。');
      setPhoto(null); photoKey.current = undefined; requestId.current = undefined;
      setNotes(''); setStool(undefined); setColor(undefined); setBlood(undefined); setPain(undefined);
    } catch {
      if (current()) setMessage('保存未确认，内容已保留。请保持内容不变并重试。');
    } finally { busy.current = false; if (current()) setSaving(false); }
  };

  const showPhoto = async (id: number) => {
    if (loadingPhoto !== null) return;
    setLoadingPhoto(id);
    try {
      const record = await getBowelRecord(session, id);
      if (!current()) return;
      if (!record.photo_url || record.user_id !== session.owner) throw new Error('photo_unavailable');
      setVisiblePhoto({ id, url: bowelPhotoUrl(record.photo_url) });
    } catch { if (current()) Alert.alert('照片暂不可用', '请稍后重新查看。'); }
    finally { if (current()) setLoadingPhoto(null); }
  };

  const disabled = saving || picking;
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
    <View style={styles.header}>
      <Pressable onPress={() => router.back()} accessibilityLabel="关闭排便记录" accessibilityRole="button"><Text style={styles.link}>关闭</Text></Pressable>
      <Text style={styles.title}>排便记录</Text>
    </View>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
      <Text style={styles.label}>时间</Text>
      <View style={styles.row}>
        <TextInput accessibilityLabel="排便日期" style={[styles.input, styles.flex]} value={date} onChangeText={setDate} editable={!disabled} placeholder="YYYY-MM-DD" />
        <TextInput accessibilityLabel="排便时间" style={[styles.input, styles.flex]} value={time} onChangeText={setTime} editable={!disabled} placeholder="HH:MM" />
      </View>
      <Text style={styles.label}>形态（可选，Bristol 分类）</Text>
      <View style={styles.choices}>{STOOLS.map((label, index) => <Choice key={label} label={`${index + 1}型 · ${label}`} selected={stool === index + 1} disabled={disabled} onPress={() => setStool(stool === index + 1 ? undefined : index + 1)} />)}</View>
      <Text style={styles.label}>颜色（可选）</Text>
      <View style={styles.choices}>{COLORS.map(([value, label]) => <Choice key={value} label={label} selected={color === value} disabled={disabled} onPress={() => setColor(color === value ? undefined : value)} />)}</View>
      <Text style={styles.label}>是否见血</Text>
      <View style={styles.choices}>{[['未观察', undefined], ['未见血', false], ['见血', true]].map(([label, value]) => <Choice key={String(label)} label={String(label)} selected={blood === value} disabled={disabled} onPress={() => setBlood(value as boolean | undefined)} />)}</View>
      <Text style={styles.label}>疼痛（可选）</Text>
      <View style={styles.choices}>{[0, 1, 2, 3, 4, 5].map(value => <Choice key={value} label={value === 0 ? '0 · 无痛' : `${value}分`} selected={pain === value} disabled={disabled} onPress={() => setPain(pain === value ? undefined : value)} />)}</View>
      <Text style={styles.label}>备注（可选）</Text>
      <TextInput accessibilityLabel="排便备注" style={styles.input} value={notes} onChangeText={setNotes} editable={!disabled} multiline maxLength={500} placeholder="补充自己的观察" />
      <Text style={styles.label}>照片（可选）</Text>
      <Text style={styles.hint}>仅作为私人记录，点击保存后上传；不进行自动诊断。</Text>
      <View style={styles.row}>
        <Choice label="拍照" selected={false} disabled={disabled} onPress={() => void pickPhoto(true)} />
        <Choice label="从相册选择" selected={false} disabled={disabled} onPress={() => void pickPhoto(false)} />
      </View>
      {picking ? <ActivityIndicator accessibilityLabel="正在选择照片" /> : null}
      {photo ? <View>
        <Image source={{ uri: photo.uri }} cachePolicy="none" style={styles.photo} accessibilityLabel="待保存的排便照片" />
        <Choice label="移除照片" selected={false} disabled={disabled} onPress={() => { setPhoto(null); photoKey.current = undefined; }} />
      </View> : null}
      {message ? <Text accessibilityRole="alert" style={styles.hint}>{message}</Text> : null}
      <Pressable accessibilityLabel="保存排便记录" accessibilityRole="button" disabled={disabled} onPress={() => void save()} style={[styles.save, disabled && styles.dim]}>
        <Text style={styles.saveText}>{saving ? '正在保存…' : '保存排便记录'}</Text>
      </Pressable>
      <Text style={styles.label}>当天记录</Text>
      {loadingHistory ? <ActivityIndicator /> : historyError ? <Text style={styles.hint}>历史记录暂不可用，请重新打开。</Text> : records.length === 0 ? <Text style={styles.hint}>当天还没有排便记录。</Text> : null}
      {records.map(record => <View key={record.id} style={styles.record}>
        <Text style={styles.label}>{record.record_date} {record.record_time?.slice(0, 5) || ''}</Text>
        <Text style={styles.hint}>{record.stool_type ? `${record.stool_type}型 · ${STOOLS[record.stool_type - 1]}` : '形态未填写'}{record.blood_present === true ? ' · 见血' : ''}</Text>
        {record.notes ? <Text style={styles.hint}>{record.notes}</Text> : null}
        {record.photo_unavailable ? <Text style={styles.hint}>关联照片暂不可用，排便记录已保留。</Text> : null}
        {record.photo_url ? <Choice label="查看照片" selected={false} disabled={loadingPhoto !== null} onPress={() => void showPhoto(record.id)} /> : null}
        {visiblePhoto?.id === record.id ? <View>
          <Image source={{ uri: visiblePhoto.url }} cachePolicy="none" style={styles.photo} accessibilityLabel="排便记录照片" onError={() => { setVisiblePhoto(null); Alert.alert('照片加载失败', '请重新点击查看照片。'); }} />
          <Choice label="收起照片" selected={false} onPress={() => setVisiblePhoto(null)} />
        </View> : null}
      </View>)}
    </ScrollView>
  </SafeAreaView>;
}

function Choice({ label, selected, disabled, onPress }: { label: string; selected: boolean; disabled?: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ selected, disabled: Boolean(disabled) }} disabled={disabled} onPress={onPress} style={[styles.choice, selected && styles.selected, disabled && styles.dim]}><Text style={styles.link}>{label}</Text></Pressable>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', gap: 20, padding: 18 },
  title: { fontFamily: revaFonts.sans, fontSize: 22, fontWeight: '700', color: C.ink1 },
  content: { padding: 18, gap: 12, paddingBottom: 32 },
  label: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1 },
  hint: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 22, color: C.ink3 },
  row: { flexDirection: 'row', gap: 10 },
  flex: { flex: 1 },
  input: { minHeight: 46, borderWidth: 1, borderColor: C.green100, borderRadius: revaRadii.md, padding: 12, color: C.ink1, backgroundColor: C.surface },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, paddingVertical: 8, borderRadius: revaRadii.md, backgroundColor: C.surface, borderWidth: 1, borderColor: C.green100 },
  selected: { backgroundColor: C.green50, borderColor: C.green600 },
  link: { fontFamily: revaFonts.sans, fontSize: 14, color: C.green700 },
  photo: { width: '100%', height: 220, borderRadius: revaRadii.md, marginVertical: 8 },
  save: { minHeight: 48, justifyContent: 'center', alignItems: 'center', borderRadius: revaRadii.md, backgroundColor: C.green600 },
  saveText: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '700', color: C.greenOn },
  dim: { opacity: 0.5 },
  record: { padding: 14, gap: 8, borderRadius: revaRadii.md, backgroundColor: C.surface },
});
