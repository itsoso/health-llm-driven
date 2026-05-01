import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { getWorkouts, type WorkoutSummary } from '../../services/workouts';
import HealthCard from '../design-system/HealthCard';
import { spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

function buildTypeIcons(c: ColorPalette): Record<string, { icon: string; color: string }> {
  return {
    running: { icon: 'walk', color: c.pink },
    walking: { icon: 'footsteps', color: c.amber },
    cycling: { icon: 'bicycle', color: c.green },
    swimming: { icon: 'water', color: c.blue },
    strength: { icon: 'barbell', color: c.purple },
    yoga: { icon: 'body', color: c.teal },
    hiking: { icon: 'trail-sign', color: c.orange },
  };
}

function getTypeInfo(type: string, c: ColorPalette) {
  const map = buildTypeIcons(c);
  const key = type.toLowerCase().replace(/[_ ]/g, '');
  return map[key] ?? { icon: 'fitness', color: c.pink };
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '--';
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h${m % 60}m` : `${m}min`;
}

function formatDistance(meters: number | null): string {
  if (!meters) return '';
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)}km` : `${meters}m`;
}

const DAY_LABELS = ['日', '一', '二', '三', '四', '五', '六'];

export default function WorkoutWeekCard() {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const router = useRouter();
  const { data: workouts } = useQuery({
    queryKey: ['workouts-week'],
    queryFn: () => getWorkouts(20, 0),
    staleTime: 120_000,
  });

  const now = new Date();
  const days: { label: string; date: string; workouts: WorkoutSummary[] }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0];
    days.push({
      label: i === 0 ? '今' : DAY_LABELS[d.getDay()],
      date: dateStr,
      workouts: (workouts ?? []).filter(w => w.workout_date === dateStr),
    });
  }

  const weekCount = days.reduce((s, d) => s + d.workouts.length, 0);
  const weekCal = days.reduce((s, d) => s + d.workouts.reduce((ss, w) => ss + (w.calories ?? 0), 0), 0);
  const weekMin = days.reduce((s, d) => s + d.workouts.reduce((ss, w) => ss + Math.round((w.duration_seconds ?? 0) / 60), 0), 0);

  function Stat({ value, unit }: { value: string; unit: string }) {
    return (
      <View style={styles.statCol}>
        <Text style={txt.statVal}>{value}</Text>
        <Text style={txt.statUnit}>{unit}</Text>
      </View>
    );
  }

  return (
    <HealthCard
      title="运动"
      icon="barbell-outline"
      iconColor={c.pink}
      iconBg={c.tintPink}
      rightAccessory={
        <TouchableOpacity onPress={() => router.push('/workout-list' as any)} hitSlop={8}>
          <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />
        </TouchableOpacity>
      }
    >
      {/* Week summary */}
      <View style={styles.summaryRow}>
        <Stat value={`${weekCount}`} unit="次" />
        <View style={styles.divider} />
        <Stat value={`${weekMin}`} unit="分钟" />
        <View style={styles.divider} />
        <Stat value={`${weekCal}`} unit="kcal" />
      </View>

      {/* Day dots */}
      <View style={styles.dayRow}>
        {days.map((d) => {
          const has = d.workouts.length > 0;
          const typeInfo = has ? getTypeInfo(d.workouts[0].workout_type, c) : null;
          return (
            <View key={d.date} style={styles.dayCol}>
              <View style={[
                styles.dayDot,
                has
                  ? { backgroundColor: `${typeInfo!.color}20` }
                  : { backgroundColor: c.fill },
              ]}>
                {has ? (
                  <Ionicons name={typeInfo!.icon as any} size={14} color={typeInfo!.color} />
                ) : (
                  <View style={styles.emptyDot} />
                )}
              </View>
              <Text style={[txt.dayLabel, d.label === '今' && txt.dayToday]}>{d.label}</Text>
            </View>
          );
        })}
      </View>

      {/* Recent workouts (last 3) */}
      {(workouts ?? []).slice(0, 3).map((w) => {
        const info = getTypeInfo(w.workout_type, c);
        return (
          <TouchableOpacity
            key={w.id}
            style={styles.workoutRow}
            onPress={() => router.push(`/workout-detail?id=${w.id}` as any)}
            activeOpacity={0.6}
          >
            <View style={[styles.typeIcon, { backgroundColor: `${info.color}15` }]}>
              <Ionicons name={info.icon as any} size={14} color={info.color} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.workoutName} numberOfLines={1}>
                {w.workout_name || w.workout_type}
              </Text>
              <Text style={txt.workoutMeta}>
                {w.workout_date.slice(5)} · {formatDuration(w.duration_seconds)}
                {w.distance_meters ? ` · ${formatDistance(w.distance_meters)}` : ''}
              </Text>
            </View>
            {w.calories != null && w.calories > 0 && (
              <Text style={txt.workoutCal}>{w.calories}kcal</Text>
            )}
          </TouchableOpacity>
        );
      })}

      {(!workouts || workouts.length === 0) && (
        <Text style={txt.empty}>最近 7 天没有运动记录</Text>
      )}
    </HealthCard>
  );
}

function createStyles(c: ColorPalette, _isDark: boolean) {
  return StyleSheet.create({
    summaryRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.lg,
      marginBottom: spacing.md,
    },
    statCol: { alignItems: 'center' },
    divider: { width: 1, height: 24, backgroundColor: c.separator },
    dayRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      marginBottom: spacing.md,
      paddingHorizontal: spacing.xs,
    },
    dayCol: { alignItems: 'center', gap: 4 },
    dayDot: {
      width: 32,
      height: 32,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
    },
    emptyDot: {
      width: 6,
      height: 6,
      borderRadius: 3,
      backgroundColor: c.labelQuaternary,
    },
    workoutRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      paddingVertical: 8,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
    },
    typeIcon: {
      width: 28,
      height: 28,
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    statVal: { fontSize: 20, fontWeight: '700', color: c.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
    statUnit: { fontSize: 11, color: c.labelTertiary, marginTop: 1 } as TextStyle,
    dayLabel: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    dayToday: { color: c.brand, fontWeight: '600' } as TextStyle,
    workoutName: { fontSize: 14, fontWeight: '500', color: c.labelPrimary } as TextStyle,
    workoutMeta: { fontSize: 12, color: c.labelTertiary, marginTop: 1 } as TextStyle,
    workoutCal: { fontSize: 13, fontWeight: '600', color: c.pink, fontVariant: ['tabular-nums'] as const } as TextStyle,
    empty: { fontSize: 13, color: c.labelTertiary, textAlign: 'center', paddingVertical: 12 } as TextStyle,
  };
}
