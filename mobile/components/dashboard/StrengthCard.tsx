import React, { useState, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import api from '../../services/api';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

interface ExerciseConfig {
  type: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  quickAmounts: number[];
  dailyTarget: number;
}

interface Props {
  exerciseToday: any[];
  onUpdate?: () => void;
}

export default function StrengthCard({ exerciseToday, onUpdate }: Props) {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const EXERCISES: ExerciseConfig[] = useMemo(() => [
    { type: '俯卧撑', label: '俯卧撑', icon: 'body-outline', color: c.orange, bg: c.tintOrange, quickAmounts: [10, 15, 20, 30], dailyTarget: 100 },
    { type: '深蹲', label: '深蹲', icon: 'barbell-outline', color: c.purple, bg: c.tintPurple, quickAmounts: [10, 15, 20, 30], dailyTarget: 100 },
  ], [c]);

  const [localCounts, setLocalCounts] = useState<Record<string, number>>({});
  const [recording, setRecording] = useState<string | null>(null);

  const getCount = (type: string) => {
    if (type in localCounts) return localCounts[type];
    return (exerciseToday || [])
      .filter((e: any) => e.exercise_type === type)
      .reduce((s: number, e: any) => s + (e.reps || 0), 0);
  };

  const doRecord = useCallback(async (type: string, reps: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setRecording(type);
    const prevCount = getCount(type);
    setLocalCounts(prev => ({ ...prev, [type]: prevCount + reps }));
    try {
      await api.post('/daily-health/exercise', {
        record_date: today(),
        exercise_type: type,
        reps,
        sets: 1,
        intensity: 'high',
      });
    } catch {
      setLocalCounts(prev => ({ ...prev, [type]: prevCount }));
    } finally {
      setRecording(null);
    }
  }, [exerciseToday, localCounts]);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: c.tintOrange }]}>
          <Ionicons name="fitness-outline" size={16} color={c.orange} />
        </View>
        <Text style={txt.title}>力量训练</Text>
        <Text style={txt.date}>今日</Text>
      </View>

      {EXERCISES.map(ex => {
        const count = getCount(ex.type);
        const pct = Math.min(count / ex.dailyTarget, 1);

        return (
          <View key={ex.type} style={styles.exerciseSection}>
            <View style={styles.exerciseHeader}>
              <View style={[styles.exIconDot, { backgroundColor: ex.bg }]}>
                <Ionicons name={ex.icon} size={14} color={ex.color} />
              </View>
              <Text style={txt.exerciseName}>{ex.label}</Text>
              <Text style={[txt.exerciseCount, { color: ex.color }]}>{count}</Text>
              <Text style={txt.exerciseTarget}>/ {ex.dailyTarget}</Text>
            </View>

            {/* Progress bar */}
            <View style={styles.progressBg}>
              <View style={[styles.progressFill, { width: `${pct * 100}%`, backgroundColor: ex.color }]} />
            </View>

            {/* Quick add buttons */}
            <View style={styles.quickRow}>
              {ex.quickAmounts.map(amt => (
                <TouchableOpacity
                  key={amt}
                  style={[styles.quickBtn, { borderColor: `${ex.color}30` }]}
                  onPress={() => doRecord(ex.type, amt)}
                  activeOpacity={0.7}
                  disabled={recording === ex.type}
                >
                  <Text style={[txt.quickBtnText, { color: ex.color }]}>+{amt}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        );
      })}
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.xl,
      padding: spacing.lg, marginBottom: spacing.md,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, shadowRadius: 3, elevation: 1 }),
    },
    header: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: spacing.lg },
    iconWrap: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
    exerciseSection: { marginBottom: spacing.md },
    exerciseHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
    exIconDot: { width: 26, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
    progressBg: { height: 6, backgroundColor: c.bgPrimary, borderRadius: 3, marginBottom: spacing.sm, overflow: 'hidden' },
    progressFill: { height: 6, borderRadius: 3 },
    quickRow: { flexDirection: 'row', gap: spacing.sm },
    quickBtn: {
      flex: 1, borderWidth: 1, borderRadius: radii.md,
      paddingVertical: 8, alignItems: 'center',
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    date: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    exerciseName: { fontSize: 15, fontWeight: '500', color: c.labelPrimary, flex: 1 } as TextStyle,
    exerciseCount: { fontSize: 22, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
    exerciseTarget: { fontSize: 13, color: c.labelTertiary } as TextStyle,
    quickBtnText: { fontSize: 14, fontWeight: '600' } as TextStyle,
  };
}
