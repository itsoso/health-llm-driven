/**
 * 今日 Tab —— Phase 2 重做 (2026-05-11).
 *
 * 设计 (Agent Native Mobile First):
 *   1. Critical/High 告警卡片 (0 条不显示)
 *   2. 本周建议队列 (source_type='weekly_advisor', 3-5 条)
 *   3. Twin 摘要 (4 个数, 折叠)
 *
 * 旧 10+ 组件 (HomeHeader / AgentSurface / TodayCoachPanel / ...) 全部先沉默,
 * 备份在 index.legacy.tsx.bak. 数据观察 1-2 周后决定保留或删.
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
  const weeklyAdvice = pickWeeklySuggestionCards(cards);

  const twinSnap = pickTwinSnapshot(twinQuery.data);
  const activePlanCount = dailyPlanQuery.data?.actions?.length ?? 0;
  const nextAction = (dailyPlanQuery.data?.actions ?? []).find(action => Boolean(action?.title)) ?? null;

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
        <HomeCommandHeader
          criticalCount={criticalAlerts.length}
          planCount={activePlanCount}
          refreshing={isRefreshing}
          onOpenAgent={() => router.push('/(tabs)/chat' as any)}
          onOpenRecord={() => router.push('/(tabs)/record' as any)}
        />

        <NextBestActionCard
          action={nextAction}
          loading={dailyPlanQuery.isLoading}
          onStart={openPlanAction}
          onFallbackRecord={() => router.push('/(tabs)/record' as any)}
          onFallbackAgent={() => router.push('/(tabs)/chat' as any)}
        />

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

        <TodayPlanPanel
          plan={dailyPlanQuery.data}
          loading={dailyPlanQuery.isLoading}
          onPressAction={openPlanAction}
          onActionEvent={() => qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] })}
        />

        <TrajectorySnapshotPanel
          snapshot={trajectoryQuery.data}
          loading={trajectoryQuery.isLoading}
          onPress={openTrajectoryChat}
        />

        {/* 环境(天气 + AQI)卡 — 旧首页有, P2 重做漏了, 2026-05-11 补回 */}
        <EnvironmentCard />

        {isLoading && (
          <View style={styles.loading}>
            <ActivityIndicator />
          </View>
        )}

        {/* 1. Critical/High 告警卡 */}
        {criticalAlerts.length > 0 && (
          <View style={styles.section}>
            <SectionHeader title="需要立即处理" subtitle={`${criticalAlerts.length} 条高优先级`} />
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

        {/* 3. 身体快照 — 2x2 grid, 默认展开学 VitalsGrid 风格 */}
        <View style={styles.section}>
          <SectionHeader title="身体快照" subtitle="恢复、睡眠与生命体征" />
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
      </ScrollView>
    </SafeAreaView>
  );
}

