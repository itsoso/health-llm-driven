import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, shadows, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { InterventionDraft, InterventionMetricKey } from '../../services/interventionDraft';

interface Props {
  visible: boolean;
  draft: InterventionDraft | null;
  isSaving?: boolean;
  onClose: () => void;
  onSubmit: (draft: InterventionDraft) => void;
}

const METRICS: { key: InterventionMetricKey; label: string }[] = [
  { key: 'sleep_score', label: '睡眠' },
  { key: 'spo2_odi', label: '血氧' },
  { key: 'hrv', label: 'HRV' },
  { key: 'rhr', label: '心率' },
  { key: 'bp', label: '血压' },
  { key: 'weight', label: '体重' },
  { key: 'custom', label: '自定义' },
];

export default function InterventionDraftSheet({ visible, draft, isSaving, onClose, onSubmit }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [form, setForm] = useState<InterventionDraft | null>(draft);

  useEffect(() => {
    setForm(draft);
  }, [draft]);

  if (!form) return null;

  const sourceLabel = getSourceLabel(form.source_type);
  const summary = getPlanSummary(form.content, form.title);
  const metricLabel = getMetricLabel(form.metric_key);

  const update = (patch: Partial<InterventionDraft>) => {
    setForm(prev => prev ? { ...prev, ...patch } : prev);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <View style={{ flex: 1 }}>
              <Text style={txt.kicker}>从 AI 建议生成</Text>
              <Text style={txt.title}>加入今日计划</Text>
            </View>
            <Pressable style={styles.iconBtn} onPress={onClose} accessibilityRole="button" accessibilityLabel="关闭">
              <Ionicons name="close" size={18} color={c.labelSecondary} />
            </Pressable>
          </View>

          <ScrollView
            style={styles.content}
            contentContainerStyle={styles.contentInner}
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.sourceCard}>
              <View style={styles.sourceTopRow}>
                <View style={styles.sourcePill}>
                  <Ionicons name="sparkles" size={12} color={c.brand} />
                  <Text style={txt.sourcePill}>{sourceLabel}</Text>
                </View>
                <View style={styles.sourcePillMuted}>
                  <Ionicons name="calendar-outline" size={12} color={c.labelSecondary} />
                  <Text style={txt.sourcePillMuted}>今天执行</Text>
                </View>
              </View>
              <Text style={txt.sourceSummary} numberOfLines={3}>
                {summary}
              </Text>
            </View>

            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionIcon}>
                  <Ionicons name="flag-outline" size={15} color={c.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={txt.sectionTitle}>今日要做</Text>
                  <Text style={txt.sectionSub}>可以调整成你今天真的会执行的表述</Text>
                </View>
              </View>
              <TextInput
                accessibilityLabel="今日计划标题"
                style={styles.titleInput}
                value={form.title}
                onChangeText={title => update({ title })}
                placeholder="行动标题"
                placeholderTextColor={c.labelTertiary}
                multiline
              />
            </View>

            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionIcon}>
                  <Ionicons name="checkmark-done-outline" size={15} color={c.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={txt.sectionTitle}>执行检查项</Text>
                  <Text style={txt.sectionSub}>加入后会出现在今日计划里</Text>
                </View>
              </View>
              <View style={styles.checkList}>
                {form.checklist.slice(0, 4).map((item, index) => (
                  <View key={`${item.item}-${index}`} style={styles.checkRow}>
                    <View style={styles.checkIndex}>
                      <Text style={txt.checkIndex}>{index + 1}</Text>
                    </View>
                    <Text style={txt.checkText} numberOfLines={2}>{item.item}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <View style={styles.sectionIcon}>
                  <Ionicons name="analytics-outline" size={15} color={c.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={txt.sectionTitle}>如何验证</Text>
                  <Text style={txt.sectionSub}>让计划有复盘出口，而不是只添加一条待办</Text>
                </View>
              </View>
              <View style={styles.metricCurrent}>
                <Text style={txt.metricCurrentLabel}>跟踪指标</Text>
                <Text style={txt.metricCurrentValue}>{metricLabel}</Text>
              </View>
              <View style={styles.metricWrap}>
                {METRICS.map(metric => {
                  const active = form.metric_key === metric.key;
                  return (
                    <Pressable
                      key={metric.key}
                      style={[styles.metricChip, active && styles.metricChipActive]}
                      onPress={() => update({ metric_key: metric.key })}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                    >
                      <Text style={[txt.metricChip, active && txt.metricChipActive]}>{metric.label}</Text>
                    </Pressable>
                  );
                })}
              </View>

              <View style={styles.twoCol}>
                <View style={styles.col}>
                  <Text style={txt.fieldLabel}>基线</Text>
                  <TextInput
                    style={styles.input}
                    value={form.baseline_value || ''}
                    onChangeText={baseline_value => update({ baseline_value })}
                    placeholder="可选"
                    placeholderTextColor={c.labelTertiary}
                  />
                </View>
                <View style={styles.col}>
                  <Text style={txt.fieldLabel}>目标</Text>
                  <TextInput
                    style={styles.input}
                    value={form.target_value || ''}
                    onChangeText={target_value => update({ target_value })}
                    placeholder="可选"
                    placeholderTextColor={c.labelTertiary}
                  />
                </View>
              </View>

              <Text style={txt.fieldLabel}>复盘窗口</Text>
              <View style={styles.stepperRow}>
                {[1, 3, 7, 14].map(days => (
                  <Pressable
                    key={days}
                    style={[styles.dayBtn, form.verification_days === days && styles.dayBtnActive]}
                    onPress={() => update({ verification_days: days })}
                    accessibilityRole="button"
                    accessibilityState={{ selected: form.verification_days === days }}
                  >
                    <Text style={[txt.dayBtn, form.verification_days === days && txt.dayBtnActive]}>{days}天</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          </ScrollView>

          <Pressable
            style={({ pressed }) => [styles.submitBtn, pressed && !isSaving && styles.submitBtnPressed]}
            onPress={() => onSubmit(form)}
            disabled={isSaving}
            accessibilityRole="button"
            accessibilityLabel="确认加入今日计划"
          >
            {isSaving ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="add-circle" size={16} color="#fff" />}
            <Text style={txt.submit}>{isSaving ? '正在加入...' : '确认加入今日计划'}</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

function getSourceLabel(sourceType?: string): string {
  if (sourceType === 'sleep_spo2') return '来自血氧分析';
  if (sourceType === 'chat') return '来自阿衡建议';
  return '来自健康建议';
}

function getMetricLabel(key?: InterventionMetricKey): string {
  return METRICS.find(metric => metric.key === key)?.label || '自定义';
}

function getPlanSummary(content: string, title: string): string {
  const cleaned = content
    .split('\n')
    .map(line => line.replace(/^#{1,6}\s*/, '').replace(/^[-*]\s*/, '').trim())
    .filter(line => line && line !== title && !line.startsWith('复盘窗口'));
  return cleaned[0] || '将这条建议转成今天可执行、之后能复盘的健康计划。';
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    overlay: { flex: 1, justifyContent: 'flex-end' },
    backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.35)' },
    sheet: {
      maxHeight: '88%',
      backgroundColor: c.bgPrimary,
      borderTopLeftRadius: 22,
      borderTopRightRadius: 22,
      paddingHorizontal: spacing.lg,
      paddingTop: 8,
      paddingBottom: 24,
      gap: 12,
      ...shadows.heavy,
    },
    handle: { alignSelf: 'center', width: 38, height: 4, borderRadius: 2, backgroundColor: c.separator, marginBottom: 2 },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
    iconBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: c.bgCard, alignItems: 'center', justifyContent: 'center' },
    content: { marginHorizontal: -2 },
    contentInner: { gap: spacing.sm, paddingHorizontal: 2, paddingBottom: 2 },
    sourceCard: {
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      ...shadows.subtle,
    },
    sourceTopRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
    sourcePill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      borderRadius: radii.full,
      backgroundColor: c.brandLight,
      paddingHorizontal: 8,
      paddingVertical: 4,
    },
    sourcePillMuted: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      borderRadius: radii.full,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 8,
      paddingVertical: 4,
    },
    section: {
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      gap: spacing.sm,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    sectionIcon: {
      width: 30,
      height: 30,
      borderRadius: 10,
      backgroundColor: c.brandLight,
      alignItems: 'center',
      justifyContent: 'center',
    },
    titleInput: {
      minHeight: 44,
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 12,
      paddingVertical: 9,
      color: c.labelPrimary,
      fontSize: 16,
      fontWeight: '700',
      lineHeight: 21,
    },
    checkList: { gap: 8 },
    checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
    checkIndex: {
      width: 20,
      height: 20,
      borderRadius: 10,
      backgroundColor: c.brandLight,
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: 1,
    },
    metricCurrent: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 12,
      paddingVertical: 10,
    },
    metricWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    metricChip: {
      borderRadius: radii.full,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 11,
      paddingVertical: 7,
      borderWidth: 1,
      borderColor: c.separator,
    },
    metricChipActive: { backgroundColor: c.brand, borderColor: c.brand },
    twoCol: { flexDirection: 'row', gap: spacing.sm },
    col: { flex: 1, gap: 6 },
    input: {
      minHeight: 40,
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 12,
      color: c.labelPrimary,
      fontSize: 14,
    },
    stepperRow: { flexDirection: 'row', gap: 8 },
    dayBtn: {
      flex: 1,
      minHeight: 34,
      borderRadius: radii.md,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: c.bgPrimary,
    },
    dayBtnActive: { backgroundColor: c.brandLight },
    submitBtn: {
      minHeight: 46,
      borderRadius: radii.md,
      backgroundColor: c.brand,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
    },
    submitBtnPressed: { opacity: 0.84 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    kicker: { fontSize: 11, fontWeight: '800', color: c.brand, marginBottom: 2 } as TextStyle,
    title: { fontSize: 18, fontWeight: '800', color: c.labelPrimary } as TextStyle,
    sourcePill: { fontSize: 11, fontWeight: '800', color: c.brand } as TextStyle,
    sourcePillMuted: { fontSize: 11, fontWeight: '700', color: c.labelSecondary } as TextStyle,
    sourceSummary: { fontSize: 13, lineHeight: 19, color: c.labelSecondary, fontWeight: '500' } as TextStyle,
    sectionTitle: { fontSize: 14, fontWeight: '800', color: c.labelPrimary } as TextStyle,
    sectionSub: { fontSize: 11, lineHeight: 15, color: c.labelTertiary, marginTop: 1 } as TextStyle,
    checkIndex: { fontSize: 11, fontWeight: '800', color: c.brand } as TextStyle,
    checkText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.labelSecondary, fontWeight: '600' } as TextStyle,
    metricCurrentLabel: { fontSize: 12, fontWeight: '700', color: c.labelSecondary } as TextStyle,
    metricCurrentValue: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
    metricChip: { fontSize: 12, fontWeight: '700', color: c.labelSecondary } as TextStyle,
    metricChipActive: { color: '#fff' } as TextStyle,
    fieldLabel: { fontSize: 12, fontWeight: '700', color: c.labelSecondary } as TextStyle,
    dayBtn: { fontSize: 12, fontWeight: '700', color: c.labelSecondary } as TextStyle,
    dayBtnActive: { color: c.brand } as TextStyle,
    submit: { fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
  };
}
