/**
 * 今日议程页 —— 消费后端 /agenda/today(R1)。
 *
 * 一处可见「今天该做什么」:三域协议待办(饮水/用药/饮食)+ 到期复查;
 * 协议项可一键「完成」(双轨协议轨 → 经 /agenda/complete 写真实业务记录)。
 *
 * 入口:Today / 设置 跳转。后端能力首次在手机可见可用。
 */
import React, { useMemo } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator, RefreshControl,
  Alert, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { useAgendaToday, useCompleteAgendaItem, useSeedDemo, useSmartAgendaToday } from '../hooks/useAgenda';
import { isProtocolActionable, MANUAL_CAPTURE, type AgendaItem, type SmartAgendaItem } from '../services/agenda';
import { agendaItemPresentation, agendaSummary } from '../utils/agendaPresentation';

const TONE_COLOR: Record<string, string> = {
  green: '#34C759',
  yellow: '#FFCC00',
  red: '#FF3B30',
  blue: '#0A84FF',
  gray: '#8E8E93',
};

export default function AgendaScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data, isLoading, isError, refetch, isRefetching } = useAgendaToday();
  const { data: smartData, isLoading: smartLoading } = useSmartAgendaToday(3);
  const complete = useCompleteAgendaItem();
  const seed = useSeedDemo();
  const summary = agendaSummary(data?.items ?? []);
  const smartItems = smartData?.smart?.top_items ?? [];

  const onComplete = (item: AgendaItem) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    complete.mutate({ source: item.source });
  };

  // 手工轨:弹量/剂量输入 → 带 value 完成(写同一份记录、同一议程事件)。
  const onManual = (item: AgendaItem) => {
    const cfg = MANUAL_CAPTURE[item.type];
    if (!cfg) { onComplete(item); return; }
    const submit = (text?: string) => {
      const raw = (text ?? '').trim();
      let value: Record<string, unknown> | undefined;
      if (raw) {
        value = { [cfg.valueKey]: cfg.numeric ? Number(raw) : raw };
        if (cfg.numeric && Number.isNaN(value[cfg.valueKey] as number)) {
          Alert.alert('请输入数字'); return;
        }
      }
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
      complete.mutate({ source: item.source, track: 'manual', value });
    };
    if (Platform.OS === 'ios') {
      Alert.prompt(item.title, cfg.prompt, submit, 'plain-text', '',
        cfg.numeric ? 'numeric' : 'default');
    } else {
      // Android 无 Alert.prompt:退回手工轨默认完成(量留空)。
      submit();
    }
  };

  const statusColor = (status: string): string => {
    if (status === 'completed') return c.brand;
    if (status === 'overdue') return c.red;
    return c.labelTertiary;
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>今日议程</Text>
        {data ? <Text style={styles.subtitle}>{data.agenda_date} · {data.count} 项</Text> : null}
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
      ) : isError ? (
        <View style={styles.center}>
          <Text style={styles.muted}>加载失败</Text>
          <TouchableOpacity onPress={() => refetch()}><Text style={styles.retry}>重试</Text></TouchableOpacity>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
        >
          {smartLoading || smartItems.length > 0 ? (
            <SmartAgendaPanel items={smartItems} loading={smartLoading} styles={styles} />
          ) : null}
          {data && data.items.length > 0 ? (
            <View style={styles.summaryRow}>
              <SummaryPill label="待执行" value={summary.actionable} color={c.brand} />
              <SummaryPill label="逾期" value={summary.overdue} color={c.red} />
              <SummaryPill label="建议" value={summary.info} color={c.amber} />
            </View>
          ) : null}
          {(data?.items ?? []).length === 0 ? (
            <View style={styles.center}>
              <Text style={styles.muted}>今天没有待办</Text>
              <TouchableOpacity
                style={styles.seedBtn}
                disabled={seed.isPending}
                onPress={() => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
                  seed.mutate();
                }}
              >
                <Text style={styles.seedBtnText}>
                  {seed.isPending ? '生成中…' : '一键试用(水杯协议 + 登记胃溃疡)'}
                </Text>
              </TouchableOpacity>
            </View>
          ) : (
            (data?.items ?? []).map((item, idx) => (
              <AgendaCard
                key={`${item.source.object_type}-${item.source.object_id}-${idx}`}
                item={item}
                styles={styles}
                completePending={complete.isPending}
                statusColor={statusColor}
                onComplete={onComplete}
                onManual={onManual}
                completedColor={c.brand}
                fallbackColor={c.labelTertiary}
              />
            ))
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function surfaceLabel(surface: string): string {
  if (surface === 'watch') return 'Watch';
  if (surface === 'rokid') return 'Rokid';
  if (surface === 'mac') return 'Mac';
  return '手机';
}

function stateVariableLabel(value?: string | null): string | null {
  if (!value) return null;
  const labels: Record<string, string> = {
    waist_cm: '腰围',
    blood_pressure: '血压',
    metabolic_labs: '代谢指标',
    metabolic_health_anchor: '代谢锚点',
    training_readiness_score: '训练准备度',
    sleep_score: '睡眠分',
    sleep_duration_h: '睡眠时长',
    hrv_status: 'HRV',
    recovery_capacity_anchor: '恢复锚点',
    pace_of_aging: '衰老速度代理',
    biological_age_delta_years: '生物年龄差',
    methylation_report: '甲基化报告',
  };
  return labels[value] ?? value;
}

function horizonLabel(value?: string | null): string | null {
  if (!value) return null;
  const labels: Record<string, string> = {
    upstream_14d: '14天恢复轨迹',
    upstream_90d: '90天上游轨迹',
  };
  return labels[value] ?? value;
}

function trajectorySummary(item: SmartAgendaItem): string | null {
  const target = stateVariableLabel(item.target_state_variable ?? item.trajectory_context?.state_variable);
  const horizon = horizonLabel(item.trajectory_context?.horizon);
  if (!target && !horizon) return null;
  const parts = [];
  if (target) parts.push(`目标: ${target}`);
  if (horizon) parts.push(`周期: ${horizon}`);
  return parts.join(' · ');
}

function verifySummary(item: SmartAgendaItem): string | null {
  const metrics = Array.isArray(item.verify_by?.metrics) ? item.verify_by.metrics as string[] : [];
  const windowDays = typeof item.verify_by?.window_days === 'number'
    ? item.verify_by.window_days
    : item.trajectory_context?.verification_window_days;
  if (metrics.length === 0 && !windowDays) return null;
  const parts = [];
  if (metrics.length > 0) parts.push(metrics.map((metric) => stateVariableLabel(metric) ?? metric).join(' / '));
  if (windowDays) parts.push(`${windowDays}天`);
  return parts.join(' · ');
}

function SmartAgendaPanel({
  items,
  loading,
  styles,
}: {
  items: SmartAgendaItem[];
  loading: boolean;
  styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.smartPanel}>
      <View style={styles.smartHeader}>
        <View style={styles.smartTitleRow}>
          <Ionicons name="sparkles-outline" size={18} color="#0E8F66" />
          <Text style={styles.smartTitle}>智能优先处理</Text>
        </View>
        <Text style={styles.smartMeta}>{items.length > 0 ? `${items.length} 项` : '生成中'}</Text>
      </View>
      {loading && items.length === 0 ? (
        <View style={styles.smartLoading}>
          <ActivityIndicator size="small" color="#0E8F66" />
          <Text style={styles.smartMuted}>正在按风险、时间窗和执行端排序…</Text>
        </View>
      ) : (
        items.map((item, index) => (
          <View key={item.id} style={styles.smartItem}>
            <View style={styles.smartIndex}>
              <Text style={styles.smartIndexText}>{index + 1}</Text>
            </View>
            <View style={styles.smartBody}>
              <View style={styles.smartItemHeader}>
                <Text style={styles.smartItemTitle}>{item.title}</Text>
                <View style={styles.surfaceBadge}>
                  <Text style={styles.surfaceBadgeText}>{surfaceLabel(item.surface.primary)}</Text>
                </View>
              </View>
              <Text style={styles.smartLine}>{item.why_now}</Text>
              <Text style={styles.smartAction}>{item.do_now}</Text>
              {trajectorySummary(item) ? <Text style={styles.smartTrajectory}>{trajectorySummary(item)}</Text> : null}
              {verifySummary(item) ? <Text style={styles.smartVerify}>验证: {verifySummary(item)}</Text> : null}
            </View>
          </View>
        ))
      )}
    </View>
  );
}

function AgendaCard({
  item,
  styles,
  completePending,
  statusColor,
  onComplete,
  onManual,
  completedColor,
  fallbackColor,
}: {
  item: AgendaItem;
  styles: ReturnType<typeof createStyles>;
  completePending: boolean;
  statusColor: (status: string) => string;
  onComplete: (item: AgendaItem) => void;
  onManual: (item: AgendaItem) => void;
  completedColor: string;
  fallbackColor: string;
}) {
  const presentation = agendaItemPresentation(item);
  const toneColor = TONE_COLOR[presentation.tone] ?? fallbackColor;

  return (
    <View style={styles.card}>
      <Ionicons
        name={presentation.icon as keyof typeof Ionicons.glyphMap}
        size={22}
        color={toneColor}
        style={styles.icon}
      />
      <View style={styles.cardBody}>
        <Text style={styles.cardTitle}>{item.title}</Text>
        <Text style={[styles.cardStatus, { color: statusColor(item.status) }]}>
          {presentation.statusLabel}
          {presentation.meta ? ` · ${presentation.meta}` : ''}
        </Text>
        {item.detail ? <Text style={styles.cardDetail}>{item.detail}</Text> : null}
      </View>
      {item.type === 'training' && item.light ? (
        <View style={styles.lightWrap}>
          <View style={[styles.lightDot, { backgroundColor: toneColor }]} />
          {typeof item.readiness_score === 'number' && item.readiness_score > 0 ? (
            <Text style={styles.lightScore}>{item.readiness_score}</Text>
          ) : null}
        </View>
      ) : presentation.canComplete && isProtocolActionable(item) ? (
        <View style={styles.actions}>
          {MANUAL_CAPTURE[item.type] ? (
            <TouchableOpacity
              style={styles.manualBtn}
              disabled={completePending}
              onPress={() => onManual(item)}
            >
              <Text style={styles.manualBtnText}>手工</Text>
            </TouchableOpacity>
          ) : null}
          <TouchableOpacity
            style={styles.doneBtn}
            disabled={completePending}
            onPress={() => onComplete(item)}
          >
            <Ionicons name="checkmark" size={18} color="#fff" />
          </TouchableOpacity>
        </View>
      ) : item.status === 'completed' ? (
        <Ionicons name="checkmark-circle" size={24} color={completedColor} />
      ) : null}
    </View>
  );
}

function SummaryPill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={[summaryStyles.pill, { borderColor: color }]}>
      <Text style={[summaryStyles.value, { color }]}>{value}</Text>
      <Text style={summaryStyles.label}>{label}</Text>
    </View>
  );
}

