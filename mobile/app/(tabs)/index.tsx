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
import TodayPlanPanel from '../../components/dashboard/TodayPlanPanel';
import TrajectorySnapshotPanel from '../../components/dashboard/TrajectorySnapshotPanel';
import DataFreshnessPanel from '../../components/dashboard/DataFreshnessPanel';
import EvidenceChip from '../../components/shared/EvidenceChip';
import { createTodayAgentContext, pushChatWithContext } from '../../utils/agentContext';
import { getDailyOperatingPlan, type DailyPlanAction } from '../../services/dailyPlan';
import { getHealthTrajectory } from '../../services/trajectory';

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
  const labs = twin.labs ?? {};
  // 字段对齐 backend app/twin/schema.py + builder.py:
  //   PhysiologicalState: hrv_latest / hrv_7d_avg / sleep_score_latest /
  //                       resting_hr_latest / spo2_avg / spo2_min_overnight
  //   LabsContext: blood_pressure_systolic / blood_pressure_diastolic
  // 注: BodyCompositionState 不含 BP (历史误读修正 2026-05-12)
  return {
    hrv: phys.hrv_latest ?? phys.hrv_7d_avg ?? null,
    sleep_score: phys.sleep_score_latest ?? null,
    resting_hr: phys.resting_hr_latest ?? null,
    systolic_bp: labs.blood_pressure_systolic ?? null,
    diastolic_bp: labs.blood_pressure_diastolic ?? null,
    spo2_avg: phys.spo2_avg ?? phys.spo2_min_overnight ?? null,
  };
}

