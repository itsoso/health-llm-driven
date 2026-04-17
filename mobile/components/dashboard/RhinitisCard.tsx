import React, { useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { updateCheckin } from '@/services/records';
import { colors, spacing, radii, shadows } from '@/constants/theme';

interface Props {
  checkin: any;
  onUpdate?: () => void;
}

export default function RhinitisCard({ checkin, onUpdate }: Props) {
  // Use props directly — no local state to avoid stale initialization
  const sneezeCount = checkin?.sneeze_count || 0;
  const washCount = checkin?.nasal_wash_count || 0;
  const mometasone = !!checkin?.mometasone;

  const doAction = useCallback(async (field: string, value: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await updateCheckin(field, value);
      onUpdate?.();
    } catch { /* ignore */ }
  }, [onUpdate]);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={{ fontSize: 14 }}>🤧</Text>
        <Text style={txt.title}>鼻炎</Text>
      </View>
      <View style={styles.row}>
        <TouchableOpacity style={styles.chip} onPress={() => doAction('nasal_wash_count', washCount + 1)} activeOpacity={0.7}>
          <Text style={[txt.chipVal, { color: '#5AC8FA' }]}>{washCount}</Text>
          <Text style={txt.chipLabel}>洗鼻</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.chip} onPress={() => doAction('sneeze_count', sneezeCount + 1)} activeOpacity={0.7}>
          <Text style={[txt.chipVal, { color: '#FF9F0A' }]}>{sneezeCount}</Text>
          <Text style={txt.chipLabel}>喷嚏</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.chip, mometasone && { backgroundColor: '#E8FAF0' }]} onPress={() => doAction('mometasone', mometasone ? 0 : 1)} activeOpacity={0.7}>
          <Ionicons name={mometasone ? 'checkmark-circle' : 'ellipse-outline'} size={16} color={mometasone ? '#30D158' : colors.labelTertiary} />
          <Text style={txt.chipLabel}>莫米松</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.md, marginBottom: spacing.md, ...shadows.subtle,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  row: { flexDirection: 'row', gap: spacing.sm },
  chip: {
    flex: 1, backgroundColor: colors.bgPrimary, borderRadius: radii.md,
    paddingVertical: 8, alignItems: 'center', gap: 2,
  },
});

const txt = {
  title: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  chipVal: { fontSize: 20, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  chipLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
};
