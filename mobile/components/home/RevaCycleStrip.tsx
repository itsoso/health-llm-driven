/**
 * RevaCycleStrip —— 首页 90 天代谢周期细条(Reva 重设计第 4 块)。
 *
 * 数据来自 useActiveCycle(同 MetabolicEntryCard 的源)。
 *   - 有进行中周期:DayProgress(第 N / total 天)+ 一行主指标 baseline → target(mono,改善绿)。
 *   - 无周期 / 加载中 / 失败:诚实退化为引导条(去 /metabolic-profile 开始干预),不假装。
 * 点击进 /intervention-cycle(进行中)或 /metabolic-profile(未开始)。
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { revaColors as C, revaSemantic } from '../../constants/revaTheme';
import { Card, DayProgress, Icon, SectionLabel } from '../reva/RevaKit';
import { useActiveCycle } from '../../hooks/useHealthOs';
import type { InterventionCycle, OutcomeMetric } from '../../services/healthOs';

function daysBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  if (Number.isNaN(da) || Number.isNaN(db)) return null;
  return Math.round((db - da) / 86400000);
}

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '待定';
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10);
}

function pickPrimaryOutcome(outcomes: OutcomeMetric[] = []): OutcomeMetric | null {
  return outcomes.find((o) => o.status !== 'met') ?? outcomes[0] ?? null;
}

export default function RevaCycleStrip() {
  const router = useRouter();
  const { data: cycle, isLoading } = useActiveCycle();
  const active = cycle?.status === 'active';

  return (
    <View>
      <SectionLabel>90 天代谢周期</SectionLabel>
      {active && cycle ? (
        <ActiveStrip cycle={cycle} onPress={() => router.push('/intervention-cycle' as any)} />
      ) : (
        <IdleStrip
          loading={isLoading}
          onPress={() => router.push('/metabolic-profile' as any)}
        />
      )}
    </View>
  );
}

function ActiveStrip({ cycle, onPress }: { cycle: InterventionCycle; onPress: () => void }) {
  const total = daysBetween(cycle.start_date, cycle.planned_end_date) ?? 90;
  const elapsed = daysBetween(cycle.start_date, new Date().toISOString()) ?? 0;
  const day = Math.max(1, Math.min(total, elapsed + 1));
  const outcome = pickPrimaryOutcome(cycle.outcomes ?? []);
  const improving = outcome?.status === 'improving' || outcome?.status === 'met';

  return (
    <Card
      onPress={onPress}
      testID="home-health-cycle-cockpit"
      accessibilityLabel="查看 90 天健康周期"
    >
      <DayProgress day={day} total={total} />
      {outcome ? (
        <View style={styles.metricRow}>
          <Text style={styles.metricLabel} numberOfLines={1}>
            {outcome.display}
          </Text>
          <Text style={styles.metricValue}>
            {fmt(outcome.baseline_value)}
            <Text style={styles.arrow}>{'  →  '}</Text>
            <Text style={improving ? styles.target : styles.metricValue}>
              {fmt(outcome.target_value)}
              {outcome.unit ? ` ${outcome.unit}` : ''}
            </Text>
          </Text>
        </View>
      ) : (
        <Text style={styles.idleSub}>先锁定体检基线,再追踪复查变化</Text>
      )}
    </Card>
  );
}

function IdleStrip({ loading, onPress }: { loading: boolean; onPress: () => void }) {
  return (
    <Card onPress={onPress} accessibilityLabel="代谢健康,查看代谢风险并开始 90 天干预">
      <View style={styles.idleRow}>
        <View style={styles.idleIcon}>
          <Icon name="activity" size={17} color={C.green500} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.idleTitle}>
            {loading ? '正在同步周期' : '看风险 · 开始 90 天干预'}
          </Text>
          <Text style={styles.idleSub}>
            {loading ? '读取体检和行动目标中' : '把体检异常项变成可执行的 90 天'}
          </Text>
        </View>
        <Icon name="chevron-right" size={18} color={C.ink4} />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  metricRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 14,
  },
  metricLabel: { fontSize: 13, fontWeight: '600', color: C.ink2, flex: 1, minWidth: 0 },
  metricValue: { fontFamily: 'IBMPlexMono', fontSize: 15, fontWeight: '500', color: C.ink1 },
  arrow: { fontFamily: 'IBMPlexMono', color: C.ink3 },
  target: { fontFamily: 'IBMPlexMono', fontSize: 15, fontWeight: '500', color: revaSemantic.normal.fg },
  idleRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  idleIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  idleTitle: { fontSize: 15, fontWeight: '700', color: C.ink1 },
  idleSub: { fontSize: 12.5, color: C.ink3, marginTop: 3 },
});
