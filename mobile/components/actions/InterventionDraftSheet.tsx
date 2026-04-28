import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadows, spacing } from '../../constants/theme';
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
  const [form, setForm] = useState<InterventionDraft | null>(draft);

  useEffect(() => {
    setForm(draft);
  }, [draft]);

  if (!form) return null;

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
            <Text style={txt.title}>加入健康行动</Text>
            <Pressable style={styles.iconBtn} onPress={onClose} accessibilityRole="button" accessibilityLabel="关闭">
              <Ionicons name="close" size={18} color={colors.labelSecondary} />
            </Pressable>
          </View>

          <Text style={txt.label}>标题</Text>
          <TextInput
            style={styles.input}
            value={form.title}
            onChangeText={title => update({ title })}
            placeholder="行动标题"
            placeholderTextColor={colors.labelTertiary}
          />

          <Text style={txt.label}>成功指标</Text>
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
              <Text style={txt.label}>基线</Text>
              <TextInput
                style={styles.input}
                value={form.baseline_value || ''}
                onChangeText={baseline_value => update({ baseline_value })}
                placeholder="可选"
                placeholderTextColor={colors.labelTertiary}
              />
            </View>
            <View style={styles.col}>
              <Text style={txt.label}>目标</Text>
              <TextInput
                style={styles.input}
                value={form.target_value || ''}
                onChangeText={target_value => update({ target_value })}
                placeholder="可选"
                placeholderTextColor={colors.labelTertiary}
              />
            </View>
          </View>

          <Text style={txt.label}>复盘窗口</Text>
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

          <View style={styles.preview}>
            <Text style={txt.previewTitle}>检查项</Text>
            {form.checklist.slice(0, 3).map((item, index) => (
              <View key={`${item.item}-${index}`} style={styles.checkRow}>
                <Ionicons name="ellipse-outline" size={13} color={colors.labelTertiary} />
                <Text style={txt.checkText} numberOfLines={1}>{item.item}</Text>
              </View>
            ))}
          </View>

          <Pressable
            style={({ pressed }) => [styles.submitBtn, pressed && !isSaving && styles.submitBtnPressed]}
            onPress={() => onSubmit(form)}
            disabled={isSaving}
            accessibilityRole="button"
            accessibilityLabel="加入行动"
          >
            {isSaving ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="add-circle" size={16} color="#fff" />}
            <Text style={txt.submit}>加入行动</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: {
    backgroundColor: colors.bgCard,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    paddingHorizontal: spacing.lg,
    paddingTop: 8,
    paddingBottom: 28,
    gap: 10,
    ...shadows.heavy,
  },
  handle: { alignSelf: 'center', width: 38, height: 4, borderRadius: 2, backgroundColor: colors.separator, marginBottom: 4 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  input: {
    minHeight: 40,
    borderRadius: radii.md,
    backgroundColor: colors.bgPrimary,
    paddingHorizontal: 12,
    color: colors.labelPrimary,
    fontSize: 14,
  },
  metricWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metricChip: {
    borderRadius: radii.full,
    backgroundColor: colors.bgPrimary,
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderWidth: 1,
    borderColor: colors.separator,
  },
  metricChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  twoCol: { flexDirection: 'row', gap: spacing.sm },
  col: { flex: 1, gap: 6 },
  stepperRow: { flexDirection: 'row', gap: 8 },
  dayBtn: {
    flex: 1,
    minHeight: 34,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.bgPrimary,
  },
  dayBtnActive: { backgroundColor: colors.brandLight },
  preview: { borderRadius: radii.md, backgroundColor: colors.bgPrimary, padding: spacing.sm, gap: 6 },
  checkRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  submitBtn: {
    minHeight: 44,
    borderRadius: radii.md,
    backgroundColor: colors.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 2,
  },
  submitBtnPressed: { opacity: 0.84 },
});

const txt = {
  title: { fontSize: 17, fontWeight: '800', color: colors.labelPrimary } as TextStyle,
  label: { fontSize: 12, fontWeight: '700', color: colors.labelSecondary } as TextStyle,
  metricChip: { fontSize: 12, fontWeight: '700', color: colors.labelSecondary } as TextStyle,
  metricChipActive: { color: '#fff' } as TextStyle,
  dayBtn: { fontSize: 12, fontWeight: '700', color: colors.labelSecondary } as TextStyle,
  dayBtnActive: { color: colors.brand } as TextStyle,
  previewTitle: { fontSize: 12, fontWeight: '800', color: colors.labelPrimary } as TextStyle,
  checkText: { flex: 1, fontSize: 12, color: colors.labelSecondary } as TextStyle,
  submit: { fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
};
