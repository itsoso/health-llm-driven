/**
 * 今日 Tab —— Reva「今日」时间线优先布局 (2026-06-16 真机修正).
 *
 * 首页只留日常驱动,从上到下:
 *   问候头 → 深绿 Hero(就绪环 + 现在只做一件事) → 今日时间线 → 用药(折叠)
 *   → 身体数据(ActivityRing + Vitals + BodyStats) → 90 天周期 → 天气行 → 快捷动作
 *
 * 深度分析(结果归因 / 生物年龄 / 抗衰下一步 / 设备一致性 / Agent 话题)已移出首页,
 * 见「我」tab 的「健康分析」分组(各组件路由仍可达)。
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
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getSafetyReport, type SafetyAlert } from '../../services/safety';
import api from '../../services/api';
import { spacing } from '../../constants/theme';
import { useDashboardData, useLatestGarmin } from '../../hooks/useDashboardData';
import { useMedicationReminders } from '../../hooks/useMedicationReminders';
import { useBehaviorLoopReminders } from '../../hooks/useBehaviorLoopReminders';
import { useActiveCycle } from '../../hooks/useHealthOs';
import { garminSleepHours, garminDeepSleepHours, type GarminDailyRow } from '../../types/garmin';
import {
  getDailyOperatingPlan,
  type DailyPlanAction,
} from '../../services/dailyPlan';
import ActivityRingBar from '../../components/dashboard/ActivityRingBar';
import VitalsGrid from '../../components/dashboard/VitalsGrid';
import MedicationCheckin from '../../components/dashboard/MedicationCheckin';
import BodyStatsRow from '../../components/home/BodyStatsRow';
import RevaGreetingHeader from '../../components/home/RevaGreetingHeader';
import RevaHeroCard from '../../components/home/RevaHeroCard';
import RevaTimelineStrip from '../../components/home/RevaTimelineStrip';
import RevaCycleStrip from '../../components/home/RevaCycleStrip';
import RevaWeatherRow from '../../components/home/RevaWeatherRow';
import RevaQuickActions from '../../components/home/RevaQuickActions';
import RevaSectionGroup from '../../components/home/RevaSectionGroup';
import { useRevaFonts } from '../../components/reva/useRevaFonts';
import { revaColors } from '../../constants/revaTheme';
import { useHomeColdStartTrace } from '../../services/perfTrace';

interface TwinSnapshot {
  hrv?: number | null;
  readiness?: number | null;
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

type InterventionDomainKey = 'diet' | 'sleep' | 'movement' | 'supplement' | 'emotion';

export default function TodayScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const revaFontsLoaded = useRevaFonts();
  const [manualRefreshing, setManualRefreshing] = useState(false);

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

  const onRefresh = useCallback(async () => {
    setManualRefreshing(true);
    try {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['safety', 'me'] }),
        qc.invalidateQueries({ queryKey: ['twin', 'me'] }),
        qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] }),
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

  const twinSnap = pickTwinSnapshot(twinQuery.data, garmin);
  const nextAction = (dailyPlanQuery.data?.actions ?? []).find((a) => Boolean(a?.title)) ?? null;
  const actionLeverLabel = buildActionLeverLabel(nextAction, criticalAlerts.length);

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

  // Hero 行动:有 nextAction → 走其专属落点;否则补齐今天记录。
  const onHeroAction = useCallback(() => {
    if (nextAction) openPlanAction(nextAction);
    else router.push('/(tabs)/record' as any);
  }, [nextAction, openPlanAction, router]);

  // ── Vitals 数据 ──
  const vitalsProps = {
    // 睡眠时长优先用 Twin 的 sleep_duration_h_latest(已跨源合并、已是小时);
    // 回退到 garmin days[0](/garmin/me 未按日期合并,可能落到全 null 行)。
    sleep: twinSnap.sleep_hours ?? sleepHoursRaw,
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

  // ── Reva Hero 派生值 ────────────────────────────────────
  // 就绪分:用 Garmin 官方 Training Readiness(twin physiological.training_readiness_score),
  // 与时间线 advisory 写的「恢复就绪度」同源。不再用 body_battery 兜底(那是另一指标,
  // 同屏会与时间线就绪分矛盾)。拿不到 → null(Hero 显示「待同步」)。
  const readinessScore = twinSnap.readiness ?? null;
  // 问候名:取 /profile/me 昵称(无 → 不带名,只问候)。不引入 auth 依赖。
  const profileName: string | null = dashboardQuery.data?.profile?.nickname ?? null;
  // Hero「现在只做一件事」:有 nextAction → 其标题 + lever + openPlanAction;否则退化成「补齐今天记录」走 /record。
  const heroActionTitle = nextAction?.title ?? '补齐今天记录';

  // 字体没 load 时给个 ActivityIndicator(参考 app/reva.tsx),避免 mono 数字闪烁。
  if (!revaFontsLoaded) {
    return (
      <View style={[styles.fontGate, { backgroundColor: revaColors.paper }]}>
        <ActivityIndicator color={revaColors.green500} />
      </View>
    );
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: revaColors.paper }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={manualRefreshing} onRefresh={onRefresh} />}
      >
        {/* 1 · 问候头 */}
        <RevaGreetingHeader name={profileName} />

        {/* 2 · 深绿 Hero(就绪环 + 现在只做一件事) */}
        <RevaHeroCard
          readiness={readinessScore}
          actionTitle={heroActionTitle}
          actionLever={actionLeverLabel}
          onPressAction={onHeroAction}
        />

        {/* 3 · 今日时间线 strip(自取数) */}
        <RevaTimelineStrip />

        {/* 4 · 用药(折叠:汇总 + 待服最多 3 条 + 查看全部) */}
        <MedicationCheckin
          items={dashboardQuery.data?.medicationToday}
          onChanged={() => qc.invalidateQueries({ queryKey: ['dashboard'] })}
        />

        {/* 5 · 身体数据(ActivityRing + Vitals + BodyStats,一个分组) */}
        <RevaSectionGroup title="身体数据">
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
        </RevaSectionGroup>

        {/* 6 · 90 天代谢周期细条(自取数) */}
        <RevaCycleStrip />

        {/* 7 · 天气一行(降级) */}
        <RevaWeatherRow />

        {/* 8 · 快捷动作行 */}
        <RevaQuickActions
          onRun={() => router.push('/live-run' as any)}
          onVoice={() => router.push('/voice-chat?intent=journal' as any)}
          onRecord={() => router.push('/(tabs)/record' as any)}
        />

        {/* 深度分析(结果归因 / 生物年龄 / 抗衰下一步 / 设备一致性 / Agent 话题)
            已移出首页 → 「我」tab 的「健康分析」分组(信息架构:首页只留日常驱动)。 */}

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
    // Garmin 官方 Training Readiness(physiological.training_readiness_score, 0-100)。
    // 这是 Hero 就绪环与时间线 advisory 应同源的「真就绪分」;之前 Hero 用 body_battery
    // 兜底导致同屏两个就绪分自相矛盾(36 vs 93)。null → Hero 显示「待同步」。
    readiness: phys.training_readiness_score ?? null,
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

function classifyInterventionDomain(action: DailyPlanAction): InterventionDomainKey | null {
  const h = `${action.domain ?? ''} ${action.action_key ?? ''} ${action.title ?? ''} ${action.why ?? ''} ${action.metric_key ?? ''}`.toLowerCase();
  if (/supplement|补剂|镁|维生素|鱼油|益生菌/.test(h)) return 'supplement';
  if (/mood|emotion|mental|stress|breath|情绪|压力|呼吸|焦虑|冥想/.test(h)) return 'emotion';
  if (/sleep|bed|睡眠|入睡|上床|血氧|spo2|hrv|恢复/.test(h)) return 'sleep';
  if (/movement|exercise|workout|walk|run|zone|运动|训练|步行|跑|vo2|max|体脂/.test(h)) return 'movement';
  if (/nutrition|diet|meal|protein|water|food|饮食|蛋白|热量|饮水|午餐|晚餐|早餐/.test(h)) return 'diet';
  return null;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  // 暖纸背景 + 统一垂直节奏(各块/分组间距 18)
  content: { padding: spacing.lg, paddingBottom: 110, gap: 18 },
  fontGate: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
});
