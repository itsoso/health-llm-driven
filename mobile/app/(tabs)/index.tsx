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
import EvidenceChip from '../../components/shared/EvidenceChip';
import { pushChatWithContext } from '../../utils/agentContext';
import {
  getDailyOperatingPlan,
  pickTopPlanActions,
  recordDailyPlanActionEvent,
  type DailyOperatingPlan,
  type DailyPlanAction,
} from '../../services/dailyPlan';
import {
  getHealthTrajectory,
  pickPrimaryTrajectoryRisks,
  type HealthTrajectorySnapshot,
  type TrajectoryRisk,
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
          action={nextAction}
          onOpenFocus={() => (
            criticalAlerts.length > 0
              ? router.push('/alerts' as any)
              : nextAction
                ? openPlanAction(nextAction)
                : router.push('/(tabs)/record' as any)
          )}
          onOpenAgent={openWorkspaceChat}
          onOpenRecord={() => router.push('/(tabs)/record' as any)}
          onOpenMetric={(route) => router.push(route as any)}
        />

        {(!riskTakesPrimarySlot || activePlanCount > 0) ? (
          <TodayExecutionQueue
            plan={dailyPlanQuery.data}
            action={riskTakesPrimarySlot ? null : nextAction}
            loading={dailyPlanQuery.isLoading}
            completionState={visibleNextActionState}
            excludeActionKey={nextActionKey}
            onStart={openPlanAction}
            onComplete={completeNextAction}
            onPressAction={openPlanAction}
            onFallbackRecord={() => router.push('/(tabs)/record' as any)}
            onFallbackAgent={() => router.push('/(tabs)/chat' as any)}
          />
        ) : null}

        {isLoading && (
          <View style={styles.loading}>
            <ActivityIndicator />
          </View>
        )}

        <View style={styles.section}>
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
  onOpenRecord,
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
  onOpenRecord: () => void;
  onOpenMetric: (route: string) => void;
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
  const evidenceLabel = `${evidenceSourceCount} 源画像`;
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
    ? '后台任务 · 风险优先'
    : activeDomainCount > 0
      ? `后台任务 · ${activeDomainCount} 个干预域`
      : '后台任务 · 观察中';
  const focusText = criticalCount > 0
    ? improvementFocus.target
    : planCount > 0
      ? improvementFocus.target
      : improvementFocus.target;
  const evidenceSummary = `${evidenceLabel} · ${buildEvidenceSourceSummary({
    hasGenetic: geneticHits != null,
    hasClinical: clinicalReady,
    hasWearable: wearableReady,
  })}`;
  const agentStepItems = [
    { key: 'diagnosis', label: '判断', value: loopStrategy.diagnosisLabel },
    { key: 'intervention', label: '干预', value: activeDomainSummary || loopStrategy.interventionLabel },
    {
      key: 'verification',
      label: '验证',
      value: loopStrategy.verificationLabel || loopMetrics.map(metric => metric.label).slice(0, 2).join('/'),
    },
  ] as const;
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
          {
            borderLeftColor: c.brand,
            opacity: pressed ? 0.78 : 1,
          },
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
        <Text style={[styles.commandAgentCopy, { color: c.labelTertiary }]} numberOfLines={1}>
          {evidenceSummary}
        </Text>
      </Pressable>

      <View style={styles.commandOutcomeBlock}>
        <View style={[styles.agentStepRail, { backgroundColor: c.bgPrimary }]}>
          {agentStepItems.map((item, index) => (
            <React.Fragment key={item.key}>
              <View style={styles.agentStepSegment}>
                <Text style={[styles.agentStepLabel, { color: c.labelTertiary }]}>{item.label}</Text>
                <Text style={[styles.agentStepValue, { color: c.labelPrimary }]} numberOfLines={1}>
                  {item.value}
                </Text>
              </View>
              {index < agentStepItems.length - 1 ? (
                <Text style={[styles.agentStepDivider, { color: c.labelTertiary }]}>/</Text>
              ) : null}
            </React.Fragment>
          ))}
        </View>
        <View style={styles.commandSignalLine}>
          {visibleLoopMetrics.map(metric => {
            const color = c[metric.colorName];
            return (
              <Pressable
                key={metric.key}
                onPress={() => onOpenMetric(metric.route)}
                style={({ pressed }) => [
                  styles.commandSignalChip,
                  { opacity: pressed ? 0.72 : 1 },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`${metric.label} ${metric.value}`}
              >
                <View style={[styles.commandSignalDot, { backgroundColor: color }]} />
                <Text style={[styles.commandSignalLabel, { color: c.labelSecondary }]} numberOfLines={1}>
                  {metric.label}
                </Text>
                <Text style={[styles.commandSignalValue, { color }]} numberOfLines={1}>
                  {metric.value}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.commandActions}>
        <Pressable
          style={({ pressed }) => [
            styles.primaryAction,
            { backgroundColor: c.brandLight, borderColor: `${c.brand}2E`, opacity: pressed ? 0.76 : 1 },
          ]}
          onPress={primaryAction}
          accessibilityRole="button"
          accessibilityLabel={primaryLabel}
        >
          <Ionicons name={primaryIcon} size={17} color={c.brand} />
          <Text style={[styles.primaryActionText, { color: c.brand }]}>{primaryLabel}</Text>
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
    <View style={styles.shortcutCard}>
      <View style={styles.shortcutStrip}>
        <View style={styles.shortcutHeaderText}>
          <Text style={[styles.shortcutTitle, { color: c.labelPrimary }]}>更多入口</Text>
          <Text style={[styles.shortcutSubtitle, { color: c.labelTertiary }]}>低频数据先收起</Text>
        </View>
        <View style={styles.shortcutRail}>
          {shortcuts.map((item, index) => (
            <React.Fragment key={item.label}>
              <Pressable
                onPress={item.onPress}
                style={({ pressed }) => [
                  styles.shortcutPill,
                  { opacity: pressed ? 0.58 : 1 },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`${item.label} ${item.value}`}
              >
                <View style={[styles.shortcutIcon, { backgroundColor: item.bg }]}>
                  <Ionicons name={item.icon} size={11} color={item.color} />
                </View>
                <View style={styles.shortcutTextBlock}>
                  <Text style={[styles.shortcutLabel, { color: c.labelSecondary }]} numberOfLines={1}>
                    {item.label}
                  </Text>
                </View>
              </Pressable>
              {index < shortcuts.length - 1 ? (
                <View style={[styles.shortcutSeparator, { backgroundColor: c.separator }]} />
              ) : null}
            </React.Fragment>
          ))}
        </View>
        <Pressable
          onPress={onOpenAll}
          style={({ pressed }) => [styles.shortcutAllButton, { opacity: pressed ? 0.65 : 1 }]}
          accessibilityRole="button"
          accessibilityLabel="查看全部入口"
        >
          <Text style={[styles.shortcutAllText, { color: c.brand }]}>全部</Text>
          <Ionicons name="chevron-forward" size={13} color={c.brand} />
        </Pressable>
      </View>
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
  onPressAction,
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
  onPressAction: (action: DailyPlanAction) => void;
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
  const remainingActions = pickTopPlanActions(
    (plan?.actions ?? []).filter(item => (item.action_key || item.title) !== excludeActionKey),
    2,
  );
  const totalActionCount = plan?.actions?.length ?? 0;
  const queueSubtitle = loading
    ? 'Agent 正在根据实时反馈排序'
    : totalActionCount > 0
      ? `${totalActionCount} 件事按影响指标排序`
      : '先补齐数据，Agent 再生成干预';

  return (
    <View style={[styles.executionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.executionHeader}>
        <View style={[styles.executionIcon, { backgroundColor: c.tintGreen }]}>
          <Ionicons name="play-circle-outline" size={17} color={c.green} />
        </View>
        <View style={styles.executionHeaderText}>
          <Text style={[styles.executionTitle, { color: c.labelPrimary }]}>执行队列</Text>
          <Text style={[styles.executionSubtitle, { color: c.labelTertiary }]}>{queueSubtitle}</Text>
        </View>
        <Pressable
          onPress={onFallbackAgent}
          style={({ pressed }) => [
            styles.executionAdjustButton,
            { backgroundColor: c.brandLight, opacity: pressed ? 0.72 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel="问 Agent 调整执行队列"
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

      <View style={styles.executionNextBlock}>
        <View style={styles.executionNextHeader}>
          <Text style={[styles.executionNextTitle, { color: c.labelPrimary }]}>接下来</Text>
          <Text style={[styles.executionNextMeta, { color: c.labelTertiary }]}>
            {remainingActions.length > 0 ? `${remainingActions.length} 个排队任务` : '完成后自动生成'}
          </Text>
        </View>
        {remainingActions.length > 0 ? (
          <View style={styles.executionNextList}>
            {remainingActions.map((item, index) => (
              <Pressable
                key={`${item.action_key || item.title}-${index}`}
                onPress={() => onPressAction(item)}
                style={({ pressed }) => [
                  styles.executionNextRow,
                  { borderColor: c.separator, opacity: pressed ? 0.72 : 1 },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`打开接下来任务 ${item.title}`}
              >
                <View style={[styles.executionNextIcon, { backgroundColor: c.fill }]}>
                  <Ionicons name={getDailyActionIcon(item.domain)} size={13} color={c.brand} />
                </View>
                <Text style={[styles.executionNextText, { color: c.labelPrimary }]} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={[styles.executionNextMetric, { color: c.labelTertiary }]} numberOfLines={1}>
                  {getActionQueueMeta(item)}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : (
          <Text style={[styles.executionEmptyText, { color: c.labelTertiary }]}>
            当前重点完成后，Agent 会根据新反馈排下一步。
          </Text>
        )}
      </View>
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
  const showWeeklyPendingRow = weeklyAdvice.length === 0 && trajectoryRisks.length === 0;
  const showWeeklyPendingPill = weeklyAdvice.length === 0 && trajectoryRisks.length > 0;
  const queueCount = trajectoryRisks.length + visibleAdvice.length + (showWeeklyPendingRow ? 1 : 0);
  const hiddenCount = Math.max(
    0,
    trajectoryRisks.length - (primaryRisk ? 1 : 0)
    + weeklyAdvice.length - (showPrimaryAdvice ? 1 : 0),
  );
  const subtitle = loading
    ? 'Agent 后台队列 · 整理长期轨迹'
    : weeklyAdvice.length > 0
      ? `后台队列 · ${trajectoryRisks.length} 轨迹/${weeklyAdvice.length} 建议`
      : trajectoryRisks.length > 0
        ? `后台队列 · ${trajectoryRisks.length} 轨迹/周建议排队`
        : '后台队列 · 先执行上方闭环';

  return (
    <View style={[styles.followUpCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.followUpHeader}>
        <View style={[styles.followUpIcon, { backgroundColor: c.tintPurple }]}>
          <Ionicons name="git-branch-outline" size={17} color={c.purple} />
        </View>
        <View style={styles.followUpTitleBlock}>
          <Text style={[styles.followUpTitle, { color: c.labelPrimary }]}>后续关注</Text>
          <Text style={[styles.followUpSubtitle, { color: c.labelTertiary }]}>{subtitle}</Text>
        </View>
        <View style={[styles.followUpCountPill, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
          <Text style={[styles.followUpCountText, { color: c.labelSecondary }]}>{queueCount} 项</Text>
        </View>
      </View>

      {(gapCount > 0 || hiddenCount > 0 || showWeeklyPendingPill) ? (
        <View style={styles.followUpSummaryRail}>
          {hiddenCount > 0 ? (
            <Pressable
              onPress={onOpenTrajectory}
              style={({ pressed }) => [
                styles.followUpSummaryPill,
                { backgroundColor: c.bgPrimary, borderColor: c.separator, opacity: pressed ? 0.72 : 1 },
              ]}
              accessibilityRole="button"
              accessibilityLabel="查看更多后续队列"
            >
              <Ionicons name="albums-outline" size={12} color={c.labelTertiary} />
              <Text style={[styles.followUpSummaryText, { color: c.labelSecondary }]}>另 {hiddenCount} 项</Text>
            </Pressable>
          ) : null}
          {showWeeklyPendingPill ? (
            <View
              style={[
                styles.followUpSummaryPill,
                { backgroundColor: c.tintTeal, borderColor: `${c.brand}33` },
              ]}
            >
              <Ionicons name="calendar-outline" size={12} color={c.brand} />
              <Text style={[styles.followUpSummaryText, { color: c.brand }]}>周建议排队</Text>
            </View>
          ) : null}
          {gapCount > 0 ? (
            <Pressable
              onPress={onOpenTrajectory}
              style={({ pressed }) => [
                styles.followUpSummaryPill,
                { backgroundColor: c.tintAmber, borderColor: `${c.amber}55`, opacity: pressed ? 0.72 : 1 },
              ]}
              accessibilityRole="button"
              accessibilityLabel="查看健康轨迹缺口"
            >
              <Ionicons name="alert-circle-outline" size={12} color={c.amber} />
              <Text style={[styles.followUpSummaryText, { color: c.amber }]}>缺口 {gapCount}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      <View style={styles.followUpList}>
        {primaryRisk ? (
          <TrajectoryQueueRow
            key={`${primaryRisk.domain}-${primaryRisk.level}-${primaryRisk.title}`}
            risk={primaryRisk}
            onPress={onOpenTrajectory}
          />
        ) : showPrimaryAdvice && primaryAdvice ? (
          <AdviceQueueRow
            key={primaryAdvice.id}
            card={primaryAdvice}
            onPress={() => onOpenAdvice(primaryAdvice)}
          />
        ) : !showWeeklyPendingRow ? (
          <FollowUpPlainRow
            icon="analytics-outline"
            tint={c.brandLight}
            color={c.brand}
            title={loading ? '正在读取 90 天轨迹' : '轨迹暂无新增风险'}
            detail={loading ? '同步完成后会补上长期判断。' : '继续用睡眠、血氧、体成分和检查数据校准。'}
            rightLabel={loading ? '同步中' : '观察'}
            onPress={onOpenTrajectory}
          />
        ) : null}

        {showWeeklyPendingRow ? (
          <FollowUpPlainRow
            icon="calendar-outline"
            tint={c.tintTeal}
            color={c.brand}
            title="本周建议待生成"
            detail="当前先做上方闭环，周日晚 21:07 自动复盘长期建议。"
            rightLabel="排队"
          />
        ) : null}

      </View>
    </View>
  );
}

function TrajectoryQueueRow({ risk, onPress }: { risk: TrajectoryRisk; onPress: () => void }) {
  const { c } = useTheme();
  const color = getTrajectoryLevelColor(risk.level, c);
  return (
    <FollowUpPlainRow
      icon={getTrajectoryRiskIcon(risk.domain)}
      tint={color.tint}
      color={color.color}
      title={risk.title}
      detail={risk.primary_action || risk.why || 'Agent 会继续观察长期轨迹变化。'}
      rightLabel={getTrajectoryLevelLabel(risk.level)}
      onPress={onPress}
    />
  );
}

function AdviceQueueRow({ card, onPress }: { card: ActionCard; onPress: () => void }) {
  const { c } = useTheme();
  const decided = !!card.user_decision;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.followUpRow, { opacity: pressed ? 0.72 : 1 }]}
      accessibilityRole="button"
      accessibilityLabel={card.title}
    >
      <View style={[styles.followUpRowIcon, { backgroundColor: c.tintOrange }]}>
        <Ionicons name="bulb-outline" size={15} color={c.orange} />
      </View>
      <View style={styles.followUpRowText}>
        <View style={styles.followUpRowTitleLine}>
          <Text style={[styles.followUpRowTitle, { color: c.labelPrimary }]} numberOfLines={1}>
            {card.title}
          </Text>
          <EvidenceChip level={card.evidence_level} />
        </View>
        <Text style={[styles.followUpRowDetail, { color: c.labelSecondary }]} numberOfLines={1}>
          {card.content}
        </Text>
      </View>
      <Text style={[styles.followUpRowRight, { color: decided ? c.green : c.amber }]}>
        {decided ? '已决策' : '建议'}
      </Text>
    </Pressable>
  );
}

function FollowUpPlainRow({
  icon,
  tint,
  color,
  title,
  detail,
  rightLabel,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  tint: string;
  color: string;
  title: string;
  detail: string;
  rightLabel: string;
  onPress?: () => void;
}) {
  const { c } = useTheme();
  const content = (
    <>
      <View style={[styles.followUpRowIcon, { backgroundColor: tint }]}>
        <Ionicons name={icon} size={15} color={color} />
      </View>
      <View style={styles.followUpRowText}>
        <Text style={[styles.followUpRowTitle, { color: c.labelPrimary }]} numberOfLines={1}>
          {title}
        </Text>
        <Text style={[styles.followUpRowDetail, { color: c.labelSecondary }]} numberOfLines={1}>
          {detail}
        </Text>
      </View>
      <Text style={[styles.followUpRowRight, { color }]}>{rightLabel}</Text>
    </>
  );

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [styles.followUpRow, { opacity: pressed ? 0.72 : 1 }]}
        accessibilityRole="button"
        accessibilityLabel={title}
      >
        {content}
      </Pressable>
    );
  }

  return <View style={styles.followUpRow}>{content}</View>;
}

function isBodyMeasurementAction(action: DailyPlanAction): boolean {
  if (action.domain !== 'measurement') return false;
  const haystack = `${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();
  return /体重|腰围|weight|waist|bmi/.test(haystack);
}

function getDailyActionIcon(domain?: string | null): keyof typeof Ionicons.glyphMap {
  if (domain === 'nutrition') return 'restaurant-outline';
  if (domain === 'movement') return 'walk-outline';
  if (domain === 'sleep') return 'moon-outline';
  if (domain === 'measurement') return 'analytics-outline';
  if (domain === 'doctor') return 'medical-outline';
  return 'checkmark-circle-outline';
}

function getActionQueueMeta(action: DailyPlanAction): string {
  const metric = action.verification?.metric || action.metric_key;
  if (/sleep|sleep_score/.test(metric ?? '')) return '睡眠';
  if (/hrv/.test(metric ?? '')) return 'HRV';
  if (/spo2|oxygen/.test(metric ?? '')) return '血氧';
  if (/bmi|weight|waist/.test(metric ?? '')) return '体成分';
  if (/body_fat|fat/.test(metric ?? '')) return '体脂';
  if (/vo2|max|cardio/.test(metric ?? '')) return '有氧';
  if (/bp|blood_pressure/.test(metric ?? '')) return '血压';
  if (/lab|blood|glucose|lipid|ldl|hdl|tg/.test(metric ?? '')) return '血检';
  if (action.when === 'morning') return '早晨';
  if (action.when === 'meals') return '饮食';
  if (action.when === 'evening') return '晚间';
  return action.domain === 'nutrition'
    ? '饮食'
    : action.domain === 'movement'
      ? '运动'
      : action.domain === 'sleep'
        ? '睡眠'
        : '今天';
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
    '表观',
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

function formatHomeDate(value: Date): string {
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][value.getDay()];
  return `${value.getMonth() + 1}月${value.getDate()}日 · ${weekday}`;
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
  section: { gap: spacing.sm },
  commandHeader: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    paddingHorizontal: 12,
    paddingTop: 11,
    paddingBottom: 11,
    gap: 8,
  },
  commandAgentHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  commandAgentTitleBlock: { flex: 1, minWidth: 0, gap: 2 },
  commandAgentIdentity: { flexDirection: 'row', alignItems: 'center', gap: 7, minWidth: 0 },
  commandAgentLabel: { fontSize: 14, lineHeight: 18, fontWeight: '800' },
  commandAgentSubLabel: { fontSize: 10, lineHeight: 13, fontWeight: '700' },
  commandRightMeta: { alignItems: 'flex-end', gap: 5 },
  commandMetaPills: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 5 },
  commandAgentCopy: { fontSize: 12, lineHeight: 17, fontWeight: '700' },
  commandOutcomeBlock: { gap: 7 },
  agentStepRail: {
    minHeight: 24,
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
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  commandSignalChip: {
    flex: 1,
    minWidth: 0,
    minHeight: 24,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  commandSignalDot: { width: 5, height: 5, borderRadius: 2.5 },
  commandSignalLabel: { fontSize: 10, lineHeight: 12, fontWeight: '700' },
  commandSignalValue: { flex: 1, minWidth: 0, fontSize: 11, lineHeight: 13, fontWeight: '800', fontVariant: ['tabular-nums'] },
  commandFocusArea: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: spacing.xs,
  },
  commandFocusTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  commandDecisionArea: {
    borderLeftWidth: 2,
    paddingLeft: 9,
    paddingVertical: 1,
    gap: 4,
  },
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
  commandFocusLabel: { fontSize: 11, lineHeight: 14, fontWeight: '800' },
  commandTitle: { minWidth: 0, fontSize: 18, fontWeight: '800', lineHeight: 23, letterSpacing: 0 },
  commandHint: { fontSize: 12, lineHeight: 16, fontWeight: '600' },
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
    minHeight: 35,
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  primaryActionText: { fontSize: 14, fontWeight: '800' },
  secondaryAction: {
    minHeight: 35,
    minWidth: 76,
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
  executionNextBlock: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(120, 120, 128, 0.14)',
    paddingTop: 8,
    gap: 7,
  },
  executionNextHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  executionNextTitle: { fontSize: 13, lineHeight: 16, fontWeight: '800' },
  executionNextMeta: { fontSize: 11, lineHeight: 13, fontWeight: '700' },
  executionNextList: { flexDirection: 'row', gap: 6 },
  executionNextRow: {
    flex: 1,
    minWidth: 0,
    minHeight: 34,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  executionNextIcon: {
    width: 22,
    height: 22,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  executionNextText: { flex: 1, minWidth: 0, fontSize: 12, lineHeight: 15, fontWeight: '800' },
  executionNextMetric: { maxWidth: 44, fontSize: 10, lineHeight: 12, fontWeight: '700' },
  executionEmptyText: { fontSize: 12, lineHeight: 16, fontWeight: '600' },
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
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: 10,
    paddingVertical: 9,
    gap: 5,
  },
  followUpHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  followUpIcon: {
    width: 24,
    height: 24,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followUpTitleBlock: { flex: 1, minWidth: 0, gap: 2 },
  followUpTitle: { fontSize: 14, lineHeight: 18, fontWeight: '800' },
  followUpSubtitle: { fontSize: 11, lineHeight: 13, fontWeight: '600' },
  followUpCountPill: {
    minHeight: 22,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.full,
    paddingHorizontal: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followUpCountText: { fontSize: 10, lineHeight: 12, fontWeight: '800' },
  followUpSummaryRail: { flexDirection: 'row', flexWrap: 'nowrap', gap: 5 },
  followUpSummaryPill: {
    minHeight: 22,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.full,
    paddingHorizontal: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  followUpSummaryText: { fontSize: 10, lineHeight: 12, fontWeight: '800' },
  followUpList: { gap: 0 },
  followUpRow: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingVertical: 3,
  },
  followUpRowIcon: {
    width: 24,
    height: 24,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  followUpRowText: { flex: 1, minWidth: 0, gap: 2 },
  followUpRowTitleLine: { flexDirection: 'row', alignItems: 'center', gap: 5, minWidth: 0 },
  followUpRowTitle: { flexShrink: 1, fontSize: 12, lineHeight: 15, fontWeight: '800' },
  followUpRowDetail: { fontSize: 11, lineHeight: 13, fontWeight: '500' },
  followUpRowRight: { fontSize: 11, lineHeight: 13, fontWeight: '800' },
  shortcutCard: {
    gap: 0,
  },
  shortcutStrip: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
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
  shortcutAllButton: { minHeight: 30, flexDirection: 'row', alignItems: 'center', gap: 1 },
  shortcutAllText: { fontSize: 12, lineHeight: 14, fontWeight: '800' },
  shortcutRail: { flex: 1, minWidth: 0, flexDirection: 'row', flexWrap: 'nowrap', alignItems: 'center' },
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