function HomeCommandHeader({
  criticalCount,
  planCount,
  refreshing,
  onOpenAgent,
  onOpenRecord,
}: {
  criticalCount: number;
  planCount: number;
  refreshing: boolean;
  onOpenAgent: () => void;
  onOpenRecord: () => void;
}) {
  const { c } = useTheme();
  const dateLabel = formatHomeDate(new Date());
  const statusColor = criticalCount > 0 ? c.red : c.green;
  const statusLabel = criticalCount > 0 ? `${criticalCount} 个风险` : '状态稳定';
  const headline = planCount > 0 ? `今天先做 ${planCount} 件事` : '保持记录节奏';
  const focusText = criticalCount > 0
    ? '先看风险，再处理计划'
    : planCount > 0
      ? '按优先级完成今日计划'
      : '暂无硬性任务，保持记录节奏';
  return (
    <View style={[styles.commandHeader, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.commandTop}>
        <View style={styles.commandTitleBlock}>
          <Text style={[styles.commandDate, { color: c.labelTertiary }]}>{dateLabel}</Text>
          <Text style={[styles.commandFocusLabel, { color: c.brand }]}>今日重点</Text>
          <Text style={[styles.commandTitle, { color: c.labelPrimary }]} numberOfLines={2}>
            {headline}
          </Text>
          <Text style={[styles.commandHint, { color: c.labelSecondary }]}>{focusText}</Text>
        </View>
        <View style={[styles.statusPill, { backgroundColor: `${statusColor}18` }]}>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          <Text style={[styles.statusText, { color: statusColor }]}>{statusLabel}</Text>
        </View>
      </View>

      <View style={styles.commandMetaRow}>
        <MetaChip icon="compass-outline" label={`${planCount} 个计划`} />
        <MetaChip icon="sync-outline" label={refreshing ? '同步中' : '已同步'} />
      </View>

      <View style={styles.commandActions}>
        <Pressable
          style={({ pressed }) => [
            styles.primaryAction,
            { backgroundColor: c.brand, opacity: pressed ? 0.86 : 1 },
          ]}
          onPress={onOpenAgent}
          accessibilityRole="button"
          accessibilityLabel="打开健康 Agent"
        >
          <Ionicons name="sparkles-outline" size={17} color="#FFFFFF" />
          <Text style={styles.primaryActionText}>问 Agent</Text>
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
      <SectionHeader title="高频入口" subtitle="常用路径" action="全部" onPress={onOpenAll} />
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

function MetaChip({ icon, label }: { icon: keyof typeof Ionicons.glyphMap; label: string }) {
  const { c } = useTheme();
  return (
    <View style={[styles.metaChip, { backgroundColor: c.bgPrimary }]}>
      <Ionicons name={icon} size={13} color={c.labelSecondary} />
      <Text style={[styles.metaChipText, { color: c.labelSecondary }]}>{label}</Text>
    </View>
  );
}

function NextBestActionCard({
  action,
  loading,
  onStart,
  onFallbackRecord,
  onFallbackAgent,
}: {
  action?: DailyPlanAction | null;
  loading?: boolean;
  onStart: (action: DailyPlanAction) => void;
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

  return (
    <View style={[styles.nextActionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.nextActionTop}>
        <View style={[styles.nextActionIcon, { backgroundColor: c.tintGreen }]}>
          <Ionicons name="navigate-outline" size={17} color={c.green} />
        </View>
        <View style={styles.nextActionMain}>
          <Text style={[styles.nextActionEyebrow, { color: c.green }]}>现在先做</Text>
          <Text style={[styles.nextActionTitle, { color: c.labelPrimary }]} numberOfLines={2}>
            {title}
          </Text>
          <Text style={[styles.nextActionReason, { color: c.labelSecondary }]} numberOfLines={2}>
            {reason}
          </Text>
        </View>
      </View>
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

function formatHomeDate(value: Date): string {
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][value.getDay()];
  return `${value.getMonth() + 1}月${value.getDate()}日 · ${weekday}`;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.lg },  // 110 = tab bar 83 + 缓冲
  loading: { paddingVertical: spacing.xl, alignItems: 'center' },
  section: { gap: spacing.sm },
  commandHeader: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.xl,
    padding: spacing.lg,
    gap: spacing.md,
  },
  commandTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  commandTitleBlock: { flex: 1, gap: 4 },
  commandDate: { fontSize: 12, fontWeight: '700' },
  commandFocusLabel: { fontSize: 12, fontWeight: '800' },
  commandTitle: { fontSize: 26, fontWeight: '800', lineHeight: 32, letterSpacing: 0 },
  commandHint: { fontSize: 13, lineHeight: 18, fontWeight: '500' },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radii.full,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 12, fontWeight: '800' },
  commandMetaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  metaChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: radii.full,
  },
  metaChipText: { fontSize: 12, fontWeight: '600' },
  commandActions: { flexDirection: 'row', gap: spacing.sm },
  primaryAction: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  primaryActionText: { color: '#FFFFFF', fontSize: 15, fontWeight: '800' },
  secondaryAction: {
    minHeight: 44,
    minWidth: 102,
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  secondaryActionText: { fontSize: 15, fontWeight: '700' },
  nextActionCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
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
  nextActionButtons: { flexDirection: 'row', gap: spacing.sm },
  nextActionPrimary: {
    flex: 1,
    minHeight: 42,
    borderRadius: radii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  nextActionPrimaryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
  nextActionSecondary: {
    minHeight: 42,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  nextActionSecondaryText: { fontSize: 14, fontWeight: '800' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
  sectionHeaderText: { flex: 1, gap: 2 },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  sectionSubtitle: { fontSize: 12, fontWeight: '500' },
  sectionAction: { flexDirection: 'row', alignItems: 'center', gap: 2, minHeight: 32 },
  sectionActionText: { fontSize: 13, fontWeight: '700' },
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
  // 2x2 grid 学健康记录 VitalsGrid 风格
  gridRow: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: spacing.md,
  },
  tile: {
    flexBasis: '47.5%',
    flexGrow: 1,
    minWidth: 150,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: 14,
  },
  tileHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  iconDot: {
    width: 24, height: 24, borderRadius: 7,
    alignItems: 'center', justifyContent: 'center',
  },
  tileLabel: { fontSize: 13, fontWeight: '700' },
  tileValueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 1 },
  tileValue: { fontSize: 24, fontWeight: '800', fontVariant: ['tabular-nums'], letterSpacing: 0 },
  tileUnit: { fontSize: 13, fontWeight: '500' },
  tileSub: { fontSize: 11, marginTop: 4 },
});
