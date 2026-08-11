/**
 * 今日内容主体 —— 小巴 agent-native shell 内的时间线详情正文 (2026-07-06 抽出).
 *
 * 从 app/(tabs)/today.tsx 抽出, 让两处入口复用同一份卡片组装:
 *   - 深链/通知落地的 /(tabs)/today 整屏路由 (mode="screen", 顶部有「返回小巴」)
 *   - 聊天上滑出的今日半屏 sheet /today-sheet (mode="sheet", 用原生抓手 + 下滑关, 不渲染返回条)
 *
 * 首页从上到下:
 *   问候头 → 小巴动态今日行动 → 待确认写入 → 接下来 → 用药/补剂摘要
 *   → 身体信号 → 情境天气 → 90 天周期兜底 → 快捷动作
 *
 * 深度分析(结果归因 / 生物年龄 / 抗衰下一步 / 设备一致性 / 小巴话题)已移出今日详情,
 * 见个人中心的「健康分析」分组(各组件路由仍可达)。
 * 数据缺失走"待记录"占位, 不掩盖空状态.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getSafetyReport, type SafetyAlert } from '../../services/safety';
import api from '../../services/api';
import { spacing } from '../../constants/theme';
import { useFloatingTabBarHeight } from '../../hooks/useFloatingTabBarHeight';
import { useToast } from '../../hooks/useToast';
import { useDashboardData, useLatestGarmin } from '../../hooks/useDashboardData';
import { useMedicationReminders } from '../../hooks/useMedicationReminders';
import { useBehaviorLoopReminders } from '../../hooks/useBehaviorLoopReminders';
import { useActiveCycle } from '../../hooks/useHealthOs';
import { useCompleteAgendaItem, useTodayTimeline } from '../../hooks/useTodayTimeline';
import type { TodayTimelineItem } from '../../services/todayTimeline';
import type { AgendaSkipReason } from '../../services/agenda';
import { garminSleepHours } from '../../types/garmin';
import {
  getDailyOperatingPlan,
  type DailyPlanAction,
} from '../../services/dailyPlan';
import {
  completeDailyArtifactAction,
  getDailyArtifact,
  recordDailyArtifactEvent,
  resolveDailyArtifactCompletionTarget,
  type DailyArtifact,
  type DailyArtifactTopAction,
} from '../../services/dailyArtifact';
import {
  buildTodayBriefingOverview,
  getTodayMorningBriefing,
} from '../../services/todayBriefingOverview';
import BackToChatBar from '../common/BackToChatBar';
import RevaGreetingHeader from './RevaGreetingHeader';
import RevaHeroCard from './RevaHeroCard';
import DailyArtifactCard from './DailyArtifactCard';
import TodayBriefingOverview from './TodayBriefingOverview';
import WriteIntentCard from './WriteIntentCard';
import RevaTimelineStrip from './RevaTimelineStrip';
import RevaCycleStrip from './RevaCycleStrip';
import RevaWeatherRow from './RevaWeatherRow';
import DynamicTodayRenderer from './DynamicTodayRenderer';
import HomeMedicationSummary from './HomeMedicationSummary';
import TodaySignalsPanel, { type TodaySignalKey } from './TodaySignalsPanel';
import TodaySafetyAlertCard from './TodaySafetyAlertCard';
import {
  buildDailyArtifactAtomicContract,
  buildSafetyAlertAtomicContract,
} from './todayAtomicCards';
import { useRevaFonts } from '../reva/useRevaFonts';
import { revaColors } from '../../constants/revaTheme';
import { useHomeColdStartTrace } from '../../services/perfTrace';
import {
  getTodayDynamicView,
  hasRenderableTodayDynamicView,
  type TodayDynamicView,
} from '../../services/todayDynamicView';
import { dispatchChatCardAction } from '../../services/chatCardActions';
import {
  buildDailyArtifactAskRoute,
  buildDailyArtifactBasisRoute,
  buildDailyArtifactExecuteRoute,
  normalizeHealthActionRoute,
  routeForNutritionActionText,
} from '../../utils/dailyArtifactNavigation';
import type {
  ChatCardActionDescriptor,
  ServerCardDescriptor,
} from '../chat/cards/types';

interface TwinSnapshot {
  hrv?: number | null;
  readiness?: number | null;
  readiness_date?: string | null;
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

/**
 * 呈现模式:
 *   - "screen": 深链/通知落地的整屏 (顶部渲染「返回小巴」)。
 *   - "sheet":  聊天上滑出的半屏 formSheet (用原生抓手 + 下滑关, 不渲染返回条; 不占 top 安全区)。
 */
