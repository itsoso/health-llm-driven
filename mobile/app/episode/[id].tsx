/**
 * Episode 详情页 — Agent-Native v3 闭环 UI.
 *
 * 路由: /episode/[id]
 *
 * UI 结构:
 *   Header (back + 标题 + risk pill)
 *   Headline 卡 (一句教练话, 来自 planner._make_headline)
 *   Risk flags chip 列 (heat / acwr / sleep_short / redflag:xxx)
 *   ActionGraph 卡片列 (按 sequence)
 *   Disclaimer (validator 注入, 可选)
 *
 * Action 完成/跳过 → POST /episodes/{id}/feedback → 自动失效 detail + list 缓存.
 */
import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { useEpisode, useEpisodeFeedback } from '../../hooks/useEpisode';
import ActionGraphCard from '../../components/episode/ActionGraphCard';
import type { EpisodeOutcome, RiskLevel } from '../../services/episodes';

export default function EpisodeDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const episodeId = Number(id);
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data: ep, isLoading, isError, refetch, isRefetching } = useEpisode(
    Number.isFinite(episodeId) ? episodeId : null,
  );
  const feedback = useEpisodeFeedback(episodeId);

  const onDone = (actionId: number) => {
    feedback.mutate({ kind: 'action_done', action_id: actionId, source: 'mobile' });
  };
  const onSkip = (actionId: number) => {
    feedback.mutate({ kind: 'action_skipped', action_id: actionId, source: 'mobile' });
  };

  if (!Number.isFinite(episodeId)) {
    return <ErrorState c={c} message="无效的 Episode 编号" />;
  }
  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
      </SafeAreaView>
    );
  }
  if (isError || !ep) {
    return <ErrorState c={c} message="加载失败, 下拉重试" onRetry={refetch} />;
  }

  const sortedActions = [...ep.actions].sort((a, b) => a.sequence - b.sequence);
  const pendingId = feedback.isPending ? feedback.variables?.action_id : undefined;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={{ padding: 6 }}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>跑后恢复</Text>
        <RiskPill level={ep.risk_level} c={c} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxxl }}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />
        }
      >
        {!!ep.headline && (
          <View style={styles.headlineCard}>
            <Text style={styles.headlineText}>{ep.headline}</Text>
          </View>
        )}

        {ep.risk_flags && ep.risk_flags.length > 0 && (
          <View style={styles.flagsRow}>
            {ep.risk_flags.map((f, i) => (
              <View key={i} style={styles.flagChip}>
                <Text style={styles.flagText}>{_humanFlag(f)}</Text>
              </View>
            ))}
          </View>
        )}

        <View style={styles.protocolMeta}>
          <Text style={styles.protocolText}>
            {ep.protocol_slug
              ? `方案 ${ep.protocol_slug}@${ep.protocol_version}`
              : '常规恢复'}
            {' · '}
            完成 {ep.actions_done}/{ep.actions_total}
          </Text>
        </View>

        {sortedActions.map((a) => (
          <ActionGraphCard
            key={a.id}
            action={a}
            onDone={onDone}
            onSkip={onSkip}
            pending={pendingId === a.id}
          />
        ))}

        {ep.status === 'closed' && ep.outcome?.summary && (
          <ReflectionCard outcome={ep.outcome} c={c} />
        )}

        <Text style={styles.disclaimer}>
          以上建议仅为运动恢复参考, 非医疗处方. 如症状持续或加重, 请咨询医生.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function ErrorState({ c, message, onRetry }: { c: ColorPalette; message: string; onRetry?: () => void }) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.bgPrimary }} edges={['top']}>
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <Ionicons name="alert-circle-outline" size={42} color={c.labelTertiary} />
        <Text style={{ color: c.labelSecondary, marginTop: 12 }}>{message}</Text>
        {!!onRetry && (
          <TouchableOpacity
            onPress={() => onRetry()}
            style={{
              marginTop: 18, paddingHorizontal: 20, paddingVertical: 10,
              borderRadius: 999, backgroundColor: c.brand,
            }}
          >
            <Text style={{ color: '#fff', fontWeight: '600' }}>重试</Text>
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

function ReflectionCard({ outcome, c }: { outcome: EpisodeOutcome; c: ColorPalette }) {
  const styles = useMemo(() => createReflectionStyles(c), [c]);
  const delta = outcome.metrics_delta || {};
  const chips: { label: string; tone: 'good' | 'bad' | 'neutral' }[] = [];

  const hrvD = delta.hrv_delta_vs_baseline;
  if (typeof hrvD === 'number') {
    const sign = hrvD >= 0 ? '+' : '';
    chips.push({
      label: `HRV ${sign}${hrvD.toFixed(0)} ms`,
      tone: hrvD >= 3 ? 'good' : hrvD <= -5 ? 'bad' : 'neutral',
    });
  } else if (typeof delta.hrv_next_morning === 'number') {
    chips.push({ label: `HRV ${delta.hrv_next_morning} ms`, tone: 'neutral' });
  }

  if (typeof delta.sleep_score_next_night === 'number') {
    const s = delta.sleep_score_next_night;
    chips.push({
      label: `睡眠 ${s}`,
      tone: s >= 80 ? 'good' : s <= 60 ? 'bad' : 'neutral',
    });
  }
  if (typeof delta.sleep_delta_min_vs_baseline === 'number') {
    const m = delta.sleep_delta_min_vs_baseline;
    const sign = m >= 0 ? '+' : '';
    chips.push({
      label: `时长 ${sign}${m} 分`,
      tone: m >= 0 ? 'good' : m <= -30 ? 'bad' : 'neutral',
    });
  }

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Ionicons name="sparkles-outline" size={16} color={c.brand} />
        <Text style={styles.title}>次日复盘</Text>
      </View>
      <Text style={styles.summary}>{outcome.summary}</Text>
      {chips.length > 0 && (
        <View style={styles.chipsRow}>
          {chips.map((ch, i) => (
            <View
              key={i}
              style={[
                styles.chip,
                ch.tone === 'good' && { backgroundColor: c.tintGreen },
                ch.tone === 'bad' && { backgroundColor: c.tintRed },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  ch.tone === 'good' && { color: c.green },
                  ch.tone === 'bad' && { color: c.red },
                ]}
              >
                {ch.label}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const createReflectionStyles = (c: ColorPalette) =>
  StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      marginTop: spacing.md,
      ...shadows.subtle,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginBottom: spacing.sm,
    },
    title: {
      fontSize: 13,
      fontWeight: '700',
      color: c.brand,
      letterSpacing: 0.3,
    },
    summary: {
      fontSize: 14,
      lineHeight: 21,
      color: c.labelPrimary,
    },
    chipsRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: spacing.sm,
      marginTop: spacing.md,
    },
    chip: {
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: 999,
      backgroundColor: c.bgElevated,
    },
    chipText: {
      fontSize: 12,
      fontWeight: '600',
      color: c.labelSecondary,
    },
  });

function RiskPill({ level, c }: { level: RiskLevel; c: ColorPalette }) {
  const map: Record<RiskLevel, { label: string; color: string; bg: string }> = {
    L0: { label: '常规', color: c.green, bg: c.tintGreen },
    L1: { label: '关注', color: c.amber, bg: c.tintAmber },
    L2: { label: '观察', color: c.orange, bg: c.tintOrange },
    L3: { label: '高风险', color: c.red, bg: c.tintRed },
    L4: { label: '紧急', color: c.red, bg: c.tintRed },
  };
  const s = map[level] || map.L0;
  return (
    <View style={{
      paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999,
      backgroundColor: s.bg,
    }}>
      <Text style={{ fontSize: 12, fontWeight: '700', color: s.color }}>{s.label}</Text>
    </View>
  );
}

function _humanFlag(flag: string): string {
  // "redflag:chest_pain" → "急症: 胸痛"
  // "heat_32C" → "高温 32°C"
  // "sleep_short_4.5h" → "睡眠不足 4.5h"
  // "acwr_1.65" → "训练负荷 1.65"
  if (flag.startsWith('redflag:')) {
    const name = flag.slice(8);
    const map: Record<string, string> = {
      chest_pain: '胸痛',
      severe_chest_pain: '严重胸痛',
      syncope: '晕厥',
      fainting: '昏厥',
      severe_dyspnea: '严重呼吸困难',
      severe_breathlessness: '严重气短',
      confusion: '意识混乱',
      stroke_signs: '中风征兆',
      slurred_speech: '言语不清',
      severe_headache_sudden: '突发剧烈头痛',
    };
    return `急症: ${map[name] || name}`;
  }
  if (flag.startsWith('heat_')) return `高温 ${flag.slice(5)}`;
  if (flag.startsWith('sleep_short_')) return `睡眠不足 ${flag.slice(12)}`;
  if (flag.startsWith('acwr_')) return `训练负荷 ${flag.slice(5)}`;
  if (flag.startsWith('chest_discomfort')) return '胸部不适';
  if (flag.startsWith('pain_')) return `疼痛 ${flag.slice(5)}/10`;
  return flag;
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    header: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md,
      paddingTop: spacing.sm,
      paddingBottom: spacing.md,
      gap: spacing.md,
    },
    headerTitle: {
      flex: 1, fontSize: 18, fontWeight: '700', color: c.labelPrimary,
    },
    headlineCard: {
      backgroundColor: c.brandLight,
      borderRadius: radii.lg,
      padding: spacing.lg,
      marginBottom: spacing.md,
    },
    headlineText: {
      fontSize: 15, lineHeight: 22, fontWeight: '500',
      color: c.labelPrimary,
    },
    flagsRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: spacing.sm,
      marginBottom: spacing.md,
    },
    flagChip: {
      backgroundColor: c.tintAmber,
      paddingHorizontal: 10,
      paddingVertical: 5,
      borderRadius: 999,
    },
    flagText: { fontSize: 12, color: c.amber, fontWeight: '600' },
    protocolMeta: {
      marginBottom: spacing.md,
    },
    protocolText: {
      fontSize: 12, color: c.labelTertiary, fontWeight: '500',
    },
    disclaimer: {
      marginTop: spacing.lg,
      fontSize: 11,
      lineHeight: 16,
      color: c.labelTertiary,
      textAlign: 'center',
      fontStyle: 'italic',
    },
  });
