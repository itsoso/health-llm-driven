/**
 * 「小巴对你的了解」— 记忆透明可纠 (Slice 5, 2026-07-07).
 *
 * 让用户看见小巴根据对话/数据记住了什么, 并能一键纠正:
 * - 每条记忆 = 人读句子 + 视觉弱化的置信度 + 「不对」(dismiss) / 「确认」(reinforce)
 *   双动作, 乐观更新 + 失败回滚 toast.
 * - 低置信 (effective_confidence < 0.4) 默认折叠, 防"满屏噪音事实"
 *   (简报记忆过度抽取的历史坑).
 * - 进屏推导矛盾对 (同 subject、谓词方向互斥) → 顶部横幅并排让用户裁决, 走 supersede.
 *
 * 人格 = 小巴 (忠实的边牧参谋): 忠实呈现它记住的, 不臆造; 你说不对就改。
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
  listMyFacts,
  getMyStats,
  dismissFact,
  reinforceFact,
  supersedeFact,
  findContradictionPairs,
  effectiveConfidence,
  factSentence,
  primarySourceType,
  sourceTypeLabel,
  LOW_CONFIDENCE_THRESHOLD,
  type MemoryFact,
} from '../services/memoryFacts';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, SemanticPalette, useTheme } from '../hooks/useTheme';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import ContradictionBanner from '../components/memory/ContradictionBanner';
import { createMemoryAgentContext } from '../utils/agentContext';

const FACTS_KEY = ['memory-facts', 'transparency'] as const;
const STATS_KEY = ['memory-facts', 'stats'] as const;

function splitByConfidence(facts: MemoryFact[]): { high: MemoryFact[]; low: MemoryFact[] } {
  const sorted = [...facts].sort((a, b) => effectiveConfidence(b) - effectiveConfidence(a));
  return {
    high: sorted.filter(f => effectiveConfidence(f) >= LOW_CONFIDENCE_THRESHOLD),
    low: sorted.filter(f => effectiveConfidence(f) < LOW_CONFIDENCE_THRESHOLD),
  };
}

// optional-call short-circuits arg evaluation when the fn is absent (test mocks),
// so this never throws even if the haptics module is partially mocked.
function hapticSuccess() {
  try { Haptics.notificationAsync?.(Haptics.NotificationFeedbackType.Success); } catch { /* noop */ }
}
function hapticError() {
  try { Haptics.notificationAsync?.(Haptics.NotificationFeedbackType.Error); } catch { /* noop */ }
}

