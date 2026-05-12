/**
 * 今日 Tab —— Phase 2 重做 (2026-05-11).
 *
 * 设计 (Agent Native Mobile First):
 *   1. Critical/High 告警卡片 (0 条不显示)
 *   2. 本周建议队列 (source_type='weekly_advisor', 3-5 条)
 *   3. Twin 摘要 (4 个数, 折叠)
 *   4. AI 会诊入口
 *
 * 旧 10+ 组件 (HomeHeader / AgentSurface / TodayCoachPanel / ...) 全部先沉默,
 * 备份在 index.legacy.tsx.bak. 数据观察 1-2 周后决定保留或删.
 */

import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getSafetyReport, type SafetyAlert } from '../../services/safety';
import { getActiveCards, type ActionCard } from '../../services/actionCards';
import api from '../../services/api';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import EnvironmentCard from '../../components/dashboard/EnvironmentCard';

interface TwinSnapshot {
  hrv?: number | null;
  sleep_score?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  spo2_avg?: number | null;
  resting_hr?: number | null;
}

function getSeverityKey(s: any): string {
  return typeof s === 'string' ? s : s?.label ?? 'info';
}

function pickTwinSnapshot(twin: any): TwinSnapshot {
  if (!twin) return {};
  const phys = twin.physiological ?? {};
  const body = twin.body_composition ?? {};
  // 字段名对齐后端 app/twin/schema.py:
  //   PhysiologicalState: hrv_latest / hrv_7d_avg / sleep_score_latest /
  //                       resting_hr_latest / spo2_avg / spo2_min_overnight
  //   BodyCompositionState: blood_pressure_systolic / blood_pressure_diastolic
  return {
    hrv: phys.hrv_latest ?? phys.hrv_7d_avg ?? null,
    sleep_score: phys.sleep_score_latest ?? null,
    resting_hr: phys.resting_hr_latest ?? null,
    systolic_bp: body.blood_pressure_systolic ?? null,
    diastolic_bp: body.blood_pressure_diastolic ?? null,
    spo2_avg: phys.spo2_avg ?? phys.spo2_min_overnight ?? null,
  };
}

