import React, { useRef, useState, useEffect } from 'react';
import { View, Text, TextInput, Pressable, Alert, ActivityIndicator } from 'react-native';
import { JourneySource, journeyAPI, journeyToday, isJourneyDate, locateJourneyCity, assertJourneySession } from '../../services/journey';
import { journeyStyles as s } from './styles';

export default function JourneyEditor({ source, timezone, revision, onSaved, onClose, onReload }: {
  source: JourneySource; timezone: string; revision: number; onSaved: () => void; onClose: () => void; onReload: () => void;
}) {
  const [city, setCity] = useState(source.place?.city || '');
  const [date, setDate] = useState(source.place?.local_date || source.suggested_date);
  const [origin, setOrigin] = useState<'manual' | 'device'>(source.place?.location_source || 'manual');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const lock = useRef(false);
  useEffect(() => () => { mounted.current = false; generation.current += 1; }, []);
  const today = journeyToday();
  const changeDate = (next: string) => {
    generation.current += 1;
    lock.current = false;
    setBusy(false);
    setDate(next);
    if (origin === 'device') setCity('');
    setOrigin('manual');
  };
  const locate = () => Alert.alert('为这条记录添加城市', '仅在本次点击后获取当前位置，并将城市保存为足迹。系统地理编码可能访问地图服务；不会上传经纬度或修改天气城市。', [
    { text: '手动填写', style: 'cancel' },
    { text: '同意并定位一次', onPress: async () => {
      if (lock.current || !mounted.current) return;
      lock.current = true; setBusy(true); setError('');
      const ticket = ++generation.current;
      try {
        assertJourneySession(revision);
        const result = await locateJourneyCity(true, date, journeyToday(), () => {
          assertJourneySession(revision);
          if (!mounted.current || ticket !== generation.current) throw new Error('定位已取消');
        });
        if (ticket !== generation.current) return;
        assertJourneySession(revision);
        setCity(result); setOrigin('device');
      } catch { if (ticket === generation.current) setError('未能获取城市。可以检查系统权限后重试，或直接手动填写。'); }
      finally { if (ticket === generation.current) { lock.current = false; setBusy(false); } }
    } },
  ]);
  const save = async () => {
    if (lock.current || conflict) return;
    if (!isJourneyDate(date) || !city.trim() || city.trim().length > 80) { setError('请填写有效日期及城市（最多 80 字）。'); return; }
    if (origin === 'device' && date !== journeyToday()) { setError('历史日期不能使用当前位置，请手动填写城市。'); return; }
    lock.current = true; setBusy(true); setError('');
    const ticket = ++generation.current;
    try {
      await journeyAPI.save(source, { city: city.trim(), local_date: date, timezone, location_source: origin, expected_version: source.place?.version || 0, confirmed: true }, revision);
      assertJourneySession(revision);
      if (ticket === generation.current) onSaved();
    } catch (failure: any) {
      if (ticket !== generation.current) return;
      const stale = failure?.response?.status === 409;
      setConflict(stale);
      setError(stale ? '记录已被修改，草稿仍在。请重新读取最新记录后再编辑；不会覆盖其他修改。' : '保存失败，草稿已保留，请重试。');
    } finally { if (ticket === generation.current) { lock.current = false; setBusy(false); } }
  };
  return <View style={s.card}>
    <Text style={s.heading}>给这个片段一个地点</Text>
    <Text style={s.body}>{source.title}</Text>
    {source.date_basis === 'message' && <Text style={s.note}>建议日期来自消息发送时间，不是照片拍摄时间。请核对真实发生日期。</Text>}
    <Text style={s.label}>发生日期 · YYYY-MM-DD</Text>
    <TextInput accessibilityLabel="发生日期" editable={!busy} value={date} onChangeText={changeDate} style={s.input} autoCapitalize="none" />
    <Text style={s.label}>城市 · 请勿填写住址、酒店或具体地址</Text>
    <TextInput accessibilityLabel="城市" editable={!busy} value={city} maxLength={80} onChangeText={value => { setCity(value); setOrigin('manual'); }} style={s.input} placeholder="例如：成都" />
    <Text style={s.note}>时区：{timezone}。地点仅关联这条记录；撤回定位权限不会删除已保存足迹。</Text>
    <Pressable accessibilityRole="button" disabled={date !== today || busy} style={[s.secondary, date !== today && s.disabled]} onPress={locate}><Text style={s.link}>{date === today ? '使用当前位置 · 单次定位' : '历史记录请手动填写城市'}</Text></Pressable>
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {conflict && <Pressable style={s.secondary} onPress={() => Alert.alert('重新读取？', '当前未保存草稿将放弃。', [{ text: '保留草稿', style: 'cancel' }, { text: '重新读取', onPress: onReload }])}><Text style={s.link}>重新读取最新记录</Text></Pressable>}
    <View style={s.row}>
      <Pressable style={s.secondary} onPress={onClose}><Text style={s.link}>取消</Text></Pressable>
      <Pressable style={[s.button, (busy || conflict) && s.disabled]} onPress={save} disabled={busy || conflict}>{busy ? <ActivityIndicator /> : <Text style={s.buttonText}>确认日期与城市，保存</Text>}</Pressable>
    </View>
  </View>;
}
