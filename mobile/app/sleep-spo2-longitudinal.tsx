import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle, ScrollView,
  ActivityIndicator, RefreshControl, Pressable,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import { colors, spacing, radii, shadows } from '../constants/theme';
import {
  getSpo2Longitudinal,
  SEVERITY_LABEL, SEVERITY_COLOR, FLAG_LABEL,
  type LongitudinalResponse, type NightSummary,
} from '../services/sleepSpo2';

const RANGES: Array<{ days: number; label: string }> = [
  { days: 14, label: '2 周' },
  { days: 30, label: '30 天' },
  { days: 90, label: '90 天' },
];

export default function Spo2LongitudinalScreen() {
  const router = useRouter();
  const [days, setDays] = useState(30);

  const { data, isLoading, isRefetching, refetch } = useQuery<LongitudinalResponse>({
    queryKey: ['spo2Longitudinal', days],
    queryFn: () => getSpo2Longitudinal(days),
    staleTime: 60_000,
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.btn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>SpO2 趋势 · {days} 天</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.rangeRow}>
        {RANGES.map(r => {
          const active = days === r.days;
          return (
            <TouchableOpacity
              key={r.days}
              style={[styles.rangeChip, active && styles.rangeChipActive]}
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                setDays(r.days);
              }}
              activeOpacity={0.7}
            >
              <Text style={[txt.rangeText, active && txt.rangeTextActive]}>{r.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {isLoading || !data ? (
        <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
          }
        >
          <PatternCard data={data} />
          <Text style={txt.hint}>
            窗口：{data.window.start} → {data.window.end} · 含 {data.pattern.covered_nights} 夜数据
          </Text>

          {data.pattern.pattern_flags.length > 0 && (
            <View style={styles.flagsCard}>
              <Text style={txt.sectionTitle}>观察到的模式</Text>
              {data.pattern.pattern_flags.map(f => (
                <View key={f} style={styles.flagRow}>
                  <Ionicons name="pulse" size={14} color={colors.brand} />
                  <View style={{ flex: 1 }}>
                    <Text style={txt.flagLabel}>{FLAG_LABEL[f]?.label ?? f}</Text>
                    <Text style={txt.flagHint}>{FLAG_LABEL[f]?.hint}</Text>
                  </View>
                </View>
              ))}
              <Text style={txt.disclaimer}>
                说明：以上是数据模式描述，不是医学诊断。OSAHS 确诊需要 PSG/便携监测。
              </Text>
            </View>
          )}

          {data.nights.length === 0 ? (
            <View style={styles.card}>
              <Text style={txt.empty}>暂无夜间数据，请确保睡眠时佩戴 Garmin 并开启全天血氧。</Text>
            </View>
          ) : (
            <>
              <Text style={txt.sectionLabel}>每晚明细</Text>
              <View style={styles.timelineCard}>
                {data.nights.map((n, i) => (
                  <NightRow
                    key={n.night_date}
                    night={n}
                    last={i === data.nights.length - 1}
                    onPress={() => router.push({
                      pathname: '/sleep-spo2-analysis',
                      params: { night_date: n.night_date },
                    } as any)}
                  />
                ))}
              </View>
            </>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function PatternCard({ data }: { data: LongitudinalResponse }) {
  const p = data.pattern;
  const avgOdi = p.avg_odi ?? 0;
  const medSpo2 = p.median_min_spo2 ?? 0;
  return (
    <View style={styles.card}>
      <View style={styles.summaryRow}>
        <SummaryStat
          label="平均 ODI"
          value={p.avg_odi !== null ? avgOdi.toFixed(1) : '—'}
          hint={`${p.nights_with_odi} 夜有效`}
          color={
            avgOdi >= 15 ? '#FF3B30'
              : avgOdi >= 5 ? '#FF9500'
              : '#34C759'
          }
        />
        <SummaryStat
          label="最低 SpO2 中位"
          value={p.median_min_spo2 !== null ? `${medSpo2}%` : '—'}
          hint={
            p.pct_nights_min_spo2_below_90 !== null
              ? `${(p.pct_nights_min_spo2_below_90 * 100).toFixed(0)}% 夜 < 90%`
              : ''
          }
          color={medSpo2 >= 92 ? '#34C759' : medSpo2 >= 88 ? '#FF9500' : '#FF3B30'}
        />
      </View>

      <View style={[styles.severityBar, { marginTop: spacing.lg }]}>
        {(() => {
          const total = p.covered_nights || 1;
          const normal = p.covered_nights - p.mild_nights - p.moderate_nights - p.severe_nights;
          return (
            <>
              <SevSegment pct={normal / total} color={SEVERITY_COLOR.normal} />
              <SevSegment pct={p.mild_nights / total} color={SEVERITY_COLOR.mild} />
              <SevSegment pct={p.moderate_nights / total} color={SEVERITY_COLOR.moderate} />
              <SevSegment pct={p.severe_nights / total} color={SEVERITY_COLOR.severe} />
            </>
          );
        })()}
      </View>
      <View style={styles.legendRow}>
        <LegendDot color={SEVERITY_COLOR.normal} label={`正常 ${p.covered_nights - p.mild_nights - p.moderate_nights - p.severe_nights}`} />
        <LegendDot color={SEVERITY_COLOR.mild} label={`轻 ${p.mild_nights}`} />
        <LegendDot color={SEVERITY_COLOR.moderate} label={`中 ${p.moderate_nights}`} />
        <LegendDot color={SEVERITY_COLOR.severe} label={`重 ${p.severe_nights}`} />
      </View>
    </View>
  );
}

function SummaryStat({ label, value, hint, color }: {
  label: string; value: string; hint: string; color: string;
}) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={txt.statLabel}>{label}</Text>
      <Text style={[txt.statValue, { color }]}>{value}</Text>
      {!!hint && <Text style={txt.statHint}>{hint}</Text>}
    </View>
  );
}

function SevSegment({ pct, color }: { pct: number; color: string }) {
  if (pct <= 0) return null;
  return <View style={{ flex: pct, backgroundColor: color, height: '100%' }} />;
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={txt.legendText}>{label}</Text>
    </View>
  );
}

function NightRow({ night, last, onPress }: {
  night: NightSummary; last: boolean; onPress: () => void;
}) {
  const sevColor = SEVERITY_COLOR[night.severity];
  return (
    <Pressable
      onPress={onPress}
      style={[styles.nightRow, !last && styles.nightRowBorder]}
      accessibilityRole="button"
      accessibilityLabel={`${night.night_date} 夜间血氧详情`}
    >
      <View style={[styles.nightDot, { backgroundColor: sevColor }]} />
      <View style={{ flex: 1 }}>
        <Text style={txt.nightDate}>{night.night_date}</Text>
        <Text style={txt.nightMeta}>
          {night.odi !== null ? `ODI ${night.odi}` : 'ODI —'}
          {night.min_spo2 !== null ? ` · 最低 ${night.min_spo2}%` : ''}
          {night.events_count > 0 ? ` · ${night.events_count} 事件` : ''}
        </Text>
      </View>
      <Text style={[txt.sevPill, { backgroundColor: sevColor + '22', color: sevColor }]}>
        {SEVERITY_LABEL[night.severity]}
      </Text>
      <Ionicons name="chevron-forward" size={14} color={colors.labelTertiary} style={{ marginLeft: 4 }} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  btn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  rangeRow: {
    flexDirection: 'row', gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingBottom: spacing.sm,
  },
  rangeChip: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 16, backgroundColor: colors.fill,
  },
  rangeChipActive: { backgroundColor: colors.brand },
  content: { padding: spacing.lg, paddingBottom: 60 },
  card: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md,
    ...shadows.subtle,
  },
  flagsCard: {
    backgroundColor: colors.brandLight, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md,
  },
  flagRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10,
    marginTop: spacing.sm,
  },
  summaryRow: { flexDirection: 'row', gap: spacing.lg },
  severityBar: {
    flexDirection: 'row', height: 10, borderRadius: 5,
    backgroundColor: colors.fill, overflow: 'hidden',
  },
  legendRow: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: 12, marginTop: spacing.sm,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  timelineCard: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    marginBottom: spacing.md, ...shadows.subtle,
  },
  nightRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.lg, paddingVertical: 12, gap: 10,
  },
  nightRowBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  nightDot: { width: 10, height: 10, borderRadius: 5 },
});