export default function TodayScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();
  const [twinExpanded, setTwinExpanded] = useState(false);

  const safetyQuery = useQuery({
    queryKey: ['safety', 'me'],
    queryFn: getSafetyReport,
    staleTime: 5 * 60 * 1000,
  });

  const cardsQuery = useQuery({
    queryKey: ['action-cards', 'active'],
    queryFn: getActiveCards,
    staleTime: 60 * 1000,
  });

  const twinQuery = useQuery({
    queryKey: ['twin', 'me'],
    queryFn: async () => {
      const { data } = await api.get('/twin/me');
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const onRefresh = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['safety', 'me'] }),
      qc.invalidateQueries({ queryKey: ['action-cards', 'active'] }),
      qc.invalidateQueries({ queryKey: ['twin', 'me'] }),
    ]);
  }, [qc]);

  const isLoading = safetyQuery.isLoading || cardsQuery.isLoading || twinQuery.isLoading;
  const isRefreshing = safetyQuery.isRefetching || cardsQuery.isRefetching || twinQuery.isRefetching;

  const alerts: SafetyAlert[] = safetyQuery.data?.alerts ?? [];
  const criticalAlerts = alerts.filter(a =>
    ['critical', 'high'].includes(getSeverityKey(a.severity)),
  );

  const cards: ActionCard[] = cardsQuery.data ?? [];
  const weeklyAdvice = cards.filter(c => c.source_type === 'weekly_advisor');

  const twinSnap = pickTwinSnapshot(twinQuery.data);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.headerTitle, { color: c.labelPrimary }]}>今日</Text>
            <Text style={[styles.headerSub, { color: c.labelTertiary }]}>
              Agent 替你看,只在该看时打扰你
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => router.push('/settings' as any)}
            accessibilityLabel="设置"
            style={styles.headerSettings}
          >
            <Ionicons name="settings-outline" size={22} color={c.labelTertiary} />
          </TouchableOpacity>
        </View>

        {/* 环境(天气 + AQI)卡 — 旧首页有, P2 重做漏了, 2026-05-11 补回 */}
        <EnvironmentCard />

        {/* 我的基因快捷入口 — G-W2 (2026-05-12) */}
        <TouchableOpacity
          onPress={() => router.push('/genetic-report' as any)}
          style={[styles.quickEntry, { backgroundColor: c.bgCard, borderColor: c.separator }]}
        >
          <Text style={styles.quickEntryEmoji}>🧬</Text>
          <View style={{ flex: 1 }}>
            <Text style={[styles.quickEntryTitle, { color: c.labelPrimary }]}>我的基因</Text>
            <Text style={[styles.quickEntrySub, { color: c.labelTertiary }]}>52 关键位点 · AI 解读 + 当前生效建议</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
        </TouchableOpacity>

        {isLoading && (
          <View style={styles.loading}>
            <ActivityIndicator />
          </View>
        )}

        {/* 1. Critical/High 告警卡 */}
        {criticalAlerts.length > 0 && (
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>需要立即处理</Text>
            {criticalAlerts.slice(0, 3).map(a => (
              <AlertRow
                key={a.rule_id}
                alert={a}
                onPress={() => router.push(`/alerts`)}
              />
            ))}
            {criticalAlerts.length > 3 && (
              <TouchableOpacity onPress={() => router.push('/alerts')} style={styles.moreLink}>
                <Text style={[styles.moreText, { color: c.brand }]}>查看全部 {criticalAlerts.length} 条</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* 2. 本周建议队列 */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>本周建议</Text>
          {weeklyAdvice.length === 0 ? (
            <View style={[styles.emptyBlock, { borderColor: c.separator }]}>
              <Text style={[styles.emptyText, { color: c.labelTertiary }]}>
                本周尚无 Agent 主动建议. 周日晚 21:07 自动生成.
              </Text>
            </View>
          ) : (
            weeklyAdvice.map(card => (
              <SuggestionRow
                key={card.id}
                card={card}
                onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
              />
            ))
          )}
        </View>

        {/* 3. Twin 摘要 */}
        <View style={styles.section}>
          <TouchableOpacity
            style={styles.collapseHeader}
            onPress={() => setTwinExpanded(v => !v)}
          >
            <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>身体快照</Text>
            <Ionicons
              name={twinExpanded ? 'chevron-up' : 'chevron-down'}
              size={18}
              color={c.labelTertiary}
            />
          </TouchableOpacity>
          {twinExpanded && (
            <View style={styles.twinGrid}>
              <TwinCell label="HRV" value={fmt(twinSnap.hrv)} unit="ms" />
              <TwinCell label="睡眠" value={fmt(twinSnap.sleep_score)} unit="分" />
              <TwinCell
                label="血压"
                value={
                  twinSnap.systolic_bp && twinSnap.diastolic_bp
                    ? `${twinSnap.systolic_bp}/${twinSnap.diastolic_bp}`
                    : '—'
                }
                unit=""
              />
              <TwinCell label="SpO2" value={fmt(twinSnap.spo2_avg)} unit="%" />
            </View>
          )}
        </View>

        {/* 4. AI 会诊入口 */}
        <TouchableOpacity
          style={[styles.chatEntry, { backgroundColor: c.brand }]}
          onPress={() => router.push('/(tabs)/chat')}
        >
          <Ionicons name="chatbubbles" size={20} color="#fff" />
          <Text style={styles.chatEntryText}>AI 会诊</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function AlertRow({ alert, onPress }: { alert: SafetyAlert; onPress: () => void }) {
  const { c } = useTheme();
  const sev = getSeverityKey(alert.severity);
  const color = sev === 'critical' ? c.red : c.amber;
  return (
    <TouchableOpacity style={[styles.row, { borderColor: color }]} onPress={onPress}>
      <View style={styles.rowMain}>
        <Text style={[styles.rowTitle, { color: c.labelPrimary }]}>{alert.title}</Text>
        <Text style={[styles.rowSub, { color: c.labelSecondary }]} numberOfLines={2}>
          {alert.message}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={color} />
    </TouchableOpacity>
  );
}

function SuggestionRow({ card, onPress }: { card: ActionCard; onPress: () => void }) {
  const { c } = useTheme();
  const decided = !!card.user_decision;
  return (
    <TouchableOpacity style={[styles.row, { borderColor: c.separator }]} onPress={onPress}>
      <View style={styles.rowMain}>
        <Text style={[styles.rowTitle, { color: c.labelPrimary }]}>{card.title}</Text>
        <Text style={[styles.rowSub, { color: c.labelSecondary }]} numberOfLines={2}>
          {card.content}
        </Text>
        {decided && (
          <View style={styles.decidedTag}>
            <Text style={styles.decidedText}>{card.user_decision}</Text>
          </View>
        )}
      </View>
      <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
    </TouchableOpacity>
  );
}

function TwinCell({ label, value, unit }: { label: string; value: string; unit: string }) {
  const { c } = useTheme();
  return (
    <View style={[styles.twinCell, { backgroundColor: c.bgCard }]}>
      <Text style={[styles.twinLabel, { color: c.labelTertiary }]}>{label}</Text>
      <Text style={[styles.twinValue, { color: c.labelPrimary }]}>
        {value}
        {value !== '—' && unit ? <Text style={styles.twinUnit}> {unit}</Text> : null}
      </Text>
    </View>
  );
}

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: spacing.xl * 2, gap: spacing.lg },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 4, marginTop: spacing.sm },
  headerSettings: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
  },
  headerTitle: { fontSize: 28, fontWeight: '700' },
  headerSub: { fontSize: 13 },
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
  section: { gap: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  collapseHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  emptyBlock: {
    borderWidth: 1,
    borderRadius: radii.md,
    borderStyle: 'dashed',
    padding: spacing.lg,
    alignItems: 'center',
  },
  emptyText: { fontSize: 13, lineHeight: 20, textAlign: 'center' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  rowMain: { flex: 1, gap: 4 },
  rowTitle: { fontSize: 15, fontWeight: '600' },
  rowSub: { fontSize: 13, lineHeight: 18 },
  decidedTag: {
    alignSelf: 'flex-start',
    backgroundColor: '#F1F5F9',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    marginTop: 4,
  },
  decidedText: { fontSize: 11, color: '#475569', fontWeight: '600' },
  moreLink: { paddingVertical: spacing.xs, alignItems: 'center' },
  moreText: { fontSize: 13, fontWeight: '500' },
  twinGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  twinCell: {
    flexBasis: '47%',
    flexGrow: 1,
    padding: spacing.md,
    borderRadius: radii.md,
    gap: 4,
  },
  twinLabel: { fontSize: 11, fontWeight: '500' },
  twinValue: { fontSize: 22, fontWeight: '700' },
  twinUnit: { fontSize: 12, fontWeight: '400' },
  chatEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    borderRadius: radii.md,
    marginTop: spacing.sm,
  },
  chatEntryText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  quickEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  quickEntryEmoji: { fontSize: 22 },
  quickEntryTitle: { fontSize: 15, fontWeight: '600' },
  quickEntrySub: { fontSize: 12, marginTop: 2 },
});
