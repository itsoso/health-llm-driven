/**
 * 今日 Tab —— Agent 工作台 (2026-05-23).
 *
 * 设计 (Agent Native Mobile First):
 *   1. 首屏先回答 Agent 正在后台做什么.
 *   2. 再给出今天最该执行的一步.
 *   3. 最后下沉身体反馈、本周建议和长期档案.
 */

import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
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
import { pushChatWithContext } from '../../utils/agentContext';
import {
  getDailyOperatingPlan,
  recordDailyPlanActionEvent,
  type DailyOperatingPlan,
  type DailyPlanAction,
} from '../../services/dailyPlan';
import {
  getHealthTrajectory,
  pickPrimaryTrajectoryRisks,
  type HealthTrajectorySnapshot,
} from '../../services/trajectory';

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
          action={nextAction}
          onOpenFocus={() => (
            criticalAlerts.length > 0
              ? router.push('/alerts' as any)
              : nextAction
                ? openPlanAction(nextAction)
                : router.push('/(tabs)/record' as any)
          )}
          onOpenAgent={openWorkspaceChat}
          onOpenMetric={(route) => router.push(route as any)}
        />

        {nextAction ? (
          <PlanQueueCompactRow
            plan={dailyPlanQuery.data}
            action={nextAction}
            completionState={visibleNextActionState}
            excludeActionKey={nextActionKey}
            onComplete={completeNextAction}
            onFallbackAgent={() => router.push('/(tabs)/chat' as any)}
          />
        ) : criticalAlerts.length === 0 ? (
          <TodayExecutionQueue
            plan={dailyPlanQuery.data}
            action={null}
            loading={dailyPlanQuery.isLoading}
            completionState={visibleNextActionState}
            excludeActionKey={nextActionKey}
            onStart={openPlanAction}
            onComplete={completeNextAction}
            onFallbackRecord={() => router.push('/(tabs)/record' as any)}
            onFallbackAgent={() => router.push('/(tabs)/chat' as any)}
          />
        ) : null}

        {isLoading && (
          <View style={styles.loading}>
            <ActivityIndicator />
          </View>
        )}

        <View style={[styles.section, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
          <AgentFollowUpQueue
            snapshot={trajectoryQuery.data}
            loading={trajectoryQuery.isLoading}
            weeklyAdvice={weeklyAdvice}
            onOpenTrajectory={openTrajectoryChat}
            onOpenAdvice={(card) => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
          />
          <EnvironmentCard compact mode="micro" />
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
  action,
  onOpenFocus,
  onOpenAgent,
  onOpenMetric,
}: {
  criticalCount: number;
  planCount: number;
  refreshing: boolean;
  riskTitle?: string;
  geneticHits?: number | null;
  progressTotal?: number | null;
  twinSnapshot: TwinSnapshot;
  domains: InterventionDomainStatus[];
  action?: DailyPlanAction | null;
  onOpenFocus: () => void;
  onOpenAgent: () => void;
  onOpenMetric: (route: string) => void;
}) {
  const { c } = useTheme();
  const statusColor = criticalCount > 0 ? c.red : c.green;
  const statusLabel = criticalCount > 0
    ? `${criticalCount} 个风险`
    : planCount > 0
      ? `${planCount} 个计划`
      : '状态稳定';
  const activeDomainCount = domains.filter(domain => domain.activeCount > 0).length;
  const wearableReady = Boolean(
    twinSnapshot.hrv
    || twinSnapshot.sleep_score
    || twinSnapshot.resting_hr
    || twinSnapshot.spo2_avg,
  );
  const clinicalReady = Boolean(twinSnapshot.systolic_bp || twinSnapshot.diastolic_bp);
  const activeCount = domains.reduce((sum, domain) => sum + domain.activeCount, 0);
  const loopStrategy = buildAgentLoopStrategy({ activeCount, action, riskTitle });
  const loopMetrics = buildLoopFeedbackMetrics(twinSnapshot, action, riskTitle);
  const visibleLoopMetrics = loopMetrics.slice(0, 3);
  const activeDomainLabels = domains
    .filter(domain => domain.activeCount > 0)
    .map(domain => domain.label);
  const activeDomainSummary = activeDomainLabels.length > 3
    ? `${activeDomainLabels.slice(0, 3).join('/')} +${activeDomainLabels.length - 3}`
    : activeDomainLabels.join('/');
  const improvementFocus = buildImprovementFocus({
    action,
    criticalCount,
    planCount,
    riskTitle,
    activeDomainCount,
    loopMetrics,
  });
  const headline = criticalCount > 0
    ? improvementFocus.headline
    : planCount > 0
      ? improvementFocus.headline
      : '保持记录节奏';
  const focusKicker = criticalCount > 0
    ? '今日洞察 · 风险优先'
    : activeDomainCount > 0
      ? `今日洞察 · ${activeDomainCount} 个干预域`
      : '今日洞察 · 观察中';
  const focusText = criticalCount > 0
    ? improvementFocus.target
    : planCount > 0
      ? improvementFocus.target
      : improvementFocus.target;
  const evidenceSummary = `依据：${buildEvidenceSourceSummary({
    hasGenetic: geneticHits != null,
    hasClinical: clinicalReady,
    hasWearable: wearableReady,
  })}`;
  const agentStepItems = [
    { key: 'strategy', label: '策略', value: activeDomainSummary || loopStrategy.interventionLabel },
    {
      key: 'watch',
      label: '观察',
      value: loopStrategy.verificationLabel || loopMetrics.map(metric => metric.label).slice(0, 2).join('/'),
    },
  ] as const;
  const agentLoopLine = agentStepItems
    .filter(item => item.value)
    .map(item => `${item.label} ${item.value}`)
    .join(' · ');
  const nextStepLabel = buildHomeNextStepLabel({ action, criticalCount });
  const nextStepActionText = nextStepLabel.replace(/^下一步：/, '');
  const decisionIcon: keyof typeof Ionicons.glyphMap = criticalCount > 0 ? 'warning-outline' : 'sparkles-outline';
  const decisionColor = criticalCount > 0 ? c.red : c.brand;
  const decisionTint = criticalCount > 0 ? c.tintRed : c.brandLight;
  return (
    <View style={[styles.commandHeader, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.commandAgentHeader}>
        <View style={styles.commandAgentTitleBlock}>
          <View style={styles.commandAgentIdentity}>
            <View style={[styles.statusDot, { backgroundColor: c.brand }]} />
            <Text style={[styles.commandAgentLabel, { color: c.labelPrimary }]}>健康 Agent</Text>
            <Text style={[styles.commandAgentSubLabel, { color: c.labelTertiary }]}>
              {refreshing ? '正在同步新数据' : '后台监测中'}
            </Text>
          </View>
          <Text style={[styles.commandAgentCopy, { color: c.labelTertiary }]} numberOfLines={1}>
            {evidenceSummary}
          </Text>
        </View>
        <View style={styles.commandRightMeta}>
          <View style={styles.commandRightTop}>
            <View style={[styles.statusPill, { backgroundColor: `${statusColor}14` }]}>
              <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
              <Text style={[styles.statusText, { color: statusColor }]}>{statusLabel}</Text>
            </View>
          </View>
          <View style={styles.commandMiniActions}>
            <Pressable
              onPress={onOpenAgent}
              style={({ pressed }) => [
                styles.commandMiniAction,
                { backgroundColor: c.bgPrimary, borderColor: c.separator, opacity: pressed ? 0.7 : 1 },
              ]}
              accessibilityRole="button"
              accessibilityLabel="问 Agent"
            >
              <Ionicons name="chatbubble-ellipses-outline" size={15} color={c.brand} />
              <Text style={[styles.commandMiniActionText, { color: c.brand }]}>问 Agent</Text>
            </Pressable>
          </View>
        </View>
      </View>

      <Pressable
        style={({ pressed }) => [
          styles.commandDecisionArea,
          {
            backgroundColor: c.bgPrimary,
            borderColor: `${decisionColor}30`,
            opacity: pressed ? 0.78 : 1,
          },
        ]}
        onPress={onOpenFocus}
        accessibilityRole="button"
        accessibilityLabel="打开今日重点"
      >
        <View style={styles.commandDecisionTop}>
          <View style={[styles.commandDecisionIcon, { backgroundColor: decisionTint }]}>
            <Ionicons name={decisionIcon} size={18} color={decisionColor} />
          </View>
          <View style={styles.commandTitleBlock}>
            <Text style={[styles.commandFocusLabel, { color: decisionColor }]}>{focusKicker}</Text>
            <Text style={[styles.commandTitle, { color: c.labelPrimary }]} numberOfLines={2}>
              {headline}
            </Text>
          </View>
        </View>
        <Text style={[styles.commandHint, { color: c.labelSecondary }]} numberOfLines={2}>{focusText}</Text>
        <View style={[styles.commandLoopLine, { backgroundColor: c.bgCard }]}>
          <Ionicons name="git-compare-outline" size={13} color={decisionColor} />
          <Text style={[styles.commandLoopText, { color: c.labelSecondary }]} numberOfLines={1}>
            {agentLoopLine}
          </Text>
        </View>
      </Pressable>

      <View style={styles.commandMetricGrid}>
        {visibleLoopMetrics.map(metric => {
          const color = c[metric.colorName];
          return (
            <Pressable
              key={metric.key}
              onPress={() => onOpenMetric(metric.route)}
              style={({ pressed }) => [
                styles.commandMetricCard,
                { backgroundColor: c.bgPrimary, opacity: pressed ? 0.72 : 1 },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`${metric.label} ${metric.value}`}
            >
              <Text style={[styles.commandSignalLabel, { color: c.labelTertiary }]} numberOfLines={1}>
                {metric.label}
              </Text>
              <Text style={[styles.commandSignalValue, { color }]} numberOfLines={1}>
                {metric.value}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable
        onPress={onOpenFocus}
        style={({ pressed }) => [
          styles.commandNextStep,
          { backgroundColor: c.brand, borderColor: c.brand, opacity: pressed ? 0.82 : 1 },
        ]}
        accessibilityRole="button"
        accessibilityLabel="打开下一步"
      >
        <Ionicons name="arrow-forward-circle-outline" size={18} color="#FFFFFF" />
        <View style={styles.commandNextStepCopy}>
          <Text style={styles.commandNextStepLabel}>下一步</Text>
          <Text style={styles.commandNextStepText} numberOfLines={1}>{nextStepActionText}</Text>
        </View>
      </Pressable>

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
    <View style={[styles.shortcutCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.shortcutStrip}>
        <View style={styles.shortcutHeaderText}>
          <Text style={[styles.shortcutTitle, { color: c.labelPrimary }]}>长期档案</Text>
          <Text style={[styles.shortcutSubtitle, { color: c.labelTertiary }]}>基因/检查/趋势</Text>
        </View>
        <View style={styles.shortcutRail}>
          {shortcuts.map((item, index) => (
            <React.Fragment key={item.label}>
              <Pressable
                onPress={item.onPress}
                style={({ pressed }) => [
                  styles.shortcutTextButton,
                  { opacity: pressed ? 0.58 : 1 },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`${item.label} ${item.value}`}
              >
                <Text style={[styles.shortcutLabel, { color: c.labelSecondary }]} numberOfLines={1}>
                  {item.label}
                </Text>
              </Pressable>
              {index < shortcuts.length - 1 ? (
                <Text style={[styles.shortcutSeparatorText, { color: c.labelTertiary }]}>·</Text>
              ) : null}
            </React.Fragment>
          ))}
        </View>
        <Pressable
          onPress={onOpenAll}
          style={({ pressed }) => [styles.shortcutAllButton, { opacity: pressed ? 0.65 : 1 }]}
          accessibilityRole="button"
          accessibilityLabel="查看全部长期档案"
        >
          <Text style={[styles.shortcutAllText, { color: c.brand }]}>全部</Text>
          <Ionicons name="chevron-forward" size={13} color={c.brand} />
        </Pressable>
      </View>
    </View>
  );
}

function PlanQueueCompactRow({
  plan,
  action,
  completionState,
  excludeActionKey,
  onComplete,
  onFallbackAgent,
}: {
  plan?: DailyOperatingPlan | null;
  action: DailyPlanAction;
  completionState: NextActionCompletionState;
  excludeActionKey?: string | null;
  onComplete: (action: DailyPlanAction) => void;
  onFallbackAgent: () => void;
}) {
  const { c } = useTheme();
  const remainingActionCount = Math.max(
    0,
    (plan?.actions ?? []).filter(item => (item.action_key || item.title) !== excludeActionKey).length,
  );
  const queueSummary = remainingActionCount > 0
    ? `余下 ${remainingActionCount} 件后台排队`
    : '完成后 Agent 再排下一步';
  const canComplete = Boolean(action.action_key);

  return (
    <View style={styles.planQueueBlock}>
      <View style={[styles.planQueueStrip, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
        <View style={[styles.planQueueIcon, { backgroundColor: c.tintGreen }]}>
          <Ionicons name="layers-outline" size={15} color={c.green} />
        </View>
        <View style={styles.planQueueText}>
          <Text style={[styles.planQueueTitle, { color: c.labelPrimary }]}>后台排队</Text>
          <Text style={[styles.planQueueSubtitle, { color: c.labelSecondary }]} numberOfLines={1}>
            {queueSummary}
          </Text>
        </View>
        {canComplete ? (
          <Pressable
            onPress={() => onComplete(action)}
            disabled={completionState === 'sending' || completionState === 'completed'}
            style={({ pressed }) => [
              styles.planQueueDoneButton,
              {
                backgroundColor: completionState === 'completed' ? c.tintGreen : c.bgPrimary,
                borderColor: completionState === 'completed' ? c.green : c.separator,
                opacity: pressed ? 0.72 : 1,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="完成当前行动"
          >
            <Ionicons
              name={completionState === 'completed' ? 'checkmark-circle' : 'checkmark-circle-outline'}
              size={14}
              color={completionState === 'completed' ? c.green : c.labelSecondary}
            />
            <Text
              style={[
                styles.planQueueDoneText,
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
            styles.planQueueAdjustButton,
            { backgroundColor: c.brandLight, opacity: pressed ? 0.72 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel="问 Agent 调整后台排队"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={14} color={c.brand} />
        </Pressable>
      </View>
      {completionState === 'error' ? (
        <View style={[styles.nextActionError, { backgroundColor: c.tintRed }]}>
          <Ionicons name="alert-circle-outline" size={14} color={c.red} />
          <Text style={[styles.nextActionErrorText, { color: c.red }]}>记录失败，请重试</Text>
        </View>
      ) : null}
    </View>
  );
}

function TodayExecutionQueue({
  plan,
  action,
  loading,
  completionState,
  excludeActionKey,
  onStart,
  onComplete,
  onFallbackRecord,
  onFallbackAgent,
}: {
  plan?: DailyOperatingPlan | null;
  action?: DailyPlanAction | null;
  loading?: boolean;
  completionState: NextActionCompletionState;
  excludeActionKey?: string | null;
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
  const totalActionCount = plan?.actions?.length ?? 0;
  const remainingActionCount = Math.max(
    0,
    (plan?.actions ?? []).filter(item => (item.action_key || item.title) !== excludeActionKey).length,
  );
  const queueSubtitle = loading
    ? 'Agent 正在排序最小下一步'
    : totalActionCount > 0
      ? totalActionCount === 1
        ? '1 件事正在执行闭环'
        : `${totalActionCount} 件事后台排队，只露出最该做的一件`
      : '先补齐数据，Agent 再生成干预';
  const queueSummary = remainingActionCount > 0
    ? `余下 ${remainingActionCount} 件后台排队，完成后再推送`
    : '完成后 Agent 会根据新反馈排下一步';

  return (
    <View style={[styles.executionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.executionHeader}>
        <View style={[styles.executionIcon, { backgroundColor: c.tintGreen }]}>
          <Ionicons name="radio-button-on-outline" size={17} color={c.green} />
        </View>
        <View style={styles.executionHeaderText}>
          <Text style={[styles.executionTitle, { color: c.labelPrimary }]}>现在只做一件</Text>
          <Text style={[styles.executionSubtitle, { color: c.labelTertiary }]}>{queueSubtitle}</Text>
        </View>
        <Pressable
          onPress={onFallbackAgent}
          style={({ pressed }) => [
            styles.executionAdjustButton,
            { backgroundColor: c.brandLight, opacity: pressed ? 0.72 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel="问 Agent 调整后台排队"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={13} color={c.brand} />
          <Text style={[styles.executionAdjustText, { color: c.brand }]}>调整</Text>
        </Pressable>
      </View>

      <View style={[styles.executionPrimary, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
        <View style={styles.executionPrimaryTop}>
          <Text style={[styles.executionEyebrow, { color: c.green }]}>现在先做</Text>
          <Text style={[styles.executionPrimaryTitle, { color: c.labelPrimary }]} numberOfLines={2}>
            {title}
          </Text>
        </View>
        <Text style={[styles.executionReason, { color: c.labelSecondary }]} numberOfLines={2}>
          {reason}
        </Text>
        {impactMetrics.length > 0 ? (
          <View style={styles.executionImpactChips}>
            {impactMetrics.map(metric => {
              const color = c[metric.colorName];
              return (
                <View key={metric.key} style={[styles.executionImpactChip, { backgroundColor: c[metric.tintName] }]}>
                  <Text style={[styles.executionImpactText, { color }]}>{metric.label}</Text>
                </View>
              );
            })}
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
            <Ionicons name="play-outline" size={15} color="#FFFFFF" />
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
                  backgroundColor: completionState === 'completed' ? c.tintGreen : c.bgCard,
                  opacity: pressed ? 0.72 : 1,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`完成 ${title}`}
            >
              <Ionicons
                name={completionState === 'completed' ? 'checkmark-circle' : 'checkmark-circle-outline'}
                size={14}
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
        </View>
      </View>

      {completionState === 'error' ? (
        <View style={[styles.nextActionError, { backgroundColor: c.tintRed }]}>
          <Ionicons name="alert-circle-outline" size={14} color={c.red} />
          <Text style={[styles.nextActionErrorText, { color: c.red }]}>记录失败，请重试</Text>
        </View>
      ) : null}

      <Pressable
        onPress={onFallbackAgent}
        style={({ pressed }) => [
          styles.executionQueueSummary,
          { backgroundColor: c.bgPrimary, opacity: pressed ? 0.68 : 1 },
        ]}
        accessibilityRole="button"
        accessibilityLabel="查看后台排队任务"
      >
        <Ionicons name="layers-outline" size={14} color={c.labelSecondary} />
        <Text style={[styles.executionQueueSummaryText, { color: c.labelSecondary }]} numberOfLines={1}>
          {queueSummary}
        </Text>
        <Ionicons name="chevron-forward" size={13} color={c.labelTertiary} />
      </Pressable>
    </View>
  );
}

function AgentFollowUpQueue({
  snapshot,
  loading,
  weeklyAdvice,
  onOpenTrajectory,
  onOpenAdvice,
}: {
  snapshot?: HealthTrajectorySnapshot | null;
  loading?: boolean;
  weeklyAdvice: ActionCard[];
  onOpenTrajectory: () => void;
  onOpenAdvice: (card: ActionCard) => void;
}) {
  const { c } = useTheme();
  const trajectoryRisks = pickPrimaryTrajectoryRisks(snapshot?.trajectory_risks ?? [], 2);
  const gapCount = snapshot?.data_gaps?.length ?? 0;
  const visibleAdvice = weeklyAdvice.slice(0, 1);
  const primaryRisk = trajectoryRisks[0] ?? null;
  const primaryAdvice = visibleAdvice[0] ?? null;
  const showPrimaryAdvice = !primaryRisk && !!primaryAdvice;
  const hiddenCount = Math.max(
    0,
    trajectoryRisks.length - (primaryRisk ? 1 : 0)
    + weeklyAdvice.length - (showPrimaryAdvice ? 1 : 0),
  );
  const queueTitle = loading
    ? '正在整理长期轨迹'
    : primaryRisk
      ? primaryRisk.title
      : showPrimaryAdvice && primaryAdvice
        ? primaryAdvice.title
        : weeklyAdvice.length === 0 && trajectoryRisks.length === 0
          ? '本周建议等待复盘'
          : '轨迹暂无新增风险';
  const queueDetail = loading
    ? '同步完成后会补上长期判断。'
    : primaryRisk
      ? (primaryRisk.primary_action || primaryRisk.why || 'Agent 会继续观察长期轨迹变化。')
      : showPrimaryAdvice && primaryAdvice
        ? primaryAdvice.content
        : weeklyAdvice.length === 0 && trajectoryRisks.length === 0
          ? '当前先做上方闭环，周日晚自动复盘。'
          : '继续用睡眠、血氧、体成分和检查数据观察。';
  const queueRightLabel = gapCount > 0
    ? `缺口 ${gapCount}`
    : hiddenCount > 0
      ? '待关注'
      : primaryRisk
        ? getTrajectoryLevelLabel(primaryRisk.level)
        : showPrimaryAdvice
          ? '建议'
          : '观察';
  const queueTint = primaryRisk
    ? getTrajectoryLevelColor(primaryRisk.level, c).tint
    : showPrimaryAdvice
      ? c.tintOrange
      : c.brandLight;
  const queueColor = primaryRisk
    ? getTrajectoryLevelColor(primaryRisk.level, c).color
    : showPrimaryAdvice
      ? c.orange
      : c.brand;
  const queueIcon: keyof typeof Ionicons.glyphMap = primaryRisk
    ? getTrajectoryRiskIcon(primaryRisk.domain)
    : showPrimaryAdvice
      ? 'bulb-outline'
      : 'git-branch-outline';
  const onOpenQueue = showPrimaryAdvice && primaryAdvice
    ? () => onOpenAdvice(primaryAdvice)
    : onOpenTrajectory;

  return (
    <Pressable
      onPress={onOpenQueue}
      style={({ pressed }) => [styles.followUpCompactRow, { opacity: pressed ? 0.72 : 1 }]}
      accessibilityRole="button"
      accessibilityLabel={queueTitle}
    >
      <View style={[styles.followUpRowIcon, { backgroundColor: queueTint }]}>
        <Ionicons name={queueIcon} size={15} color={queueColor} />
      </View>
      <View style={styles.followUpRowText}>
        <Text style={[styles.followUpTitle, { color: c.labelSecondary }]}>后台继续看</Text>
        <Text style={[styles.followUpRowTitle, { color: c.labelPrimary }]} numberOfLines={1}>
          {queueTitle}
        </Text>
        <Text style={[styles.followUpRowDetail, { color: c.labelSecondary }]} numberOfLines={1}>
          {queueDetail}
        </Text>
      </View>
      <Text style={[styles.followUpRowRight, { color: queueColor }]}>{queueRightLabel}</Text>
    </Pressable>
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

function buildLoopFeedbackMetrics(
  twinSnapshot: TwinSnapshot,
  action?: DailyPlanAction | null,
  riskTitle?: string,
): OutcomeFeedbackMetric[] {
  const haystack = `${riskTitle ?? ''} ${action?.domain ?? ''} ${action?.title ?? ''} ${action?.why ?? ''} ${action?.metric_key ?? ''}`.toLowerCase();
  let priority: string[] = [];

  if (/sleep|bed|spo2|oxygen|血氧|呼吸|睡眠|鼾|鼻/.test(haystack)) {
    priority = ['spo2', 'sleep_score', 'hrv'];
  } else if (/bmi|weight|waist|fat|体重|腰围|体脂|身材/.test(haystack)) {
    priority = ['body_shape', 'vo2max', 'hrv'];
  } else if (/bp|blood_pressure|pressure|血压|心血管/.test(haystack)) {
    priority = ['blood_pressure', 'hrv', 'sleep_score'];
  } else if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|uric|lab|blood|血糖|血脂|尿酸|肝|生化|血检/.test(haystack)) {
    priority = ['labs', 'body_shape', 'sleep_score'];
  }

  if (priority.length === 0) {
    return buildOutcomeFeedbackMetrics(twinSnapshot, action).slice(0, 3);
  }

  return priority
    .map(key => buildOutcomeFeedbackMetric(key, twinSnapshot))
    .filter(Boolean)
    .slice(0, 3) as OutcomeFeedbackMetric[];
}

function buildImprovementFocus({
  action,
  activeDomainCount,
  criticalCount,
  planCount,
  riskTitle,
  loopMetrics,
}: {
  action?: DailyPlanAction | null;
  activeDomainCount: number;
  criticalCount: number;
  planCount: number;
  riskTitle?: string;
  loopMetrics: OutcomeFeedbackMetric[];
}) {
  const haystack = `${riskTitle ?? ''} ${action?.domain ?? ''} ${action?.title ?? ''} ${action?.why ?? ''} ${action?.metric_key ?? ''}`.toLowerCase();
  const metricLabels = loopMetrics
    .map(metric => metric.label.replace('BMI/体脂', 'BMI 和体脂').replace('血液/生化', '血液和生化'))
    .slice(0, 3);
  const metricTarget = metricLabels.length > 0
    ? metricLabels.join('、')
    : '关键健康指标';

  if (/sleep|bed|spo2|oxygen|血氧|呼吸|睡眠|鼾|鼻/.test(haystack)) {
    return {
      headline: '稳住夜间血氧',
      target: '目标：血氧稳定，睡眠分和 HRV 回升',
      outcome: '夜间血氧、睡眠分和 HRV 改善',
    };
  }
  if (/bmi|weight|waist|fat|体重|腰围|体脂|身材/.test(haystack)) {
    return {
      headline: '改善体成分',
      target: '目标：BMI 和体脂下降，恢复指标不掉线',
      outcome: 'BMI、体脂和有氧能力改善',
    };
  }
  if (/bp|blood_pressure|pressure|血压|心血管/.test(haystack)) {
    return {
      headline: '降低血压负荷',
      target: '目标：血压更稳，HRV 和睡眠恢复同步改善',
      outcome: '血压、HRV 和睡眠恢复改善',
    };
  }
  if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|uric|lab|blood|血糖|血脂|尿酸|肝|生化|血检/.test(haystack)) {
    return {
      headline: '校准代谢指标',
      target: '目标：饮食、运动和补剂最终反映到血检',
      outcome: '血液和生化指标改善',
    };
  }
  if (action?.title) {
    return {
      headline: action.title,
      target: `目标：改善 ${metricTarget}`,
      outcome: `${metricTarget}改善`,
    };
  }
  if (criticalCount > 0) {
    return {
      headline: riskTitle || `${criticalCount} 个风险待处理`,
      target: `目标：先压低风险，再观察 ${metricTarget}`,
      outcome: `${metricTarget}改善`,
    };
  }
  if (planCount > 0) {
    return {
      headline: `今天 ${planCount} 件事`,
      target: activeDomainCount > 0
        ? `目标：用 ${activeDomainCount} 个干预域改善 ${metricTarget}`
        : `目标：完成计划并观察 ${metricTarget}`,
      outcome: `${metricTarget}改善`,
    };
  }
  return {
    headline: '保持记录节奏',
    target: '目标：补齐数据，让建议更贴近身体反馈',
    outcome: '建议精度和长期趋势判断改善',
  };
}

function buildHomeNextStepLabel({
  action,
  criticalCount,
}: {
  action?: DailyPlanAction | null;
  criticalCount: number;
}): string {
  if (action?.title) return `下一步：${action.title}`;
  if (criticalCount > 0) return '下一步：查看风险原因，调整今晚策略';
  return '下一步：补齐今天记录，Agent 再排干预';
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

function buildEvidenceSourceSummary({
  hasClinical,
  hasGenetic,
  hasWearable,
}: {
  hasClinical: boolean;
  hasGenetic: boolean;
  hasWearable: boolean;
}): string {
  const sources = [
    hasGenetic ? '基因' : null,
    '表观遗传',
    hasClinical ? '体检' : null,
    hasWearable ? '穿戴' : null,
  ].filter(Boolean);

  return sources.length > 0 ? sources.join('/') : '记录/检查/穿戴';
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

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function getTrajectoryLevelLabel(level: string): string {
  if (level === 'high') return '高';
  if (level === 'attention') return '关注';
  if (level === 'unknown') return '缺数据';
  if (level === 'ok') return '稳定';
  return level || '轨迹';
}

function getTrajectoryRiskIcon(domain: string): keyof typeof Ionicons.glyphMap {
  if (domain === 'metabolic_health') return 'pulse-outline';
  if (domain === 'recovery_capacity') return 'battery-charging-outline';
  if (domain === 'aging_pace') return 'hourglass-outline';
  return 'analytics-outline';
}

function getTrajectoryLevelColor(level: string, c: ReturnType<typeof useTheme>['c']) {
  if (level === 'high') return { tint: c.tintRed, color: c.red };
  if (level === 'attention') return { tint: c.tintAmber, color: c.amber };
  if (level === 'ok') return { tint: c.tintGreen, color: c.green };
  return { tint: c.fill, color: c.labelSecondary };
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },  // 110 = tab bar 83 + 缓冲
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
  section: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: spacing.sm,
  },
  commandHeader: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    paddingHorizontal: 12,
    paddingTop: 11,
    paddingBottom: 12,
    gap: 9,
  },
  commandAgentHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  commandAgentTitleBlock: { flex: 1, minWidth: 0, gap: 4 },
  commandAgentIdentity: { flexDirection: 'row', alignItems: 'center', gap: 7, minWidth: 0 },
  commandAgentLabel: { fontSize: 14, lineHeight: 18, fontWeight: '800' },
  commandAgentSubLabel: { fontSize: 11, lineHeight: 14, fontWeight: '700' },
  commandRightMeta: { alignItems: 'flex-end', gap: 5, flexShrink: 0 },
  commandRightTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 },
  commandMiniActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 },
  commandMiniAction: {
    minWidth: 84,
    height: 29,
    borderRadius: radii.full,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 5,
    paddingHorizontal: 9,
  },
  commandMiniActionText: { fontSize: 12, lineHeight: 14, fontWeight: '800' },
  commandMetaPills: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 5 },
  commandAgentCopy: { fontSize: 10, lineHeight: 13, fontWeight: '700' },
  commandOutcomeBlock: {
    minHeight: 28,
    borderRadius: radii.full,
    paddingHorizontal: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  commandMetricGrid: { flexDirection: 'row', gap: 7 },
  commandMetricCard: {
    flex: 1,
    minWidth: 0,
    minHeight: 48,
    borderRadius: radii.md,
    paddingHorizontal: 9,
    paddingVertical: 7,
    justifyContent: 'center',
    gap: 2,
  },
  agentStepRail: {
    minHeight: 22,
    borderRadius: radii.full,
    paddingHorizontal: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  agentStepSegment: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 4 },
  agentStepLabel: { fontSize: 9, lineHeight: 11, fontWeight: '800' },
  agentStepValue: { flex: 1, minWidth: 0, fontSize: 10, lineHeight: 12, fontWeight: '800' },
  agentStepDivider: { fontSize: 10, lineHeight: 12, fontWeight: '800' },
  commandSignalLine: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  commandSignalChip: {
    minWidth: 0,
    minHeight: 24,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  commandSignalDot: { width: 5, height: 5, borderRadius: 2.5 },
  commandSignalPrefix: { fontSize: 10, lineHeight: 12, fontWeight: '800' },
  commandSignalLabel: { fontSize: 10, lineHeight: 12, fontWeight: '700' },
  commandSignalValue: { minWidth: 0, fontSize: 14, lineHeight: 18, fontWeight: '800', fontVariant: ['tabular-nums'] },
  commandSignalSeparator: { fontSize: 10, lineHeight: 12, fontWeight: '700', paddingHorizontal: 6 },
  commandNextStep: {
    minHeight: 44,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  commandNextStepCopy: { flex: 1, minWidth: 0, gap: 1 },
  commandNextStepLabel: { color: 'rgba(255,255,255,0.72)', fontSize: 10, lineHeight: 12, fontWeight: '800' },
  commandNextStepText: { color: '#FFFFFF', fontSize: 13, lineHeight: 16, fontWeight: '800' },
  commandFocusArea: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: spacing.xs,
  },
  commandFocusTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  commandDecisionArea: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: 10,
    gap: 7,
  },
  commandDecisionTop: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  commandDecisionIcon: {
    width: 34,
    height: 34,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  commandTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  commandTitleBlock: { flex: 1, gap: 4, minWidth: 0 },
  commandStatusLine: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flexWrap: 'wrap' },
  commandDate: { fontSize: 11, lineHeight: 14, fontWeight: '800' },
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
  commandFocusLabel: { fontSize: 11, lineHeight: 14, fontWeight: '800' },
  commandTitle: { minWidth: 0, fontSize: 21, fontWeight: '800', lineHeight: 25, letterSpacing: 0 },
  commandHint: { fontSize: 12, lineHeight: 17, fontWeight: '600' },
  commandLoopLine: {
    minHeight: 25,
    alignSelf: 'stretch',
    borderRadius: radii.full,
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  commandLoopText: { flex: 1, minWidth: 0, fontSize: 10, lineHeight: 12, fontWeight: '800' },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: radii.full,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 11, fontWeight: '800' },
  commandActions: { flexDirection: 'row', gap: 8 },
  primaryAction: {
    flex: 1,
    minHeight: 36,
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  primaryActionText: { fontSize: 14, fontWeight: '800' },
  secondaryAction: {
    flex: 1,
    minHeight: 36,
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  secondaryActionText: { fontSize: 13, fontWeight: '800' },
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
  executionCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: 11,
    gap: 8,
  },
  executionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  executionIcon: {
    width: 30,
    height: 30,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  executionHeaderText: { flex: 1, minWidth: 0, gap: 2 },
  executionTitle: { fontSize: 15, lineHeight: 19, fontWeight: '800' },
  executionSubtitle: { fontSize: 12, lineHeight: 15, fontWeight: '600' },
  executionAdjustButton: {
    minHeight: 31,
    borderRadius: radii.full,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  executionAdjustText: { fontSize: 12, lineHeight: 14, fontWeight: '800' },
  executionPrimary: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: 9,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  executionPrimaryTop: { flex: 1, minWidth: 0, gap: 3 },
  executionEyebrow: { fontSize: 12, lineHeight: 15, fontWeight: '800' },
  executionPrimaryTitle: { fontSize: 16, lineHeight: 20, fontWeight: '800' },
  executionReason: { fontSize: 12, lineHeight: 16, fontWeight: '600' },
  executionImpactChips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  executionImpactChip: {
    minHeight: 22,
    borderRadius: radii.full,
    paddingHorizontal: 7,
    flexDirection: 'row',
    alignItems: 'center',
  },
  executionImpactText: { fontSize: 11, lineHeight: 13, fontWeight: '800' },
  nextActionError: {
    borderRadius: radii.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  nextActionErrorText: { fontSize: 12, fontWeight: '800' },
  nextActionButtons: { width: 82, gap: 6 },
  nextActionPrimary: {
    minHeight: 34,
    borderRadius: radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  nextActionPrimaryText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
  nextActionComplete: {
    minHeight: 32,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  nextActionCompleteText: { fontSize: 12, fontWeight: '800' },
  executionQueueSummary: {
    minHeight: 30,
    borderRadius: radii.md,
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  executionQueueSummaryText: { flex: 1, minWidth: 0, fontSize: 11, lineHeight: 14, fontWeight: '700' },
  loopCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    padding: 11,
    gap: 9,
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
    paddingVertical: 6,
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
    minHeight: 58,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: 8,
    paddingVertical: 6,
    justifyContent: 'center',
    gap: 4,
  },
  loopMetricIcon: {
    width: 22,
    height: 22,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loopMetricLabel: { fontSize: 10, lineHeight: 12, fontWeight: '700' },
  loopMetricValue: { fontSize: 13, lineHeight: 16, fontWeight: '800', fontVariant: ['tabular-nums'] },
  followUpCard: {
    paddingHorizontal: 0,
    paddingVertical: 2,
    gap: 3,
  },
  followUpCompactRow: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 2,
    paddingHorizontal: 2,
  },
  followUpHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 2,
  },
  followUpIcon: {
    width: 20,
    height: 20,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followUpTitleBlock: { flex: 1, minWidth: 0, gap: 1 },
  followUpTitle: { fontSize: 13, lineHeight: 16, fontWeight: '800' },
  followUpSubtitle: { fontSize: 10, lineHeight: 12, fontWeight: '600' },
  followUpCountPill: {
    minHeight: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followUpCountText: { fontSize: 9, lineHeight: 11, fontWeight: '800' },
  followUpSummaryRail: { flexDirection: 'row', flexWrap: 'nowrap', alignItems: 'center', gap: 8, paddingHorizontal: 2 },
  followUpSummaryPill: {
    minHeight: 16,
    flexDirection: 'row',
    alignItems: 'center',
  },
  followUpSummaryText: { fontSize: 9, lineHeight: 11, fontWeight: '800' },
  followUpList: { gap: 0 },
  followUpRow: {
    minHeight: 30,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 1,
    paddingHorizontal: 2,
  },
  followUpRowIcon: {
    width: 21,
    height: 21,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followUpRowText: { flex: 1, minWidth: 0, gap: 1 },
  followUpRowTitleLine: { flexDirection: 'row', alignItems: 'center', gap: 5, minWidth: 0 },
  followUpRowTitle: { flexShrink: 1, fontSize: 11, lineHeight: 14, fontWeight: '800' },
  followUpRowDetail: { fontSize: 10, lineHeight: 12, fontWeight: '500' },
  followUpRowRight: { fontSize: 10, lineHeight: 12, fontWeight: '800' },
  shortcutCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 0,
  },
  shortcutStrip: {
    minHeight: 28,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  shortcutHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  shortcutHeaderText: { width: 72, minWidth: 72, gap: 1 },
  shortcutTitle: { fontSize: 12, lineHeight: 14, fontWeight: '800' },
  shortcutSubtitle: { fontSize: 9, lineHeight: 11, fontWeight: '600' },
  shortcutAllButton: { minHeight: 26, flexDirection: 'row', alignItems: 'center', gap: 1 },
  shortcutAllText: { fontSize: 12, lineHeight: 14, fontWeight: '800' },
  shortcutRail: { flex: 1, minWidth: 0, flexDirection: 'row', flexWrap: 'nowrap', alignItems: 'center', justifyContent: 'flex-end' },
  shortcutTextButton: {
    minHeight: 24,
    justifyContent: 'center',
  },
  shortcutPill: {
    flex: 1,
    minWidth: 0,
    minHeight: 30,
    paddingHorizontal: 4,
    paddingVertical: 3,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  shortcutSeparatorText: { fontSize: 10, lineHeight: 12, fontWeight: '700', paddingHorizontal: 2 },
  shortcutSeparator: { width: StyleSheet.hairlineWidth, height: 16 },
  shortcutIcon: {
    width: 15, height: 15, borderRadius: 7.5,
    alignItems: 'center', justifyContent: 'center',
  },
  shortcutTextBlock: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shortcutLabel: { fontSize: 11, lineHeight: 13, fontWeight: '800', textAlign: 'center' },
  shortcutValue: { flexShrink: 1, minWidth: 0, fontSize: 10, lineHeight: 12, fontWeight: '800', textAlign: 'center' },
  planQueueBlock: { gap: 6 },
  planQueueStrip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    minHeight: 62,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  planQueueIcon: {
    width: 32,
    height: 32,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  planQueueText: { flex: 1, minWidth: 0, gap: 2 },
  planQueueTitle: { fontSize: 14, lineHeight: 17, fontWeight: '800' },
  planQueueSubtitle: { fontSize: 12, lineHeight: 15, fontWeight: '700' },
  planQueueDoneButton: {
    minHeight: 32,
    borderRadius: radii.full,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  planQueueDoneText: { fontSize: 12, lineHeight: 15, fontWeight: '800' },
  planQueueAdjustButton: {
    width: 32,
    height: 32,
    borderRadius: radii.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
