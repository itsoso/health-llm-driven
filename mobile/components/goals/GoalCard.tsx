import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { GoalResponse } from '../../services/goals';

interface Props {
  goal: GoalResponse;
  onPress?: () => void;
  onUpdateProgress?: () => void;
}

const TYPE_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  weight: 'scale-outline',
  exercise: 'barbell-outline',
  sleep: 'moon-outline',
  diet: 'nutrition-outline',
  water: 'water-outline',
  supplement: 'medkit-outline',
  outdoor: 'trail-sign-outline',
  other: 'flag-outline',
};

export default function GoalCard({ goal, onPress, onUpdateProgress }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const targetVal = goal.target_value ?? 0;
  const currentVal = goal.current_value ?? 0;
  const progress = targetVal > 0 ? Math.min(currentVal / targetVal, 1) : 0;
  const pct = Math.round(progress * 100);
  const barColor = pct >= 100 ? c.green : pct >= 50 ? c.amber : c.brand;
  const icon = TYPE_ICONS[goal.goal_type] || 'flag-outline';
  const daysLeft = goal.end_date ? Math.max(0, Math.ceil((new Date(goal.end_date).getTime() - Date.now()) / 86400000)) : null;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.topRow}>
        <View style={[styles.iconCircle, { backgroundColor: `${barColor}20` }]}>
          <Ionicons name={icon} size={16} color={barColor} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={1}>{goal.title}</Text>
          <Text style={styles.sub}>
            {currentVal} / {targetVal} {goal.target_unit || ''}
            {daysLeft != null && `  ·  剩余 ${daysLeft} 天`}
          </Text>
        </View>
        {onUpdateProgress && (
          <TouchableOpacity onPress={onUpdateProgress} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="add-circle-outline" size={22} color={c.brand} />
          </TouchableOpacity>
        )}
      </View>
      <View style={styles.barBg}>
        <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      <Text style={[styles.pct, { color: barColor }]}>{pct}%</Text>
    </TouchableOpacity>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.lg,
      padding: spacing.lg, marginBottom: spacing.md, ...shadows.subtle,
    },
    topRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: spacing.sm },
    iconCircle: { width: 32, height: 32, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
    barBg: { height: 6, backgroundColor: c.bgPrimary, borderRadius: 3, overflow: 'hidden' },
    barFill: { height: 6, borderRadius: 3 },
    title: { fontSize: 15, fontWeight: '600', color: c.labelPrimary },
    sub: { fontSize: 12, color: c.labelSecondary, marginTop: 2 },
    pct: { fontSize: 11, fontWeight: '600', textAlign: 'right', marginTop: 4 },
  });
}
