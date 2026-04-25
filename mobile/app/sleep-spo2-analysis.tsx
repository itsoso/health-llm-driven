// 夜间 SpO2 根因分析页面（P1b Mobile UI）
// 路由: /sleep-spo2-analysis?night_date=YYYY-MM-DD（缺省 = 昨天）
import React, { useMemo, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, RefreshControl, TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import * as Haptics from 'expo-haptics';

import SpO2AnalysisChart from '@/components/sleep/SpO2AnalysisChart';
import { useNightAnalysis, useNightTimeseries, useReanalyzeNight, useConfirmNoAlcohol } from '@/hooks/useSpo2Analysis';
import { SpO2Correlation } from '@/services/sleepSpo2';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function yesterdayISO(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

const SEVERITY_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  alert: { bg: '#FEE2E2', border: '#DC2626', icon: '#B91C1C' },
  warning: { bg: '#FEF3C7', border: '#D97706', icon: '#B45309' },
  info: { bg: '#DBEAFE', border: '#2563EB', icon: '#1E40AF' },
};

const SEVERITY_LABEL: Record<string, string> = {
  alert: '高优先',
  warning: '关注',
  info: '提示',
};

const CATEGORY_ICON: Record<string, any> = {
  medication: 'medical',
  supplement: 'flask',
  exercise: 'fitness',
  diet: 'restaurant',
  environment: 'leaf',
  diagnostic: 'pulse',
};

export default function SleepSpo2AnalysisScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ night_date?: string }>();
  const [selectedDate, setSelectedDate] = useState(params.night_date || yesterdayISO());
  const [overlay, setOverlay] = useState<'hr' | 'respiration' | 'none'>('none');

  const analysisQ = useNightAnalysis(selectedDate);
  const tsQ = useNightTimeseries(selectedDate, 'spo2,hr,respiration,sleep_stage');
  const reanalyzeM = useReanalyzeNight();
  const confirmNoAlcoholM = useConfirmNoAlcohol();

  const analysis = analysisQ.data;
  const ts = tsQ.data;

  const isLoading = analysisQ.isLoading || tsQ.isLoading;

  // 日期翻页
  const shift = (days: number) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    Haptics.selectionAsync();
    setSelectedDate(d.toISOString().slice(0, 10));
  };

  const onRefresh = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    reanalyzeM.mutate(selectedDate);
  };

  // 规则按 severity 分组
  const grouped = useMemo(() => {
    const out: Record<string, SpO2Correlation[]> = { alert: [], warning: [], info: [] };
    if (!analysis) return out;
    analysis.correlations.forEach((c) => {
      if (!out[c.severity]) out[c.severity] = [];
      out[c.severity].push(c);
    });
    return out;
  }, [analysis]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.btn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>夜间血氧分析</Text>
        <TouchableOpacity onPress={onRefresh} style={styles.btn} disabled={reanalyzeM.isPending}>
          <Ionicons name="refresh" size={22} color={reanalyzeM.isPending ? colors.labelTertiary : colors.labelPrimary} />
        </TouchableOpacity>
      </View>

      {/* 日期选择 */}
      <View style={styles.dateBar}>
        <TouchableOpacity onPress={() => shift(-1)} style={styles.dateBtn}>
          <Ionicons name="chevron-back" size={18} color={colors.brand} />
        </TouchableOpacity>
        <Text style={txt.dateLabel}>{selectedDate}</Text>
        <TouchableOpacity
          onPress={() => shift(1)}
          style={styles.dateBtn}
          disabled={selectedDate >= yesterdayISO()}
        >
          <Ionicons
            name="chevron-forward"
            size={18}
            color={selectedDate >= yesterdayISO() ? colors.labelTertiary : colors.brand}
          />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={analysisQ.isRefetching} onRefresh={() => analysisQ.refetch()} />}
      >
        {isLoading && !analysis ? (
          <View style={styles.loading}>
            <ActivityIndicator size="large" color={colors.brand} />
            <Text style={[txt.body, { marginTop: 12 }]}>加载分析中...</Text>
          </View>
        ) : !analysis ? (
          <View style={styles.loading}>
            <Text style={txt.body}>暂无数据</Text>
          </View>
        ) : (
          <>
            {/* 摘要卡片 */}
            <View style={styles.summary}>
              <SummaryTile
                label="最低 SpO₂"
                value={analysis.min_spo2 != null ? `${analysis.min_spo2.toFixed(0)}%` : '—'}
                color={
                  !analysis.min_spo2 ? colors.labelTertiary :
                  analysis.min_spo2 < 85 ? '#DC2626' :
                  analysis.min_spo2 < 88 ? '#D97706' :
                  '#10B981'
                }
              />
              <SummaryTile
                label="ODI"
                value={analysis.odi.toFixed(1)}
                color={
                  analysis.odi >= 15 ? '#DC2626' :
                  analysis.odi >= 5 ? '#D97706' :
                  '#10B981'
                }
                sub="/小时"
              />
              <SummaryTile
                label="氧降事件"
                value={String(analysis.events_count)}
                color={colors.labelPrimary}
              />
              <SummaryTile
                label="睡眠"
                value={`${(analysis.total_sleep_minutes / 60).toFixed(1)}h`}
                color={colors.labelPrimary}
              />
            </View>

            {/* 图表 */}
            {ts && ts.metrics?.spo2?.length ? (
              <View style={styles.chartCard}>
                <View style={styles.chartHeader}>
                  <Text style={txt.sectionTitle}>夜间时序</Text>
                  <View style={styles.overlayBtns}>
                    <OverlayBtn
                      active={overlay === 'none'}
                      label="仅 SpO₂"
                      onPress={() => setOverlay('none')}
                    />
                    <OverlayBtn
                      active={overlay === 'hr'}
                      label="+ 心率"
                      onPress={() => setOverlay('hr')}
                    />
                    <OverlayBtn
                      active={overlay === 'respiration'}
                      label="+ 呼吸"
                      onPress={() => setOverlay('respiration')}
                    />
                  </View>
                </View>
                <SpO2AnalysisChart
                  spo2Series={ts.metrics.spo2 || []}
                  hrSeries={ts.metrics.hr || []}
                  respirationSeries={ts.metrics.respiration || []}
                  events={analysis.events}
                  sleepStages={ts.sleep_stages || []}
                  showOverlay={overlay}
                  height={240}
                />
              </View>
            ) : null}

            {/* 数据缺口追问 — 当夜有问题但关键数据没录入 */}
            {analysis.ask_questions && analysis.ask_questions.length > 0 ? (
              <View style={styles.askCard}>
                <Text style={txt.askTitle}>❓ 帮我补全这些信息</Text>
                <Text style={txt.askSub}>当夜确认有低氧/事件，但缺关键背景。补一下能让分析更准。</Text>
                {analysis.ask_questions.map((q, i) => {
                  const isAlcohol = q.includes('饮酒');
                  const isIpra = q.includes('异丙托溴铵');
                  const isWorkout = q.includes('运动');
                  return (
                    <View key={i} style={styles.askItem}>
                      <Text style={txt.askText}>{q}</Text>
                      <View style={styles.askBtnRow}>
                        {isAlcohol ? (
                          <TouchableOpacity
                            style={[styles.askChip, styles.askChipPrimary]}
                            onPress={() => {
                              Haptics.selectionAsync();
                              confirmNoAlcoholM.mutate(selectedDate);
                            }}
                            disabled={confirmNoAlcoholM.isPending}
                            activeOpacity={0.7}
                          >
                            <Text style={txt.askChipPrimary}>没喝</Text>
                          </TouchableOpacity>
                        ) : null}
                        <TouchableOpacity
                          style={styles.askChip}
                          onPress={() => {
                            if (isIpra) router.push('/(tabs)/record');
                            else if (isWorkout) router.push('/workout-list');
                            else router.push('/diet');
                          }}
                          activeOpacity={0.7}
                        >
                          <Text style={txt.askChipSecondary}>
                            {isIpra ? '去打卡 →' : isWorkout ? '去记录 →' : '补录 →'}
                          </Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : null}

            {/* 今晚可试 — action priorities */}
            {analysis.action_priorities.length > 0 ? (
              <View style={styles.actionCard}>
                <Text style={txt.sectionTitle}>✨ 今晚可试</Text>
                {analysis.action_priorities.map((a, i) => (
                  <View key={i} style={styles.actionRow}>
                    <Text style={txt.actionNum}>{i + 1}</Text>
                    <Text style={txt.actionText}>{a}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {/* 根因假设（按严重度分组）*/}
            {['alert', 'warning', 'info'].map((sev) => {
              const items = grouped[sev] || [];
              if (!items.length) return null;
              const sc = SEVERITY_COLORS[sev];
              return (
                <View key={sev} style={{ marginBottom: spacing.lg }}>
                  <Text style={[txt.sectionTitle, { marginBottom: 8 }]}>
                    {SEVERITY_LABEL[sev]} · {items.length}
                  </Text>
                  {items.map((c) => (
                    <View
                      key={c.rule}
                      style={[styles.findingCard, { backgroundColor: sc.bg, borderLeftColor: sc.border }]}
                    >
                      <View style={styles.findingHeader}>
                        <Ionicons
                          name={CATEGORY_ICON[c.category] || 'alert-circle'}
                          size={16}
                          color={sc.icon}
                        />
                        <Text style={[txt.findingSubject, { color: sc.icon }]}>
                          {c.subject}
                        </Text>
                        <Text style={txt.confidence}>{c.confidence}</Text>
                      </View>
                      <Text style={txt.hypothesis}>{c.hypothesis}</Text>
                      <Text style={[txt.action, { color: sc.border }]}>
                        → {c.suggested_action}
                      </Text>
                    </View>
                  ))}
                </View>
              );
            })}

            {analysis.correlations.length === 0 ? (
              <View style={styles.noFindings}>
                <Ionicons name="checkmark-circle" size={40} color={colors.green} />
                <Text style={[txt.body, { marginTop: 8 }]}>本夜无规则触发</Text>
                <Text style={[txt.caption, { marginTop: 4, textAlign: 'center' }]}>
                  继续记录用药时间、运动、饮食，规则会给出更针对的建议
                </Text>
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function SummaryTile({
  label,
  value,
  color,
  sub,
}: {
  label: string;
  value: string;
  color: string;
  sub?: string;
}) {
  return (
    <View style={styles.sumTile}>
      <Text style={txt.sumLabel}>{label}</Text>
      <Text style={[txt.sumValue, { color }]}>{value}{sub ? <Text style={txt.sumSub}>{sub}</Text> : null}</Text>
    </View>
  );
}

function OverlayBtn({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.overlayBtn, active && styles.overlayBtnActive]}
    >
      <Text style={[txt.overlayBtn, active && txt.overlayBtnActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  btn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  dateBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: spacing.sm,
    gap: 16,
  },
  dateBtn: { padding: 4 },
  content: { padding: spacing.md, paddingBottom: spacing.xl },
  loading: { paddingVertical: 60, alignItems: 'center' },
  summary: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  sumTile: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: radii.md,
    padding: spacing.sm,
    alignItems: 'center',
    ...shadows.subtle,
  },
  chartCard: {
    backgroundColor: '#fff',
    borderRadius: radii.md,
    padding: spacing.sm,
    marginBottom: spacing.md,
    ...shadows.subtle,
  },
  chartHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xs,
    marginBottom: 4,
  },
  overlayBtns: { flexDirection: 'row', gap: 4 },
  overlayBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    backgroundColor: '#F3F4F6',
  },
  overlayBtnActive: { backgroundColor: colors.brand },
  actionCard: {
    backgroundColor: '#ECFDF5',
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: '#10B981',
  },
  askCard: {
    backgroundColor: '#FFF7ED',
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: '#F97316',
  },
  askRow: { marginTop: 8 },
  askItem: {
    marginTop: 10, paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#FED7AA',
  },
  askBtnRow: { flexDirection: 'row', gap: 8, marginTop: 8, justifyContent: 'flex-end' },
  askChip: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: radii.full, backgroundColor: '#fff',
    borderWidth: 1, borderColor: '#F97316',
  },
  askChipPrimary: { backgroundColor: '#F97316', borderColor: '#F97316' },
  askGoBtn: {
    marginTop: 12,
    alignSelf: 'flex-end',
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#F97316',
    borderRadius: radii.full,
  },
  actionRow: {
    flexDirection: 'row',
    marginTop: 8,
    gap: 8,
    alignItems: 'flex-start',
  },
  findingCard: {
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    borderLeftWidth: 3,
  },
  findingHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  noFindings: {
    alignItems: 'center',
    paddingVertical: 40,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  dateLabel: { fontSize: 16, fontWeight: '500', color: colors.labelPrimary } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  askTitle: { fontSize: 15, fontWeight: '600', color: '#9A3412' } as TextStyle,
  askSub: { fontSize: 12, color: '#9A3412', marginTop: 4 } as TextStyle,
  askText: { fontSize: 13, color: '#7C2D12', lineHeight: 19 } as TextStyle,
  askGoText: { fontSize: 13, fontWeight: '600', color: '#fff' } as TextStyle,
  askChipPrimary: { fontSize: 13, fontWeight: '600', color: '#fff' } as TextStyle,
  askChipSecondary: { fontSize: 13, fontWeight: '600', color: '#F97316' } as TextStyle,
  body: { fontSize: 14, color: colors.labelPrimary } as TextStyle,
  caption: { fontSize: 12, color: colors.labelSecondary } as TextStyle,
  sumLabel: { fontSize: 11, color: colors.labelSecondary, marginBottom: 4 } as TextStyle,
  sumValue: { fontSize: 20, fontWeight: '700' } as TextStyle,
  sumSub: { fontSize: 11, fontWeight: '400', color: colors.labelSecondary } as TextStyle,
  findingSubject: { fontSize: 14, fontWeight: '600', flex: 1 } as TextStyle,
  confidence: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  hypothesis: { fontSize: 13, color: colors.labelPrimary, marginTop: 4, lineHeight: 19 } as TextStyle,
  action: { fontSize: 13, fontWeight: '500', marginTop: 8, lineHeight: 19 } as TextStyle,
  overlayBtn: { fontSize: 11, color: colors.labelSecondary } as TextStyle,
  overlayBtnActive: { color: '#fff', fontWeight: '600' } as TextStyle,
  actionNum: {
    fontSize: 13,
    fontWeight: '700',
    color: '#065F46',
    minWidth: 18,
  } as TextStyle,
  actionText: {
    fontSize: 13,
    color: '#065F46',
    flex: 1,
    lineHeight: 19,
  } as TextStyle,
};
