/**
 * FitnessSnapshotCard — 体能年龄 + 本周强度进度 双 KPI 小卡.
 *
 * 数据源: /api/v1/fitness-snapshot/me (VO2max 推算 fitness_age, 强度分钟本周汇总).
 * 位置: 健康记录页, ActivityRingBar 下面.
 *
 * 设计:
 * - 左半: 体能年龄 (大数字) + "比实际年轻 X 岁" 副标 (绿色激励 / 灰色中性 / 红色警示)
 * - 右半: 本周强度进度 圆环 (total / goal) + "X/150 min" 数字
 * - vo2max 不可用 → 左半 placeholder "测 VO2max 后解锁"
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import Svg, { Circle } from 'react-native-svg';
import api from '../../services/api';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Snapshot {
  vo2max: number | null;
  vo2max_source: string | null;
  chronological_age: number | null;
  fitness_age: number | null;
  age_delta: number | null;
  intensity_this_week: number;
  intensity_goal: number;
  intensity_pct: number;
  moderate_this_week: number;
  vigorous_this_week: number;
  days_tracked_this_week: number;
  last_data_date: string | null;
}

export default function FitnessSnapshotCard() {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const { data } = useQuery<Snapshot>({
    queryKey: ['fitnessSnapshot'],
    queryFn: () => api.get('/fitness-snapshot/me').then(r => r.data),
    staleTime: 600_000,
  });

  if (!data) return null;

  const hasFitAge = data.fitness_age != null && data.chronological_age != null;
  const deltaColor =
    data.age_delta == null ? c.labelSecondary :
    data.age_delta <= -3 ? c.green :
    data.age_delta <= 1 ? c.labelSecondary :
    '#FF9F0A';

  const pct = Math.max(0, Math.min(100, data.intensity_pct));
  const ringRadius = 26;
  const circumference = 2 * Math.PI * ringRadius;
  const strokeDash = circumference * (pct / 100);
  const ringColor = pct >= 100 ? c.green : pct >= 67 ? c.brand : c.amber;

  return (
    <View style={styles.card}>
      {/* Left: Fitness Age */}
      <View style={styles.left}>
        <View style={styles.iconRow}>
          <Ionicons name="flash-outline" size={14} color={c.brand} />
          <Text style={txt.label}>体能年龄</Text>
        </View>
        {hasFitAge ? (
          <>
            <Text style={[txt.bigNumber, { color: c.labelPrimary }]}>
              {data.fitness_age}
              <Text style={txt.unit}>岁</Text>
            </Text>
            <Text style={[txt.delta, { color: deltaColor }]}>
              {data.age_delta! < 0 ? `比实际年轻 ${Math.abs(data.age_delta!)} 岁` :
               data.age_delta! === 0 ? '与实际同龄' :
               `比实际大 ${data.age_delta!} 岁`}
            </Text>
            {data.vo2max != null && (
              <Text style={txt.footnote}>
                基于 VO₂max {data.vo2max.toFixed(0)}
              </Text>
            )}
          </>
        ) : (
          <>
            <Text style={[txt.bigNumber, { color: c.labelTertiary }]}>--</Text>
            <Text style={txt.footnote}>测 VO₂max 后解锁</Text>
          </>
        )}
      </View>

      <View style={styles.divider} />

      {/* Right: Weekly Intensity */}
      <View style={styles.right}>
        <View style={styles.iconRow}>
          <Ionicons name="pulse-outline" size={14} color={ringColor} />
          <Text style={txt.label}>本周强度</Text>
        </View>
        <View style={styles.ringWrap}>
          <Svg width={72} height={72} viewBox="0 0 72 72">
            <Circle
              cx={36} cy={36} r={ringRadius}
              stroke={c.fill} strokeWidth={6} fill="none"
            />
            <Circle
              cx={36} cy={36} r={ringRadius}
              stroke={ringColor} strokeWidth={6} fill="none"
              strokeLinecap="round"
              strokeDasharray={`${strokeDash} ${circumference}`}
              transform="rotate(-90 36 36)"
            />
          </Svg>
          <View style={styles.ringCenter}>
            <Text style={[txt.ringPct, { color: ringColor }]}>
              {Math.round(pct)}%
            </Text>
          </View>
        </View>
        <Text style={txt.footnote}>
          {data.intensity_this_week} / {data.intensity_goal} min
        </Text>
      </View>
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      flexDirection: 'row',
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.md,
      marginBottom: spacing.lg,
      alignItems: 'center',
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
          }),
    },
    left: { flex: 1, gap: 4 },
    right: { flex: 1, alignItems: 'center', gap: 4 },
    divider: {
      width: StyleSheet.hairlineWidth,
      height: 70,
      backgroundColor: c.separator,
      marginHorizontal: spacing.md,
    },
    iconRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
    ringWrap: { width: 72, height: 72, position: 'relative', marginVertical: 2 },
    ringCenter: {
      position: 'absolute', left: 0, right: 0, top: 0, bottom: 0,
      alignItems: 'center', justifyContent: 'center',
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    label: { fontSize: 12, color: c.labelSecondary, fontWeight: '500' as const } as TextStyle,
    bigNumber: {
      fontSize: 32, fontWeight: '800' as const, letterSpacing: 0,
      fontVariant: ['tabular-nums' as const],
    } as TextStyle,
    unit: { fontSize: 14, fontWeight: '500' as const } as TextStyle,
    delta: { fontSize: 12, fontWeight: '600' as const, marginTop: -2 } as TextStyle,
    footnote: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    ringPct: { fontSize: 17, fontWeight: '700' as const, fontVariant: ['tabular-nums' as const] } as TextStyle,
  };
}
