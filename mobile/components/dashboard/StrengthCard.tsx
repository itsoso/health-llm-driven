import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
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

function fmtSeconds(total: number): string {
  if (total < 60) return `${total}s`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s === 0 ? `${m}m` : `${m}m${s}s`;
}

type ExerciseMode = 'reps' | 'duration_seconds';

interface ExerciseConfig {
  type: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  mode: ExerciseMode;
  quickAmounts: number[];      // reps: 个; duration: 秒
  dailyTarget: number;         // reps: 个; duration: 秒
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
    { type: '俯卧撑',   label: '俯卧撑',   icon: 'body-outline',    color: c.orange, bg: c.tintOrange, mode: 'reps',             quickAmounts: [10, 15, 20, 30],   dailyTarget: 100 },
    { type: '深蹲',     label: '深蹲',     icon: 'barbell-outline', color: c.purple, bg: c.tintPurple, mode: 'reps',             quickAmounts: [10, 15, 20, 30],   dailyTarget: 100 },
    { type: '引体向上', label: '引体向上', icon: 'fitness-outline', color: c.blue,   bg: c.tintBlue,   mode: 'reps',             quickAmounts: [3, 5, 8, 10],      dailyTarget: 30  },
    { type: '倒立',     label: '倒立',     icon: 'sync-outline',    color: c.teal,   bg: c.tintTeal,   mode: 'duration_seconds', quickAmounts: [30, 60, 90, 120],  dailyTarget: 300 },
  ], [c]);

  // 本地乐观计数, 按 type 累加 (reps: 个数; duration: 秒数)
  const [localAdd, setLocalAdd] = useState<Record<string, number>>({});
  const [recording, setRecording] = useState<string | null>(null);
  // 同步锁: 比 React state 快, 阻挡同 type 的并发调用 (双击 race fix)
  const inFlightRef = useRef<Set<string>>(new Set());
  // 上一次 server 端总数 — 用来检测 server 涨了多少, 同步释放 localAdd
  // (修 bug: 不释放则用户点 +10, server 收到后 fromServer+localAdd 会变 20)
  const prevServerTotalRef = useRef<Record<string, number>>({});

  // 计算 server 端各 type 当前总数
  const serverTotals = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const cfg of EXERCISES) {
      const rows = (exerciseToday || []).filter((e: any) => e.exercise_type === cfg.type);
      totals[cfg.type] = rows.reduce((s: number, e: any) => {
        if (cfg.mode === 'reps') return s + (e.reps || 0);
        return s + (e.duration_seconds || 0);
      }, 0);
    }
    return totals;
  }, [exerciseToday, EXERCISES]);

  // 当 server 总数增长 → 把对应 amount 从 localAdd 里扣掉, 避免重复计数
  useEffect(() => {
    setLocalAdd(prev => {
      let changed = false;
      const next = { ...prev };
      for (const type of Object.keys(serverTotals)) {
        const prevTotal = prevServerTotalRef.current[type] || 0;
        const delta = serverTotals[type] - prevTotal;
        if (delta > 0 && (next[type] || 0) > 0) {
          next[type] = Math.max(0, (next[type] || 0) - delta);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    prevServerTotalRef.current = serverTotals;
  }, [serverTotals]);

  const getCount = (cfg: ExerciseConfig): number => {
    return (serverTotals[cfg.type] || 0) + (localAdd[cfg.type] || 0);
  };

  const doRecord = useCallback(async (cfg: ExerciseConfig, amount: number) => {
    // 防双击重入: setRecording 是 React state, 异步更新, 渲染前 button disabled
    // 还没生效, 用户双击会两次进 doRecord. 用 ref 锁同步阻挡 (16ms 渲染窗口).
    // 见 https://github.com/facebook/react-native/issues/known-touch-rebound
    const lockKey = cfg.type;
    if (inFlightRef.current.has(lockKey)) return;
    inFlightRef.current.add(lockKey);

    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setRecording(cfg.type);
    setLocalAdd(prev => ({ ...prev, [cfg.type]: (prev[cfg.type] || 0) + amount }));
    try {
      const payload: Record<string, unknown> = {
        record_date: today(),
        exercise_type: cfg.type,
        sets: 1,
        intensity: 'high',
      };
      if (cfg.mode === 'reps') {
        payload.reps = amount;
      } else {
        payload.duration_seconds = amount;
      }
      await api.post('/daily-health/exercise', payload);
      onUpdate?.();
    } catch {
      // 回滚乐观更新
      setLocalAdd(prev => ({ ...prev, [cfg.type]: (prev[cfg.type] || 0) - amount }));
    } finally {
      setRecording(null);
      inFlightRef.current.delete(lockKey);
    }
  }, [onUpdate]);

  const formatValue = (cfg: ExerciseConfig, v: number) =>
    cfg.mode === 'reps' ? `${v}` : fmtSeconds(v);

  const formatQuick = (cfg: ExerciseConfig, n: number) =>
    cfg.mode === 'reps' ? `+${n}` : `+${n}s`;

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
        const count = getCount(ex);
        const pct = Math.min(count / ex.dailyTarget, 1);

        return (
          <View key={ex.type} style={styles.exerciseSection}>
            <View style={styles.exerciseHeader}>
              <View style={[styles.exIconDot, { backgroundColor: ex.bg }]}>
                <Ionicons name={ex.icon} size={14} color={ex.color} />
              </View>
              <Text style={txt.exerciseName}>{ex.label}</Text>
              <Text style={[txt.exerciseCount, { color: ex.color }]}>{formatValue(ex, count)}</Text>
              <Text style={txt.exerciseTarget}>/ {formatValue(ex, ex.dailyTarget)}</Text>
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
                  onPress={() => doRecord(ex, amt)}
                  activeOpacity={0.7}
                  disabled={recording === ex.type}
                  accessibilityLabel={`记录${ex.label} ${ex.mode === 'reps' ? `${amt} 个` : `${amt} 秒`}`}
                >
                  <Text style={[txt.quickBtnText, { color: ex.color }]}>{formatQuick(ex, amt)}</Text>
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
