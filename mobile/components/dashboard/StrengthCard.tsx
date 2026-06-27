import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import api from '../../services/api';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

// 每个动作的装饰性 hue (俯卧撑橙 / 深蹲紫 / 引体蓝 / 倒立青) —— 「区分类目」的色码,
// 不是「指标好坏」的三步临床语义,故为局部字面量 (同 VitalsGrid 的 HUES)。
const EX_HUES = {
  orange: { color: '#C97A2E', bg: '#F6E9DA' },
  purple: { color: '#7C5CBF', bg: '#EDE7F6' },
  blue: { color: '#2A6FDB', bg: '#E4ECF8' },
  teal: { color: '#2F9E8F', bg: '#E0EFEC' },
} as const;

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

const EXERCISES: ExerciseConfig[] = [
  { type: '俯卧撑',   label: '俯卧撑',   icon: 'body-outline',    color: EX_HUES.orange.color, bg: EX_HUES.orange.bg, mode: 'reps',             quickAmounts: [10, 15, 20, 30],   dailyTarget: 100 },
  { type: '深蹲',     label: '深蹲',     icon: 'barbell-outline', color: EX_HUES.purple.color, bg: EX_HUES.purple.bg, mode: 'reps',             quickAmounts: [10, 15, 20, 30],   dailyTarget: 100 },
  { type: '引体向上', label: '引体向上', icon: 'fitness-outline', color: EX_HUES.blue.color,   bg: EX_HUES.blue.bg,   mode: 'reps',             quickAmounts: [3, 5, 8, 10],      dailyTarget: 30  },
  { type: '倒立',     label: '倒立',     icon: 'sync-outline',    color: EX_HUES.teal.color,   bg: EX_HUES.teal.bg,   mode: 'duration_seconds', quickAmounts: [30, 60, 90, 120],  dailyTarget: 300 },
];

export default function StrengthCard({ exerciseToday, onUpdate }: Props) {
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
  }, [exerciseToday]);

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
        <View style={[styles.iconWrap, { backgroundColor: EX_HUES.orange.bg }]}>
          <Ionicons name="fitness-outline" size={16} color={EX_HUES.orange.color} />
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

// Reva 设计语言:暖白 surface / r-lg 18 / paper2 recessed 进度槽 / light-first 软阴影。动作色为类目装饰色。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s3,
    ...revaShadows.sm,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: revaSpacing.s4 },
  iconWrap: { width: 28, height: 28, borderRadius: revaRadii.sm, alignItems: 'center', justifyContent: 'center' },
  exerciseSection: { marginBottom: revaSpacing.s3 },
  exerciseHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  exIconDot: { width: 26, height: 26, borderRadius: revaRadii.sm, alignItems: 'center', justifyContent: 'center' },
  progressBg: { height: 6, backgroundColor: C.paper2, borderRadius: 3, marginBottom: revaSpacing.s2, overflow: 'hidden' },
  progressFill: { height: 6, borderRadius: 3 },
  quickRow: { flexDirection: 'row', gap: revaSpacing.s2 },
  quickBtn: {
    flex: 1, borderWidth: 1, borderRadius: revaRadii.md,
    paddingVertical: 8, alignItems: 'center',
  },
});

// 数字(动作计数/目标/快捷量)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1 } as TextStyle,
  date: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3 } as TextStyle,
  exerciseName: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '500', color: C.ink1, flex: 1 } as TextStyle,
  exerciseCount: { fontFamily: revaFonts.mono, fontSize: 22, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  exerciseTarget: { fontFamily: revaFonts.mono, fontSize: 13, color: C.ink3 } as TextStyle,
  quickBtnText: { fontFamily: revaFonts.mono, fontSize: 14, fontWeight: '600' } as TextStyle,
};
