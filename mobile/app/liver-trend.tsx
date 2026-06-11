/**
 * /liver-trend —— 肝脏趋势页(消费后端 GET /chronic/liver,PR #121)。
 *
 * 展示 ALT/GGT 趋势(配色按 verdict)、AST/ALT 比值、FIB-4(+band)、脂肪肝风险、
 * 以及后端组好的人话 advice。底部固定免责:趋势提示,非诊断。
 * available=false → 友好空态(reason)。
 */
import React, { useMemo } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import {
  getLiverAssessment,
  verdictLabel,
  verdictColor,
  type LiverTrend,
} from '../services/chronicHealth';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';

function TrendCard({
  title,
  trend,
  summaryLines,
}: {
  title: string;
  trend: LiverTrend | null;
  summaryLines: string[];
}) {
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  if (!trend) return null;
  const color = verdictColor(trend.verdict, s);
  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.cardHeader}>
        <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>{title}</Text>
        <View style={[styles.badge, { backgroundColor: color }]}>
          <Text style={styles.badgeText}>{verdictLabel(trend.verdict)}</Text>
        </View>
      </View>
      {summaryLines.length > 0 ? (
        summaryLines.map((line, i) => (
          <Text key={i} style={[styles.summaryLine, { color: c.labelSecondary }]}>
            {line}
          </Text>
        ))
      ) : (
        <Text style={[styles.summaryLine, { color: c.labelTertiary }]}>
          {trend.first_value} → {trend.last_value}（{trend.first_date} ~ {trend.last_date}）
        </Text>
      )}
    </View>
  );
}

function MetricRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.metricRow}>
      <Text style={[styles.metricLabel, { color: c.labelSecondary }]}>{label}</Text>
      <View style={{ flex: 1, alignItems: 'flex-end' }}>
        <Text style={[styles.metricValue, { color: c.labelPrimary }]}>{value}</Text>
        {hint ? <Text style={[styles.metricHint, { color: c.labelTertiary }]}>{hint}</Text> : null}
      </View>
    </View>
  );
}

export default function LiverTrendScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['liver-assessment'],
    queryFn: getLiverAssessment,
    staleTime: 5 * 60 * 1000,
  });

  const header = (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
        <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
      </TouchableOpacity>
      <Text style={[styles.title, { color: c.labelPrimary }]}>肝脏趋势</Text>
      <View style={{ width: 24 }} />
    </View>
  );

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      {header}

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        {isLoading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={c.labelTertiary} />
        ) : error ? (
          <Text style={[styles.empty, { color: c.labelTertiary }]}>加载失败,下拉重试</Text>
        ) : !data || !data.available ? (
          <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <Text style={[styles.emptyTitle, { color: c.labelPrimary }]}>暂无肝脏趋势</Text>
            <Text style={[styles.summaryLine, { color: c.labelTertiary }]}>
              {data?.reason || '需要至少两次含肝功能(ALT/AST/GGT)的化验记录,补一次抽血即可生成趋势。'}
            </Text>
          </View>
        ) : (
          <>
            <TrendCard title="ALT 趋势" trend={data.alt_trend} summaryLines={data.summary_lines} />
            <TrendCard title="GGT 趋势" trend={data.ggt_trend} summaryLines={[]} />

            {/* 指标卡:AST/ALT 比值 + FIB-4 + 脂肪肝风险 */}
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary, marginBottom: 4 }]}>指标</Text>

              {data.ast_alt_ratio != null && (
                <MetricRow label="AST / ALT 比值" value={data.ast_alt_ratio.toFixed(2)} />
              )}

              {data.fib4 != null ? (
                <MetricRow
                  label="FIB-4"
                  value={data.fib4.toFixed(2)}
                  hint={data.fib4_band || undefined}
                />
              ) : (
                <View style={styles.metricRow}>
                  <Text style={[styles.metricLabel, { color: c.labelSecondary }]}>FIB-4</Text>
                  <Text style={[styles.metricHint, { color: c.labelTertiary, flex: 1, textAlign: 'right' }]}>
                    缺血小板,补一次血常规即可评估
                  </Text>
                </View>
              )}

              {data.fatty_liver_risk ? (
                <View style={[styles.riskRow, { backgroundColor: s.warning.bg }]}>
                  <Ionicons name="alert-circle-outline" size={16} color={s.warning.solid} />
                  <Text style={[styles.riskText, { color: s.warning.fg }]}>
                    脂肪肝风险{data.fatty_liver_risk}
                  </Text>
                </View>
              ) : null}
            </View>

            {/* advice */}
            {data.advice.length > 0 && (
              <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                <Text style={[styles.cardTitle, { color: c.labelPrimary, marginBottom: 4 }]}>建议</Text>
                {data.advice.map((a, i) => (
                  <View key={i} style={styles.adviceRow}>
                    <Ionicons name="ellipse" size={6} color={c.brand} style={{ marginTop: 7 }} />
                    <Text style={[styles.adviceText, { color: c.labelSecondary }]}>{a}</Text>
                  </View>
                ))}
              </View>
            )}

            <Text style={[styles.disclaimer, { color: c.labelTertiary }]}>
              趋势提示,非诊断,请结合腹部超声 + 医生
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    safe: { flex: 1 },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    title: { fontSize: 17, fontWeight: '700' },
    content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
    empty: { fontSize: 14, textAlign: 'center', marginTop: 40, lineHeight: 20, paddingHorizontal: spacing.lg },
    emptyTitle: { fontSize: 15, fontWeight: '800', marginBottom: 6 },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 6 },
    cardHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    cardTitle: { fontSize: 15, fontWeight: '800' },
    badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
    badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
    summaryLine: { fontSize: 13, lineHeight: 19 },
    metricRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: 8,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
      gap: 12,
    },
    metricLabel: { fontSize: 14, fontWeight: '500' },
    metricValue: { fontSize: 15, fontWeight: '700' },
    metricHint: { fontSize: 12, fontWeight: '500', marginTop: 1 },
    riskRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      borderRadius: radii.md,
      paddingHorizontal: 10,
      paddingVertical: 8,
      marginTop: 6,
    },
    riskText: { fontSize: 13, fontWeight: '600' },
    adviceRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
    adviceText: { fontSize: 13, lineHeight: 19, flex: 1 },
    disclaimer: { fontSize: 12, textAlign: 'center', lineHeight: 17, marginTop: spacing.sm },
  });
