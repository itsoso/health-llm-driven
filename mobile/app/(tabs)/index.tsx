/**
 * 今日 Tab —— Agent 工作台 (2026-05-23).
 *
 * 设计 (Agent Native Mobile First):
 *   1. 首屏先回答 Agent 正在后台做什么.
 *   2. 再给出今天最该执行的一步.
 *   3. 最后下沉身体反馈、本周建议和更多入口.
 */

import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
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
import { getActiveCards, pickWeeklySuggestionCards, type ActionCard } from '../../services/actionCards';
import api from '../../services/api';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import EnvironmentCard from '../../components/dashboard/EnvironmentCard';
import TodayPlanPanel from '../../components/dashboard/TodayPlanPanel';
import TrajectorySnapshotPanel from '../../components/dashboard/TrajectorySnapshotPanel';
import EvidenceChip from '../../components/shared/EvidenceChip';
import { EvidenceRefsRow } from '../../components/knowledge';
import { pushChatWithContext } from '../../utils/agentContext';
import { getDailyOperatingPlan, recordDailyPlanActionEvent, type DailyPlanAction } from '../../services/dailyPlan';
import { getHealthTrajectory } from '../../services/trajectory';

interface TwinSnapshot {
  hrv?: number | null;
  sleep_score?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  spo2_avg?: number | null;
  resting_hr?: number | null;
  bmi?: number | null;
  body_fat_pct?: number | null;
  vo2max?: number | null;
}

type NextActionCompletionState = 'idle' | 'sending' | 'completed' | 'error';
type InterventionDomainKey = 'diet' | 'sleep' | 'movement' | 'supplement' | 'emotion';

interface InterventionDomainStatus {
  key: InterventionDomainKey;
  label: string;
  detail: string;
  activeCount: number;
  icon: keyof typeof Ionicons.glyphMap;
  colorName: 'orange' | 'purple' | 'green' | 'teal' | 'blue';
  tintName: 'tintOrange' | 'tintPurple' | 'tintGreen' | 'tintTeal' | 'tintBlue';
  route: '/diet-plan' | '/sleep' | '/movement-plan' | '/(tabs)/chat';
}

type ImpactMetricColorName = 'green' | 'blue' | 'purple' | 'orange' | 'teal' | 'pink' | 'red';
type ImpactMetricTintName = 'tintGreen' | 'tintBlue' | 'tintPurple' | 'tintOrange' | 'tintTeal' | 'tintPink' | 'tintRed';

interface ImpactMetricChip {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  colorName: ImpactMetricColorName;
  tintName: ImpactMetricTintName;
}

interface OutcomeFeedbackMetric {
  key: string;
  label: string;
  value: string;
  detail: string;
  icon: keyof typeof Ionicons.glyphMap;
  colorName: ImpactMetricColorName;
  tintName: ImpactMetricTintName;
  route: string;
}

function getSeverityKey(s: any): string {
  return typeof s === 'string' ? s : s?.label ?? 'info';
}

function pickTwinSnapshot(twin: any): TwinSnapshot {
  if (!twin) return {};
  const phys = twin.physiological ?? {};
  const labs = twin.labs ?? {};
  const body = twin.body_composition ?? {};
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
    bmi: body.bmi ?? null,
    body_fat_pct: body.body_fat_pct ?? body.body_fat_percentage ?? null,
    vo2max: phys.vo2max_latest ?? phys.vo2max ?? null,
  };
}

const INTERVENTION_DOMAINS: Omit<InterventionDomainStatus, 'activeCount'>[] = [
  {
    key: 'diet',
    label: '饮食',
    detail: 'BMI / 体脂 / 血检',
    icon: 'restaurant-outline',
    colorName: 'orange',
    tintName: 'tintOrange',
    route: '/diet-plan',
  },
  {
    key: 'sleep',
    label: '睡眠',
    detail: '睡眠分 / 血氧 / HRV',
    icon: 'moon-outline',
    colorName: 'purple',
    tintName: 'tintPurple',
    route: '/sleep',
  },
  {
    key: 'movement',
    label: '运动',
    detail: 'VO2max / 体脂 / HRV',
    icon: 'walk-outline',
    colorName: 'green',
    tintName: 'tintGreen',
    route: '/movement-plan',
  },
  {
    key: 'supplement',
    label: '补剂',
    detail: '血检 / 睡眠 / 炎症',
    icon: 'medkit-outline',
    colorName: 'teal',
    tintName: 'tintTeal',
    route: '/diet-plan',
  },
  {
    key: 'emotion',
    label: '情绪',
    detail: 'HRV / 睡眠 / 压力',
    icon: 'cloudy-outline',
    colorName: 'blue',
    tintName: 'tintBlue',
    route: '/(tabs)/chat',
  },
];