export default function TodayScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();
  const [manualRefreshing, setManualRefreshing] = useState(false);

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

  const dailyPlanQuery = useQuery({
    queryKey: ['daily-plan', 'me'],
    queryFn: getDailyOperatingPlan,
    staleTime: 60 * 1000,
  });

  const trajectoryQuery = useQuery({
    queryKey: ['trajectory', 'me'],
    queryFn: getHealthTrajectory,
    staleTime: 5 * 60 * 1000,
  });

  // Hero 数据 — 给 quickEntry tile 显示数字而不是干口号
  const geneticStatsQuery = useQuery({
    queryKey: ['genetic-stats'],
    queryFn: async () => {
      try {
        const { data } = await api.get('/genetic/report/me?include_summary=false');
        return { hits: data?.stats?.hits ?? null, total: data?.stats?.total_known ?? null };
      } catch {
        return { hits: null, total: null };
      }
    },
    staleTime: 10 * 60 * 1000,
  });

  const progressStatsQuery = useQuery({
    queryKey: ['progress-stats', 30],
    queryFn: async () => {
      try {
        const { data } = await api.get('/my-progress?days=30');
        return {
          improved: data?.stats?.improved_and_closed ?? data?.stats?.improved ?? null,
          total: data?.stats?.total_surfaced ?? null,
        };
      } catch {
        return { improved: null, total: null };
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const onRefresh = useCallback(async () => {
    setManualRefreshing(true);
    try {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['safety', 'me'] }),
        qc.invalidateQueries({ queryKey: ['action-cards', 'active'] }),
        qc.invalidateQueries({ queryKey: ['twin', 'me'] }),
        qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] }),
        qc.invalidateQueries({ queryKey: ['trajectory', 'me'] }),
        // EnvironmentCard 数据 — 不加这几条用户下拉时天气/AQI/明日预报不动
        qc.invalidateQueries({ queryKey: ['env', 'weather'] }),
        qc.invalidateQueries({ queryKey: ['env', 'aqi'] }),
        qc.invalidateQueries({ queryKey: ['env', 'forecast'] }),
        qc.invalidateQueries({ queryKey: ['env', 'location'] }),
      ]);
    } finally {
      setManualRefreshing(false);
    }
  }, [qc]);

  const isLoading = safetyQuery.isLoading || cardsQuery.isLoading || twinQuery.isLoading || dailyPlanQuery.isLoading;
  // RefreshControl spinner: 用户主动下拉时立刻显示, 直到所有 invalidate 完成 (含 env)
  const isRefreshing = manualRefreshing
    || safetyQuery.isRefetching
    || cardsQuery.isRefetching
    || twinQuery.isRefetching
    || dailyPlanQuery.isRefetching
    || trajectoryQuery.isRefetching;

  const alerts: SafetyAlert[] = safetyQuery.data?.alerts ?? [];
  const criticalAlerts = alerts.filter(a =>
    ['critical', 'high'].includes(getSeverityKey(a.severity)),
  );

  const cards: ActionCard[] = cardsQuery.data ?? [];
  const weeklyAdvice = cards.filter(c => c.source_type === 'weekly_advisor');

  const twinSnap = pickTwinSnapshot(twinQuery.data);
  const todayMetricsContext = {
    hrv: twinSnap.hrv ?? null,
    sleep_score: twinSnap.sleep_score ?? null,
    resting_hr: twinSnap.resting_hr ?? null,
    systolic_bp: twinSnap.systolic_bp ?? null,
    diastolic_bp: twinSnap.diastolic_bp ?? null,
    spo2_avg: twinSnap.spo2_avg ?? null,
  };

  const openPlanAction = useCallback((action: DailyPlanAction) => {
    if (action.source_card_id) {
      router.push({ pathname: '/card/[id]' as any, params: { id: String(action.source_card_id) } });
      return;
    }
    if (action.domain === 'nutrition') router.push('/diet-plan' as any);
    else if (action.domain === 'movement') router.push('/movement-plan' as any);
    else if (action.domain === 'sleep') router.push('/sleep' as any);
    else if (isBodyMeasurementAction(action)) {
      router.push('/body-measurements?focus=morning' as any);
    } else if (action.domain === 'measurement') router.push('/record' as any);
    else router.push('/(tabs)/chat' as any);
  }, [router]);

  const openTrajectoryChat = useCallback(() => {
    const snapshot = trajectoryQuery.data;
    const contextObject = (value?: Record<string, unknown> | null) => (
      value ? JSON.parse(JSON.stringify(value)) : null
    );
    pushChatWithContext(router, {
      prompt: '从疾病上游轨迹看, 我接下来 7 天最应该优先做什么?',
      badge: '基于健康轨迹',
      context: {
        from: 'trajectory/home',
        focus_domains: snapshot?.focus_domains ?? [],
        trajectory_risks: (snapshot?.trajectory_risks ?? []).map(risk => ({
          domain: risk.domain,
          level: risk.level,
          title: risk.title,
          why: risk.why ?? null,
          signals: risk.signals ?? [],
          primary_action: risk.primary_action ?? null,
        })),
        clinical_anchors: contextObject(snapshot?.clinical_anchors),
        realtime_state: contextObject(snapshot?.realtime_state),
        data_gaps: (snapshot?.data_gaps ?? []).map(gap => ({
          code: gap.code,
          label: gap.label,
          next_step: gap.next_step ?? null,
        })),
      },
    });
  }, [router, trajectoryQuery.data]);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />}
      >
        {/* 环境(天气 + AQI)卡 — 旧首页有, P2 重做漏了, 2026-05-11 补回 */}
        <EnvironmentCard />

        <TodayPlanPanel
          plan={dailyPlanQuery.data}
          loading={dailyPlanQuery.isLoading}
          onPressAction={openPlanAction}
        />

        {/* 数据完整度 — Agent 准确率的因, 缺数据时一目了然该补哪几项 */}
        <DataFreshnessPanel />

        <TrajectorySnapshotPanel
          snapshot={trajectoryQuery.data}
          loading={trajectoryQuery.isLoading}
          onPress={openTrajectoryChat}
        />

        {/* 4 入口 — 2x2 grid 学健康记录 VitalsGrid 风格 (2026-05-12 重做) */}
        <View style={styles.gridRow}>
          <HeroTile
            label="我的基因"
            emoji="🧬"
            value={geneticStatsQuery.data?.hits != null ? String(geneticStatsQuery.data.hits) : '—'}
            unit={geneticStatsQuery.data?.total != null ? ` / ${geneticStatsQuery.data.total}` : ''}
            sub="关键位点 · AI 解读"
            color={c.purple}
            bg={c.tintPurple}
            onPress={() => router.push('/genetic-report' as any)}
          />
          <HeroTile
            label="我的进度"
            emoji="📈"
            value={progressStatsQuery.data?.improved != null ? String(progressStatsQuery.data.improved) : '—'}
            unit={progressStatsQuery.data?.total != null ? ` / ${progressStatsQuery.data.total}` : ''}
            sub="改善闭环 · 30 天"
            color={c.blue}
            bg={c.tintBlue}
            onPress={() => router.push('/my-progress' as any)}
          />
          <HeroTile
            label="我的运动"
            emoji="🏃"
            value="处方"
            sub="ACWR · 基因偏好"
            color={c.pink}
            bg={c.tintPink}
            onPress={() => router.push('/movement-plan' as any)}
          />
          <HeroTile
            label="我的饮食"
            emoji="🥗"
            value="方案"
            sub="TDEE · 蛋白 · 化验"
            color={c.orange}
            bg={c.tintOrange}
            onPress={() => router.push('/diet-plan' as any)}
          />
        </View>

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

        {/* 3. 身体快照 — 2x2 grid, 默认展开学 VitalsGrid 风格 */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>身体快照</Text>
          <View style={styles.gridRow}>
            <HeroTile
              label="HRV"
              ionIcon="pulse"
              value={fmt(twinSnap.hrv)}
              unit={twinSnap.hrv != null ? ' ms' : ''}
              sub="压力 & 恢复"
              color={c.teal}
              bg={c.tintTeal}
              onPress={() => router.push('/indicator-history?type=hrv' as any)}
            />
            <HeroTile
              label="睡眠"
              ionIcon="moon"
              value={fmt(twinSnap.sleep_score)}
              unit={twinSnap.sleep_score != null ? ' 分' : ''}
              sub="昨夜评分"
              color={c.purple}
              bg={c.tintPurple}
              onPress={() => router.push('/sleep' as any)}
            />
            <HeroTile
              label="血压"
              ionIcon="heart"
              value={
                twinSnap.systolic_bp && twinSnap.diastolic_bp
                  ? `${twinSnap.systolic_bp}/${twinSnap.diastolic_bp}`
                  : '—'
              }
              unit=""
              sub="收缩 / 舒张"
              color={c.pink}
              bg={c.tintPink}
              onPress={() => router.push('/indicator-history?type=blood_pressure' as any)}
            />
            <HeroTile
              label="血氧"
              ionIcon="water"
              value={fmt(twinSnap.spo2_avg)}
              unit={twinSnap.spo2_avg != null ? ' %' : ''}
              sub="夜间均值"
              color={c.blue}
              bg={c.tintBlue}
              onPress={() => router.push('/sleep-spo2-analysis' as any)}
            />
          </View>
        </View>

        {/* 4. AI 会诊入口 */}
        <TouchableOpacity
          style={[styles.chatEntry, { backgroundColor: c.brand }]}
          onPress={() => pushChatWithContext(router, {
            prompt: '请基于我今天的身体快照和当前告警, 帮我做一次整体健康会诊, 按优先级给出今天该做的事。',
            context: createTodayAgentContext({
              alerts,
              twinSnapshot: todayMetricsContext,
            }),
            badge: `基于今日快照${alerts.length > 0 ? ` · ${alerts.length} 条告警` : ''}`,
          })}
        >
          <Ionicons name="chatbubbles" size={20} color="#fff" />
          <Text style={styles.chatEntryText}>AI 会诊</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function isBodyMeasurementAction(action: DailyPlanAction): boolean {
  if (action.domain !== 'measurement') return false;
  const haystack = `${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();
  return /体重|腰围|weight|waist|bmi/.test(haystack);
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
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={[styles.rowTitle, { color: c.labelPrimary, flex: 1 }]}>{card.title}</Text>
          <EvidenceChip level={card.evidence_level} />
        </View>
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

function HeroTile({
  label, value, unit, sub, emoji, ionIcon, color, bg, onPress,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  emoji?: string;
  ionIcon?: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  onPress: () => void;
}) {
  const { c } = useTheme();
  return (
    <TouchableOpacity
      style={[styles.tile, { backgroundColor: c.bgCard, borderColor: c.separator }]}
      onPress={onPress}
      activeOpacity={0.75}
      accessibilityLabel={`${label} ${value}${unit ?? ''}`}
    >
      <View style={styles.tileHeader}>
        <View style={[styles.iconDot, { backgroundColor: bg }]}>
          {emoji ? (
            <Text style={{ fontSize: 13 }}>{emoji}</Text>
          ) : ionIcon ? (
            <Ionicons name={ionIcon} size={14} color={color} />
          ) : null}
        </View>
        <Text style={[styles.tileLabel, { color: c.labelSecondary }]}>{label}</Text>
        <Ionicons name="chevron-forward" size={12} color={c.labelTertiary} style={{ marginLeft: 'auto' }} />
      </View>
      <View style={styles.tileValueRow}>
        <Text style={[styles.tileValue, { color }]} numberOfLines={1}>{value}</Text>
        {unit ? <Text style={[styles.tileUnit, { color }]}>{unit}</Text> : null}
      </View>
      {sub ? <Text style={[styles.tileSub, { color: c.labelTertiary }]} numberOfLines={1}>{sub}</Text> : null}
    </TouchableOpacity>
  );
}

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.lg },  // 110 = tab bar 83 + 缓冲, 否则 AI 会诊被遮
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
  section: { gap: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
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
  // 2x2 grid 学健康记录 VitalsGrid 风格
  gridRow: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: spacing.md,
  },
  tile: {
    width: '47.5%',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: 14,
  },
  tileHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  iconDot: {
    width: 24, height: 24, borderRadius: 7,
    alignItems: 'center', justifyContent: 'center',
  },
  tileLabel: { fontSize: 13, fontWeight: '500' },
  tileValueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 1 },
  tileValue: { fontSize: 24, fontWeight: '800', fontVariant: ['tabular-nums'], letterSpacing: -0.6 },
  tileUnit: { fontSize: 13, fontWeight: '500' },
  tileSub: { fontSize: 11, marginTop: 4 },
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
});