export default function MemoryScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c, s, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [showLow, setShowLow] = useState(false);
  const [bannerCollapsed, setBannerCollapsed] = useState(false);

  const factsQuery = useQuery({
    queryKey: FACTS_KEY,
    queryFn: () => listMyFacts({ limit: 200 }),
    staleTime: 30_000,
  });
  const statsQuery = useQuery({
    queryKey: STATS_KEY,
    queryFn: getMyStats,
    staleTime: 60_000,
  });

  const facts = factsQuery.data ?? [];
  const { high, low } = useMemo(() => splitByConfidence(facts), [facts]);
  const pairs = useMemo(() => findContradictionPairs(facts), [facts]);

  const totalAll = useMemo(
    () => statsQuery.data?.by_tier.reduce((sum, r) => sum + r.total, 0) ?? facts.length,
    [statsQuery.data, facts.length],
  );

  const notifyError = (title: string, msg: string) => {
    hapticError();
    Alert.alert(title, msg);
  };

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: FACTS_KEY });
    qc.invalidateQueries({ queryKey: STATS_KEY });
  };

  // ── 「不对」— dismiss (乐观移除 + 失败回滚) ──
  const dismissMutation = useMutation({
    mutationFn: (id: number) => dismissFact(id),
    onMutate: async (id: number) => {
      await qc.cancelQueries({ queryKey: FACTS_KEY });
      const prev = qc.getQueryData<MemoryFact[]>(FACTS_KEY);
      qc.setQueryData<MemoryFact[]>(FACTS_KEY, (old) => (old ?? []).filter(f => f.id !== id));
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(FACTS_KEY, ctx.prev);
      notifyError('没保存成功', '这条记忆还留着，稍后再试一次。');
    },
    onSuccess: hapticSuccess,
    onSettled: invalidateAll,
  });

  // ── 「确认」— reinforce (乐观提升置信度 + 失败回滚) ──
  const reinforceMutation = useMutation({
    mutationFn: (id: number) => reinforceFact(id),
    onMutate: async (id: number) => {
      await qc.cancelQueries({ queryKey: FACTS_KEY });
      const prev = qc.getQueryData<MemoryFact[]>(FACTS_KEY);
      qc.setQueryData<MemoryFact[]>(FACTS_KEY, (old) => (old ?? []).map(f => f.id === id ? {
        ...f,
        reinforcement_count: (f.reinforcement_count ?? 0) + 1,
        confidence: Math.min(1, f.confidence + 0.05),
        effective_confidence: Math.min(1, effectiveConfidence(f) + 0.05),
      } : f));
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(FACTS_KEY, ctx.prev);
      notifyError('没确认成功', '稍后再试一次。');
    },
    onSuccess: hapticSuccess,
    onSettled: invalidateAll,
  });

  // ── 矛盾裁决 — supersede (保留一条, 归档另一条) ──
  const supersedeMutation = useMutation({
    mutationFn: ({ keepId, dropId }: { keepId: number; dropId: number }) =>
      supersedeFact(keepId, dropId),
    onMutate: async ({ dropId }) => {
      await qc.cancelQueries({ queryKey: FACTS_KEY });
      const prev = qc.getQueryData<MemoryFact[]>(FACTS_KEY);
      qc.setQueryData<MemoryFact[]>(FACTS_KEY, (old) => (old ?? []).filter(f => f.id !== dropId));
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(FACTS_KEY, ctx.prev);
      notifyError('没保存成功', '两条记忆都还在，稍后再试。');
    },
    onSuccess: hapticSuccess,
    onSettled: invalidateAll,
  });

  const busy = dismissMutation.isPending || reinforceMutation.isPending || supersedeMutation.isPending;
  const showBanner = pairs.length > 0 && !bannerCollapsed;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>小巴对你的了解</Text>
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
        {/* 矛盾裁决横幅 */}
        {showBanner ? (
          <ContradictionBanner
            pairs={pairs}
            onKeep={(keepId, dropId) => supersedeMutation.mutate({ keepId, dropId })}
            onCollapse={() => setBannerCollapsed(true)}
            disabled={busy}
            c={c}
            s={s}
          />
        ) : null}

        {/* Hero */}
        <View style={styles.heroCard}>
          <Text style={txt.heroTitle}>小巴记住了你 {totalAll} 条</Text>
          <Text style={txt.heroHint}>
            这些是小巴从你的对话和数据里记下的。看到不对的，点「不对」它就不再用；点「确认」让它记得更牢。
          </Text>
        </View>

        <AgentFeedbackLink
          label="跟小巴聊聊这些记忆"
          accessibilityLabel="跟小巴聊聊这些记忆"
          prompt="请基于你当前关于我的记忆，帮我找出可能不准确、过期或需要补充的内容，并说明这些记忆会怎样影响你给我的健康建议。"
          context={createMemoryAgentContext({ facts: high as any, stats: statsQuery.data as any })}
          badge={`记忆 ${totalAll} 条`}
        />

        {/* Loading / Empty */}
        {factsQuery.isLoading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="small" color={c.brand} />
          </View>
        ) : null}

        {!factsQuery.isLoading && facts.length === 0 ? (
          <View style={styles.emptyWrap}>
            <Ionicons name="sparkles-outline" size={34} color={c.labelTertiary} />
            <Text style={txt.empty}>
              小巴还没记下关于你的事{'\n'}
              多聊几次，它会自动记住你的过敏、偏好、病史这类长期信息
            </Text>
          </View>
        ) : null}

        {/* 高置信事实列表 */}
        {high.length > 0 ? (
          <View style={styles.listCard}>
            {high.map((fact, idx) => (
              <FactRow
                key={fact.id}
                fact={fact}
                isLast={idx === high.length - 1}
                onDismiss={() => dismissMutation.mutate(fact.id)}
                onConfirm={() => reinforceMutation.mutate(fact.id)}
                disabled={busy}
                c={c}
                s={s}
              />
            ))}
          </View>
        ) : null}

        {/* 低置信折叠 */}
        {low.length > 0 ? (
          <View>
            <Pressable
              style={({ pressed }) => [styles.toggleBtn, pressed && { opacity: 0.6 }]}
              onPress={() => setShowLow(v => !v)}
              accessibilityRole="button"
              accessibilityLabel={showLow ? '收起低置信记忆' : '展开低置信记忆'}
            >
              <Ionicons
                name={showLow ? 'chevron-up' : 'chevron-down'}
                size={15}
                color={c.labelSecondary}
              />
              <Text style={txt.toggleText}>
                {showLow ? '收起' : `低置信记忆 ${low.length} 条`}
              </Text>
            </Pressable>
            {showLow ? (
              <View style={styles.listCard}>
                {low.map((fact, idx) => (
                  <FactRow
                    key={fact.id}
                    fact={fact}
                    isLast={idx === low.length - 1}
                    onDismiss={() => dismissMutation.mutate(fact.id)}
                    onConfirm={() => reinforceMutation.mutate(fact.id)}
                    disabled={busy}
                    c={c}
                    s={s}
                  />
                ))}
              </View>
            ) : null}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

// ─────────────────────────── FactRow ───────────────────────────

interface FactRowProps {
  fact: MemoryFact;
  isLast: boolean;
  onDismiss: () => void;
  onConfirm: () => void;
  disabled: boolean;
  c: ColorPalette;
  s: SemanticPalette;
}

function FactRow({ fact, isLast, onDismiss, onConfirm, disabled, c, s }: FactRowProps) {
  const txt = createTxt(c);
  const conf = effectiveConfidence(fact);
  const pct = Math.round(conf * 100);
  const srcType = primarySourceType(fact);
  const srcLabel = srcType && srcType !== 'manual' ? sourceTypeLabel(srcType) : null;

  return (
    <View
      style={[
        factRowStyles.row,
        !isLast && { borderBottomColor: c.separator, borderBottomWidth: StyleSheet.hairlineWidth },
      ]}
    >
      <Text style={txt.factSentence}>{factSentence(fact)}</Text>

      {/* 视觉弱化的置信度: 细条 + 百分比 */}
      <View style={factRowStyles.confRow}>
        <View style={[factRowStyles.confTrack, { backgroundColor: c.fill }]}>
          <View
            style={[
              factRowStyles.confFill,
              { width: `${Math.max(4, pct)}%`, backgroundColor: c.brand, opacity: 0.55 },
            ]}
          />
        </View>
        <Text style={txt.confPct}>{pct}%</Text>
        {srcLabel ? <Text style={txt.srcChip}>· 来自{srcLabel}</Text> : null}
        {fact.reinforcement_count > 1 ? (
          <Text style={txt.srcChip}>· 确认{fact.reinforcement_count}次</Text>
        ) : null}
      </View>

      <View style={factRowStyles.actions}>
        <Pressable
          testID={`memory-confirm-${fact.id}`}
          onPress={onConfirm}
          disabled={disabled}
          hitSlop={6}
          accessibilityRole="button"
          accessibilityLabel="确认这条记忆"
          style={({ pressed }) => [
            factRowStyles.confirmBtn,
            { borderColor: s.success.solid },
            pressed && { opacity: 0.6 },
            disabled && { opacity: 0.4 },
          ]}
        >
          <Ionicons name="checkmark" size={14} color={s.success.fg} />
          <Text style={[txt.confirmText, { color: s.success.fg }]}>确认</Text>
        </Pressable>
        <Pressable
          testID={`memory-dismiss-${fact.id}`}
          onPress={onDismiss}
          disabled={disabled}
          hitSlop={6}
          accessibilityRole="button"
          accessibilityLabel="标记这条不对"
          style={({ pressed }) => [
            factRowStyles.dismissBtn,
            pressed && { opacity: 0.6 },
            disabled && { opacity: 0.4 },
          ]}
        >
          <Text style={[txt.dismissText, { color: c.labelSecondary }]}>不对</Text>
        </Pressable>
      </View>
    </View>
  );
}

// ─────────────────────────── styles ───────────────────────────

const factRowStyles = StyleSheet.create({
  row: { paddingVertical: spacing.md, gap: 8 },
  confRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  confTrack: { flex: 1, minWidth: 60, maxWidth: 120, height: 4, borderRadius: 2, overflow: 'hidden' },
  confFill: { height: 4, borderRadius: 2 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  confirmBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    borderRadius: radii.full, borderWidth: StyleSheet.hairlineWidth,
  },
  dismissBtn: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radii.full },
});

function createStyles(c: ColorPalette, _isDark: boolean) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    },
    content: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 40 },
    heroCard: {
      backgroundColor: c.bgCard, borderRadius: radii.lg, padding: spacing.lg, gap: 6,
      ...shadows.subtle,
    },
    listCard: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      paddingHorizontal: spacing.lg, ...shadows.subtle,
    },
    loadingWrap: { paddingVertical: 30, alignItems: 'center' },
    emptyWrap: { paddingVertical: 60, paddingHorizontal: 30, alignItems: 'center', gap: 12 },
    toggleBtn: {
      flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'center',
      paddingVertical: spacing.sm, paddingHorizontal: spacing.md,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    heroTitle: { fontSize: 18, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    heroHint: { fontSize: 13, color: c.labelSecondary, lineHeight: 19 } as TextStyle,
    factSentence: { fontSize: 15, color: c.labelPrimary, lineHeight: 21 } as TextStyle,
    confPct: { fontSize: 11, color: c.labelTertiary, fontVariant: ['tabular-nums'] } as TextStyle,
    srcChip: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    confirmText: { fontSize: 13, fontWeight: '500' } as TextStyle,
    dismissText: { fontSize: 13, fontWeight: '500' } as TextStyle,
    empty: { fontSize: 13, color: c.labelTertiary, textAlign: 'center', lineHeight: 19 } as TextStyle,
    toggleText: { fontSize: 13, color: c.labelSecondary } as TextStyle,
    bannerTitle: { flex: 1, fontSize: 14, fontWeight: '700' } as TextStyle,
    bannerHint: { fontSize: 12, lineHeight: 17 } as TextStyle,
    optionText: { fontSize: 13, color: c.labelPrimary, lineHeight: 18 } as TextStyle,
    vsText: { fontSize: 11, color: c.labelTertiary } as TextStyle,
  };
}
