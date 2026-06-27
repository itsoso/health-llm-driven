import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
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
  const targetVal = goal.target_value ?? 0;
  const currentVal = goal.current_value ?? 0;
  const progress = targetVal > 0 ? Math.min(currentVal / targetVal, 1) : 0;
  const pct = Math.round(progress * 100);
  // 进度达标度 → 三步语义:满 100% 正常绿、过半注意琥珀、其余进行中活力绿。
  const barColor = pct >= 100 ? revaSemantic.normal.fg : pct >= 50 ? revaSemantic.caution.fg : C.green500;
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
            <Ionicons name="add-circle-outline" size={22} color={C.green500} />
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

// Reva 设计语言:暖白 surface 卡 / r-lg 18 / 进度数字等宽 mono / light-first 软阴影。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s3, ...revaShadows.sm,
  },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: revaSpacing.s2 },
  iconCircle: { width: 32, height: 32, borderRadius: revaRadii.sm, alignItems: 'center', justifyContent: 'center' },
  barBg: { height: 6, backgroundColor: C.paper2, borderRadius: 3, overflow: 'hidden' },
  barFill: { height: 6, borderRadius: 3 },
  title: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '600', color: C.ink1 },
  sub: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink2, marginTop: 2 },
  pct: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '600', textAlign: 'right', marginTop: 4 },
});
