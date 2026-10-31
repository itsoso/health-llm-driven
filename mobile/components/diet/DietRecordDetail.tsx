import React, { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';

import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../constants/revaTheme';
import { BASE_URL } from '../../services/api';
import { dietRecordImageUrls, type DietRecord } from '../../services/diet';
import { buildChatImageSource, type ChatImageSource } from '../../utils/chatImageSource';
import { formatDisplayNumber } from '../../utils/displayNumber';

const MEAL_LABEL = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };
const NUTRIENTS = [
  { key: 'protein', label: '蛋白质' },
  { key: 'carbs', label: '碳水' },
  { key: 'fat', label: '脂肪' },
  { key: 'fiber', label: '膳食纤维' },
] as const;

export type DietRecordDetailProps = {
  record: DietRecord;
  authToken: string;
  visible?: boolean;
  onDismiss?: () => void;
  onClose: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onShare: () => void;
  onReview: () => void;
};

function photoSource(uri: string, authToken: string): ChatImageSource | undefined {
  try {
    const origin = new URL(BASE_URL).origin;
    const resolved = new URL(uri, origin);
    // Private record photos belong to our API. Never attach a bearer token to
    // an arbitrary host merely because its path looks like an upload route.
    if (resolved.origin !== origin || !/^https?:$/.test(resolved.protocol)
      || resolved.username || resolved.password) return undefined;
    return buildChatImageSource(resolved.href, authToken);
  } catch {
    // Invalid/untrusted URLs render an explicit unavailable state below.
    return undefined;
  }
}

function DetailPhoto({ source, index }: { source?: ChatImageSource; index: number }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { setFailed(false); }, [source?.uri, source?.headers?.Authorization]);
  if (!source) return <View style={styles.photoUnavailable}><Text style={styles.hint}>照片暂不可用</Text></View>;
  return (
    <View style={styles.photoFrame}>
      {failed ? (
        <View style={styles.photoUnavailable}>
          <Text style={styles.hint}>照片加载失败</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`重新加载照片 ${index + 1}`}
            style={styles.retry}
            onPress={() => { setFailed(false); setAttempt(value => value + 1); }}
          >
            <Text style={styles.secondaryActionText}>重试</Text>
          </Pressable>
        </View>
      ) : (
        <Image
          key={attempt}
          testID={`diet-detail-photo-${index}`}
          source={source}
          style={styles.photo}
          contentFit="contain"
          accessibilityLabel={`饮食照片 ${index + 1}`}
          onError={() => setFailed(true)}
        />
      )}
    </View>
  );
}