const summaryStyles = StyleSheet.create({
  pill: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.65)',
  },
  value: { fontSize: 18, fontWeight: '800' },
  label: { fontSize: 11, color: '#6B7280', marginTop: 2, fontWeight: '700' },
});

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.bgPrimary },
    header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
    title: { fontSize: 24, fontWeight: '700', color: c.labelPrimary },
    subtitle: { fontSize: 13, color: c.labelSecondary, marginTop: spacing.xs },
    center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: spacing.xxxl },
    muted: { color: c.labelSecondary, fontSize: 14 },
    retry: { color: c.brand, fontSize: 14, marginTop: spacing.sm },
    list: { padding: spacing.lg, gap: spacing.md },
    summaryRow: { flexDirection: 'row', gap: spacing.sm },
    smartPanel: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      gap: spacing.md,
      ...shadows.subtle,
    },
    smartHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    smartTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
    smartTitle: { fontSize: 17, fontWeight: '800', color: c.labelPrimary },
    smartMeta: { fontSize: 12, fontWeight: '700', color: c.labelTertiary },
    smartLoading: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    smartMuted: { fontSize: 13, color: c.labelSecondary, flex: 1 },
    smartItem: {
      flexDirection: 'row',
      gap: spacing.md,
      paddingTop: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
    },
    smartIndex: {
      width: 28,
      height: 28,
      borderRadius: radii.full,
      backgroundColor: 'rgba(14,143,102,0.12)',
      alignItems: 'center',
      justifyContent: 'center',
    },
    smartIndexText: { fontSize: 13, fontWeight: '800', color: '#0E8F66' },
    smartBody: { flex: 1, gap: 4 },
    smartItemHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    smartItemTitle: { flex: 1, fontSize: 15, fontWeight: '800', color: c.labelPrimary },
    surfaceBadge: {
      paddingHorizontal: spacing.sm,
      paddingVertical: 4,
      borderRadius: radii.full,
      backgroundColor: 'rgba(14,143,102,0.10)',
    },
    surfaceBadgeText: { fontSize: 11, fontWeight: '800', color: '#0E8F66' },
    smartLine: { fontSize: 13, color: c.labelSecondary, lineHeight: 18 },
    smartAction: { fontSize: 13, fontWeight: '700', color: c.labelPrimary, lineHeight: 18 },
    smartTrajectory: { fontSize: 12, fontWeight: '700', color: '#0E8F66', lineHeight: 16 },
    smartVerify: { fontSize: 12, color: c.labelTertiary, lineHeight: 16 },
    card: {
      flexDirection: 'row', alignItems: 'center', backgroundColor: c.bgCard,
      borderRadius: radii.lg, padding: spacing.lg, gap: spacing.md, ...shadows.subtle,
    },
    icon: { width: 24, textAlign: 'center' },
    cardBody: { flex: 1 },
    cardTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary },
    cardStatus: { fontSize: 13, marginTop: 2 },
    cardDetail: { fontSize: 12, color: c.labelTertiary, marginTop: 2 },
    actions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    doneBtn: {
      width: 36, height: 36, borderRadius: radii.full, backgroundColor: c.brand,
      alignItems: 'center', justifyContent: 'center',
    },
    manualBtn: {
      paddingHorizontal: spacing.md, height: 36, borderRadius: radii.full,
      borderWidth: 1, borderColor: c.brand, alignItems: 'center', justifyContent: 'center',
    },
    manualBtnText: { color: c.brand, fontSize: 13, fontWeight: '600' },
    lightWrap: { alignItems: 'center', width: 36, gap: 2 },
    lightDot: { width: 16, height: 16, borderRadius: radii.full },
    lightScore: { fontSize: 11, fontWeight: '600', color: c.labelSecondary },
    seedBtn: {
      marginTop: spacing.lg, backgroundColor: c.brand,
      paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radii.full,
    },
    seedBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  });
}
