/**
 * /my-progress —— 用户视角的执行监测看板 (G-W5, 2026-05-12).
 *
 * 跟 /admin/wscla 区别: 这个是 user 自己看, 数据只是自己的.
 * 核心目的: 让用户感受"AI 给我的建议有没有真的让我变好" — 这是
 * SelfDecode/Rootine 都不做的差异化能力.
 */

import React, { useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchMyProgress, type ProgressDashboard, type ProgressCard } from '../services/myProgress';
import { spacing, radii } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';

const WINDOW_OPTIONS = [
  { label: '7 天', days: 7 },
  { label: '30 天', days: 30 },
  { label: '90 天', days: 90 },
];

function pct(v: number | null): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

const OUTCOME_COLORS: Record<string, { bg: string; text: string; label: string; arrow: string }> = {
  improved: { bg: '#D1FAE5', text: '#065F46', label: '改善', arrow: '↑' },
  unchanged: { bg: '#F1F5F9', text: '#475569', label: '稳定', arrow: '—' },
  worsened: { bg: '#FEE2E2', text: '#991B1B', label: '反向', arrow: '↓' },
  inconclusive: { bg: '#F1F5F9', text: '#94A3B8', label: '数据不足', arrow: '?' },
};

export default function MyProgressScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();
  const [days, setDays] = useState(30);

  const { data, isLoading, isRefetching, error } = useQuery<ProgressDashboard>({
    queryKey: ['my-progress', days],
    queryFn: () => fetchMyProgress(days),
    staleTime: 2 * 60 * 1000,
  });

  const onRefresh = () => qc.invalidateQueries({ queryKey: ['my-progress'] });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }
  if (error || !data) {
    return (
      <View style={styles.center}>
        <Text style={[styles.errorText, { color: c.labelPrimary }]}>加载失败</Text>
        <Text style={[styles.errorSub, { color: c.labelTertiary }]}>{String(error)}</Text>
      </View>
    );
  }

  const s = data.stats;
  const noCards = s.total_surfaced === 0;

  return (
    <>
      <Stack.Screen options={{ title: '我的进度', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          {/* 时间窗口 chip */}
          <View style={styles.chipRow}>
            {WINDOW_OPTIONS.map(opt => (
              <TouchableOpacity
                key={opt.days}
                onPress={() => setDays(opt.days)}
                style={[
                  styles.chip,
                  {
                    backgroundColor: days === opt.days ? c.brand : c.bgCard,
                    borderColor: days === opt.days ? c.brand : c.separator,
                  },
                ]}
              >
                <Text style={[styles.chipText, { color: days === opt.days ? '#fff' : c.labelSecondary }]}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {noCards ? (
            <View style={[styles.emptyCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Ionicons name="leaf-outline" size={32} color={c.labelTertiary} />
              <Text style={[styles.emptyTitle, { color: c.labelPrimary }]}>
                这段时间还没有 AI 建议
              </Text>
              <Text style={[styles.emptySub, { color: c.labelTertiary }]}>
                Agent 主动产建议:{'\n'}
                · Safety 触发的告警 (心率/睡眠/血压异常){'\n'}
                · 周日 21:07 自动生成的本周建议{'\n'}
                · Specialist 在你提问时产出的建议
              </Text>
            </View>
          ) : (
            <>
              {/* 顶部核心数 */}
              <View style={[styles.heroCard, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
                <Text style={[styles.heroLabel, { color: c.brand }]}>已闭环且改善的建议</Text>
                <View style={styles.heroNumRow}>
                  <Text style={[styles.heroNum, { color: c.brand }]}>{s.improved}</Text>
                  <Text style={[styles.heroDenom, { color: c.brand }]}> / {s.total_surfaced}</Text>
                </View>
                <Text style={[styles.heroSub, { color: c.brand }]}>
                  AI 这 {days} 天给了 {s.total_surfaced} 条建议, 你做完并改善 {s.improved} 条
                </Text>
              </View>

              {/* 核心 4 数 */}
              <View style={styles.statGrid}>
                <StatCell label="接受率" value={pct(s.acceptance_rate)} hint={`${s.accepted}/${s.accepted + s.declined}`} c={c} />
                <StatCell label="完成率" value={pct(s.completed && s.accepted ? s.completed / s.accepted : null)} hint={`${s.completed}/${s.accepted}`} c={c} />
                <StatCell label="验证率" value={pct(s.verification_rate)} hint={`${s.graded}/${s.completed}`} c={c} />
                <StatCell label="改善率" value={pct(s.improvement_rate)} hint={`${s.improved}/${s.graded}`} c={c} />
              </View>

              {/* outcome 分布 */}
              <View style={[styles.outcomeRow, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                <OutcomePill label="改善" count={s.improved} color="#10B981" total={s.graded} />
                <OutcomePill label="稳定" count={s.unchanged} color="#94A3B8" total={s.graded} />
                <OutcomePill label="反向" count={s.worsened} color="#EF4444" total={s.graded} />
                <OutcomePill label="不足" count={s.inconclusive} color="#CBD5E1" total={s.graded} />
              </View>

              {/* 验证中 */}
              {data.verifying_cards.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>
                    验证中 ({data.verifying_cards.length})
                  </Text>
                  <Text style={[styles.sectionSub, { color: c.labelTertiary }]}>
                    你已接受并做完, 等 Agent 拉数据评估
                  </Text>
                  {data.verifying_cards.map(card => (
                    <CardRow
                      key={card.id}
                      card={card}
                      onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                      c={c}
                    />
                  ))}
                </View>
              )}

              {/* 已闭环 */}
              {data.closed_cards.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>
                    已闭环 ({data.closed_cards.length})
                  </Text>
                  <Text style={[styles.sectionSub, { color: c.labelTertiary }]}>
                    Agent 自动评估完成, 看 metric 旅程
                  </Text>
                  {data.closed_cards.map(card => (
                    <CardRow
                      key={card.id}
                      card={card}
                      onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                      c={c}
                    />
                  ))}
                </View>
              )}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

// ─── 子组件 ─────────────────────────────────────────────────────────────

function StatCell({ label, value, hint, c }: any) {
  return (
    <View style={[styles.statCell, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <Text style={[styles.statLabel, { color: c.labelTertiary }]}>{label}</Text>
      <Text style={[styles.statValue, { color: c.labelPrimary }]}>{value}</Text>
      <Text style={[styles.statHint, { color: c.labelTertiary }]}>{hint}</Text>
    </View>
  );
}

function OutcomePill({ label, count, color, total }: { label: string; count: number; color: string; total: number }) {
  const pctVal = total > 0 ? (count / total) * 100 : 0;
  return (
    <View style={styles.outcomePill}>
      <Text style={[styles.outcomeLabel, { color }]}>{label}</Text>
      <Text style={[styles.outcomeCount, { color }]}>{count}</Text>
      <View style={styles.outcomeBarBg}>
        <View style={[styles.outcomeBarFill, { width: `${pctVal}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
}

function CardRow({ card, onPress, c }: { card: ProgressCard; onPress: () => void; c: any }) {
  const oc = card.outcome ? OUTCOME_COLORS[card.outcome] : null;
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.cardRow, { backgroundColor: c.bgCard, borderColor: c.separator }]}
    >
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={[styles.cardTitle, { color: c.labelPrimary }]} numberOfLines={2}>
          {card.title}
        </Text>
        {card.metric_key && card.baseline_value && card.actual_value && (
          <Text style={[styles.cardMetric, { color: c.labelTertiary }]}>
            {card.metric_key} {card.baseline_value} → {card.actual_value}
          </Text>
        )}
        {card.metric_key && !card.actual_value && (
          <Text style={[styles.cardMetric, { color: c.labelTertiary }]}>
            等待 {card.metric_key} 数据
          </Text>
        )}
      </View>
      {oc && (
        <View style={[styles.outcomeChip, { backgroundColor: oc.bg }]}>
          <Text style={[styles.outcomeChipText, { color: oc.text }]}>
            {oc.arrow} {oc.label}
            {card.effect_size != null && card.outcome !== 'inconclusive' && (
              ` ${(Math.abs(card.effect_size) * 100).toFixed(0)}%`
            )}
          </Text>
        </View>
      )}
      <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
    </TouchableOpacity>
  );
}

// ─── styles ─────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  errorText: { fontSize: 16, fontWeight: '600' },
  errorSub: { fontSize: 12 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  chipRow: { flexDirection: 'row', gap: 8 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
  },
  chipText: { fontSize: 13, fontWeight: '500' },
  emptyCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.xl,
    alignItems: 'center',
    gap: 12,
  },
  emptyTitle: { fontSize: 16, fontWeight: '600' },
  emptySub: { fontSize: 13, lineHeight: 20, textAlign: 'center' },
  heroCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.lg,
    gap: 6,
  },
  heroLabel: { fontSize: 13, fontWeight: '600' },
  heroNumRow: { flexDirection: 'row', alignItems: 'baseline' },
  heroNum: { fontSize: 36, fontWeight: '700' },
  heroDenom: { fontSize: 18, fontWeight: '500' },
  heroSub: { fontSize: 12, lineHeight: 18, opacity: 0.85 },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  statCell: {
    flexBasis: '47%',
    flexGrow: 1,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 4,
  },
  statLabel: { fontSize: 11, fontWeight: '500' },
  statValue: { fontSize: 22, fontWeight: '700' },
  statHint: { fontSize: 11 },
  outcomeRow: {
    flexDirection: 'row',
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  outcomePill: { flex: 1, gap: 4 },
  outcomeLabel: { fontSize: 11, fontWeight: '600' },
  outcomeCount: { fontSize: 18, fontWeight: '700' },
  outcomeBarBg: { height: 4, borderRadius: 2, backgroundColor: '#F1F5F9' },
  outcomeBarFill: { height: '100%', borderRadius: 2 },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  sectionSub: { fontSize: 12 },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  cardTitle: { fontSize: 14, fontWeight: '500', lineHeight: 20 },
  cardMetric: { fontSize: 11 },
  outcomeChip: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  outcomeChipText: { fontSize: 11, fontWeight: '700' },
});
