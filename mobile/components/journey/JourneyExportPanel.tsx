import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, Pressable, Image, ActivityIndicator, Alert, Platform, PixelRatio } from 'react-native';
import { captureRef, releaseCapture } from 'react-native-view-shot';
import * as MediaLibrary from 'expo-media-library';
import { APP_DISPLAY_NAME } from '../../constants/brand';
import { revaColors as C } from '../../constants/revaTheme';
import { materializeImageForLocalUse, shareLongImage, shareImage } from '../../utils/share';
import { assertJourneySession, JourneyExport, JourneyExportSelection, journeyAPI, journeyImageSource, JOURNEY_LABELS, JOURNEY_MAX_HEIGHT, JOURNEY_WIDTH } from '../../services/journey';
import JourneyConstellation from './JourneyConstellation';
import { journeyStyles as s } from './styles';
import { journeyCaptureGeometry } from './captureOptions';

const signature = (data: JourneyExport) => JSON.stringify({ month: data.month, items: data.items.map(item => ({ city: item.city, local_date: item.local_date, kind: item.kind, images: item.images.map(image => image.key) })) });

/** Private titles never enter this component: only the server export projection. */
export default function JourneyExportPanel({ selection, token, revision, onClose }: {
  selection: JourneyExportSelection[]; token: string; revision: number; onClose: () => void;
}) {
  const [preview, setPreview] = useState<JourneyExport | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [height, setHeight] = useState(0);
  const outputWidth = JOURNEY_WIDTH * 2;
  const outputHeight = Math.round(height * (outputWidth / JOURNEY_WIDTH));
  const generation = useRef(0);
  const lock = useRef(false);
  const cleanup = useRef<Array<() => Promise<void>>>([]);
  const expectedSignature = useRef('');
  const loaded = useRef(new Set<string>());
  const target = useRef<View>(null);
  const captureUri = useRef<string | null>(null);
  const cleanupFiles = async () => {
    if (captureUri.current) { releaseCapture(captureUri.current); captureUri.current = null; }
    const work = cleanup.current.splice(0);
    const results = await Promise.allSettled(work.map(remove => remove()));
    if (results.some(result => result.status === 'rejected')) {
      // No URLs, owner identifiers, filenames, or tokens in diagnostics.
      console.warn('[journey] temporary artifact cleanup failed');
      return false;
    }
    return true;
  };
  const active = (ticket: number) => {
    assertJourneySession(revision);
    if (ticket !== generation.current) throw new Error('预览已关闭');
  };
  const prepare = async () => {
    const ticket = ++generation.current;
    lock.current = true; setBusy(true); setError(''); setReady(false); setPreview(null); loaded.current.clear();
    try {
      if (!(await cleanupFiles())) throw new Error('临时图片未能清理，请关闭页面后重试');
      active(ticket);
      const response = await journeyAPI.preview(selection, revision);
      active(ticket);
      const imageCount = response.items.reduce((count, item) => count + item.images.length, 0);
      if (imageCount > 30 || response.items.length * 150 + imageCount * 210 + 500 > JOURNEY_MAX_HEIGHT / 2) throw new Error('长图过长，请减少片段或照片后重试');
      expectedSignature.current = signature(response);
      const local: JourneyExport = { month: response.month, items: [] };
      // Sequential materialization bounds memory/network and makes late cleanup explicit.
      for (const item of response.items) {
        const images = [];
        for (const image of item.images) {
          active(ticket);
          const source = journeyImageSource(image.url, token);
          const file = await materializeImageForLocalUse(source.uri, { headers: source.headers });
          try { active(ticket); } catch (failure) { await file.cleanup(); throw failure; }
          cleanup.current.push(file.cleanup);
          images.push({ key: image.key, url: file.uri });
        }
        local.items.push({ city: item.city, local_date: item.local_date, kind: item.kind, images });
      }
      active(ticket);
      setPreview(local); setReady(imageCount === 0);
    } catch (failure: any) {
      await cleanupFiles();
      if (ticket === generation.current) setError(failure?.response?.status === 409 ? '内容或照片已变化，请关闭预览并重新选择。' : (failure instanceof Error && !failure.message.includes('status code') ? failure.message : '无法生成预览，请重试。'));
    } finally { if (ticket === generation.current) { lock.current = false; setBusy(false); } }
  };
  useEffect(() => {
    void prepare();
    return () => { generation.current += 1; void cleanupFiles(); };
    // Selection is frozen at mount; changing selection unmounts this component.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const finish = async (destination: 'save' | 'more' | 'wechat' | 'xiaohongshu') => {
    if (lock.current || !preview || !ready || !outputHeight) return;
    const ticket = generation.current;
    lock.current = true; setBusy(true); setError('');
    try {
      active(ticket);
      const geometry = journeyCaptureGeometry(height, Platform.OS, PixelRatio.get());
      if (!geometry.withinBounds) throw new Error('长图过长，请减少片段或照片');
      if (destination === 'save') {
        const permission = await MediaLibrary.requestPermissionsAsync(true);
        active(ticket);
        if (!permission.granted) throw new Error('未获得相册写入权限，可选择系统分享');
      }
      // Revalidate AFTER permission UI, immediately before materializing output.
      const current = await journeyAPI.preview(selection, revision);
      active(ticket);
      if (signature(current) !== expectedSignature.current) throw new Error('内容已变化，请关闭预览并重新选择');
      const uri = await captureRef(target, geometry.options);
      try { active(ticket); } catch (failure) { releaseCapture(uri); throw failure; }
      captureUri.current = uri;
      if (destination === 'save') {
        active(ticket);
        await MediaLibrary.saveToLibraryAsync(uri);
        active(ticket);
        Alert.alert('已保存到相册', '相册中的成品由你管理，应用内删除地点不会撤回已保存或分享的图片。');
      } else if (destination === 'more') {
        await shareImage(uri, { target: 'more', mimeType: 'image/png', beforeShare: () => active(ticket) });
      } else {
        await shareLongImage(uri, { target: destination, beforeShare: () => active(ticket) });
      }
      // Opening a system share sheet is not proof of receipt/publication.
    } catch (failure: any) {
      if (ticket === generation.current) {
        setError(failure?.response?.status === 409 || failure?.response?.status === 404 ? '片段或照片已变化，旧预览已失效，请重新选择。' : '导出未完成，旧预览已失效。请检查权限、网络或减少选择后重新预览。');
        setPreview(null); setReady(false); await cleanupFiles();
      }
    } finally {
      if (captureUri.current) { releaseCapture(captureUri.current); captureUri.current = null; }
      if (ticket === generation.current) { lock.current = false; setBusy(false); }
    }
  };
  const imageLoaded = (key: string) => {
    if (!preview) return;
    loaded.current.add(key);
    setReady(preview.items.every(item => item.images.every(image => loaded.current.has(image.key))));
  };
  return <View style={s.card}>
    <View style={s.between}><Text style={s.heading}>长图预览</Text><Pressable onPress={onClose} accessibilityLabel="关闭长图预览"><Text style={s.link}>关闭</Text></Pressable></View>
    <Text style={s.note}>只包含已选城市、日期、片段类型及照片。请检查城市输入和照片中的住址、人脸、票据等隐私。分享无法撤回。</Text>
    {preview && outputHeight > JOURNEY_MAX_HEIGHT && <Text style={s.error}>长图超出尺寸限制，请关闭并减少选择。</Text>}
    <View style={s.row}>{(['save', 'more', 'wechat', 'xiaohongshu'] as const).map(destination => <Pressable key={destination} disabled={busy || !ready || !preview || !outputHeight || outputHeight > JOURNEY_MAX_HEIGHT} style={[s.secondary, (busy || !ready || !preview || !outputHeight) && s.disabled]} onPress={() => finish(destination)}><Text style={s.link}>{{ save: '保存相册', more: '系统分享', wechat: '微信', xiaohongshu: '小红书' }[destination]}</Text></Pressable>)}</View>
    {busy && <ActivityIndicator accessibilityLabel="准备长图" />}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!preview && !busy && <Pressable style={s.secondary} onPress={prepare}><Text style={s.link}>重新校验并预览</Text></Pressable>}
    {preview && <ScrollView horizontal style={{ marginHorizontal: -18 }} contentContainerStyle={{ flexGrow: 1, justifyContent: 'center' }}><View ref={target} collapsable={false} onLayout={event => setHeight(event.nativeEvent.layout.height)} style={{ width: JOURNEY_WIDTH, backgroundColor: C.paper, padding: 16, gap: 16 }}>
      <JourneyConstellation month={preview.month} cities={[...new Set(preview.items.map(item => item.city))]} count={preview.items.length} />
      {preview.items.map((item, index) => <View key={index} style={s.card}>
        <Text style={s.note}>{item.local_date} · {JOURNEY_LABELS[item.kind]}</Text>
        <Text style={s.heading}>{item.city}</Text>
        {item.images.map(image => <Image key={image.key} source={{ uri: image.url }} style={{ width: '100%', height: 180, borderRadius: 12 }} resizeMode="contain" onLoad={() => imageLoaded(image.key)} onError={() => { setReady(false); setError('照片未能加载，不能导出。请重新预览，或关闭并取消选择该照片。'); }} />)}
      </View>)}
      <Text style={[s.note, { textAlign: 'center' }]}>{APP_DISPLAY_NAME} · 这一路{ '\n' }我的生活片段，不是实际行驶路线</Text>
    </View></ScrollView>}
  </View>;
}
