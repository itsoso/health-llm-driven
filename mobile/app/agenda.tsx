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
import { useAgendaToday, useCompleteAgendaItem, useSeedDemo } from '../hooks/useAgenda';
import { isProtocolActionable, MANUAL_CAPTURE, type AgendaItem } from '../services/agenda';
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
  const complete = useCompleteAgendaItem();
  const seed = useSeedDemo();
  const summary = agendaSummary(data?.items ?? []);

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