function Metric({ label, value, unit, name, prominent = false }: {
  label: string; value: number | null; unit: string; name: string; prominent?: boolean;
}) {
  const valid = typeof value === 'number' && Number.isFinite(value) && value >= 0;
  return (
    <View testID={`diet-detail-${name}`} style={prominent ? styles.energy : styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <View style={styles.metricValueRow}>
        <Text style={valid ? (prominent ? styles.energyValue : styles.metricValue) : styles.missing}>
          {valid ? formatDisplayNumber(value) : '未记录'}
        </Text>
        {valid ? <Text style={styles.unit}>{unit}</Text> : null}
      </View>
    </View>
  );
}

export default function DietRecordDetail({ record, authToken, visible = true, onDismiss, onClose, onEdit, onDelete, onShare, onReview }: DietRecordDetailProps) {
  const photos = dietRecordImageUrls(record);
  const photoEstimate = record.source === 'photo' || record.ai_recognized === 1;
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose} onDismiss={onDismiss}>
      <SafeAreaView testID="diet-record-detail" style={styles.screen} edges={['top', 'bottom']}>
        <View style={styles.header}>
          <View>
            <Text accessibilityRole="header" style={styles.title}>饮食详情</Text>
            <Text style={styles.date}>{record.record_date} · {MEAL_LABEL[record.meal_type] ?? record.meal_type}</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="关闭饮食详情" onPress={onClose} style={styles.close}>
            <Ionicons name="close" size={22} color={C.ink2} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {photos.map((uri, index) => (
            <View key={uri}>
              <DetailPhoto source={photoSource(uri, authToken)} index={index} />
              {photos.length > 1 ? <Text style={styles.photoCount}>照片 {index + 1} / {photos.length}</Text> : null}
            </View>
          ))}
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>食物与份量</Text>
            <Text style={styles.food}>{record.food_items}</Text>
          </View>
          <View style={styles.card}>
            <Metric name="calories" label="热量" value={record.calories} unit="kcal" prominent />
            <View style={styles.metrics}>
              {NUTRIENTS.map(({ key, label }) => <Metric key={key} name={key} label={label} value={record[key]} unit="g" />)}
            </View>
            {photoEstimate ? <Text style={styles.hint}>照片识别的营养为估算值，可修改食物或份量进行核对。</Text> : null}
          </View>
          {record.notes?.trim() ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>备注</Text>
              <Text style={styles.food}>{record.notes}</Text>
            </View>
          ) : null}
          <Pressable accessibilityRole="button" accessibilityLabel="修改食物或份量" onPress={onEdit} style={styles.primaryAction}>
            <Ionicons name="create-outline" size={20} color={C.greenOn} />
            <Text style={styles.primaryActionText}>修改食物或份量</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="复盘当天饮食" onPress={onReview} style={styles.reviewAction}>
            <Ionicons name="chatbubble-ellipses-outline" size={21} color={C.green600} />
            <View style={styles.reviewCopy}>
              <Text style={styles.secondaryActionText}>复盘当天饮食</Text>
              <Text style={styles.hint}>跟小气候聊聊这一天的饮食与下一餐</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={C.green600} />
          </Pressable>
          <View style={styles.secondaryActions}>
            <Pressable accessibilityRole="button" accessibilityLabel="分享这餐" onPress={onShare} style={styles.secondaryAction}>
              <Ionicons name="share-outline" size={18} color={C.green600} />
              <Text style={styles.secondaryActionText}>分享这餐</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="删除这条记录" onPress={onDelete} style={styles.secondaryAction}>
              <Ionicons name="trash-outline" size={18} color={revaSemantic.risk.fg} />
              <Text style={styles.deleteText}>删除这条记录</Text>
            </Pressable>
          </View>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 16 },
  title: { fontFamily: revaFonts.sans, fontSize: 22, fontWeight: '700', color: C.ink1 },
  date: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, marginTop: 5 },
  close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: C.paper2, borderRadius: revaRadii.pill },
  content: { paddingHorizontal: 20, paddingBottom: 24, gap: 14 },
  photoFrame: { backgroundColor: C.paper2, borderRadius: revaRadii.lg, overflow: 'hidden' },
  photo: { width: '100%', aspectRatio: 4 / 3 },
  photoUnavailable: { minHeight: 140, justifyContent: 'center', alignItems: 'center', backgroundColor: C.paper2, borderRadius: revaRadii.lg },
  photoCount: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, textAlign: 'right', marginTop: 6 },
  retry: { minHeight: 44, minWidth: 80, justifyContent: 'center', alignItems: 'center' },
  card: { backgroundColor: C.surface, borderRadius: revaRadii.lg, padding: 18, gap: 12 },
  sectionTitle: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, fontWeight: '600' },
  food: { fontFamily: revaFonts.sans, fontSize: 16, lineHeight: 25, color: C.ink1 },
  energy: { gap: 4, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  metric: { width: '46%', gap: 4 },
  metricLabel: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2 },
  metricValueRow: { flexDirection: 'row', alignItems: 'baseline', flexWrap: 'wrap', gap: 5 },
  energyValue: { fontFamily: revaFonts.mono, fontSize: 32, color: C.ink1 },
  metricValue: { fontFamily: revaFonts.mono, fontSize: 21, color: C.ink1 },
  unit: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3 },
  missing: { fontFamily: revaFonts.sans, fontSize: 15, color: C.ink3 },
  hint: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 19, color: C.ink2 },
  primaryAction: { minHeight: 50, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: C.green500, borderRadius: revaRadii.md },
  primaryActionText: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.greenOn },
  reviewAction: { minHeight: 68, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.green50, borderRadius: revaRadii.md },
  reviewCopy: { flex: 1, gap: 4 },
  secondaryActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  secondaryAction: { flex: 1, minHeight: 48, padding: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: C.surface, borderRadius: revaRadii.md },
  secondaryActionText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.green600 },
  deleteText: { fontFamily: revaFonts.sans, fontSize: 14, color: revaSemantic.risk.fg },
});