const txt = {
  title: {
    fontSize: 17, fontWeight: '600', color: colors.labelPrimary,
    flex: 1, textAlign: 'center',
  } as TextStyle,
  hint: {
    fontSize: 11, color: colors.labelTertiary,
    marginBottom: spacing.md, textAlign: 'center',
  } as TextStyle,
  sectionTitle: {
    fontSize: 14, fontWeight: '600', color: colors.brand,
    marginBottom: spacing.xs,
  } as TextStyle,
  sectionLabel: {
    fontSize: 13, fontWeight: '500', color: colors.labelSecondary,
    marginLeft: spacing.xs, marginBottom: spacing.xs,
  } as TextStyle,
  flagLabel: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  flagHint: { fontSize: 11, color: colors.labelSecondary, marginTop: 2, lineHeight: 16 } as TextStyle,
  disclaimer: {
    fontSize: 10, color: colors.labelTertiary,
    marginTop: spacing.sm, lineHeight: 14, fontStyle: 'italic',
  } as TextStyle,
  rangeText: { fontSize: 13, color: colors.labelPrimary } as TextStyle,
  rangeTextActive: { color: '#fff', fontWeight: '600' } as TextStyle,
  statLabel: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  statValue: { fontSize: 28, fontWeight: '700', marginVertical: 2 } as TextStyle,
  statHint: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
  legendText: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  nightDate: { fontSize: 14, color: colors.labelPrimary, fontWeight: '500' } as TextStyle,
  nightMeta: { fontSize: 11, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  sevPill: {
    fontSize: 11, fontWeight: '600',
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: 8, overflow: 'hidden',
  } as TextStyle,
  empty: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center', lineHeight: 19 } as TextStyle,
};
