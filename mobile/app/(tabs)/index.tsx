/**
 * 今日 Tab —— 健康看板 + Agent 工作台 (2026-05-28 重设计).
 *
 * 上半屏看板, 下半屏 Agent:
 *   EnvCard → Rings → VitalsGrid (4 tile + sparkline) → BodyStats (BP/SpO2/BMI/体脂)
 *   → HomeCommandCard → AgentTopicsRow
 *
 * 数据缺失走"待记录"占位, 不掩盖空状态.
 */

import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
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
import { useDashboardData, useLatestGarmin } from '../../hooks/useDashboardData';
import { garminSleepHours, garminDeepSleepHours, type GarminDailyRow } from '../../types/garmin';
import { pushChatWithContext } from '../../utils/agentContext';
import {
  getDailyOperatingPlan,
  recordDailyPlanActionEvent,
  type DailyPlanAction,
} from '../../services/dailyPlan';
import {
  getHealthTrajectory,
  pickPrimaryTrajectoryRisks,
} from '../../services/trajectory';
import ActivityRingBar from '../../components/dashboard/ActivityRingBar';
import EnvironmentCard from '../../components/dashboard/EnvironmentCard';
import VitalsGrid from '../../components/dashboard/VitalsGrid';
import HomeCommandCard from '../../components/home/HomeCommandCard';
import AgentTopicsRow, { type TopicCard } from '../../components/home/AgentTopicsRow';
import BodyStatsRow from '../../components/home/BodyStatsRow';
import StreakBadge from '../../components/home/StreakBadge';
import OutcomeWinCard from '../../components/home/OutcomeWinCard';
import MetabolicEntryCard from '../../components/home/MetabolicEntryCard';
import BiologicalAgeCard from '../../components/home/BiologicalAgeCard';
import { extractPhenoAge } from '../../services/twinHelpers';
import { getCheckinStreak } from '../../services/streak';
import { fetchMyProgress, pickBioAgeWin } from '../../services/myProgress';
import { useHomeColdStartTrace } from '../../services/perfTrace';

interface TwinSnapshot {
  hrv?: number | null;
  sleep_score?: number | null;
  sleep_hours?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  spo2_avg?: number | null;
  resting_hr?: number | null;
  body_battery?: number | null;
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
}

type MetricColorName = 'green' | 'blue' | 'purple' | 'orange' | 'teal' | 'pink' | 'red';
type MetricTintName = 'tintGreen' | 'tintBlue' | 'tintPurple' | 'tintOrange' | 'tintTeal' | 'tintPink' | 'tintRed';

interface OutcomeMetric {
  key: string;
  label: string;
  value: string;
  detail: string;
  icon: keyof typeof Ionicons.glyphMap;
  colorName: MetricColorName;
  tintName: MetricTintName;
  route: string;
}

