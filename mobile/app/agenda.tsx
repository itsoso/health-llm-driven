/**
 * 今日议程页 —— 消费后端 /agenda/today(R1)。
 *
 * 一处可见「今天该做什么」:三域协议待办(饮水/用药/饮食)+ 到期复查;
 * 协议项可一键「完成」(双轨协议轨 → 经 /agenda/complete 写真实业务记录)。
 *
 * 入口:Today / 设置 跳转。后端能力首次在手机可见可用。
 */
import React from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator, RefreshControl,
  Alert, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import {
  useAgendaToday,
  useCompleteAgendaItem,
  useRuntimeAgendaRange,
  useSeedDemo,
  useSmartAgendaToday,
} from '../hooks/useAgenda';
import {
  isProtocolActionable,
  MANUAL_CAPTURE,
  type AgendaItem,
  type RuntimeAgendaItem,
  type RuntimeAgendaRange,
  type SmartAgendaItem,
} from '../services/agenda';
import { buildBoundarySummary, buildTrajectorySummary, buildVerifySummary } from '../services/trajectoryDisplay';
import { agendaItemPresentation, agendaSummary } from '../utils/agendaPresentation';

// 议程项 tone → 三步临床语义(好不好/信息):正常绿 / 注意琥珀 / 风险红 / 信息蓝 / 中性灰。
const TONE_COLOR: Record<string, string> = {
  green: revaSemantic.normal.fg,
  yellow: revaSemantic.caution.fg,
  red: revaSemantic.risk.fg,
  blue: revaSemantic.info.fg,
  gray: C.ink3,
};

// 智能优先面板的绿色装饰 accent。
const SMART_ACCENT = C.green600;

const summaryStyles = StyleSheet.create({
  pill: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.65)',
  },
  value: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800' },
  label: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 2, fontWeight: '700' },
});

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-lg 18 / 计数读数走等宽 mono。
const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.paper },
  header: { paddingHorizontal: revaSpacing.s4, paddingVertical: revaSpacing.s3 },
  title: { fontFamily: revaFonts.sans, fontSize: 24, fontWeight: '700', color: C.ink1 },
  subtitle: { fontFamily: revaFonts.mono, fontSize: 13, color: C.ink2, marginTop: revaSpacing.s1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: revaSpacing.s7 },
  muted: { fontFamily: revaFonts.sans, color: C.ink2, fontSize: 14 },
  retry: { fontFamily: revaFonts.sans, color: C.green500, fontSize: 14, marginTop: revaSpacing.s2 },
  list: { padding: revaSpacing.s4, gap: revaSpacing.s3 },
  summaryRow: { flexDirection: 'row', gap: revaSpacing.s2 },
  smartPanel: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    gap: revaSpacing.s3,
    ...revaShadows.sm,
  },
  smartHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  smartTitleRow: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s1 },
  smartTitle: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '800', color: C.ink1 },
  smartMeta: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '700', color: C.ink3 },
  smartLoading: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  smartMuted: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, flex: 1 },
  smartItem: {
    flexDirection: 'row',
    gap: revaSpacing.s3,
    paddingTop: revaSpacing.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  smartIndex: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  smartIndexText: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '800', color: SMART_ACCENT },
  smartBody: { flex: 1, gap: 4 },
  smartItemHeader: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  smartItemTitle: { fontFamily: revaFonts.sans, flex: 1, fontSize: 15, fontWeight: '800', color: C.ink1 },
  surfaceBadge: {
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  surfaceBadgeText: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '800', color: SMART_ACCENT },
  smartLine: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, lineHeight: 18 },
  smartAction: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.ink1, lineHeight: 18 },
  smartTrajectory: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '700', color: SMART_ACCENT, lineHeight: 16 },
  smartVerify: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, lineHeight: 16 },
  smartBoundary: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, lineHeight: 15 },
  runtimePanel: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    gap: revaSpacing.s3,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  runtimeTitleRow: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s1 },
  runtimeTitle: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '800', color: C.ink1 },
  runtimeMeta: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '700', color: C.ink3 },
  runtimeNext: {
    paddingVertical: revaSpacing.s2,
    paddingHorizontal: revaSpacing.s3,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    gap: 3,
  },
  runtimeNextLabel: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '800', color: SMART_ACCENT },
  runtimeNextTitle: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '800', color: C.ink1, lineHeight: 18 },
  runtimeNextMeta: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, lineHeight: 16 },
  runtimeDayRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s3,
    paddingTop: revaSpacing.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  runtimeDayBadge: {
    width: 44,
    minHeight: 34,
    borderRadius: revaRadii.md,
    backgroundColor: C.paper,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4,
  },
  runtimeDayLabel: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '800', color: C.ink2 },
  runtimeDayBody: { flex: 1, gap: 2 },
  runtimeDayTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '800', color: C.ink1, lineHeight: 17 },
  runtimeDayMeta: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, lineHeight: 16 },
  runtimeEmpty: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, lineHeight: 18 },
  card: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface,
    borderRadius: revaRadii.lg, padding: revaSpacing.s4, gap: revaSpacing.s3, ...revaShadows.sm,
  },
  icon: { width: 24, textAlign: 'center' },
  cardBody: { flex: 1 },
  cardTitle: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1 },
  cardStatus: { fontFamily: revaFonts.sans, fontSize: 13, marginTop: 2 },
  cardDetail: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 2 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  doneBtn: {
    width: 36, height: 36, borderRadius: revaRadii.pill, backgroundColor: C.green500,
    alignItems: 'center', justifyContent: 'center',
  },
  manualBtn: {
    paddingHorizontal: revaSpacing.s3, height: 36, borderRadius: revaRadii.pill,
    borderWidth: 1, borderColor: C.green500, alignItems: 'center', justifyContent: 'center',
  },
  manualBtnText: { fontFamily: revaFonts.sans, color: C.green500, fontSize: 13, fontWeight: '600' },
  lightWrap: { alignItems: 'center', width: 36, gap: 2 },
  lightDot: { width: 16, height: 16, borderRadius: revaRadii.pill },
  lightScore: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '600', color: C.ink2 },
  seedBtn: {
    marginTop: revaSpacing.s4, backgroundColor: C.green500,
    paddingHorizontal: revaSpacing.s5, paddingVertical: revaSpacing.s3, borderRadius: revaRadii.pill,
  },
  seedBtnText: { fontFamily: revaFonts.sans, color: '#fff', fontSize: 14, fontWeight: '600' },
});

