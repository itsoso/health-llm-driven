/**
 * AI 记忆页 — 让用户看到 / 改 / 删 AI 关于他的笔记.
 *
 * P5 (2026-05-04): 用户有 69 个 memory_facts 但没地方看. 信任建立的关键是
 * "AI 不是黑盒, 我能管教". 这个页让用户:
 * - 看见 AI 记得他什么 (按主题分组)
 * - 一键 "这条不对" → soft-delete (后端 superseded_at 写入)
 * - 看到 confidence (低置信度 chip 颜色不同, 提示用户审视)
 *
 * 默认显示 semantic + episodic (长期 + 近期). working/procedural 折叠 (噪声).
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextStyle,
  Alert, RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import {
  listMemoryFacts,
  dismissMemoryFact,
  getMemoryStats,
  predicateLabel,
  groupByPredicate,
  tierLabel,
  type MemoryFact,
} from '../services/memory';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createMemoryAgentContext } from '../utils/agentContext';

export default function MemoryScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [showWorking, setShowWorking] = useState(false);

  const factsQuery = useQuery({
    queryKey: ['memory-facts', showWorking ? 'all' : 'main'],
    queryFn: () => listMemoryFacts(
      showWorking ? { limit: 200 } : { limit: 200, min_confidence: 0.3 },
    ),
    staleTime: 30_000,
  });
  const statsQuery = useQuery({
    queryKey: ['memory-stats'],
    queryFn: getMemoryStats,
    staleTime: 60_000,
  });

  const dismissMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      dismissMemoryFact(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['memory-facts'] });
      qc.invalidateQueries({ queryKey: ['memory-stats'] });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    },
    onError: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert('删除失败', '请稍后重试');
    },
  });

  const facts = factsQuery.data ?? [];

  // 按 predicate 分组. working tier 的 fact 单独走折叠区
  const mainFacts = useMemo(
    () => facts.filter(f => showWorking || f.tier !== 'working'),
    [facts, showWorking],
  );
  const grouped = useMemo(() => groupByPredicate(mainFacts), [mainFacts]);

  const totalAll = useMemo(
    () => statsQuery.data?.by_tier.reduce((s, r) => s + r.total, 0) ?? 0,
    [statsQuery.data],
  );

  const handleDismiss = (fact: MemoryFact) => {
    Alert.alert(
      '这条记忆不对？',
      `"${fact.object_value}"\n\n标记后 AI 之后不会再用这条信息。这个动作不会撤销。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '不对，删除',
          style: 'destructive',
          onPress: () => dismissMutation.mutate({ id: fact.id, reason: 'user_dismissed' }),
        },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>AI 关于你的笔记</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={factsQuery.isFetching}
            onRefresh={() => factsQuery.refetch()}
            tintColor={c.brand}
          />
        }
      >
        {/* Stats header */}
        <View style={styles.statCard}>
          <Text style={txt.statHero}>
            AI 记得你 {totalAll} 条笔记
          </Text>
          {statsQuery.data?.by_tier.length ? (
            <View style={styles.statRow}>
              {statsQuery.data.by_tier.map(t => (
                <View key={t.tier} style={styles.statPill}>
                  <Text style={txt.statPillLabel}>{tierLabel(t.tier)}</Text>
                  <Text style={txt.statPillValue}>{t.total}</Text>
                </View>
              ))}
            </View>
          ) : null}
          <Text style={txt.heroHint}>
            点 "这条不对" AI 之后不会再用这条信息
          </Text>
        </View>

        <AgentFeedbackLink
          label="跟 Agent 校准这些记忆"
          accessibilityLabel="跟 Agent 校准这些记忆"
          prompt="请基于 AI 当前关于我的记忆，帮我找出可能不准确、过期或需要补充的内容，并说明这些记忆会怎样影响健康建议。"
          context={createMemoryAgentContext({ facts: mainFacts as any, stats: statsQuery.data as any })}
          badge={`AI 记忆 ${totalAll} 条`}
        />

        {/* Loading / Empty */}
        {factsQuery.isLoading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="small" color={c.brand} />
          </View>
        ) : null}

        {!factsQuery.isLoading && grouped.length === 0 ? (
          <View style={styles.emptyWrap}>
            <Ionicons name="bookmark-outline" size={36} color={c.labelTertiary} />
            <Text style={txt.empty}>
              AI 还没记下你的事实{'\n'}
              多对话几次，AI 会自动从聊天里提炼"过敏 / 偏好 / 病史"等长期记忆
            </Text>
          </View>
        ) : null}

        {/* Grouped facts */}
        {grouped.map(group => (
          <View key={group.predicate} style={styles.groupCard}>
            <Text style={txt.groupTitle}>{group.label}</Text>
            {group.facts.map(fact => (
              <FactRow
                key={fact.id}
                fact={fact}
                onDismiss={() => handleDismiss(fact)}
                disabled={dismissMutation.isPending}
                c={c}
              />
            ))}
          </View>
        ))}

        {/* Toggle working tier */}
        <Pressable
          style={({ pressed }) => [styles.toggleBtn, pressed && { opacity: 0.6 }]}
          onPress={() => setShowWorking(v => !v)}
          accessibilityRole="button"
        >
          <Ionicons
            name={showWorking ? 'eye-off-outline' : 'eye-outline'}
            size={14}
            color={c.labelSecondary}
          />
          <Text style={txt.toggleText}>
            {showWorking ? '隐藏临时记忆' : '查看临时记忆 (噪声大)'}
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

