import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, shadows, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { OutcomeReviewDraft, OutcomeReviewStatus } from '../../services/outcomeReview';

interface Props {
  visible: boolean;
  title: string;
  draft: OutcomeReviewDraft | null;
  isSaving?: boolean;
  onClose: () => void;
  onSubmit: (draft: OutcomeReviewDraft) => void;
}

const STATUS_OPTIONS: { key: OutcomeReviewStatus; label: string }[] = [
  { key: 'met', label: '达成' },
  { key: 'not_met', label: '未达成' },
  { key: 'inconclusive', label: '不确定' },
  { key: 'pending', label: '待观察' },
];

export default function OutcomeVerificationSheet({ visible, title, draft, isSaving, onClose, onSubmit }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const [form, setForm] = useState<OutcomeReviewDraft | null>(draft);

  useEffect(() => {
    setForm(draft);
  }, [draft]);

  if (!form) return null;

  const update = (patch: Partial<OutcomeReviewDraft>) => {
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
              <Text style={styles.title}>干预复盘</Text>
              <Text style={styles.subtitle} numberOfLines={1}>{title}</Text>
            </View>
            <Pressable style={styles.iconBtn} onPress={onClose} accessibilityRole="button" accessibilityLabel="关闭">
              <Ionicons name="close" size={18} color={c.labelSecondary} />
            </Pressable>
          </View>

          <Text style={styles.label}>结果</Text>
          <View style={styles.segmented}>
            {STATUS_OPTIONS.map(option => {
              const active = form.status === option.key;
              return (
                <Pressable
                  key={option.key}
                  style={[styles.segment, active && styles.segmentActive]}
                  onPress={() => update({ status: option.key })}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                >
                  <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{option.label}</Text>
                </Pressable>
              );
            })}
          </View>

          <Text style={styles.label}>实测值</Text>
          <TextInput
            style={styles.input}
            value={form.actualValue}
            onChangeText={actualValue => update({ actualValue })}
            placeholder="例如 84 / 48ms / 126/78"
            placeholderTextColor={c.labelTertiary}
          />

          <Text style={styles.label}>结论</Text>
          <TextInput
            style={[styles.input, styles.summaryInput]}
            value={form.summary}
            onChangeText={summary => update({ summary })}
            multiline
            placeholder="这次干预是否值得继续？"
            placeholderTextColor={c.labelTertiary}
          />

          {form.evidence.length > 0 ? (
            <View style={styles.evidenceBox}>
              <Text style={styles.evidenceTitle}>证据</Text>
              {form.evidence.slice(0, 4).map((item, index) => (
                <View key={`${item}-${index}`} style={styles.evidenceRow}>
                  <Ionicons name="analytics-outline" size={13} color={c.labelTertiary} />
                  <Text style={styles.evidenceText} numberOfLines={2}>{item}</Text>
                </View>
              ))}
            </View>
          ) : null}

          <Pressable
            style={({ pressed }) => [styles.submitBtn, pressed && !isSaving && styles.submitBtnPressed]}
            onPress={() => onSubmit(form)}
            disabled={isSaving}
            accessibilityRole="button"
            accessibilityLabel="保存复盘"
          >
            {isSaving ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="checkmark-done" size={16} color="#fff" />}
            <Text style={styles.submit}>保存复盘</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    overlay: { flex: 1, justifyContent: 'flex-end' },
    backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.35)' },
    sheet: {
      backgroundColor: c.bgCard,
      borderTopLeftRadius: 18,
      borderTopRightRadius: 18,
      paddingHorizontal: spacing.lg,
      paddingTop: 8,
      paddingBottom: 28,
      gap: 10,
      ...shadows.heavy,
    },
    handle: { alignSelf: 'center', width: 38, height: 4, borderRadius: 2, backgroundColor: c.separator, marginBottom: 4 },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
    iconBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
    segmented: { flexDirection: 'row', gap: 6 },
    segment: {
      flex: 1,
      minHeight: 34,
      borderRadius: radii.md,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: c.bgPrimary,
      borderWidth: 1,
      borderColor: c.separator,
    },
    segmentActive: { backgroundColor: c.brand, borderColor: c.brand },
    input: {
      minHeight: 40,
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 12,
      paddingVertical: 9,
      color: c.labelPrimary,
      fontSize: 14,
    },
    summaryInput: { minHeight: 74, textAlignVertical: 'top' },
    evidenceBox: { borderRadius: radii.md, backgroundColor: c.bgPrimary, padding: spacing.sm, gap: 6 },
    evidenceRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6 },
    submitBtn: {
      minHeight: 44,
      borderRadius: radii.md,
      backgroundColor: c.brand,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      marginTop: 2,
    },
    submitBtnPressed: { opacity: 0.84 },
    title: { fontSize: 17, fontWeight: '800', color: c.labelPrimary },
    subtitle: { fontSize: 12, color: c.labelSecondary, marginTop: 2 },
    label: { fontSize: 12, fontWeight: '700', color: c.labelSecondary },
    segmentText: { fontSize: 12, fontWeight: '700', color: c.labelSecondary },
    segmentTextActive: { color: '#fff' },
    evidenceTitle: { fontSize: 12, fontWeight: '800', color: c.labelPrimary },
    evidenceText: { flex: 1, fontSize: 12, lineHeight: 17, color: c.labelSecondary },
    submit: { fontSize: 14, fontWeight: '800', color: '#fff' },
  });
}