type AgendaStyles = typeof styles;

export default function AgendaScreen() {
  const { data, isLoading, isError, refetch, isRefetching } = useAgendaToday();
  const { data: smartData, isLoading: smartLoading } = useSmartAgendaToday(3);
  const { data: runtimeData, isLoading: runtimeLoading } = useRuntimeAgendaRange(7);
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
    if (status === 'completed') return C.green500;
    if (status === 'overdue') return revaSemantic.risk.fg;
    return C.ink3;
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>今日议程</Text>
        {data ? <Text style={styles.subtitle}>{data.agenda_date} · {data.count} 项</Text> : null}
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={C.green500} /></View>
      ) : isError ? (
        <View style={styles.center}>
          <Text style={styles.muted}>加载失败</Text>
          <TouchableOpacity onPress={() => refetch()}><Text style={styles.retry}>重试</Text></TouchableOpacity>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={C.green500} />}
        >
          {smartLoading || smartItems.length > 0 ? (
            <SmartAgendaPanel items={smartItems} loading={smartLoading} styles={styles} />
          ) : null}
          {runtimeLoading || runtimeData ? (
            <RuntimeRangePanel projection={runtimeData} loading={runtimeLoading} styles={styles} />
          ) : null}
          {data && data.items.length > 0 ? (
            <View style={styles.summaryRow}>
              <SummaryPill label="待执行" value={summary.actionable} color={C.green500} />
              <SummaryPill label="逾期" value={summary.overdue} color={revaSemantic.risk.fg} />
              <SummaryPill label="建议" value={summary.info} color={revaSemantic.caution.fg} />
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
                completedColor={C.green500}
                fallbackColor={C.ink3}
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

function SmartAgendaPanel({
  items,
  loading,
  styles,
}: {
  items: SmartAgendaItem[];
  loading: boolean;
  styles: AgendaStyles;
}) {
  return (
    <View style={styles.smartPanel}>
      <View style={styles.smartHeader}>
        <View style={styles.smartTitleRow}>
          <Ionicons name="sparkles-outline" size={18} color={SMART_ACCENT} />
          <Text style={styles.smartTitle}>智能优先处理</Text>
        </View>
        <Text style={styles.smartMeta}>{items.length > 0 ? `${items.length} 项` : '生成中'}</Text>
      </View>
      {loading && items.length === 0 ? (
        <View style={styles.smartLoading}>
          <ActivityIndicator size="small" color={SMART_ACCENT} />
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
              {buildTrajectorySummary(item) ? (
                <Text style={styles.smartTrajectory}>{buildTrajectorySummary(item)}</Text>
              ) : null}
              {buildVerifySummary(item) ? <Text style={styles.smartVerify}>验证: {buildVerifySummary(item)}</Text> : null}
              {buildBoundarySummary(item) ? <Text style={styles.smartBoundary}>{buildBoundarySummary(item)}</Text> : null}
            </View>
          </View>
        ))
      )}
    </View>
  );
}