const INTERVENTION_DOMAINS: Omit<InterventionDomainStatus, 'activeCount'>[] = [
  { key: 'diet', label: '饮食', detail: 'BMI / 体脂 / 血检', icon: 'restaurant-outline' },
  { key: 'sleep', label: '睡眠', detail: '睡眠分 / 血氧 / HRV', icon: 'moon-outline' },
  { key: 'movement', label: '运动', detail: 'VO2max / 体脂 / HRV', icon: 'walk-outline' },
  { key: 'supplement', label: '补剂', detail: '血检 / 睡眠 / 炎症', icon: 'medkit-outline' },
  { key: 'emotion', label: '情绪', detail: 'HRV / 睡眠 / 压力', icon: 'cloudy-outline' },
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

  const streakQuery = useQuery({
    queryKey: ['checkin-streak'],
    queryFn: getCheckinStreak,
    staleTime: 5 * 60 * 1000,
  });

  const progressDashboardQuery = useQuery({
    queryKey: ['progress-dashboard', 30],
    queryFn: () => fetchMyProgress(30),
    staleTime: 5 * 60 * 1000,
  });

  const dashboardQuery = useDashboardData();

  // perf (2026-05-29): 进程启动后第一次首页 mount 时, 测 4 个 critical query
  // 全部就绪的耗时, emit 一次 home_cold_start_perf 客户端事件.
  useHomeColdStartTrace({
    twin: twinQuery,
    safety: safetyQuery,
    dailyPlan: dailyPlanQuery,
    dashboard: dashboardQuery,
  });

  const garmin = useLatestGarmin(dashboardQuery.data);
  const garminDays: GarminDailyRow[] = Array.isArray(dashboardQuery.data?.garminDaily)
    ? dashboardQuery.data!.garminDaily!
    : [];

  const steps = garmin?.steps ?? 0;
  const activeMin = garmin?.active_minutes ?? 0;
  const calories = garmin?.active_calories ?? 0;
  // 睡眠时长单位换算 + 脏数据守卫的单一真相源在 types/garmin.ts。
  // (此处曾误当秒 /3600,把 7h 显示成 0.1h —— 现在不再手算单位。)
  const sleepHoursRaw = garminSleepHours(garmin);
  const deepSleepRaw = garminDeepSleepHours(garmin);

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
        qc.invalidateQueries({ queryKey: ['checkin-streak'] }),
        qc.invalidateQueries({ queryKey: ['progress-dashboard', 30] }),
        qc.invalidateQueries({ queryKey: ['dashboard'] }),
        qc.invalidateQueries({ queryKey: ['env', 'weather'] }),
        qc.invalidateQueries({ queryKey: ['env', 'aqi'] }),
        qc.invalidateQueries({ queryKey: ['env', 'forecast'] }),
        qc.invalidateQueries({ queryKey: ['env', 'location'] }),
      ]);
    } finally {
      setManualRefreshing(false);
    }
  }, [qc]);

  const isLoading =
    safetyQuery.isLoading ||
    cardsQuery.isLoading ||
    twinQuery.isLoading ||
    dailyPlanQuery.isLoading;
  const isRefreshing =
    manualRefreshing ||
    safetyQuery.isRefetching ||
    cardsQuery.isRefetching ||
    twinQuery.isRefetching ||
    dailyPlanQuery.isRefetching ||
    trajectoryQuery.isRefetching;

  const alerts: SafetyAlert[] = safetyQuery.data?.alerts ?? [];
  const criticalAlerts = alerts.filter((a) =>
    ['critical', 'high'].includes(getSeverityKey(a.severity)),
  );
  const cards: ActionCard[] = cardsQuery.data ?? [];
  const weeklyAdvice = pickWeeklySuggestionCards(cards);

  const twinSnap = pickTwinSnapshot(twinQuery.data, garmin);
  const activePlanCount = dailyPlanQuery.data?.actions?.length ?? 0;
  const nextAction = (dailyPlanQuery.data?.actions ?? []).find((a) => Boolean(a?.title)) ?? null;
  const nextActionKey = nextAction?.action_key || nextAction?.title || null;
  const visibleNextActionState: NextActionCompletionState =
    nextActionCompletion.actionKey === nextActionKey ? nextActionCompletion.state : 'idle';

  const interventionDomains = buildInterventionDomainStatuses(dailyPlanQuery.data?.actions ?? []);
  const topLoopMetrics = buildLoopFeedbackMetrics(twinSnap, nextAction, criticalAlerts[0]?.title);
  const visibleLoopMetrics = topLoopMetrics.slice(0, 3);
  const topLoopKeys = new Set(visibleLoopMetrics.map((m) => m.key));
  const feedbackExcluded = new Set(topLoopKeys);
  if (isBodyMeasurementAction(nextAction)) feedbackExcluded.delete('body_shape');
  const feedbackMetrics = buildHomeBodyFeedbackMetrics(twinSnap, feedbackExcluded, nextAction);

  const improvementFocus = buildImprovementFocus({
    action: nextAction,
    criticalCount: criticalAlerts.length,
    planCount: activePlanCount,
    riskTitle: criticalAlerts[0]?.title,
  });
  const headline =
    criticalAlerts.length > 0 || activePlanCount > 0 ? improvementFocus.headline : '保持记录节奏';
  const nextStepLabel = buildHomeNextStepLabel({
    action: nextAction,
    criticalCount: criticalAlerts.length,
  });
  const nextStepActionText = nextStepLabel.replace(/^下一步：/, '');
  const actionLeverLabel = buildActionLeverLabel(nextAction, criticalAlerts.length);
  const agentJudgmentText = buildAgentJudgmentText({
    action: nextAction,
    criticalCount: criticalAlerts.length,
    headline,
    planCount: activePlanCount,
    riskTitle: criticalAlerts[0]?.title,
    metrics: visibleLoopMetrics,
  });
  const isRecordAction = nextAction?.domain === 'measurement';
  const canComplete = Boolean(nextAction?.action_key) && !isRecordAction;

  const openPlanAction = useCallback(
    (action: DailyPlanAction) => {
      if (action.source_card_id) {
        router.push({ pathname: '/card/[id]' as any, params: { id: String(action.source_card_id) } });
        return;
      }
      if (action.domain === 'nutrition') router.push('/diet-plan' as any);
      else if (action.domain === 'movement') router.push('/movement-plan' as any);
      else if (action.domain === 'sleep') router.push('/sleep' as any);
      else if (isBodyMeasurementAction(action)) router.push('/body-measurements?focus=morning' as any);
      else if (action.domain === 'measurement') router.push('/record' as any);
      else router.push('/(tabs)/chat' as any);
    },
    [router],
  );

  const completeNextAction = useCallback(
    async (action: DailyPlanAction) => {
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
    },
    [nextActionCompletion.state, qc],
  );

  const openTrajectoryChat = useCallback(() => {
    const snapshot = trajectoryQuery.data;
    const contextObject = (v?: Record<string, unknown> | null) => (v ? JSON.parse(JSON.stringify(v)) : null);
    pushChatWithContext(router, {
      prompt: '从疾病上游轨迹看, 我接下来 7 天最应该优先做什么?',
      badge: '基于健康轨迹',
      context: {
        from: 'trajectory/home',
        focus_domains: snapshot?.focus_domains ?? [],
        trajectory_risks: (snapshot?.trajectory_risks ?? []).map((r) => ({
          domain: r.domain,
          level: r.level,
          title: r.title,
          why: r.why ?? null,
          signals: r.signals ?? [],
          primary_action: r.primary_action ?? null,
        })),
        clinical_anchors: contextObject(snapshot?.clinical_anchors),
        realtime_state: contextObject(snapshot?.realtime_state),
        data_gaps: (snapshot?.data_gaps ?? []).map((g) => ({
          code: g.code,
          label: g.label,
          next_step: g.next_step ?? null,
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
        intervention_domains: interventionDomains.map((d) => ({
          key: d.key,
          label: d.label,
          active_count: d.activeCount,
          detail: d.detail,
        })),
        wearable_snapshot: {
          hrv: twinSnap.hrv ?? null,
          sleep_score: twinSnap.sleep_score ?? null,
          resting_hr: twinSnap.resting_hr ?? null,
          spo2_avg: twinSnap.spo2_avg ?? null,
          blood_pressure:
            twinSnap.systolic_bp && twinSnap.diastolic_bp
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

  const onPressJudgment = useCallback(() => {
    if (criticalAlerts.length > 0) router.push('/alerts' as any);
    else if (nextAction) openPlanAction(nextAction);
    else router.push('/(tabs)/record' as any);
  }, [criticalAlerts.length, nextAction, openPlanAction, router]);

  // ── 话题卡 (两个 variant 都用) ──────────────────────
  const trajectoryRisksTop = pickPrimaryTrajectoryRisks(
    trajectoryQuery.data?.trajectory_risks ?? [],
    1,
  );
  const primaryRisk = trajectoryRisksTop[0] ?? null;
  const primaryAdvice = weeklyAdvice[0] ?? null;
  const dataGapsCount = trajectoryQuery.data?.data_gaps?.length ?? 0;
  const topicCards: TopicCard[] = buildTopicCards({
    primaryRisk,
    primaryAdvice,
    feedbackMetrics,
    dataGapsCount,
    c,
    openTrajectoryChat,
    openPlanCardId: (id: number) =>
      router.push({ pathname: '/card/[id]' as any, params: { id: String(id) } }),
    openChat: () => router.push('/(tabs)/chat' as any),
    openMetricRoute: (route: string) => router.push(route as any),
  });

  // ── Vitals 数据 (variant A 用 VitalsGrid 组件; variant B 折叠进 hero) ──
  const vitalsProps = {
    sleep: sleepHoursRaw,
    deepSleep: deepSleepRaw,
    sleepScore: twinSnap.sleep_score ?? null,
    heartRate: twinSnap.resting_hr ?? null,
    hrv: twinSnap.hrv ?? null,
    bodyBatteryCurrent: twinSnap.body_battery ?? null,
    bodyBatteryMax: garmin?.body_battery_most_charged ?? null,
    garminDays,
  };
  const bodyStatsValues = {
    systolic: twinSnap.systolic_bp ?? null,
    diastolic: twinSnap.diastolic_bp ?? null,
    spo2: twinSnap.spo2_avg ?? null,
    bmi: twinSnap.bmi ?? null,
    bodyFatPct: twinSnap.body_fat_pct ?? null,
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={manualRefreshing} onRefresh={onRefresh} />}
      >
        <EnvironmentCard />
        <StreakBadge
          current={streakQuery.data?.current_streak}
          best={streakQuery.data?.best_streak}
          isError={streakQuery.isError}
          onPress={() => router.push('/(tabs)/record' as any)}
        />
        <OutcomeWinCard
          improved={progressDashboardQuery.data?.stats?.improved}
          graded={progressDashboardQuery.data?.stats?.graded}
          totalSurfaced={progressDashboardQuery.data?.stats?.total_surfaced}
          isError={progressDashboardQuery.isError}
          onPress={() => router.push('/my-progress' as any)}
        />
        <BiologicalAgeCard
          view={twinQuery.data ? extractPhenoAge(twinQuery.data) : null}
          win={pickBioAgeWin(progressDashboardQuery.data)}
          isError={twinQuery.isError}
          onPress={() => router.push('/indicator-history' as any)}
        />
        <MetabolicEntryCard />
        <HomeCommandCard
          agentJudgmentText={agentJudgmentText}
          nextStepActionText={nextStepActionText}
          actionLeverLabel={actionLeverLabel}
          refreshing={isRefreshing}
          hasCritical={criticalAlerts.length > 0}
          canComplete={canComplete}
          completionState={visibleNextActionState}
          onPressJudgment={onPressJudgment}
          onPressAction={onPressJudgment}
          onPressAgent={openWorkspaceChat}
          onPressComplete={
            canComplete && nextAction ? () => completeNextAction(nextAction) : undefined
          }
        />
        <ActivityRingBar steps={steps} activeMin={activeMin} calories={calories} />
        <VitalsGrid
          {...vitalsProps}
          onTilePress={(metric) => {
            if (metric === 'sleep') router.push('/sleep' as any);
            else if (metric === 'heart_rate') router.push('/indicator-history?type=heart_rate' as any);
            else if (metric === 'hrv') router.push('/indicator-history?type=hrv' as any);
            else router.push('/indicator-history?type=body_battery' as any);
          }}
        />
        <BodyStatsRow values={bodyStatsValues} />
        <AgentTopicsRow
          cards={topicCards}
          loading={trajectoryQuery.isLoading}
          rightHint={activePlanCount > 0 ? `${activePlanCount} 个干预进行中` : '等记录'}
        />

        {isLoading && (
          <View style={styles.loading}>
            <ActivityIndicator />
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

// ════════════════════════════════════════════════════════════
// Helpers (从老版本沿用 + 精简)
// ════════════════════════════════════════════════════════════

function getSeverityKey(s: any): string {
  return typeof s === 'string' ? s : s?.label ?? 'info';
}

function pickTwinSnapshot(twin: any, garmin: any): TwinSnapshot {
  if (!twin) return {};
  const phys = twin.physiological ?? {};
  const labs = twin.labs ?? {};
  const body = twin.body_composition ?? {};
  return {
    hrv: phys.hrv_latest ?? phys.hrv_7d_avg ?? garmin?.hrv ?? null,
    sleep_score: phys.sleep_score_latest ?? null,
    sleep_hours: phys.sleep_hours_latest ?? null,
    resting_hr: phys.resting_hr_latest ?? garmin?.resting_heart_rate ?? null,
    body_battery:
      phys.body_battery_latest ??
      garmin?.body_battery_current ??
      garmin?.body_battery_most_charged ??
      null,
    systolic_bp: labs.blood_pressure_systolic ?? null,
    diastolic_bp: labs.blood_pressure_diastolic ?? null,
    spo2_avg: phys.spo2_avg ?? phys.spo2_min_overnight ?? null,
    bmi: body.bmi ?? null,
    body_fat_pct: body.body_fat_pct ?? body.body_fat_percentage ?? null,
    vo2max: phys.vo2max_latest ?? phys.vo2max ?? null,
  };
}

function isBodyMeasurementAction(action?: DailyPlanAction | null): boolean {
  if (action?.domain !== 'measurement') return false;
  const haystack = `${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();
  return /体重|腰围|weight|waist|bmi/.test(haystack);
}

const METRIC_DEFS: Record<string, { label: string; icon: keyof typeof Ionicons.glyphMap; colorName: MetricColorName; tintName: MetricTintName }> = {
  sleep_score: { label: '睡眠分', icon: 'moon-outline', colorName: 'purple', tintName: 'tintPurple' },
  hrv: { label: 'HRV', icon: 'pulse-outline', colorName: 'teal', tintName: 'tintTeal' },
  spo2: { label: '血氧', icon: 'water-outline', colorName: 'blue', tintName: 'tintBlue' },
  body_shape: { label: 'BMI/体脂', icon: 'body-outline', colorName: 'green', tintName: 'tintGreen' },
  blood_pressure: { label: '血压', icon: 'heart-outline', colorName: 'pink', tintName: 'tintPink' },
  vo2max: { label: 'VO2max', icon: 'walk-outline', colorName: 'green', tintName: 'tintGreen' },
  labs: { label: '血液/生化', icon: 'flask-outline', colorName: 'red', tintName: 'tintRed' },
  precision: { label: '建议精度', icon: 'analytics-outline', colorName: 'teal', tintName: 'tintTeal' },
};

function buildOutcomeMetric(
  key: string,
  snap: TwinSnapshot,
  options?: { bodyShapePendingLabel?: string },
): OutcomeMetric | null {
  const def = METRIC_DEFS[key];
  if (!def) return null;
  let value = '—';
  let detail = '';
  let route = '/(tabs)/chat';

  if (key === 'sleep_score') {
    value = snap.sleep_score != null ? `${fmt(snap.sleep_score)} 分` : '待同步';
    detail = '睡眠干预'; route = '/sleep';
  } else if (key === 'hrv') {
    value = snap.hrv != null ? `${fmt(snap.hrv)} ms` : '待同步';
    detail = '恢复弹性'; route = '/indicator-history?type=hrv';
  } else if (key === 'spo2') {
    value = snap.spo2_avg != null ? `${fmt(snap.spo2_avg)} %` : '待同步';
    detail = '夜间均值'; route = '/sleep-spo2-analysis';
  } else if (key === 'body_shape') {
    const bmi = snap.bmi;
    const fat = snap.body_fat_pct;
    value = bmi != null && fat != null
      ? `${fmt(bmi)} / ${fmt(fat)}%`
      : bmi != null
        ? `${fmt(bmi)} BMI`
        : fat != null
          ? `${fmt(fat)}%`
          : options?.bodyShapePendingLabel ?? '待记录';
    detail = '身材反馈'; route = '/body-measurements?focus=morning';
  } else if (key === 'blood_pressure') {
    value = snap.systolic_bp && snap.diastolic_bp
      ? `${snap.systolic_bp}/${snap.diastolic_bp}`
      : '待记录';
    detail = '心血管反馈'; route = '/indicator-history?type=blood_pressure';
  } else if (key === 'vo2max') {
    value = snap.vo2max != null ? fmt(snap.vo2max) : '待估算';
    detail = '有氧能力'; route = '/movement-plan';
  } else if (key === 'labs') {
    value = '待复盘'; detail = '化验指标'; route = '/medical-exams';
  } else if (key === 'precision') {
    value = '4 源'; detail = '画像完整度'; route = '/(tabs)/chat';
  }

  return { key, label: def.label, value, detail, icon: def.icon, colorName: def.colorName, tintName: def.tintName, route };
}

function buildLoopFeedbackMetrics(
  snap: TwinSnapshot,
  action?: DailyPlanAction | null,
  riskTitle?: string,
): OutcomeMetric[] {
  const haystack = `${riskTitle ?? ''} ${action?.domain ?? ''} ${action?.title ?? ''} ${action?.why ?? ''} ${action?.metric_key ?? ''}`.toLowerCase();
  let priority: string[] = [];
  if (/sleep|bed|spo2|oxygen|血氧|呼吸|睡眠|鼾|鼻/.test(haystack)) priority = ['spo2', 'sleep_score', 'hrv'];
  else if (/bmi|weight|waist|fat|体重|腰围|体脂|身材/.test(haystack)) priority = ['body_shape', 'vo2max', 'hrv'];
  else if (/bp|blood_pressure|pressure|血压|心血管/.test(haystack)) priority = ['blood_pressure', 'hrv', 'sleep_score'];
  else if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|uric|lab|blood|血糖|血脂|尿酸|肝|生化|血检/.test(haystack))
    priority = ['labs', 'body_shape', 'sleep_score'];
  else priority = ['sleep_score', 'hrv', 'spo2'];

  return priority.map((k) => buildOutcomeMetric(k, snap)).filter(Boolean).slice(0, 3) as OutcomeMetric[];
}

function buildHomeBodyFeedbackMetrics(
  snap: TwinSnapshot,
  excluded: Set<string>,
  action?: DailyPlanAction | null,
): OutcomeMetric[] {
  const pending = isBodyMeasurementAction(action) ? '记录后更新' : undefined;
  return ['body_shape', 'blood_pressure', 'vo2max', 'labs', 'precision']
    .filter((k) => !excluded.has(k))
    .map((k) => buildOutcomeMetric(k, snap, { bodyShapePendingLabel: pending }))
    .filter(Boolean)
    .slice(0, 4) as OutcomeMetric[];
}

function buildAgentJudgmentText({
  action,
  criticalCount,
  headline,
  planCount,
  riskTitle,
  metrics,
}: {
  action?: DailyPlanAction | null;
  criticalCount: number;
  headline: string;
  planCount: number;
  riskTitle?: string;
  metrics: OutcomeMetric[];
}): string {
  const metricLabels = metrics.map((m) => m.label).slice(0, 3).join('、');
  if (criticalCount > 0) {
    return `${riskTitle || headline}，先查看风险原因并调整今晚策略。`;
  }
  if (action?.title) {
    return metricLabels ? `今天先 ${action.title}，观察${metricLabels}。` : `今天先 ${action.title}。`;
  }
  if (planCount > 0) return `今天先完成 ${planCount} 个计划，再用身体反馈调整。`;
  const liveLabels = metrics.filter(hasLiveValue).map((m) => m.label).slice(0, 3).join('、');
  if (liveLabels) return `已有${liveLabels}反馈，先稳住恢复并补齐关键记录。`;
  return '补齐今天记录后，Agent 会重新排序干预。';
}

function hasLiveValue(m: OutcomeMetric): boolean {
  return !/^(待|记录后|补齐|4 源)/.test(m.value);
}

function buildImprovementFocus({
  action,
  criticalCount,
  planCount,
  riskTitle,
}: {
  action?: DailyPlanAction | null;
  criticalCount: number;
  planCount: number;
  riskTitle?: string;
}) {
  const haystack = `${riskTitle ?? ''} ${action?.domain ?? ''} ${action?.title ?? ''} ${action?.why ?? ''} ${action?.metric_key ?? ''}`.toLowerCase();
  if (/sleep|bed|spo2|oxygen|血氧|呼吸|睡眠|鼾|鼻/.test(haystack)) return { headline: '稳住夜间血氧' };
  if (/bmi|weight|waist|fat|体重|腰围|体脂|身材/.test(haystack)) return { headline: '改善体成分' };
  if (/bp|blood_pressure|pressure|血压|心血管/.test(haystack)) return { headline: '降低血压负荷' };
  if (/ldl|hdl|tg|triglyceride|hba1c|glucose|alt|ast|uric|lab|blood|血糖|血脂|尿酸|肝|生化|血检/.test(haystack))
    return { headline: '校准代谢指标' };
  if (action?.title) return { headline: action.title };
  if (criticalCount > 0) return { headline: riskTitle || `${criticalCount} 个风险待处理` };
  if (planCount > 0) return { headline: `今天 ${planCount} 件事` };
  return { headline: '保持记录节奏' };
}

function buildHomeNextStepLabel({ action, criticalCount }: { action?: DailyPlanAction | null; criticalCount: number }): string {
  if (criticalCount > 0) return '下一步：查看风险原因，调整今晚策略';
  if (action?.title) return `下一步：${action.title}`;
  return '下一步：补齐今天记录，Agent 再排干预';
}

function buildActionLeverLabel(action?: DailyPlanAction | null, criticalCount = 0): string {
  if (criticalCount > 0) return '现在只做 · 风险';
  if (!action) return '现在只做';
  if (isBodyMeasurementAction(action) || action.domain === 'measurement') return '现在只做 · 记录';
  const d = classifyInterventionDomain(action);
  if (d === 'diet') return '现在只做 · 饮食';
  if (d === 'sleep') return '现在只做 · 睡眠';
  if (d === 'movement') return '现在只做 · 运动';
  if (d === 'supplement') return '现在只做 · 补剂';
  if (d === 'emotion') return '现在只做 · 情绪';
  return '现在只做';
}

function buildInterventionDomainStatuses(actions: DailyPlanAction[]): InterventionDomainStatus[] {
  const counts = INTERVENTION_DOMAINS.reduce<Record<InterventionDomainKey, number>>((acc, d) => {
    acc[d.key] = 0;
    return acc;
  }, {} as Record<InterventionDomainKey, number>);
  for (const a of actions) {
    const k = classifyInterventionDomain(a);
    if (k) counts[k] += 1;
  }
  return INTERVENTION_DOMAINS.map((d) => ({ ...d, activeCount: counts[d.key] }));
}

function classifyInterventionDomain(action: DailyPlanAction): InterventionDomainKey | null {
  const h = `${action.domain ?? ''} ${action.action_key ?? ''} ${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();
  if (/supplement|补剂|镁|维生素|鱼油|益生菌/.test(h)) return 'supplement';
  if (/mood|emotion|mental|stress|breath|情绪|压力|呼吸|焦虑|冥想/.test(h)) return 'emotion';
  if (/sleep|bed|睡眠|入睡|上床|血氧|spo2|hrv|恢复/.test(h)) return 'sleep';
  if (/movement|exercise|workout|walk|run|zone|运动|训练|步行|跑|vo2|max|体脂/.test(h)) return 'movement';
  if (/nutrition|diet|meal|protein|water|food|饮食|蛋白|热量|饮水|午餐|晚餐|早餐/.test(h)) return 'diet';
  return null;
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
    twinSnapshot.hrv || twinSnapshot.sleep_score || twinSnapshot.resting_hr || twinSnapshot.spo2_avg,
  );
  const clinicalReady = Boolean(twinSnapshot.systolic_bp || twinSnapshot.diastolic_bp);
  return [
    { key: 'genetic', label: '基因', status: geneticHits != null ? 'ready' : 'available', value: geneticHits != null ? `${geneticHits} 位点` : null },
    { key: 'epigenetic', label: '表观', status: progressTotal != null ? 'tracked' : 'lifestyle_proxy', value: progressTotal != null ? `${progressTotal} 轨迹` : null },
    { key: 'clinical', label: '体检', status: clinicalReady ? 'ready' : 'missing_or_stale', value: clinicalReady ? '结果追踪' : null },
    { key: 'wearable', label: '穿戴', status: wearableReady ? 'live' : 'missing_or_stale', value: wearableReady ? '实时回流' : null },
  ];
}

function buildTopicCards({
  primaryRisk,
  primaryAdvice,
  feedbackMetrics,
  dataGapsCount,
  c,
  openTrajectoryChat,
  openPlanCardId,
  openChat,
  openMetricRoute,
}: {
  primaryRisk: any;
  primaryAdvice: ActionCard | null;
  feedbackMetrics: OutcomeMetric[];
  dataGapsCount: number;
  c: ReturnType<typeof useTheme>['c'];
  openTrajectoryChat: () => void;
  openPlanCardId: (id: number) => void;
  openChat: () => void;
  openMetricRoute: (route: string) => void;
}): TopicCard[] {
  const cards: TopicCard[] = [];
  if (primaryRisk) {
    const lvl = getTrajectoryLevelColor(primaryRisk.level, c);
    cards.push({
      key: 'risk',
      icon: getTrajectoryRiskIcon(primaryRisk.domain),
      iconColor: lvl.color,
      iconTint: lvl.tint,
      label: '长期轨迹',
      title: primaryRisk.title,
      detail: primaryRisk.primary_action || primaryRisk.why || 'Agent 持续观察',
      badge:
        primaryRisk.level === 'high' ? '高风险' : primaryRisk.level === 'attention' ? '关注' : null,
      badgeColor: lvl.color,
      badgeTint: lvl.tint,
      onPress: openTrajectoryChat,
    });
  } else {
    cards.push({
      key: 'risk-empty',
      icon: 'git-branch-outline',
      iconColor: c.brand,
      iconTint: c.brandLight,
      label: '长期轨迹',
      title: '暂无新增风险',
      detail: '继续看睡眠、血氧、体成分',
      onPress: openTrajectoryChat,
    });
  }

  if (primaryAdvice) {
    cards.push({
      key: 'advice',
      icon: 'bulb-outline',
      iconColor: c.orange,
      iconTint: c.tintOrange,
      label: '本周建议',
      title: primaryAdvice.title,
      detail: primaryAdvice.content,
      onPress: () => openPlanCardId(primaryAdvice.id),
    });
  } else {
    cards.push({
      key: 'advice-empty',
      icon: 'bulb-outline',
      iconColor: c.orange,
      iconTint: c.tintOrange,
      label: '本周建议',
      title: '等待复盘',
      detail: '先做今日行动，周日晚自动复盘',
      onPress: openChat,
    });
  }

  if (feedbackMetrics.length > 0) {
    const top3 = feedbackMetrics.slice(0, 3);
    const head = top3[0];
    const detailLine = top3.map((m) => `${m.label} ${m.value}`).join(' · ');
    cards.push({
      key: 'results',
      icon: head.icon,
      iconColor: c.brand,
      iconTint: c.brandLight,
      label: '结果追踪',
      title: top3.length > 1 ? `${top3.length} 项关键指标` : head.label,
      detail: detailLine,
      badge: dataGapsCount > 0 ? `待补 ${dataGapsCount}` : null,
      badgeColor: c.amber,
      badgeTint: c.tintAmber,
      onPress: () => openMetricRoute(head.route),
    });
  }
  return cards;
}

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
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
  content: { padding: spacing.lg, paddingBottom: 110 },
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
});
