/**
 * 跑步后复盘页 (Live 5).
 *
 * 展数据总览 (配速 / 距离 / 时长)
 * - 触发的事件列表 (配速偏离 / 心率过载)
 * - GPS 轨迹抽样点
 * - LLM narrative 复盘 (异步, 拉不到时显示加载中)
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity,
  TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import { spacing, radii, shadows } from '../../constants/theme';
import { getLiveRun, type LiveRunSession } from '../../services/liveRun/api';
import { formatPace, formatDuration, formatDistanceKm } from '../../hooks/useLiveRun';
import AgentFeedbackLink from '../../components/agent/AgentFeedbackLink';
import { createLiveRunAgentContext } from '../../utils/agentContext';

const TARGET_LABEL_MAP: Record<string, string> = {
  easy: '轻松',
  tempo: '节奏',
  fast: '快',
  custom: '自定义',
};

export default function LiveRunDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  const [session, setSession] = useState<LiveRunSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const fetchOnce = async () => {
      try {
        const s = await getLiveRun(Number(id));
        if (cancelled) return;
        setSession(s);
        // narrative 还在生成 → 4s 后再拉, 最多 15 次 (1 分钟)
        if ((s.narrative_status === 'pending' || s.narrative_status === 'running') && attempts < 15) {
          attempts += 1;
          timer = setTimeout(fetchOnce, 4000);
        }
      } catch (e: any) {
        console.warn('[LiveRunDetail] fetch failed:', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchOnce();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={c.brand} />
          <Text style={[txt.subLabel, { marginTop: spacing.md }]}>加载跑步详情...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!session) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}>
          <Text style={txt.subLabel}>跑步记录不存在</Text>
          <TouchableOpacity
            style={[styles.secondaryBtn, { marginTop: spacing.md }]}
            onPress={() => router.back()}
            activeOpacity={0.7}
          >
            <Text style={[txt.btnLabel, { color: c.brand }]}>返回</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>跑步复盘</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* 总览 */}
        <View style={styles.card}>
          <Text style={txt.sectionTitle}>总览</Text>
          <View style={styles.row}>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{formatDistanceKm(session.total_distance_m)}</Text>
              <Text style={txt.metricLabel}>距离 (km)</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{formatDuration(session.total_duration_s)}</Text>
              <Text style={txt.metricLabel}>时长</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{formatPace(session.avg_pace_seconds)}</Text>
              <Text style={txt.metricLabel}>平均配速</Text>
            </View>
          </View>
          {session.aborted && (
            <Text style={[txt.subLabel, { marginTop: spacing.sm, color: c.amber }]}>
              本次跑步被中途放弃 (距离 {'<'} 100m)
            </Text>
          )}
          <View style={[styles.row, { marginTop: spacing.sm }]}>
            <View style={styles.metricCell}>
              <Text style={[txt.metricVal, { color: session.max_hr ? c.brand : c.labelTertiary }]}>
                {session.max_hr ?? '--'}
              </Text>
              <Text style={txt.metricLabel}>最高心率</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={txt.metricVal}>{session.z4_plus_minutes.toFixed(1)}</Text>
              <Text style={txt.metricLabel}>Z4+ (min)</Text>
            </View>
          </View>
        </View>

        <AgentFeedbackLink
          label="跟阿衡聊这次实时跑"
          accessibilityLabel="跟阿衡聊这次实时跑"
          prompt="请基于这次实时跑做一次运动复盘: 解释配速、心率和触发事件，给出拉伸恢复建议，并安排下一次训练。最后指出你还需要我补充哪些体感反馈。"
          context={createLiveRunAgentContext(session as any)}
          badge={`实时跑 ${formatDistanceKm(session.total_distance_m)}km`}
        />

        {/* 目标设定 */}
        <View style={styles.card}>
          <Text style={txt.sectionTitle}>目标设定</Text>
          <View style={styles.row}>
            <View style={styles.metricCell}>
              <Text style={txt.metricLabel}>类型</Text>
              <Text style={[txt.metricVal, { color: c.brand }]}>
                {session.target_label ? TARGET_LABEL_MAP[session.target_label] ?? session.target_label : '--'}
              </Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={txt.metricLabel}>目标配速</Text>
              <Text style={txt.metricVal}>
                {session.target_pace_seconds ? formatPace(session.target_pace_seconds) : '--'}
              </Text>
            </View>
          </View>
          {session.readiness_score != null && (
            <Text style={[txt.subLabel, { marginTop: spacing.sm }]}>
              跑前恢复度: {session.readiness_score}/100
            </Text>
          )}
        </View>

        {/* 触发事件 */}
        {session.events && session.events.length > 0 && (
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>触发事件 ({session.events.length})</Text>
            {session.events.map((e, i) => (
              <View key={i} style={styles.eventItem}>
                <View style={styles.eventHeader}>
                  <Text style={txt.eventRule}>{e.rule_id}</Text>
                  <Text style={txt.eventTime}>
                    {new Date(e.ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                  </Text>
                </View>
                <Text style={txt.eventMessage}>{e.message}</Text>
                {e.metric_snapshot && (
                  <Text style={txt.eventSnapshot}>{JSON.stringify(e.metric_snapshot)}</Text>
                )}
              </View>
            ))}
          </View>
        )}

        {/* GPS 轨迹 */}
        {session.gps_samples && session.gps_samples.length > 0 && (
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>GPS 轨迹 (抽样)</Text>
            <Text style={[txt.subLabel, { marginBottom: spacing.sm }]}>
              每约 30 秒存一个点 · {session.gps_samples.length} 个样本
            </Text>
          </View>
        )}

        {/* LLM 复盘 */}
        <View style={styles.card}>
          <Text style={txt.sectionTitle}>AI 复盘</Text>
          {session.narrative_status === 'pending' || session.narrative_status === 'running' ? (
            <View style={styles.narrativePending}>
              <ActivityIndicator size="small" color={c.brand} />
              <Text style={[txt.subLabel, { marginLeft: spacing.sm }]}>生成中...</Text>
            </View>
          ) : session.narrative_status === 'completed' && session.narrative ? (
            <Text style={txt.narrative}>{session.narrative}</Text>
          ) : session.narrative_status === 'skipped' ? (
            <Text style={[txt.subLabel, { color: c.labelTertiary }]}>跑量太短, 跳过复盘</Text>
          ) : (
            <Text style={[txt.subLabel, { color: c.red }]}>复盘生成失败</Text>
          )}
        </View>

        <TouchableOpacity
          style={styles.secondaryBtn}
          onPress={() => {
            Haptics.selectionAsync();
            router.replace({ pathname: '/live-run' } as any);
          }}
          activeOpacity={0.7}
        >
          <Ionicons name="play" size={18} color={c.brand} />
          <Text style={[txt.btnLabel, { color: c.brand, marginLeft: 6 }]}>再来一次</Text>
        </TouchableOpacity>
      </ScrollView>
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
    center: {
      flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 100,
    },
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: spacing.xs, ...shadows.subtle,
    },
    row: {
      flexDirection: 'row', justifyContent: 'space-around',
      paddingVertical: spacing.sm,
    },
    metricCell: { alignItems: 'center', gap: 4 },
    eventItem: {
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: c.separator,
      paddingVertical: spacing.sm,
    },
    eventHeader: {
      flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4,
    },
    narrativePending: {
      flexDirection: 'row', alignItems: 'center',
      paddingVertical: spacing.sm,
    },
    secondaryBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
      backgroundColor: c.bgPrimary, borderWidth: 1, borderColor: c.brand,
      borderRadius: radii.md, paddingVertical: 12, paddingHorizontal: spacing.lg,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    sectionTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    subLabel: { fontSize: 13, color: c.labelSecondary, lineHeight: 18 } as TextStyle,
    btnLabel: { fontSize: 15, fontWeight: '500' } as TextStyle,
    metricVal: {
      fontSize: 18, fontWeight: '700', color: c.labelPrimary,
      fontVariant: ['tabular-nums'] as const,
    } as TextStyle,
    metricLabel: { fontSize: 12, color: c.labelSecondary } as TextStyle,
    eventRule: {
      fontSize: 11, fontWeight: '600', color: c.brand, textTransform: 'uppercase' as const,
    } as TextStyle,
    eventTime: {
      fontSize: 11, color: c.labelTertiary, fontVariant: ['tabular-nums'] as const,
    } as TextStyle,
    eventMessage: {
      fontSize: 13, color: c.labelPrimary, lineHeight: 18,
    } as TextStyle,
    eventSnapshot: {
      fontSize: 11, color: c.labelTertiary, marginTop: spacing.xs,
    } as TextStyle,
    narrative: {
      fontSize: 14, color: c.labelPrimary, lineHeight: 22,
    } as TextStyle,
  };
}