interface FactRowProps {
  fact: MemoryFact;
  onDismiss: () => void;
  disabled: boolean;
  c: ColorPalette;
}

function FactRow({ fact, onDismiss, disabled, c }: FactRowProps) {
  const txt = createTxt(c);
  const conf = fact.effective_confidence ?? fact.confidence;
  const confColor =
    conf >= 0.7 ? c.brand :
    conf >= 0.4 ? c.amber :
    c.labelTertiary;
  return (
    <View style={factRowStyles.row}>
      <View style={factRowStyles.main}>
        <Text style={txt.factValue} numberOfLines={3}>
          {fact.object_value}
          {fact.object_unit ? ` ${fact.object_unit}` : ''}
        </Text>
        <View style={factRowStyles.meta}>
          <View style={[factRowStyles.confDot, { backgroundColor: confColor }]} />
          <Text style={[txt.factMeta, { color: confColor }]}>
            置信度 {Math.round(conf * 100)}%
          </Text>
          {fact.reinforcement_count > 1 ? (
            <Text style={txt.factMeta}> · 强化 {fact.reinforcement_count} 次</Text>
          ) : null}
        </View>
      </View>
      <Pressable
        style={({ pressed }) => [
          factRowStyles.dismissBtn,
          pressed && { opacity: 0.6 },
          disabled && { opacity: 0.4 },
        ]}
        onPress={onDismiss}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel="标记这条不对"
      >
        <Text style={[txt.dismissText, { color: c.red }]}>不对</Text>
      </Pressable>
    </View>
  );
}

const factRowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm + 2,
    gap: spacing.sm,
  },
  main: { flex: 1, gap: 4 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  confDot: { width: 6, height: 6, borderRadius: 3 },
  dismissBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radii.full,
  },
});

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    content: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 40 },
    statCard: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      gap: spacing.sm,
      ...shadows.subtle,
    },
    statRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    statPill: {
      flexDirection: 'row',
      gap: 4,
      paddingHorizontal: spacing.md,
      paddingVertical: 5,
      borderRadius: radii.full,
      backgroundColor: c.bgPrimary,
      alignItems: 'center',
    },
    groupCard: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      paddingHorizontal: spacing.lg,
      paddingTop: spacing.md,
      paddingBottom: 4,
      ...shadows.subtle,
    },
    loadingWrap: { paddingVertical: 30, alignItems: 'center' },
    emptyWrap: {
      paddingVertical: 60,
      paddingHorizontal: 30,
      alignItems: 'center',
      gap: 12,
    },
    toggleBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      alignSelf: 'center',
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    statHero: { fontSize: 18, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    statPillLabel: { fontSize: 12, color: c.labelSecondary } as TextStyle,
    statPillValue: { fontSize: 13, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    heroHint: { fontSize: 12, color: c.labelTertiary, lineHeight: 18 } as TextStyle,
    groupTitle: {
      fontSize: 12,
      fontWeight: '600',
      color: c.labelSecondary,
      letterSpacing: 0.5,
      marginBottom: 4,
    } as TextStyle,
    factValue: { fontSize: 15, color: c.labelPrimary, lineHeight: 21 } as TextStyle,
    factMeta: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    dismissText: { fontSize: 13, fontWeight: '500' } as TextStyle,
    empty: { fontSize: 13, color: c.labelTertiary, textAlign: 'center', lineHeight: 19 } as TextStyle,
    toggleText: { fontSize: 13, color: c.labelSecondary } as TextStyle,
  };
}
