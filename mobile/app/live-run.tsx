/**
 * 跑步主屏 (Live Run Coach P1).
 *
 * V1 范围:
 * - 跑前选目标配速 (easy / tempo / fast / custom)
 * - 跑步中大字显示: 配速 / 距离 / 时长 / 状态
 * - 跑后提交统计到后端, 跳转复盘页
 *
 * 不在 P1: 规则引擎 (P2), 语音提示 (P2), 心率 (P3), 跑后 LLM (P4)
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Alert, ActivityIndicator,
  TextStyle, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import {
  useLiveRun, formatPace, formatDuration, formatDistanceKm,
} from '../hooks/useLiveRun';
import { startLiveRun, endLiveRun, type LiveRunSession, type LiveRunTargetLabel } from '../services/liveRun/api';

const PRESETS: { label: LiveRunTargetLabel; title: string; pace: number; desc: string }[] = [
  { label: 'easy', title: '轻松', pace: 360, desc: '6:00 配速 · 有氧基础' },
  { label: 'tempo', title: '节奏', pace: 330, desc: '5:30 配速 · 乳酸阈' },
  { label: 'fast', title: '快', pace: 270, desc: '4:30 配速 · 速度训练' },
];

export default function LiveRunScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  const [selected, setSelected] = useState<LiveRunTargetLabel>('easy');
  const targetPace = useMemo(
    () => PRESETS.find((p) => p.label === selected)?.pace ?? 360,
    [selected],
  );
  const { state, start, end } = useLiveRun(targetPace);
  const [session, setSession] = useState<LiveRunSession | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleStart = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const s = await startLiveRun({ target_label: selected });
      setSession(s);
    } catch (e: any) {
      Alert.alert('开始失败', e?.response?.data?.detail || e?.message || '请稍后再试');
      return;
    }
    const ok = await start();
    if (!ok) {
      // GPS 启动失败, session 已建在后端, 让用户主动放弃
      Alert.alert('GPS 不可用', state.error || '检查定位权限或户外位置');
    }
  };

  const handleEnd = async () => {
    if (!session) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    Alert.alert(
      '结束跑步',
      `${formatDistanceKm(state.distanceM)} km · ${formatDuration(state.durationS)}`,
      [
        { text: '继续', style: 'cancel' },
        {
          text: '结束',
          style: 'destructive',
          onPress: async () => {
            const { gpsSamples, events } = end();
            setSubmitting(true);
            try {
              const aborted = state.distanceM < 100;
              await endLiveRun(session.id, {
                total_distance_m: state.distanceM,
                total_duration_s: state.durationS,
                avg_pace_seconds: state.avgPace ?? undefined,
                z4_plus_minutes: 0,
                events,
                gps_samples: gpsSamples,
                aborted,
              });
              router.replace({ pathname: '/live-run/[id]', params: { id: String(session.id) } } as any);
            } catch (e: any) {
              Alert.alert('提交失败', e?.message || '已记录在本地, 请稍后重试');
            } finally {
              setSubmitting(false);
            }
          },
        },
      ],
    );
  };

  const isRunning = state.status === 'running' || state.status === 'paused';
  const isPaused = state.status === 'paused';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        {!isRunning && (
          <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
          </TouchableOpacity>
        )}
        <Text style={txt.title}>{isRunning ? (isPaused ? '已暂停 · GPS 丢失' : '跑步中') : '开始跑步'}</Text>
        <View style={{ width: 40 }} />
      </View>

      {!isRunning ? (
        <ScrollView contentContainerStyle={styles.scroll}>
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>选择今日目标</Text>
            <Text style={txt.subLabel}>跑步中按规则触发提示, 暂只有手机 GPS, 不接 Garmin 心率</Text>
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              {PRESETS.map((p) => (
                <TouchableOpacity
                  key={p.label}
                  style={[styles.presetBtn, selected === p.label && { backgroundColor: c.brandLight, borderColor: c.brand }]}
                  onPress={() => {
                    Haptics.selectionAsync();
                    setSelected(p.label);
                  }}
                  activeOpacity={0.7}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={[txt.presetTitle, selected === p.label && { color: c.brand }]}>{p.title}</Text>
                    <Text style={txt.presetDesc}>{p.desc}</Text>
                  </View>
                  {selected === p.label && (
                    <Ionicons name="checkmark-circle" size={22} color={c.brand} />
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {state.error && (
            <View style={[styles.card, { backgroundColor: c.tintRed }]}>
              <Text style={[txt.subLabel, { color: c.red }]}>{state.error}</Text>
            </View>
          )}

          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={handleStart}
            disabled={state.status === 'requesting_permission'}
            activeOpacity={0.7}
          >
            {state.status === 'requesting_permission' ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Ionicons name="play" size={20} color="#fff" />
                <Text style={txt.primaryBtnLabel}>开始跑步</Text>
              </>
            )}
          </TouchableOpacity>

          <Text style={[txt.hint, { textAlign: 'center', marginTop: spacing.md }]}>
            建议户外开阔位置, 跑步中保持手机锁屏, 屏幕息屏不影响 GPS.
          </Text>
        </ScrollView>
      ) : (
        <View style={styles.runningContainer}>
          <View style={styles.metricsBlock}>
            <Text style={[txt.bigPace, isPaused && { color: c.labelTertiary }]}>
              {formatPace(state.currentPace)}
            </Text>
            <Text style={txt.bigPaceLabel}>当前配速 (秒/公里)</Text>
          </View>

          <View style={styles.row}>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{formatDistanceKm(state.distanceM)}</Text>
              <Text style={txt.metricLabel}>距离 (km)</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{formatDuration(state.durationS)}</Text>
              <Text style={txt.metricLabel}>时长</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{formatPace(state.avgPace)}</Text>
              <Text style={txt.metricLabel}>平均配速</Text>
            </View>
          </View>

          {isPaused && (
            <View style={[styles.card, { backgroundColor: c.tintAmber }]}>
              <Text style={[txt.subLabel, { color: c.amber }]}>GPS 信号丢失, 已暂停计时. 出地下/桥下后会自动恢复.</Text>
            </View>
          )}

          {state.events.length > 0 && (
            <View style={styles.eventsBlock}>
              <Text style={txt.eventsTitle}>实时提示</Text>
              <ScrollView style={{ maxHeight: 140 }}>
                {state.events.slice(-5).reverse().map((e, i) => (
                  <View key={`${e.ts}-${i}`} style={styles.eventRow}>
                    <Ionicons name="volume-high" size={14} color={c.brand} />
                    <Text style={txt.eventMsg}>{e.message}</Text>
                  </View>
                ))}
              </ScrollView>
            </View>
          )}

          <TouchableOpacity
            style={[styles.endBtn, submitting && { opacity: 0.6 }]}
            onPress={handleEnd}
            disabled={submitting}
            activeOpacity={0.7}
          >
            {submitting ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Ionicons name="stop" size={20} color="#fff" />
                <Text style={txt.primaryBtnLabel}>结束</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    backBtn: { width: 40, alignItems: 'flex-start' },
    scroll: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl, gap: spacing.md },
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: spacing.xs, ...shadows.subtle,
    },
    presetBtn: {
      flexDirection: 'row', alignItems: 'center',
      borderWidth: 1, borderColor: c.separator, borderRadius: radii.md,
      padding: spacing.md, backgroundColor: c.bgPrimary,
    },
    primaryBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm,
      backgroundColor: c.brand, borderRadius: radii.md,
      paddingVertical: 16, marginTop: spacing.md,
    },
    runningContainer: {
      flex: 1, paddingHorizontal: spacing.md, paddingBottom: spacing.xl,
      justifyContent: 'space-between',
    },
    metricsBlock: {
      alignItems: 'center', paddingVertical: spacing.xl * 2,
    },
    row: {
      flexDirection: 'row', justifyContent: 'space-around',
      backgroundColor: c.bgCard, borderRadius: radii.md, padding: spacing.lg,
      ...shadows.subtle,
    },
    metricCell: { alignItems: 'center', gap: 4 },
    eventsBlock: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: spacing.xs, marginTop: spacing.md,
      ...shadows.subtle,
    },
    eventRow: {
      flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
      paddingVertical: 6,
    },
    endBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm,
      backgroundColor: c.red, borderRadius: radii.md,
      paddingVertical: 16, marginTop: spacing.md,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    sectionTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    subLabel: { fontSize: 13, color: c.labelSecondary, lineHeight: 18 } as TextStyle,
    hint: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    presetTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    presetDesc: { fontSize: 13, color: c.labelSecondary, marginTop: 2 } as TextStyle,
    primaryBtnLabel: { fontSize: 17, fontWeight: '600', color: '#fff' } as TextStyle,
    bigPace: {
      fontSize: 96, fontWeight: '800', color: c.labelPrimary,
      fontVariant: ['tabular-nums'] as const,
    } as TextStyle,
    bigPaceLabel: { fontSize: 14, color: c.labelSecondary, marginTop: spacing.sm } as TextStyle,
    metricVal: {
      fontSize: 22, fontWeight: '700', color: c.labelPrimary,
      fontVariant: ['tabular-nums'] as const,
    } as TextStyle,
    metricLabel: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    eventsTitle: { fontSize: 13, fontWeight: '600', color: c.labelSecondary } as TextStyle,
    eventMsg: { fontSize: 14, color: c.labelPrimary, flex: 1 } as TextStyle,
  };
}