// 'inline':嵌进聊天页的动态 UI 面板(agent-native:不跳独立页,今日以卡在对话里展开)。
//          与 'sheet' 一样不渲染返回条;但不套 SafeAreaView(由父容器定界),不留 tab bar 底距。
export type TodayContentMode = 'screen' | 'sheet' | 'inline';

export function shouldRenderMedicationSummary(mode: TodayContentMode): boolean {
  return mode === 'screen';
}

export default function TodayContent({ mode = 'screen' }: { mode?: TodayContentMode }) {
  const isInline = mode === 'inline';
  const isSheet = mode === 'sheet' || isInline;
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const revaFontsLoaded = useRevaFonts();
  // 悬浮胶囊 tab bar 是 absolute,不占布局流;底部内容须按其真实高度留白,
  // 否则最后一块快捷动作会被 tab bar 半遮盖(硬编码 110 在大安全区机型不够)。
  const tabBarHeight = useFloatingTabBarHeight();
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [artifactCompleting, setArtifactCompleting] = useState(false);
  const [artifactSkipping, setArtifactSkipping] = useState(false);
  const artifactImpressionKeyRef = useRef<string | null>(null);

  const safetyQuery = useQuery({
    queryKey: ['safety', 'me'],
    queryFn: getSafetyReport,
    staleTime: 5 * 60 * 1000,
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

  const dailyArtifactQuery = useQuery({
    queryKey: ['daily-artifact', 'me'],
    queryFn: () => getDailyArtifact(),
    staleTime: 60 * 1000,
  });

  const morningBriefingQuery = useQuery({
    queryKey: ['ai-scheduler', 'morning-briefing'],
    queryFn: getTodayMorningBriefing,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const todayDynamicViewQuery = useQuery({
    queryKey: ['today-dynamic-view', 'mobile.today'],
    queryFn: () => getTodayDynamicView({
      trigger: 'open',
      clientContext: todayDynamicClientContext(),
    }),
    staleTime: 30 * 1000,
    retry: 1,
  });

  // 时间感知「现在该做什么」单一真相源:后端 /timeline/today 的 now(指向最相关一项,非清晨第一项)。
  // Hero 据此渲染(标题/why/时点 + 内联完成);时间线 body 复用同一 query(React Query 去重)。
  const timelineQuery = useTodayTimeline();
  const completeNow = useCompleteAgendaItem();
  const [heroCompleting, setHeroCompleting] = useState(false);

  const dashboardQuery = useDashboardData();

  // perf (2026-05-29): 进程启动后第一次首页 mount 时, 测 4 个 critical query
  // 全部就绪的耗时, emit 一次 home_cold_start_perf 客户端事件.
  useHomeColdStartTrace({
    twin: twinQuery,
    safety: safetyQuery,
    dailyPlan: dailyPlanQuery,
    dashboard: dashboardQuery,
  });

  const activeCycleQuery = useActiveCycle();

  // 按今日在服药品的 reminder_times 调度每日本地吃药提醒 (无权限静默跳过)
  useMedicationReminders(dashboardQuery.data?.medicationToday, dashboardQuery.isSuccess);

  // 行为闭环 → 可操作本地通知 (自动镜像到 Apple Watch): 今天最重要一件事 + 干预周期/复查.
  // 无权限静默跳过; 空态 (无 plan top action / 无周期) 不发.
  useBehaviorLoopReminders(
    dailyPlanQuery.data,
    activeCycleQuery.data,
    dailyPlanQuery.isSuccess || activeCycleQuery.isSuccess,
  );

  const garmin = useLatestGarmin(dashboardQuery.data);
  // 睡眠时长单位换算 + 脏数据守卫的单一真相源在 types/garmin.ts。
  // (此处曾误当秒 /3600,把 7h 显示成 0.1h —— 现在不再手算单位。)
  const sleepHoursRaw = garminSleepHours(garmin);

  const onRefresh = useCallback(async () => {
    setManualRefreshing(true);
    try {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['safety', 'me'] }),
        qc.invalidateQueries({ queryKey: ['twin', 'me'] }),
        qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] }),
        qc.invalidateQueries({ queryKey: ['daily-artifact', 'me'] }),
        qc.invalidateQueries({ queryKey: ['ai-scheduler', 'morning-briefing'] }),
        qc.invalidateQueries({ queryKey: ['today-dynamic-view', 'mobile.today'] }),
        qc.invalidateQueries({ queryKey: ['timeline', 'today'] }),
        qc.invalidateQueries({ queryKey: ['agenda', 'today'] }),
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
    twinQuery.isLoading ||
    dailyPlanQuery.isLoading;

  const alerts: SafetyAlert[] = safetyQuery.data?.alerts ?? [];
  const criticalAlerts = alerts.filter((a) =>
    ['critical', 'high'].includes(getSeverityKey(a.severity)),
  );
  const safetyAlertContract = buildSafetyAlertAtomicContract(alerts);
  const primarySafetyAlert = safetyAlertContract.payload;

  const twinSnap = pickTwinSnapshot(twinQuery.data, garmin);

  // ── Hero now-action:读 /timeline/today 的 now(时间感知最相关项),非清晨第一项。 ──
  // now 是 items 里某一行的 id;同时兜底在 past.events 里找(理论上 now 只指向未完成项)。
  const timeline = timelineQuery.data;
  const nowItem: TodayTimelineItem | null = useMemo(() => {
    if (!timeline?.now) return null;
    const all = [...(timeline.items ?? []), ...(timeline.past?.events ?? [])];
    return all.find((it) => it.id === timeline.now) ?? null;
  }, [timeline]);

  const nextAction = (dailyPlanQuery.data?.actions ?? []).find((a) => Boolean(a?.title)) ?? null;

  const openPlanAction = useCallback(
    (action: DailyPlanAction) => {
      if (action.source_card_id) {
        router.push({ pathname: '/card/[id]' as any, params: { id: String(action.source_card_id) } });
        return;
      }
      if (action.domain === 'nutrition') {
        const route = routeForNutritionActionText([
          action.title,
          action.why,
          action.metric_key,
        ].filter(Boolean).join(' ')) ?? '/diet-plan';
        router.push(route as any);
      }
      else if (action.domain === 'movement') router.push('/movement-plan' as any);
      else if (action.domain === 'sleep') router.push('/sleep' as any);
      else if (isBodyMeasurementAction(action)) router.push('/body-measurements?focus=morning' as any);
      else if (action.domain === 'measurement') router.push('/record' as any);
      else router.push('/(tabs)/chat' as any);
    },
    [router],
  );

  // Hero 行动落点:有 now-item → 优先其 deep_link;无深链则回退 dailyPlan 落点路由;
  // 都没有(空态)→ 补齐今天记录。
  const onHeroAction = useCallback(() => {
    if (nowItem?.deep_link) {
      const link = normalizeHealthActionRoute(nowItem.deep_link, `${nowItem.title} ${nowItem.subtitle ?? ''}`);
      if (link) router.push(link as any);
      return;
    }
    if (nextAction) openPlanAction(nextAction);
    else router.push('/(tabs)/record' as any);
  }, [nowItem, nextAction, openPlanAction, router]);

  // Hero 内联「完成」:走时间线 now-item 的 complete_ref(复用 /agenda/complete 双轨写真实记录)。
  // action-lock(heroCompleting)防双击;失败给 Alert 反馈,不静默吞。
  const heroCanComplete = Boolean(
    nowItem?.can_complete && nowItem?.complete_ref && nowItem?.status !== 'completed',
  );
  const onHeroComplete = useCallback(() => {
    const ref = nowItem?.complete_ref;
    if (!ref || heroCompleting) return;
    setHeroCompleting(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    completeNow.mutate(ref, {
      onSuccess: () => {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        setHeroCompleting(false);
      },
      onError: () => {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
        Alert.alert('完成失败', '没有保存成功,请稍后重试。');
        setHeroCompleting(false);
      },
    });
  }, [nowItem, heroCompleting, completeNow]);

  useEffect(() => {
    const artifact = dailyArtifactQuery.data;
    if (!artifact) return;
    const key = `${artifact.artifact_date}:${artifact.top_action?.id ?? 'empty'}`;
    if (artifactImpressionKeyRef.current === key) return;
    artifactImpressionKeyRef.current = key;
    recordDailyArtifactEvent({
      eventType: 'impression',
      artifactDate: artifact.artifact_date,
      topActionId: artifact.top_action?.id ?? null,
      deliveredContext: dailyArtifactContext(artifact, 'home'),
    }).catch(() => {});
  }, [dailyArtifactQuery.data]);

  const recordArtifactAccepted = useCallback((artifact: DailyArtifact, intent: string) => {
    recordDailyArtifactEvent({
      eventType: 'accepted',
      artifactDate: artifact.artifact_date,
      topActionId: artifact.top_action?.id ?? null,
      deliveredContext: dailyArtifactContext(artifact, 'home', { intent }),
    }).catch(() => {});
  }, []);

  const onArtifactComplete = useCallback(async (action: DailyArtifactTopAction, artifactOverride?: DailyArtifact) => {
    if (artifactCompleting) return;
    const completionTarget = resolveDailyArtifactCompletionTarget(action);
    const artifact = artifactOverride ?? dailyArtifactQuery.data;
    if (!completionTarget || !artifact) {
      Alert.alert('暂时不能完成', '这条行动还缺少可写入的来源。');
      return;
    }
    setArtifactCompleting(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    try {
      await completeDailyArtifactAction(action, artifact.artifact_date);
      recordDailyArtifactEvent({
        eventType: 'completed',
        artifactDate: artifact.artifact_date,
        topActionId: action.id,
        deliveredContext: dailyArtifactContext(artifact, 'home', { action: 'complete' }),
      }).catch(() => {});
      toast.show('已完成，正在刷新今日行动', 'success');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['daily-artifact', 'me'] }),
        qc.invalidateQueries({ queryKey: ['today-dynamic-view', 'mobile.today'] }),
        qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] }),
        qc.invalidateQueries({ queryKey: ['timeline', 'today'] }),
        qc.invalidateQueries({ queryKey: ['agenda', 'today'] }),
      ]);
    } catch {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      Alert.alert('完成失败', '没有保存成功,请稍后重试。');
    } finally {
      setArtifactCompleting(false);
    }
  }, [artifactCompleting, dailyArtifactQuery.data, qc, toast]);

  const onArtifactSkip = useCallback((
    reason: AgendaSkipReason,
    action: DailyArtifactTopAction | null,
    artifactOverride?: DailyArtifact,
  ) => {
    const artifact = artifactOverride ?? dailyArtifactQuery.data;
    if (!artifact || artifactSkipping) return;
    setArtifactSkipping(true);
    recordDailyArtifactEvent({
      eventType: 'skipped',
      artifactDate: artifact.artifact_date,
      topActionId: action?.id ?? null,
      skipReason: reason,
      deliveredContext: dailyArtifactContext(artifact, 'home', { action: 'skip' }),
    }).then(() => {
      qc.invalidateQueries({ queryKey: ['daily-artifact', 'me'] });
      qc.invalidateQueries({ queryKey: ['today-dynamic-view', 'mobile.today'] });
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    }).catch(() => {
      Alert.alert('跳过失败', '没有记录成功,请稍后重试。');
    }).finally(() => {
      setArtifactSkipping(false);
    });
  }, [artifactSkipping, dailyArtifactQuery.data, qc]);

  const onArtifactAskReva = useCallback((artifact: DailyArtifact) => {
    recordArtifactAccepted(artifact, 'ask_reva');
    router.push(buildDailyArtifactAskRoute(artifact) as any);
  }, [recordArtifactAccepted, router]);

  const onArtifactExplainBasis = useCallback((artifact: DailyArtifact) => {
    recordArtifactAccepted(artifact, 'explain_basis');
    const route = buildDailyArtifactBasisRoute(artifact);
    router.push({ pathname: '/daily-artifact/[date]' as any, params: route.params } as any);
  }, [recordArtifactAccepted, router]);

  const onArtifactPressAction = useCallback((action: DailyArtifactTopAction, artifactOverride?: DailyArtifact) => {
    const artifact = artifactOverride ?? dailyArtifactQuery.data;
    if (artifact) recordArtifactAccepted(artifact, 'open_detail');
    router.push(buildDailyArtifactExecuteRoute(artifact, action, {
      nowDeepLink: nowItem?.deep_link ?? null,
    }) as any);
  }, [dailyArtifactQuery.data, nowItem, recordArtifactAccepted, router]);

  const onDynamicCardAction = useCallback(async (
    action: ChatCardActionDescriptor,
    descriptor: ServerCardDescriptor,
  ) => {
    try {
      const result = await dispatchChatCardAction(action);
      if (result.route) {
        router.push(result.route as any);
        return;
      }
      qc.invalidateQueries({ queryKey: ['today-dynamic-view', 'mobile.today'] });
      qc.invalidateQueries({ queryKey: ['daily-artifact', 'me'] });
      qc.invalidateQueries({ queryKey: ['timeline', 'today'] });
      qc.invalidateQueries({ queryKey: ['agenda', 'today'] });
    } catch (error) {
      Alert.alert('操作失败', descriptor.type === 'runtime_agenda'
        ? '暂时无法打开健康编排,请稍后重试。'
        : '没有执行成功,请稍后重试。');
      throw error;
    }
  }, [qc, router]);

  // ── 身体信号:只给首页当前行动验证所需的紧凑指标,完整历史留在数据页。 ──
  const bodyStatsValues = {
    systolic: twinSnap.systolic_bp ?? null,
    diastolic: twinSnap.diastolic_bp ?? null,
    spo2: twinSnap.spo2_avg ?? null,
    bmi: twinSnap.bmi ?? null,
    bodyFatPct: twinSnap.body_fat_pct ?? null,
  };

  // ── Reva Hero 派生值 ────────────────────────────────────
  // 就绪分:用 Garmin 官方 Training Readiness(twin physiological.training_readiness_score),
  // 与时间线 advisory 写的「恢复就绪度」同源。不再用 body_battery 兜底(那是另一指标,
  // 同屏会与时间线就绪分矛盾)。拿不到 → null(Hero 显示「待同步」)。
  const readinessScore = twinSnap.readiness ?? null;
  // 新鲜度守卫:readiness 是每日晨间指标。若来源日期不是「今天」(本地),说明昨晚没同步,
  // 不能把旧分当「今日就绪」(就是用户撞到的「昨晚没同步还显示 93」)。
  const _now = new Date();
  const _todayStr = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}-${String(_now.getDate()).padStart(2, '0')}`;
  const readinessStale =
    readinessScore != null && !!twinSnap.readiness_date && twinSnap.readiness_date < _todayStr;
  // 问候名:取 /profile/me 昵称(无 → 不带名,只问候)。不引入 auth 依赖。
  const profileName: string | null = dashboardQuery.data?.profile?.nickname ?? null;
  const dynamicTodayView = todayDynamicViewQuery.data;
  const canRenderDynamicToday = hasRenderableTodayDynamicView(dynamicTodayView);
  const primaryArtifact = extractDailyArtifactFromDynamicView(dynamicTodayView) ?? dailyArtifactQuery.data ?? null;
  const primaryArtifactContract = buildDailyArtifactAtomicContract(primaryArtifact);
  const primaryTopAction = primaryArtifact?.top_action ?? null;
  const primaryActionSignal = actionSignalFromArtifact(primaryArtifact);
  const timelineExcludedTitles = useMemo(
    () => collectPromotedActionTitles(dynamicTodayView, primaryArtifact),
    [dynamicTodayView, primaryArtifact],
  );
  const primaryActionContext = [
    primaryTopAction?.title,
    primaryTopAction?.why_now,
    primaryTopAction?.do_now,
    primaryActionSignal,
    nowItem?.title,
    nowItem?.subtitle,
  ].filter(Boolean).join(' ');
  const hasAgentPrimaryAction = primaryArtifactContract.render.show;
  const briefingRows = useMemo(() => buildTodayBriefingOverview({
    morningBriefing: morningBriefingQuery.data ?? null,
    weatherResponse: dashboardQuery.data?.weather ?? null,
    airQuality: dashboardQuery.data?.airQuality ?? null,
    dailyPlan: dailyPlanQuery.data ?? null,
    dailyArtifact: primaryArtifact,
    timeline: timelineQuery.data ?? null,
    recentGarminDaily: dashboardQuery.data?.garminDaily ?? null,
  }), [
    dashboardQuery.data?.airQuality,
    dashboardQuery.data?.garminDaily,
    dashboardQuery.data?.weather,
    dailyPlanQuery.data,
    morningBriefingQuery.data,
    primaryArtifact,
    timelineQuery.data,
  ]);

  // Hero now-action 显示值:全部直接透传后端 timeline 的 now-item(R4:不在前端造处方/诊断措辞)。
  // 风险时 lever 标「风险」,否则用 now-item 的 time_window 中文化作为 lever。空态标题给「补齐今天记录」。
  const heroHasNow = nowItem != null;
  const heroNowTitle = nowItem?.title ?? '补齐今天记录';
  const heroNowSubtitle = shortSubtitle(nowItem?.subtitle);
  const heroNowTime = nowItem?.scheduled_for ?? null;
  const heroNowLever =
    criticalAlerts.length > 0 ? '现在该做 · 风险' : windowLever(nowItem?.time_window);

  // 字体没 load 时给个 ActivityIndicator(参考 app/reva.tsx),避免 mono 数字闪烁。
  if (!revaFontsLoaded) {
    return (
      <View style={[styles.fontGate, { backgroundColor: revaColors.paper }]}>
        <ActivityIndicator color={revaColors.green500} />
      </View>
    );
  }

  const body = (
    <ScrollView
      contentContainerStyle={[
        styles.content,
        // inline 面板嵌在聊天页,底部是输入框而非悬浮 tab bar,不留 tab bar 距。
        { paddingBottom: (isInline ? 0 : tabBarHeight) + spacing.lg },
        // sheet/inline 模式顶部不占 top 安全区,给抓手/面板一点呼吸。
        isSheet ? { paddingTop: spacing.sm } : null,
      ]}
      refreshControl={<RefreshControl refreshing={manualRefreshing} onRefresh={onRefresh} />}
    >
      {/* 0 · 返回小巴 (agent-native shell: 无底部 Tab Bar, chat 是主屏)。
          sheet 模式下改用原生抓手 + 下滑关, 不渲染返回条。 */}
      {isSheet ? null : <BackToChatBar />}

      {/* 1 · 问候头 */}
      <RevaGreetingHeader name={profileName} />

      {/* 聊天/半屏入口:把用户期待的简报分区先聚合露出。 */}
      {isSheet ? (
        <TodayBriefingOverview
          rows={briefingRows}
          loading={
            morningBriefingQuery.isLoading ||
            dashboardQuery.isLoading ||
            dailyPlanQuery.isLoading ||
            dailyArtifactQuery.isLoading ||
            timelineQuery.isLoading
          }
        />
      ) : null}

      {/* 2 · Daily Artifact(今日状态 + 一个 top action)。接口不可用时回退既有 Hero。 */}
      {canRenderDynamicToday ? (
        <DynamicTodayRenderer
          view={dynamicTodayView}
          completing={artifactCompleting}
          skipping={artifactSkipping}
          onDailyArtifactComplete={(artifact, action) => onArtifactComplete(action, artifact)}
          onDailyArtifactSkip={(artifact, reason, action) => onArtifactSkip(reason, action, artifact)}
          onDailyArtifactAsk={onArtifactAskReva}
          onDailyArtifactExplainBasis={onArtifactExplainBasis}
          onDailyArtifactPressAction={(artifact, action) => onArtifactPressAction(action, artifact)}
          onCardAction={onDynamicCardAction}
        />
      ) : dailyArtifactQuery.data ? (
        <DailyArtifactCard
          artifact={dailyArtifactQuery.data}
          completing={artifactCompleting}
          skipping={artifactSkipping}
          onComplete={onArtifactComplete}
          onSkip={onArtifactSkip}
          onAskReva={onArtifactAskReva}
          onExplainBasis={onArtifactExplainBasis}
          onPressAction={onArtifactPressAction}
        />
      ) : (
        <RevaHeroCard
          readiness={readinessScore}
          stale={readinessStale}
          asOf={twinSnap.readiness_date}
          hasNow={heroHasNow}
          nowTitle={heroNowTitle}
          nowSubtitle={heroNowSubtitle}
          nowTime={heroNowTime}
          nowLever={heroNowLever}
          canComplete={heroCanComplete}
          completing={heroCompleting}
          onPressAction={onHeroAction}
          onComplete={onHeroComplete}
        />
      )}

      {primarySafetyAlert ? (
        <TodaySafetyAlertCard
          alert={primarySafetyAlert}
          alertCount={criticalAlerts.length}
          onPress={() => router.push('/(tabs)/alerts')}
        />
      ) : null}

      {/* 待你确认(Write 层 v0:小巴提议替你写一件事,确认才执行;空态不渲染) */}
      <WriteIntentCard />

      {/* 3 · 接下来:只保留未完成且马上相关的行动条 */}
      <RevaTimelineStrip excludeTitles={timelineExcludedTitles} />

      {/* 4 · 用药 / 补剂:整屏保留摘要;聊天 sheet/inline 已由「接下来」承载,避免重复。 */}
      {shouldRenderMedicationSummary(mode) ? (
        <HomeMedicationSummary
          items={dashboardQuery.data?.medicationToday ?? []}
          onChanged={() => qc.invalidateQueries({ queryKey: ['dashboard'] })}
        />
      ) : null}

      {/* 5 · 身体信号:围绕当前行动验证,不再把完整 dashboard 堆在首页 */}
      <TodaySignalsPanel
        sleep={twinSnap.sleep_hours ?? sleepHoursRaw}
        sleepScore={twinSnap.sleep_score ?? null}
        hrv={twinSnap.hrv ?? null}
        bodyBatteryCurrent={twinSnap.body_battery ?? null}
        bodyStats={bodyStatsValues}
        actionSignal={primaryActionSignal}
        onSignalPress={(signal) => openSignalRoute(signal, router)}
      />

      {/* 6 · 情境天气:只有行动/空气风险相关时出现 */}
      <RevaWeatherRow relevanceText={primaryActionContext} />

      {/* 7 · 90 天代谢周期兜底:没有当下行动时才露出,长期复盘主入口在「健康分析」。 */}
      {!hasAgentPrimaryAction && !heroHasNow ? <RevaCycleStrip /> : null}

      {/* 深度分析(结果归因 / 生物年龄 / 抗衰下一步 / 设备一致性 / 小巴话题)
          已移出首页 → 「我」tab 的「健康分析」分组(信息架构:首页只留日常驱动)。 */}

      {isLoading && (
        <View style={styles.loading}>
          <ActivityIndicator />
        </View>
      )}
    </ScrollView>
  );

  // inline 模式:嵌进聊天页,父容器已定界高度,直接返回 body(不套 SafeAreaView)。
  if (isInline) {
    return body;
  }

  // sheet 模式:formSheet 已是盖在聊天上的原生浮层, 不再套 top 安全区 (那会在抓手下方留一条空白)。
  // 只用 SafeAreaView 收底部安全区; 状态栏样式交给根 Stack。
  if (isSheet) {
    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: revaColors.paper }]} edges={['bottom']}>
        {body}
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: revaColors.paper }]} edges={['top']}>
      <StatusBar style="dark" />
      {body}
    </SafeAreaView>
  );
}

// ════════════════════════════════════════════════════════════
// Helpers (从老版本沿用 + 精简)
// ════════════════════════════════════════════════════════════

function todayDynamicClientContext(): Record<string, unknown> {
  return {
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone ?? null,
    client_capabilities: ['daily_artifact', 'runtime_agenda'],
  };
}

function extractDailyArtifactFromDynamicView(view: TodayDynamicView | null | undefined): DailyArtifact | null {
  for (const section of view?.sections ?? []) {
    for (const card of section.cards ?? []) {
      if (todayDynamicCardAtom(card) === 'daily_artifact' && card.data && typeof card.data === 'object') {
        return card.data as DailyArtifact;
      }
    }
  }
  return null;
}

function actionSignalFromArtifact(artifact: DailyArtifact | null | undefined): string | null {
  const action = artifact?.top_action;
  if (!action) return null;
  if (action.verification_signal) return action.verification_signal;
  if (action.target_state_variable) return action.target_state_variable;
  const evidenceMetric = artifact.evidence
    .flatMap((item) => item.metrics ?? [])
    .find((metric) => typeof metric === 'string' && metric.trim());
  return evidenceMetric ?? null;
}

function collectPromotedActionTitles(
  view: TodayDynamicView | null | undefined,
  artifact: DailyArtifact | null | undefined,
): string[] {
  const titles = new Set<string>();
  if (artifact?.top_action?.title) titles.add(artifact.top_action.title);
  for (const section of view?.sections ?? []) {
    for (const card of section.cards ?? []) {
      const atom = todayDynamicCardAtom(card);
      if (atom === 'daily_artifact') {
        const data = card.data as Partial<DailyArtifact>;
        if (data.top_action?.title) titles.add(data.top_action.title);
      }
      if (atom === 'runtime_agenda') {
        const data = card.data as { next_action?: { title?: unknown } };
        if (typeof data.next_action?.title === 'string') titles.add(data.next_action.title);
      }
    }
  }
  return [...titles];
}

function todayDynamicCardAtom(card: TodayDynamicView['sections'][number]['cards'][number]): string {
  const atom = card.render?.atom;
  return typeof atom === 'string' && atom.trim() ? atom.trim() : card.type;
}

function openSignalRoute(signal: TodaySignalKey, router: { push: (href: any) => void }) {
  if (signal === 'sleep') router.push('/sleep' as any);
  else if (signal === 'hrv') router.push('/indicator-history?type=hrv' as any);
  else if (signal === 'body_battery') router.push('/indicator-history?type=body_battery' as any);
  else if (signal === 'blood_pressure') router.push('/indicator-history?type=blood_pressure' as any);
  else if (signal === 'spo2') router.push('/sleep-spo2-analysis' as any);
  else router.push('/body-measurements?focus=morning' as any);
}

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
    // Garmin 官方 Training Readiness(physiological.training_readiness_score, 0-100)。
    // 这是 Hero 就绪环与时间线 advisory 应同源的「真就绪分」;之前 Hero 用 body_battery
    // 兜底导致同屏两个就绪分自相矛盾(36 vs 93)。null → Hero 显示「待同步」。
    readiness: phys.training_readiness_score ?? null,
    readiness_date: phys.training_readiness_date ?? null,
    sleep_score: phys.sleep_score_latest ?? null,
    // Twin 物理分区字段名:resting_hr / body_battery_current / sleep_duration_h_latest
    // (之前误用 *_latest 后缀的不存在键 → 读空 → 回退到未合并的 garmin days[0] → "--")
    sleep_hours: phys.sleep_duration_h_latest ?? null,
    resting_hr: phys.resting_hr ?? garmin?.resting_heart_rate ?? null,
    body_battery:
      phys.body_battery_current ??
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

// Hero now-action lever:把 timeline now-item 的 time_window 中文化(无 → 「现在该做」)。
// R4:lever 只表达「什么时间窗」,不造处方/诊断措辞。
function windowLever(window?: string | null): string {
  switch (window) {
    case 'morning': return '现在该做 · 上午';
    case 'noon': return '现在该做 · 中午';
    case 'afternoon': return '现在该做 · 下午';
    case 'evening': return '现在该做 · 傍晚';
    case 'bedtime': return '现在该做 · 睡前';
    default: return '现在该做';
  }
}

// subtitle 一眼扫:只取第一个分句(到首个 ; ; , , 。 . 止),完整内容留给点击进详情。
function shortSubtitle(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const s = raw.trim();
  if (!s) return undefined;
  const cut = s.search(/[;；,，。.]/);
  return (cut > 0 ? s.slice(0, cut) : s).trim() || undefined;
}

function dailyArtifactContext(
  artifact: DailyArtifact,
  surface: 'home',
  extra?: Record<string, unknown>,
): Record<string, unknown> {
  return {
    surface,
    empty_state: artifact.empty_state,
    generated_by: artifact.generated_by ?? null,
    source_kind: typeof artifact.source?.kind === 'string' ? artifact.source.kind : null,
    runtime_horizon_days:
      typeof artifact.source?.horizon_days === 'number' ? artifact.source.horizon_days : null,
    replan_reason:
      typeof artifact.top_action?.runtime_context?.replan_reason === 'string'
        ? artifact.top_action.runtime_context.replan_reason
        : null,
    confidence: artifact.confidence,
    freshness: artifact.freshness?.status ?? null,
    evidence_count: artifact.evidence.length,
    ...(extra ?? {}),
  };
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  // 暖纸背景 + 统一垂直节奏(各块/分组间距 18)
  content: { padding: spacing.lg, gap: 18 }, // paddingBottom 动态注入(见 tabBarHeight)
  fontGate: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
});