function formatRuntimeDay(dateText: string, isToday: boolean): string {
  if (isToday) return '今天';
  const parts = dateText.split('-');
  if (parts.length !== 3) return dateText;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

function firstRuntimeItem(day: RuntimeAgendaRange['days'][number]): RuntimeAgendaItem | null {
  if (day.next_action) return day.next_action;
  for (const window of day.time_windows) {
    if (window.items.length > 0) return window.items[0];
  }
  return null;
}

function runtimeMeta(item: RuntimeAgendaItem): string {
  const verify = item.runtime_context.verification_window;
  const metrics = verify.metrics.slice(0, 2).join('、');
  const surface = surfaceLabel(item.surface.primary);
  return `${surface} · ${verify.window_days}天验证${metrics ? ` · ${metrics}` : ''}`;
}

function RuntimeRangePanel({
  projection,
  loading,
  styles,
}: {
  projection?: RuntimeAgendaRange;
  loading: boolean;
  styles: AgendaStyles;
}) {
  const previewDays = projection?.days.slice(0, 4) ?? [];
  return (
    <View style={styles.runtimePanel}>
      <View style={styles.smartHeader}>
        <View style={styles.runtimeTitleRow}>
          <Ionicons name="calendar-outline" size={18} color={SMART_ACCENT} />
          <Text style={styles.runtimeTitle}>7天运行时</Text>
        </View>
        <Text style={styles.runtimeMeta}>
          {projection ? `${projection.start} → ${projection.end}` : '生成中'}
        </Text>
      </View>
      {loading && !projection ? (
        <View style={styles.smartLoading}>
          <ActivityIndicator size="small" color={SMART_ACCENT} />
          <Text style={styles.smartMuted}>正在生成未来 7 天行动投影…</Text>
        </View>
      ) : projection?.next_action ? (
        <View style={styles.runtimeNext}>
          <Text style={styles.runtimeNextLabel}>下一步</Text>
          <Text style={styles.runtimeNextTitle}>{projection.next_action.title}</Text>
          <Text style={styles.runtimeNextMeta}>{runtimeMeta(projection.next_action)}</Text>
        </View>
      ) : (
        <Text style={styles.runtimeEmpty}>未来 7 天暂无可执行行动。</Text>
      )}
      {previewDays.map((day) => {
        const item = firstRuntimeItem(day);
        return (
          <View key={day.date} style={styles.runtimeDayRow}>
            <View style={styles.runtimeDayBadge}>
              <Text style={styles.runtimeDayLabel}>{formatRuntimeDay(day.date, day.is_today)}</Text>
            </View>
            <View style={styles.runtimeDayBody}>
              <Text style={styles.runtimeDayTitle}>{item?.title ?? '暂无行动'}</Text>
              {item ? <Text style={styles.runtimeDayMeta}>{runtimeMeta(item)}</Text> : null}
            </View>
          </View>
        );
      })}
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
  styles: AgendaStyles;
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
