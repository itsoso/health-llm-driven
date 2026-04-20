import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii, shadows, scoreColor } from '@/constants/theme';
import type { GoalResponse } from '@/services/goals';

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
  const targetVal = goal.target_value ?? 0;
  const currentVal = goal.current_value ?? 0;
  const progress = targetVal > 0 ? Math.min(currentVal / targetVal, 1) : 0;
  const pct = Math.round(progress * 100);
  const barColor = pct >= 100 ? colors.green : pct >= 50 ? colors.amber : colors.brand;
  const icon = TYPE_ICONS[goal.goal_type] || 'flag-outline';
  const daysLeft = goal.end_date ? Math.max(0, Math.ceil((new Date(goal.end_date).getTime() - Date.now()) / 86400000)) : null;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.topRow}>
        <View style={[styles.iconCircle, { backgroundColor: `${barColor}20` }]}>
          <Ionicons name={icon} size={16} color={barColor} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={txt.title} numberOfLines={1}>{goal.title}</Text>
          <Text style={txt.sub}>
            {currentVal} / {targetVal} {goal.target_unit || ''}
            {daysLeft != null && `  ·  剩余 ${daysLeft} 天`}
          </Text>
        </View>
        {onUpdateProgress && (
          <TouchableOpacity onPress={onUpdateProgress} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="add-circle-outline" size={22} color={colors.brand} />
          </TouchableOpacity>
        )}
      </View>
      <View style={styles.barBg}>
        <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      <Text style={[txt.pct, { color: barColor }]}>{pct}%</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md, ...shadows.subtle,
  },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: spacing.sm },
  iconCircle: { width: 32, height: 32, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  barBg: { height: 6, backgroundColor: colors.bgPrimary, borderRadius: 3, overflow: 'hidden' },
  barFill: { height: 6, borderRadius: 3 },
});

const txt = {
  title: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  sub: { fontSize: 12, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  pct: { fontSize: 11, fontWeight: '600', textAlign: 'right', marginTop: 4 } as TextStyle,
};