export default function TodayScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [nextActionCompletion, setNextActionCompletion] = useState<{
    actionKey: string | null;
    state: NextActionCompletionState;
  }>({ actionKey: null, state: 'idle' });

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
  const weeklyAdvice = pickWeeklySuggestionCards(cards);

  const twinSnap = pickTwinSnapshot(twinQuery.data);
  const activePlanCount = dailyPlanQuery.data?.actions?.length ?? 0;
  const nextAction = (dailyPlanQuery.data?.actions ?? []).find(action => Boolean(action?.title)) ?? null;
  const nextActionKey = nextAction?.action_key || nextAction?.title || null;
  const riskTakesPrimarySlot = criticalAlerts.length > 0 && !nextAction;
  const visibleNextActionState: NextActionCompletionState =
    nextActionCompletion.actionKey === nextActionKey ? nextActionCompletion.state : 'idle';
  const interventionDomains = buildInterventionDomainStatuses(dailyPlanQuery.data?.actions ?? []);

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

  const completeNextAction = useCallback(async (action: DailyPlanAction) => {
    if (!action.action_key || nextActionCompletion.state === 'sending') return;
    setNextActionCompletion({ actionKey: action.action_key, state: 'sending' });
    try {
      await recordDailyPlanActionEvent(action.action_key, {
        event_type: 'completed',
        payload: { source: 'next_best_action' },
      });
      setNextActionCompletion({ actionKey: action.action_key, state: 'completed' });
      await qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] });
    } catch {
      setNextActionCompletion({ actionKey: action.action_key, state: 'error' });
    }
  }, [nextActionCompletion.state, qc]);

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

  const openWorkspaceChat = useCallback(() => {
    pushChatWithContext(router, {
      prompt: '请解释你现在对我健康状态的判断: 正在监测哪些数据, 哪些生活方式干预最重要, 今天为什么优先这些任务?',
      badge: '首页工作台',
      context: {
        from: 'home/agent-workspace',
        risk_count: criticalAlerts.length,
        plan_count: activePlanCount,
        data_sources: buildWorkspaceDataSources({
          geneticHits: geneticStatsQuery.data?.hits,
          progressTotal: progressStatsQuery.data?.total,
          twinSnapshot: twinSnap,
        }),
        intervention_domains: interventionDomains.map(domain => ({
          key: domain.key,
          label: domain.label,
          active_count: domain.activeCount,
          detail: domain.detail,
        })),
        wearable_snapshot: {
          hrv: twinSnap.hrv ?? null,
          sleep_score: twinSnap.sleep_score ?? null,
          resting_hr: twinSnap.resting_hr ?? null,
          spo2_avg: twinSnap.spo2_avg ?? null,
          blood_pressure: twinSnap.systolic_bp && twinSnap.diastolic_bp
            ? `${twinSnap.systolic_bp}/${twinSnap.diastolic_bp}`
            : null,
        },
      },
    });
  }, [
    activePlanCount,
    criticalAlerts.length,
    geneticStatsQuery.data?.hits,
    interventionDomains,
    progressStatsQuery.data?.total,
    router,
    twinSnap,
  ]);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} />}
      >
        <HomeCommandHeader
          criticalCount={criticalAlerts.length}
          planCount={activePlanCount}
          refreshing={isRefreshing}
          riskTitle={criticalAlerts[0]?.title}
          geneticHits={geneticStatsQuery.data?.hits}
          progressTotal={progressStatsQuery.data?.total}
          twinSnapshot={twinSnap}
          domains={interventionDomains}
          onOpenFocus={() => (
            criticalAlerts.length > 0
              ? router.push('/alerts' as any)
              : nextAction
                ? openPlanAction(nextAction)
                : router.push('/(tabs)/record' as any)
          )}
          onOpenAgent={openWorkspaceChat}
          onOpenRecord={() => router.push('/(tabs)/record' as any)}
        />

        <View style={styles.section}>
          {!riskTakesPrimarySlot && (
            <NextBestActionCard
              action={nextAction}
              loading={dailyPlanQuery.isLoading}
              completionState={visibleNextActionState}
              onStart={openPlanAction}
              onComplete={completeNextAction}
              onFallbackRecord={() => router.push('/(tabs)/record' as any)}
              onFallbackAgent={() => router.push('/(tabs)/chat' as any)}
            />
          )}
          {(!riskTakesPrimarySlot || activePlanCount > 0) && (
            <TodayPlanPanel
              plan={dailyPlanQuery.data}
              loading={dailyPlanQuery.isLoading}
              compact={riskTakesPrimarySlot}
              title={riskTakesPrimarySlot ? '风险处理后继续' : '余下计划'}
              excludeActionKey={nextActionKey}
              onPressAction={openPlanAction}
              onActionEvent={() => qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] })}
            />
          )}
          <AgentHealthLoopPanel
            domains={interventionDomains}
            twinSnapshot={twinSnap}
            action={nextAction}
            riskTitle={criticalAlerts[0]?.title}
            onPressDomain={(domain) => router.push(domain.route as any)}
            onOpenMetric={(route) => router.push(route as any)}
          />
        </View>

        {isLoading && (
          <View style={styles.loading}>
            <ActivityIndicator />
          </View>
        )}

        <View style={styles.section}>
          <TrajectorySnapshotPanel
            snapshot={trajectoryQuery.data}
            loading={trajectoryQuery.isLoading}
            onPress={openTrajectoryChat}
          />
          <EnvironmentCard />
        </View>

        <View style={styles.section}>
          <SectionHeader
            title="本周建议"
            subtitle={weeklyAdvice.length > 0 ? `${weeklyAdvice.length} 个待处理` : '等待 Agent 生成'}
          />
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

        <CompactShortcutSection
          shortcuts={[
            {
              label: '基因',
              icon: 'git-branch-outline',
              value: geneticStatsQuery.data?.hits != null ? String(geneticStatsQuery.data.hits) : '—',
              color: c.purple,
              bg: c.tintPurple,
              onPress: () => router.push('/genetic-report' as any),
            },
            {
              label: '进度',
              icon: 'trending-up-outline',
              value: progressStatsQuery.data?.improved != null ? String(progressStatsQuery.data.improved) : '—',
              color: c.blue,
              bg: c.tintBlue,
              onPress: () => router.push('/my-progress' as any),
            },
            {
              label: '运动',
              icon: 'walk-outline',
              value: '处方',
              color: c.pink,
              bg: c.tintPink,
              onPress: () => router.push('/movement-plan' as any),
            },
            {
              label: '饮食',
              icon: 'restaurant-outline',
              value: '方案',
              color: c.orange,
              bg: c.tintOrange,
              onPress: () => router.push('/diet-plan' as any),
            },
          ]}
          onOpenAll={() => router.push('/(tabs)/record' as any)}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function HomeCommandHeader({
  criticalCount,
  planCount,
  refreshing,
  riskTitle,
  geneticHits,
  progressTotal,
  twinSnapshot,
  domains,
  onOpenFocus,
  onOpenAgent,
  onOpenRecord,
}: {
  criticalCount: number;
  planCount: number;
  refreshing: boolean;
  riskTitle?: string;
  geneticHits?: number | null;
  progressTotal?: number | null;
  twinSnapshot: TwinSnapshot;
  domains: InterventionDomainStatus[];
  onOpenFocus: () => void;
  onOpenAgent: () => void;
  onOpenRecord: () => void;
}) {
  const { c } = useTheme();
  const dateLabel = formatHomeDate(new Date());
  const statusColor = criticalCount > 0 ? c.red : c.green;
  const statusLabel = criticalCount > 0 ? `${criticalCount} 个风险` : '状态稳定';
  const primaryLabel = criticalCount > 0 ? '查看风险' : '问 Agent';
  const primaryIcon: keyof typeof Ionicons.glyphMap = criticalCount > 0 ? 'warning-outline' : 'sparkles-outline';
  const primaryAction = criticalCount > 0 ? onOpenFocus : onOpenAgent;
  const activeDomainCount = domains.filter(domain => domain.activeCount > 0).length;
  const wearableReady = Boolean(
    twinSnapshot.hrv
    || twinSnapshot.sleep_score
    || twinSnapshot.resting_hr
    || twinSnapshot.spo2_avg,
  );
  const clinicalReady = Boolean(twinSnapshot.systolic_bp || twinSnapshot.diastolic_bp);
  const evidenceSourceCount = [
    geneticHits != null,
    true,
    clinicalReady,
    wearableReady,
  ].filter(Boolean).length;
  const evidenceLabel = `${evidenceSourceCount}源画像`;
  const headline = criticalCount > 0
    ? `先处理 ${criticalCount} 个风险`
    : planCount > 0
      ? `今天 ${planCount} 件事`
      : '保持记录节奏';
  const focusKicker = criticalCount > 0
    ? '当前重点 · 风险优先'
    : activeDomainCount > 0
      ? `当前重点 · ${activeDomainCount} 个干预域执行中`
      : '当前重点 · 等待新任务';
  const focusText = criticalCount > 0
    ? (riskTitle || '先确认风险，再处理今天的计划')
    : planCount > 0
      ? '按优先级完成今日计划'
      : '暂无硬性任务，保持记录节奏';
  const liveSignalSummary = buildLiveSignalSummary(twinSnapshot);
  const agentInsight = criticalCount > 0
    ? `正在看 ${liveSignalSummary}，优先解释并处理「${riskTitle || '风险信号'}」。`
    : `正在看 ${liveSignalSummary}，继续调整生活方式干预。`;
  return (
    <View style={[styles.commandHeader, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.commandAgentHeader}>
        <View style={styles.commandAgentTitleBlock}>
          <View style={styles.commandAgentIdentity}>
            <View style={[styles.statusDot, { backgroundColor: c.brand }]} />
            <Text style={[styles.commandAgentLabel, { color: c.labelPrimary }]}>健康 Agent</Text>
          </View>
          <Text style={[styles.commandAgentSubLabel, { color: c.labelTertiary }]}>
            {refreshing ? '正在同步新数据' : '后台监测中'}
          </Text>
        </View>
        <View style={styles.commandRightMeta}>
          <Text style={[styles.commandDate, { color: c.labelTertiary }]}>{dateLabel}</Text>
          <View style={styles.commandMetaPills}>
            <View style={[styles.evidencePill, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
              <Ionicons name="layers-outline" size={11} color={c.labelTertiary} />
              <Text style={[styles.evidenceText, { color: c.labelSecondary }]}>{evidenceLabel}</Text>
            </View>
            <View style={[styles.statusPill, { backgroundColor: `${statusColor}14` }]}>
              <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
              <Text style={[styles.statusText, { color: statusColor }]}>{statusLabel}</Text>
            </View>
          </View>
        </View>
      </View>

      <Pressable
        style={({ pressed }) => [
          styles.commandDecisionArea,
          { opacity: pressed ? 0.78 : 1 },
        ]}
        onPress={onOpenFocus}
        accessibilityRole="button"
        accessibilityLabel="打开今日重点"
      >
        <Text style={[styles.commandFocusLabel, { color: c.brand }]}>{focusKicker}</Text>
        <Text style={[styles.commandTitle, { color: c.labelPrimary }]} numberOfLines={2}>
          {headline}
        </Text>
        <Text style={[styles.commandHint, { color: c.labelSecondary }]} numberOfLines={2}>{focusText}</Text>
      </Pressable>

      <View style={[styles.commandInsightBox, { backgroundColor: c.brandLight }]}>
        <Ionicons name="pulse-outline" size={15} color={c.brand} />
        <Text style={[styles.commandAgentCopy, { color: c.labelSecondary }]} numberOfLines={2}>
          {agentInsight}
        </Text>
      </View>

      <View style={styles.commandActions}>
        <Pressable
          style={({ pressed }) => [
            styles.primaryAction,
            { backgroundColor: c.brand, opacity: pressed ? 0.86 : 1 },
          ]}
          onPress={primaryAction}
          accessibilityRole="button"
          accessibilityLabel={primaryLabel}
        >
          <Ionicons name={primaryIcon} size={17} color="#FFFFFF" />
          <Text style={styles.primaryActionText}>{primaryLabel}</Text>
        </Pressable>
        <Pressable
          style={({ pressed }) => [
            styles.secondaryAction,
            { borderColor: c.separator, backgroundColor: c.bgPrimary, opacity: pressed ? 0.76 : 1 },
          ]}
          onPress={onOpenRecord}
          accessibilityRole="button"
          accessibilityLabel="记录健康数据"
        >
          <Ionicons name="add-circle-outline" size={17} color={c.brand} />
          <Text style={[styles.secondaryActionText, { color: c.labelPrimary }]}>记录</Text>
        </Pressable>
      </View>
    </View>
  );
}

function CompactShortcutSection({
  shortcuts,
  onOpenAll,
}: {
  shortcuts: {
    label: string;
    value: string;
    icon: keyof typeof Ionicons.glyphMap;
    color: string;
    bg: string;
    onPress: () => void;
  }[];
  onOpenAll: () => void;
}) {
  const { c } = useTheme();
  return (
    <View style={styles.compactSection}>
      <SectionHeader title="更多入口" subtitle="常用路径" action="全部" onPress={onOpenAll} />
      <View style={styles.shortcutRail}>
        {shortcuts.map(item => (
          <Pressable
            key={item.label}
            onPress={item.onPress}
            style={({ pressed }) => [
              styles.shortcutPill,
              { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed ? 0.72 : 1 },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`${item.label} ${item.value}`}
          >
            <View style={[styles.shortcutIcon, { backgroundColor: item.bg }]}>
              <Ionicons name={item.icon} size={15} color={item.color} />
            </View>
            <View style={styles.shortcutTextBlock}>
              <Text style={[styles.shortcutLabel, { color: c.labelSecondary }]}>{item.label}</Text>
              <Text style={[styles.shortcutValue, { color: c.labelPrimary }]} numberOfLines={1}>
                {item.value}
              </Text>
            </View>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function AgentHealthLoopPanel({
  domains,
  twinSnapshot,
  action,
  riskTitle,
  onPressDomain,
  onOpenMetric,
}: {
  domains: InterventionDomainStatus[];
  twinSnapshot: TwinSnapshot;
  action?: DailyPlanAction | null;
  riskTitle?: string;
  onPressDomain: (domain: InterventionDomainStatus) => void;
  onOpenMetric: (route: string) => void;
}) {
  const { c } = useTheme();
  const activeCount = domains.reduce((sum, domain) => sum + domain.activeCount, 0);
  const metrics = buildOutcomeFeedbackMetrics(twinSnapshot, action).slice(0, 3);
  const loopStrategy = buildAgentLoopStrategy({ activeCount, action, riskTitle });
  const visibleDomains = pickPriorityInterventionDomains(domains, riskTitle, action).slice(0, 4);

  return (
    <View style={[styles.loopCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.loopHeader}>
        <View style={[styles.loopIcon, { backgroundColor: c.brandLight }]}>
          <Ionicons name="sync-circle-outline" size={19} color={c.brand} />
        </View>
        <View style={styles.loopTitleBlock}>
          <Text style={[styles.loopTitle, { color: c.labelPrimary }]}>Agent 干预闭环</Text>
          <Text style={[styles.loopSubtitle, { color: c.labelTertiary }]} numberOfLines={2}>
            {loopStrategy.subtitle}
          </Text>
        </View>
      </View>

      <View style={[styles.loopPipeline, { borderColor: c.separator }]}>
        {[
          { label: '判断', value: loopStrategy.diagnosisLabel, icon: 'pulse-outline' as const },
          { label: '干预', value: loopStrategy.interventionLabel, icon: 'git-network-outline' as const },
          { label: '验证', value: loopStrategy.verificationLabel || `${metrics.length}项`, icon: 'analytics-outline' as const },
        ].map(step => (
          <View key={step.label} style={styles.loopPipelineStep}>
            <Ionicons name={step.icon} size={14} color={c.brand} />
            <Text style={[styles.loopStepLabel, { color: c.labelTertiary }]}>{step.label}</Text>
            <Text style={[styles.loopStepValue, { color: c.labelPrimary }]} numberOfLines={1}>
              {step.value}
            </Text>
          </View>
        ))}
      </View>

      <View style={styles.loopDomainRail}>
        {visibleDomains.map(domain => {
          const color = c[domain.colorName];
          const active = domain.activeCount > 0;
          return (
            <Pressable
              key={domain.key}
              onPress={() => onPressDomain(domain)}
              style={({ pressed }) => [
                styles.loopDomainChip,
                {
                  backgroundColor: active ? c[domain.tintName] : c.bgPrimary,
                  borderColor: active ? `${color}55` : c.separator,
                  opacity: pressed ? 0.72 : 1,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`打开${domain.label}干预`}
            >
              <Ionicons name={domain.icon} size={13} color={color} />
              <Text style={[styles.loopDomainText, { color: c.labelPrimary }]} numberOfLines={1}>
                {domain.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.loopMetricRail}>
        {metrics.map(metric => {
          const color = c[metric.colorName];
          return (
            <Pressable
              key={metric.key}
              onPress={() => onOpenMetric(metric.route)}
              style={({ pressed }) => [
                styles.loopMetricTile,
                { backgroundColor: c.bgPrimary, borderColor: c.separator, opacity: pressed ? 0.72 : 1 },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`${metric.label} ${metric.value}`}
            >
              <View style={[styles.loopMetricIcon, { backgroundColor: c[metric.tintName] }]}>
                <Ionicons name={metric.icon} size={13} color={color} />
              </View>
              <Text style={[styles.loopMetricLabel, { color: c.labelTertiary }]} numberOfLines={1}>
                {metric.label}
              </Text>
              <Text style={[styles.loopMetricValue, { color }]} numberOfLines={1}>
                {metric.value}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function NextBestActionCard({
  action,
  loading,
  completionState,
  onStart,
  onComplete,
  onFallbackRecord,
  onFallbackAgent,
}: {
  action?: DailyPlanAction | null;
  loading?: boolean;
  completionState: NextActionCompletionState;
  onStart: (action: DailyPlanAction) => void;
  onComplete: (action: DailyPlanAction) => void;
  onFallbackRecord: () => void;
  onFallbackAgent: () => void;
}) {
  const { c } = useTheme();
  const hasAction = Boolean(action?.title);
  const title = loading
    ? '正在判断下一步'
    : hasAction
      ? action!.title
      : '补齐今日记录';
  const reason = loading
    ? '同步计划后会给出当前最值得做的一件事'
    : hasAction
      ? (action?.why || action?.when || '先完成这一步，再看后续计划')
      : '没有硬性任务时，先补齐今天会影响建议的数据';
  const impactMetrics = buildActionImpactMetrics(action);

  return (
    <View style={[styles.nextActionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.nextActionTop}>
        <View style={[styles.nextActionIcon, { backgroundColor: c.tintGreen }]}>
          <Ionicons name="navigate-outline" size={17} color={c.green} />
        </View>
        <View style={styles.nextActionMain}>
          <Text style={[styles.nextActionEyebrow, { color: c.green }]}>今日行动 · 现在先做</Text>
          <Text style={[styles.nextActionTitle, { color: c.labelPrimary }]} numberOfLines={2}>
            {title}
          </Text>
          {impactMetrics.length > 0 ? (
            <View style={styles.nextActionImpact}>
              <Text style={[styles.nextActionImpactLabel, { color: c.labelTertiary }]}>影响指标</Text>
              <View style={styles.nextActionImpactChips}>
                {impactMetrics.map(metric => {
                  const color = c[metric.colorName];
                  return (
                    <View key={metric.key} style={[styles.nextActionImpactChip, { backgroundColor: c[metric.tintName] }]}>
                      <Ionicons name={metric.icon} size={12} color={color} />
                      <Text style={[styles.nextActionImpactText, { color }]}>{metric.label}</Text>
                    </View>
                  );
                })}
              </View>
            </View>
          ) : null}
          <Text style={[styles.nextActionReason, { color: c.labelSecondary }]} numberOfLines={2}>
            {reason}
          </Text>
        </View>
      </View>
      {completionState === 'error' ? (
        <View style={[styles.nextActionError, { backgroundColor: c.tintRed }]}>
          <Ionicons name="alert-circle-outline" size={14} color={c.red} />
          <Text style={[styles.nextActionErrorText, { color: c.red }]}>记录失败，请重试</Text>
        </View>
      ) : null}
      <View style={styles.nextActionButtons}>
        <Pressable
          onPress={() => (hasAction && action ? onStart(action) : onFallbackRecord())}
          style={({ pressed }) => [
            styles.nextActionPrimary,
            { backgroundColor: c.green, opacity: pressed ? 0.82 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel={hasAction ? `开始 ${title}` : '开始记录'}
        >
          <Ionicons name="play-outline" size={16} color="#FFFFFF" />
          <Text style={styles.nextActionPrimaryText}>开始</Text>
        </Pressable>
        {hasAction && action?.action_key ? (
          <Pressable
            onPress={() => onComplete(action)}
            disabled={completionState === 'sending' || completionState === 'completed'}
            style={({ pressed }) => [
              styles.nextActionComplete,
              {
                borderColor: completionState === 'completed' ? c.green : c.separator,
                backgroundColor: completionState === 'completed' ? c.tintGreen : c.bgPrimary,
                opacity: pressed ? 0.72 : 1,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`完成 ${title}`}
          >
            <Ionicons
              name={completionState === 'completed' ? 'checkmark-circle' : 'checkmark-circle-outline'}
              size={15}
              color={completionState === 'completed' ? c.green : c.labelSecondary}
            />
            <Text
              style={[
                styles.nextActionCompleteText,
                { color: completionState === 'completed' ? c.green : c.labelSecondary },
              ]}
            >
              {completionState === 'sending' ? '记录中' : completionState === 'completed' ? '已完成' : '完成'}
            </Text>
          </Pressable>
        ) : null}
        <Pressable
          onPress={onFallbackAgent}
          style={({ pressed }) => [
            styles.nextActionSecondary,
            { borderColor: c.separator, opacity: pressed ? 0.7 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel="问 Agent 调整下一步"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={15} color={c.brand} />
          <Text style={[styles.nextActionSecondaryText, { color: c.brand }]}>调整</Text>
        </Pressable>
      </View>
    </View>
  );
}

function SectionHeader({
  title,
  subtitle,
  action,
  onPress,
}: {
  title: string;
  subtitle?: string;
  action?: string;
  onPress?: () => void;
}) {
  const { c } = useTheme();
  return (
    <View style={styles.sectionHeader}>
      <View style={styles.sectionHeaderText}>
        <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>{title}</Text>
        {subtitle ? <Text style={[styles.sectionSubtitle, { color: c.labelTertiary }]}>{subtitle}</Text> : null}
      </View>
      {action && onPress ? (
        <Pressable
          onPress={onPress}
          style={({ pressed }) => [styles.sectionAction, { opacity: pressed ? 0.65 : 1 }]}
          accessibilityRole="button"
          accessibilityLabel={action}
        >
          <Text style={[styles.sectionActionText, { color: c.brand }]}>{action}</Text>
          <Ionicons name="chevron-forward" size={13} color={c.brand} />
        </Pressable>
      ) : null}
    </View>
  );
}

function isBodyMeasurementAction(action: DailyPlanAction): boolean {
  if (action.domain !== 'measurement') return false;
  const haystack = `${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();
  return /体重|腰围|weight|waist|bmi/.test(haystack);
}

const IMPACT_METRIC_DEFINITIONS: Record<string, ImpactMetricChip> = {
  sleep_score: { key: 'sleep_score', label: '睡眠分', icon: 'moon-outline', colorName: 'purple', tintName: 'tintPurple' },
  hrv: { key: 'hrv', label: 'HRV', icon: 'pulse-outline', colorName: 'teal', tintName: 'tintTeal' },
  spo2: { key: 'spo2', label: '血氧', icon: 'water-outline', colorName: 'blue', tintName: 'tintBlue' },
  bmi: { key: 'bmi', label: 'BMI', icon: 'body-outline', colorName: 'green', tintName: 'tintGreen' },
  body_fat: { key: 'body_fat', label: '体脂', icon: 'fitness-outline', colorName: 'orange', tintName: 'tintOrange' },
  vo2max: { key: 'vo2max', label: 'VO2max', icon: 'walk-outline', colorName: 'green', tintName: 'tintGreen' },
  blood_pressure: { key: 'blood_pressure', label: '血压', icon: 'heart-outline', colorName: 'pink', tintName: 'tintPink' },
  labs: { key: 'labs', label: '血检', icon: 'flask-outline', colorName: 'red', tintName: 'tintRed' },
  precision: { key: 'precision', label: '建议精度', icon: 'analytics-outline', colorName: 'teal', tintName: 'tintTeal' },
};

function buildActionImpactMetrics(action?: DailyPlanAction | null): ImpactMetricChip[] {
  const picked: ImpactMetricChip[] = [];
  const seen = new Set<string>();
  const add = (...keys: string[]) => {
    for (const key of keys) {
      const metric = IMPACT_METRIC_DEFINITIONS[key];
      if (!metric || seen.has(metric.key) || picked.length >= 3) continue;
      seen.add(metric.key);
      picked.push(metric);
    }
  };

  if (!action) {
    add('precision');
    return picked;
  }

  const metricText = `${action.metric_key ?? ''} ${action.verification?.metric ?? ''}`.toLowerCase();
  const haystack = [
    action.domain,
    action.action_key,
    action.title,
    action.why,
    action.when,
    action.metric_key,
    action.target_value,
    action.verification?.metric,
  ].filter(Boolean).join(' ').toLowerCase();

  if (/sleep|sleep_score|睡眠|入睡|上床|bedtime/.test(metricText)) add('sleep_score');
  if (/hrv|recovery|body_battery|恢复/.test(metricText)) add('hrv');
  if (/spo2|oxygen|血氧/.test(metricText)) add('spo2');
  if (/bmi|weight|waist|体重|腰围/.test(metricText)) add('bmi', 'body_fat');
  if (/body_fat|fat|体脂/.test(metricText)) add('body_fat');
  if (/vo2|max|cardio|最大摄氧/.test(metricText)) add('vo2max');
  if (/bp|blood_pressure|pressure|血压/.test(metricText)) add('blood_pressure');
  if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|lab|blood|血液|血糖|血脂|生化/.test(metricText)) add('labs');

  if (/sleep|bed|睡眠|入睡|上床|节律|夜间|spo2|血氧|hrv|恢复/.test(haystack)) add('sleep_score', 'hrv', 'spo2');
  if (/mood|emotion|mental|stress|breath|情绪|压力|呼吸|焦虑|冥想/.test(haystack)) add('hrv', 'sleep_score');
  if (/movement|exercise|workout|walk|run|zone|运动|训练|步行|跑|vo2|max|最大摄氧|有氧/.test(haystack)) add('vo2max', 'hrv', 'body_fat');
  if (/nutrition|diet|meal|protein|water|food|calorie|饮食|蛋白|热量|饮水|午餐|晚餐|早餐/.test(haystack)) add('body_fat', 'bmi', 'labs');
  if (/weight|waist|bmi|body fat|体重|腰围|体脂|身材/.test(haystack)) add('bmi', 'body_fat');
  if (/bp|blood pressure|血压/.test(haystack)) add('blood_pressure');
  if (/lab|blood|ldl|hdl|tg|hba1c|glucose|alt|ast|血液|血糖|血脂|生化|体检|化验/.test(haystack)) add('labs');

  if (picked.length === 0) add('precision');
  return picked;
}

function buildOutcomeFeedbackMetrics(
  twinSnapshot: TwinSnapshot,
  action?: DailyPlanAction | null,
): OutcomeFeedbackMetric[] {
  const metrics: OutcomeFeedbackMetric[] = [];
  const seen = new Set<string>();
  const add = (key: string) => {
    const normalizedKey = key === 'bmi' || key === 'body_fat' ? 'body_shape' : key;
    if (seen.has(normalizedKey) || metrics.length >= 4) return;
    const metric = buildOutcomeFeedbackMetric(normalizedKey, twinSnapshot);
    if (!metric) return;
    seen.add(normalizedKey);
    metrics.push(metric);
  };

  const deferredImpactKeys: string[] = [];
  buildActionImpactMetrics(action).forEach(metric => {
    if (metric.key === 'labs' || metric.key === 'precision') {
      deferredImpactKeys.push(metric.key);
      return;
    }
    add(metric.key);
  });
  ['sleep_score', 'hrv', 'spo2', 'body_shape', 'blood_pressure'].forEach(add);
  deferredImpactKeys.forEach(add);

  return metrics.slice(0, 4);
}

function buildOutcomeFeedbackMetric(
  key: string,
  twinSnapshot: TwinSnapshot,
): OutcomeFeedbackMetric | null {
  if (key === 'sleep_score') {
    return {
      key,
      label: '睡眠分',
      value: twinSnapshot.sleep_score != null ? `${fmt(twinSnapshot.sleep_score)} 分` : '待同步',
      detail: '睡眠干预',
      icon: 'moon-outline',
      colorName: 'purple',
      tintName: 'tintPurple',
      route: '/sleep',
    };
  }
  if (key === 'hrv') {
    return {
      key,
      label: 'HRV',
      value: twinSnapshot.hrv != null ? `${fmt(twinSnapshot.hrv)} ms` : '待同步',
      detail: '恢复弹性',
      icon: 'pulse-outline',
      colorName: 'teal',
      tintName: 'tintTeal',
      route: '/indicator-history?type=hrv',
    };
  }
  if (key === 'spo2') {
    return {
      key,
      label: '血氧',
      value: twinSnapshot.spo2_avg != null ? `${fmt(twinSnapshot.spo2_avg)} %` : '待同步',
      detail: '夜间均值',
      icon: 'water-outline',
      colorName: 'blue',
      tintName: 'tintBlue',
      route: '/sleep-spo2-analysis',
    };
  }
  if (key === 'body_shape') {
    const bmi = twinSnapshot.bmi;
    const bodyFat = twinSnapshot.body_fat_pct;
    const value = bmi != null && bodyFat != null
      ? `${fmt(bmi)} / ${fmt(bodyFat)}%`
      : bmi != null
        ? `${fmt(bmi)} BMI`
        : bodyFat != null
          ? `${fmt(bodyFat)}%`
          : '待记录';
    return {
      key,
      label: 'BMI/体脂',
      value,
      detail: '身材反馈',
      icon: 'body-outline',
      colorName: 'green',
      tintName: 'tintGreen',
      route: '/body-measurements?focus=morning',
    };
  }
  if (key === 'blood_pressure') {
    return {
      key,
      label: '血压',
      value: twinSnapshot.systolic_bp && twinSnapshot.diastolic_bp
        ? `${twinSnapshot.systolic_bp}/${twinSnapshot.diastolic_bp}`
        : '待记录',
      detail: '心血管反馈',
      icon: 'heart-outline',
      colorName: 'pink',
      tintName: 'tintPink',
      route: '/indicator-history?type=blood_pressure',
    };
  }
  if (key === 'vo2max') {
    return {
      key,
      label: 'VO2max',
      value: twinSnapshot.vo2max != null ? fmt(twinSnapshot.vo2max) : '待估算',
      detail: '有氧能力',
      icon: 'walk-outline',
      colorName: 'green',
      tintName: 'tintGreen',
      route: '/movement-plan',
    };
  }
  if (key === 'labs') {
    return {
      key,
      label: '血液/生化',
      value: '待复盘',
      detail: '化验指标',
      icon: 'flask-outline',
      colorName: 'red',
      tintName: 'tintRed',
      route: '/medical-exams',
    };
  }
  if (key === 'precision') {
    return {
      key,
      label: '建议精度',
      value: '4 源',
      detail: '画像完整度',
      icon: 'analytics-outline',
      colorName: 'teal',
      tintName: 'tintTeal',
      route: '/(tabs)/chat',
    };
  }
  return null;
}

function buildInterventionDomainStatuses(actions: DailyPlanAction[]): InterventionDomainStatus[] {
  const counts = INTERVENTION_DOMAINS.reduce<Record<InterventionDomainKey, number>>((acc, domain) => {
    acc[domain.key] = 0;
    return acc;
  }, {} as Record<InterventionDomainKey, number>);

  for (const action of actions) {
    const key = classifyInterventionDomain(action);
    if (key) counts[key] += 1;
  }

  return INTERVENTION_DOMAINS.map(domain => ({
    ...domain,
    activeCount: counts[domain.key],
  }));
}

function buildAgentLoopStrategy({
  activeCount,
  action,
  riskTitle,
}: {
  activeCount: number;
  action?: DailyPlanAction | null;
  riskTitle?: string;
}) {
  const haystack = `${riskTitle ?? ''} ${action?.domain ?? ''} ${action?.title ?? ''} ${action?.why ?? ''} ${action?.metric_key ?? ''}`.toLowerCase();
  const activeLabel = activeCount > 0 ? `${activeCount}项` : null;

  if (/spo2|oxygen|血氧|呼吸|睡眠|鼾|鼻/.test(haystack)) {
    return {
      subtitle: '先稳夜间血氧，再看睡眠分和 HRV 是否回升',
      diagnosisLabel: '血氧风险',
      interventionLabel: activeLabel ?? '睡眠优先',
      verificationLabel: '血氧/睡眠',
    };
  }
  if (/bmi|weight|waist|fat|体重|腰围|体脂|身材/.test(haystack)) {
    return {
      subtitle: '用饮食和运动干预体成分，再看 BMI/体脂变化',
      diagnosisLabel: '体成分',
      interventionLabel: activeLabel ?? '饮食+运动',
      verificationLabel: 'BMI/体脂',
    };
  }
  if (/bp|blood_pressure|pressure|血压|心血管/.test(haystack)) {
    return {
      subtitle: '先降低心血管负荷，再跟踪血压、HRV 和睡眠恢复',
      diagnosisLabel: '血压负荷',
      interventionLabel: activeLabel ?? '恢复优先',
      verificationLabel: '血压/HRV',
    };
  }
  if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|uric|lab|blood|血糖|血脂|尿酸|肝|生化|血检/.test(haystack)) {
    return {
      subtitle: '先调整饮食、运动和补剂，再用血液/生化指标复盘',
      diagnosisLabel: '生化指标',
      interventionLabel: activeLabel ?? '代谢优先',
      verificationLabel: '血检/体成分',
    };
  }

  return {
    subtitle: activeCount > 0
      ? `${activeCount} 个任务用真实反馈校准下一步`
      : '保持记录节奏，Agent 用关键指标寻找下一轮干预机会',
    diagnosisLabel: '实时',
    interventionLabel: activeLabel ?? '观察中',
    verificationLabel: '',
  };
}

function pickPriorityInterventionDomains(
  domains: InterventionDomainStatus[],
  riskTitle?: string,
  action?: DailyPlanAction | null,
): InterventionDomainStatus[] {
  const activeDomains = domains.filter(domain => domain.activeCount > 0);
  if (activeDomains.length > 0) return activeDomains;

  const haystack = `${riskTitle ?? ''} ${action?.domain ?? ''} ${action?.title ?? ''} ${action?.why ?? ''} ${action?.metric_key ?? ''}`.toLowerCase();
  let priority: InterventionDomainKey[] = [];
  if (/spo2|oxygen|血氧|呼吸|睡眠|鼾|鼻/.test(haystack)) {
    priority = ['sleep', 'emotion', 'movement'];
  } else if (/bmi|weight|waist|fat|体重|腰围|体脂|身材/.test(haystack)) {
    priority = ['diet', 'movement', 'sleep'];
  } else if (/bp|blood_pressure|pressure|血压|心血管/.test(haystack)) {
    priority = ['movement', 'sleep', 'emotion', 'diet'];
  } else if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|uric|lab|blood|血糖|血脂|尿酸|肝|生化|血检/.test(haystack)) {
    priority = ['diet', 'movement', 'supplement', 'sleep'];
  }

  if (priority.length === 0) return domains;
  const byKey = new Map(domains.map(domain => [domain.key, domain]));
  return priority.map(key => byKey.get(key)).filter(Boolean) as InterventionDomainStatus[];
}

function buildWorkspaceDataSources({
  geneticHits,
  progressTotal,
  twinSnapshot,
}: {
  geneticHits?: number | null;
  progressTotal?: number | null;
  twinSnapshot: TwinSnapshot;
}) {
  const wearableReady = Boolean(
    twinSnapshot.hrv
    || twinSnapshot.sleep_score
    || twinSnapshot.resting_hr
    || twinSnapshot.spo2_avg,
  );
  const clinicalReady = Boolean(twinSnapshot.systolic_bp || twinSnapshot.diastolic_bp);

  return [
    {
      key: 'genetic',
      label: '基因',
      status: geneticHits != null ? 'ready' : 'available',
      value: geneticHits != null ? `${geneticHits} 位点` : null,
    },
    {
      key: 'epigenetic',
      label: '表观',
      status: progressTotal != null ? 'tracked' : 'lifestyle_proxy',
      value: progressTotal != null ? `${progressTotal} 轨迹` : null,
    },
    {
      key: 'clinical',
      label: '体检',
      status: clinicalReady ? 'ready' : 'missing_or_stale',
      value: clinicalReady ? '指标反馈' : null,
    },
    {
      key: 'wearable',
      label: '穿戴',
      status: wearableReady ? 'live' : 'missing_or_stale',
      value: wearableReady ? '实时回流' : null,
    },
  ];
}

function buildLiveSignalSummary(twinSnapshot: TwinSnapshot): string {
  const signals: string[] = [];
  if (twinSnapshot.sleep_score != null) signals.push(`睡眠 ${fmt(twinSnapshot.sleep_score)}分`);
  if (twinSnapshot.hrv != null) signals.push(`HRV ${fmt(twinSnapshot.hrv)}ms`);
  if (twinSnapshot.spo2_avg != null) signals.push(`血氧 ${fmt(twinSnapshot.spo2_avg)}%`);
  if (twinSnapshot.bmi != null) signals.push(`BMI ${fmt(twinSnapshot.bmi)}`);
  if (twinSnapshot.body_fat_pct != null) signals.push(`体脂 ${fmt(twinSnapshot.body_fat_pct)}%`);
  if (twinSnapshot.vo2max != null) signals.push(`VO2max ${fmt(twinSnapshot.vo2max)}`);
  if (signals.length === 0) return '可穿戴、身体记录和检查反馈';
  return signals.slice(0, 3).join('、');
}

function classifyInterventionDomain(action: DailyPlanAction): InterventionDomainKey | null {
  const haystack = `${action.domain ?? ''} ${action.action_key ?? ''} ${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();

  if (/supplement|补剂|镁|维生素|鱼油|益生菌/.test(haystack)) return 'supplement';
  if (/mood|emotion|mental|stress|breath|情绪|压力|呼吸|焦虑|冥想/.test(haystack)) return 'emotion';
  if (/sleep|bed|睡眠|入睡|上床|血氧|spo2|hrv|恢复/.test(haystack)) return 'sleep';
  if (/movement|exercise|workout|walk|run|zone|运动|训练|步行|跑|vo2|max|体脂/.test(haystack)) return 'movement';
  if (/nutrition|diet|meal|protein|water|food|饮食|蛋白|热量|饮水|午餐|晚餐|早餐/.test(haystack)) return 'diet';

  return null;
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
        <EvidenceRefsRow refs={card.evidence_refs} />
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

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function formatHomeDate(value: Date): string {
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][value.getDay()];
  return `${value.getMonth() + 1}月${value.getDate()}日 · ${weekday}`;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },  // 110 = tab bar 83 + 缓冲
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
  section: { gap: spacing.sm },
  commandHeader: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
    gap: 11,
  },
  commandAgentHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  commandAgentTitleBlock: { flex: 1, minWidth: 0, gap: 2 },
  commandAgentIdentity: { flexDirection: 'row', alignItems: 'center', gap: 7, minWidth: 0 },
  commandAgentLabel: { fontSize: 16, lineHeight: 20, fontWeight: '800' },
  commandAgentSubLabel: { fontSize: 11, lineHeight: 14, fontWeight: '700' },
  commandRightMeta: { alignItems: 'flex-end', gap: 6 },
  commandMetaPills: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 5 },
  evidencePill: {
    minHeight: 24,
    borderRadius: radii.full,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  evidenceText: { fontSize: 10, lineHeight: 12, fontWeight: '800' },
  commandAgentCopy: { flex: 1, fontSize: 12, lineHeight: 17, fontWeight: '700' },
  commandInsightBox: {
    minHeight: 36,
    borderRadius: radii.md,
    paddingHorizontal: 10,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
  },
  commandFocusArea: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: spacing.xs,
  },
  commandFocusTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  commandDecisionArea: { gap: 5 },
  commandTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  commandTitleBlock: { flex: 1, gap: 4, minWidth: 0 },
  commandStatusLine: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flexWrap: 'wrap' },
  commandDate: { fontSize: 11, lineHeight: 13, fontWeight: '800' },
  agentRunningPill: {
    minHeight: 22,
    borderRadius: radii.full,
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  agentRunningText: { fontSize: 12, fontWeight: '800' },
  commandSyncText: { fontSize: 11, fontWeight: '700' },
  commandFocusRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8, minWidth: 0 },
  commandFocusLabel: { fontSize: 12, lineHeight: 15, fontWeight: '800' },
  commandTitle: { minWidth: 0, fontSize: 23, fontWeight: '800', lineHeight: 29, letterSpacing: 0 },
  commandHint: { fontSize: 13, lineHeight: 18, fontWeight: '600' },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 9,
    paddingVertical: 6,
    borderRadius: radii.full,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 12, fontWeight: '800' },
  commandActions: { flexDirection: 'row', gap: spacing.sm },
  primaryAction: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.lg,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  primaryActionText: { color: '#FFFFFF', fontSize: 15, fontWeight: '800' },
  secondaryAction: {
    minHeight: 44,
    minWidth: 104,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  secondaryActionText: { fontSize: 14, fontWeight: '800' },
  workspaceCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: 8,
  },
  workspaceTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  workspaceStatusIcon: {
    width: 34,
    height: 34,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  workspaceTitleBlock: { flex: 1, minWidth: 0, gap: 3 },
  workspaceEyebrow: { fontSize: 12, fontWeight: '800' },
  workspaceTitle: { fontSize: 16, fontWeight: '800', lineHeight: 20 },
  workspaceCopy: { fontSize: 12, lineHeight: 16 },
  workspaceAskButton: {
    minHeight: 36,
    borderRadius: radii.full,
    paddingHorizontal: 11,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  workspaceAskText: { fontSize: 13, fontWeight: '800' },
  workspaceDetailBlock: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: 8,
    gap: 7,
  },
  workspaceDetailGroup: { gap: 5 },
  workspaceDetailHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm },
  workspaceDetailLabel: { fontSize: 10, lineHeight: 13, fontWeight: '800' },
  sourceRail: { flexDirection: 'row', flexWrap: 'nowrap', alignItems: 'center', gap: 5 },
  sourceChip: {
    flex: 1,
    minWidth: 0,
    minHeight: 26,
    borderRadius: radii.full,
    paddingHorizontal: 4,
    paddingVertical: 3,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sourceLabel: { fontSize: 10, fontWeight: '800' },
  sourceValue: { fontSize: 8, lineHeight: 10, fontWeight: '700', marginTop: 1, textAlign: 'center' },
  workspaceInterventionBlock: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: 9,
    gap: 8,
  },
  workspaceInterventionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  workspaceInterventionTitleBlock: { flex: 1, minWidth: 0, gap: 2 },
  workspaceInterventionTitle: { fontSize: 14, lineHeight: 18, fontWeight: '800' },
  workspaceInterventionHint: { fontSize: 12, lineHeight: 16, fontWeight: '500' },
  workspaceInterventionSummary: { fontSize: 12, lineHeight: 16, fontWeight: '800' },
  workspaceInterventionBadges: {
    alignItems: 'flex-end',
    gap: 5,
  },
  workspaceInterventionBadge: {
    minHeight: 25,
    borderRadius: radii.full,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  workspaceInterventionBadgeText: { fontSize: 11, fontWeight: '800' },
  interventionGrid: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
    gap: 5,
  },
  interventionDomain: {
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
    minHeight: 30,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.full,
    paddingHorizontal: 4,
    paddingVertical: 4,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  interventionDomainIcon: {
    width: 16,
    height: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  interventionDomainText: { alignItems: 'center', minWidth: 0, flexShrink: 1 },
  interventionDomainLabel: { fontSize: 10, lineHeight: 12, fontWeight: '800', textAlign: 'center' },
  interventionDomainStatus: { fontSize: 8, fontWeight: '700', marginTop: 1, textAlign: 'center' },
  nextActionCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: spacing.sm,
  },
  nextActionTop: { flexDirection: 'row', gap: spacing.sm },
  nextActionIcon: {
    width: 36,
    height: 36,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  nextActionMain: { flex: 1, gap: 3 },
  nextActionEyebrow: { fontSize: 12, fontWeight: '800' },
  nextActionTitle: { fontSize: 18, fontWeight: '800', lineHeight: 23 },
  nextActionReason: { fontSize: 13, lineHeight: 18 },
  nextActionImpact: { gap: 6 },
  nextActionImpactLabel: { fontSize: 11, fontWeight: '800' },
  nextActionImpactChips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  nextActionImpactChip: {
    minHeight: 26,
    borderRadius: radii.full,
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  nextActionImpactText: { fontSize: 11, fontWeight: '800' },
  nextActionError: {
    borderRadius: radii.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  nextActionErrorText: { fontSize: 12, fontWeight: '800' },
  nextActionButtons: { flexDirection: 'row', gap: spacing.sm },
  nextActionPrimary: {
    flex: 1,
    minHeight: 38,
    borderRadius: radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  nextActionPrimaryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
  nextActionSecondary: {
    minHeight: 38,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  nextActionSecondaryText: { fontSize: 14, fontWeight: '800' },
  nextActionComplete: {
    minHeight: 38,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  nextActionCompleteText: { fontSize: 14, fontWeight: '800' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
  sectionHeaderText: { flex: 1, gap: 2 },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  sectionSubtitle: { fontSize: 12, fontWeight: '500' },
  sectionAction: { flexDirection: 'row', alignItems: 'center', gap: 2, minHeight: 32 },
  sectionActionText: { fontSize: 13, fontWeight: '700' },
  loopCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    padding: spacing.md,
    gap: spacing.sm,
  },
  loopHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  loopIcon: {
    width: 36,
    height: 36,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loopTitleBlock: { flex: 1, minWidth: 0, gap: 2 },
  loopTitle: { fontSize: 16, lineHeight: 20, fontWeight: '800' },
  loopSubtitle: { fontSize: 12, lineHeight: 16, fontWeight: '600' },
  loopPipeline: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
  },
  loopPipelineStep: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  loopStepLabel: { fontSize: 10, lineHeight: 12, fontWeight: '700' },
  loopStepValue: { fontSize: 12, lineHeight: 15, fontWeight: '800' },
  loopDomainRail: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  loopDomainChip: {
    minHeight: 30,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.full,
    paddingHorizontal: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  loopDomainText: { fontSize: 12, lineHeight: 14, fontWeight: '800' },
  loopMetricRail: { flexDirection: 'row', gap: spacing.xs },
  loopMetricTile: {
    flex: 1,
    minWidth: 0,
    minHeight: 70,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: 8,
    paddingVertical: 8,
    justifyContent: 'center',
    gap: 4,
  },
  loopMetricIcon: {
    width: 24,
    height: 24,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loopMetricLabel: { fontSize: 10, lineHeight: 12, fontWeight: '700' },
  loopMetricValue: { fontSize: 14, lineHeight: 17, fontWeight: '800', fontVariant: ['tabular-nums'] },
  compactSection: { gap: spacing.sm },
  shortcutRail: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  shortcutPill: {
    width: '48.5%',
    minHeight: 58,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    paddingHorizontal: 11,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  shortcutIcon: {
    width: 30, height: 30, borderRadius: 9,
    alignItems: 'center', justifyContent: 'center',
  },
  shortcutTextBlock: { flex: 1, minWidth: 0 },
  shortcutLabel: { fontSize: 11, fontWeight: '600' },
  shortcutValue: { fontSize: 14, fontWeight: '800', marginTop: 1 },
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
});
