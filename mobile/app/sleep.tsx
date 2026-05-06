import React, { useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import MetricTile from '../components/design-system/MetricTile';
import HealthCard from '../components/design-system/HealthCard';
import SleepWeeklyChart from '../components/sleep/SleepWeeklyChart';
import SpO2NightChart from '../components/sleep/SpO2NightChart';
import SleepBreathingSummary from '../components/sleep/SleepBreathingSummary';
import { useSleepStats, useSleepDebt } from '../hooks/useSleepData';
import { useSpO2LatestNight } from '../hooks/useSpO2Data';
import { getDeepAnalysis } from '../services/sleep';
import { spacing, radii, scoreColor, scoreGrade, metricColors } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';

export default function SleepScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const [period, setPeriod] = useState(7);
  const { data: stats, isLoading, refetch, isRefetching } = useSleepStats(period);
  const { data: debt } = useSleepDebt();
  const { data: spo2Data } = useSpO2LatestNight();
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  const loadAnalysis = async () => {
    setAnalysisLoading(true);
    try {
      const res = await getDeepAnalysis(period);
      setAnalysis(res.analysis);
    } catch {
      setAnalysis('分析暂时不可用');
    } finally {
      setAnalysisLoading(false);
    }
  };

  const avgDuration = stats?.avg_duration_hours ?? 0;
  const avgScore = stats?.avg_sleep_score ?? 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>睡眠</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
        showsVerticalScrollIndicator={false}>

        {/* Period toggle */}
        <View style={styles.periodRow}>
          {[7, 14, 30].map(d => (
            <TouchableOpacity key={d} style={[styles.periodBtn, period === d && styles.periodBtnActive]}
              onPress={() => setPeriod(d)} activeOpacity={0.7}>
              <Text style={[txt.periodText, period === d && txt.periodTextActive]}>{d}天</Text>
            </TouchableOpacity>
          ))}
        </View>

        {isLoading ? (
          <ActivityIndicator color={c.brand} style={{ marginTop: 40 }} />
        ) : (
          <>
            {/* Metrics */}
            <View style={styles.metricsRow}>
              <MetricTile label="平均时长" value={(avgDuration || 0).toFixed(1)} unit="h"
                icon="moon" color={metricColors.sleep.main} tintColor={metricColors.sleep.tint} />
              <MetricTile label="睡眠质量" value={avgScore > 0 ? Math.round(avgScore).toString() : '--'} unit=""
                subtitle={avgScore > 0 ? scoreGrade(avgScore) : undefined}
                icon="star" color={scoreColor(avgScore)} tintColor={`${scoreColor(avgScore)}20`} />
            </View>

            {/* Sleep debt */}
            {debt && debt.status === 'success' && (
              <View style={styles.metricsRow}>
                <MetricTile label="睡眠债务" value={(debt.cumulative_debt_hours ?? 0).toFixed(1)} unit="h"
                  icon="trending-down" color={(debt.cumulative_debt_hours ?? 0) > 3 ? c.red : c.amber}
                  tintColor={(debt.cumulative_debt_hours ?? 0) > 3 ? c.tintRed : c.tintAmber} />
                <MetricTile label="推荐时长" value={(debt.target_hours ?? 0).toFixed(1)} unit="h"
                  icon="bed" color={c.brand} tintColor={c.brandLight} />
              </View>
            )}

            {/* Chart */}
            {stats?.daily_trend && stats.daily_trend.length > 0 && (
              <HealthCard title="周趋势" icon="bar-chart-outline" iconColor={metricColors.sleep.main} iconBg={metricColors.sleep.tint}>
                <SleepWeeklyChart data={stats.daily_trend} />
              </HealthCard>
            )}

            {/* SpO2 Overnight */}
            {spo2Data && spo2Data.timeline.length > 0 && (
              <HealthCard title="夜间血氧" icon="pulse-outline" iconColor="#007AFF" iconBg="#E6F0FF"
                rightAccessory={
                  <TouchableOpacity
                    onPress={() => router.push('/sleep-spo2-analysis')}
                    style={styles.osaBadge}
                    activeOpacity={0.7}
                  >
                    <Ionicons name="analytics-outline" size={12} color={c.brand} />
                    <Text style={[txt.osaBadgeText, { color: c.brand }]}>根因分析</Text>
                  </TouchableOpacity>
                }>
                <SpO2NightChart data={spo2Data.timeline} sleepStart={spo2Data.sleep_start} sleepEnd={spo2Data.sleep_end} />
              </HealthCard>
            )}

            {spo2Data ? (
              <SleepBreathingSummary
                date={spo2Data.summary.record_date}
                odi={spo2Data.summary.odi}
                minSpO2={spo2Data.summary.min_spo2}
                eventCount={spo2Data.summary.desaturation_events}
                onOpenAnalysis={() => router.push('/sleep-spo2-analysis' as any)}
              />
            ) : null}

            {/* Deep analysis */}
            <HealthCard title="AI 深度分析" icon="sparkles-outline" iconColor={c.purple} iconBg={c.tintPurple}
              rightAccessory={
                !analysis && !analysisLoading ? (
                  <TouchableOpacity onPress={loadAnalysis} activeOpacity={0.7}>
                    <Text style={txt.analyzeBtn}>分析</Text>
                  </TouchableOpacity>
                ) : null
              }>
              {analysisLoading ? (
                <ActivityIndicator color={c.purple} />
              ) : analysis ? (
                <Text style={txt.analysisText}>{analysis}</Text>
              ) : (
                <Text style={txt.placeholder}>点击"分析"获取 AI 睡眠深度分析</Text>
              )}
            </HealthCard>
          </>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  periodRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.lg },
  periodBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: radii.full, backgroundColor: c.bgCard },
  periodBtnActive: { backgroundColor: c.brand },
  metricsRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  osaBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: '#FFF5E6', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  periodText: { fontSize: 13, fontWeight: '500', color: c.labelSecondary } as TextStyle,
  periodTextActive: { color: '#fff', fontWeight: '600' } as TextStyle,
  analyzeBtn: { fontSize: 14, fontWeight: '600', color: c.purple } as TextStyle,
  analysisText: { fontSize: 14, color: c.labelPrimary, lineHeight: 21 } as TextStyle,
  placeholder: { fontSize: 13, color: c.labelTertiary, textAlign: 'center', paddingVertical: 12 } as TextStyle,
  osaBadgeText: { fontSize: 11, fontWeight: '600', color: '#FF9F0A' } as TextStyle,
});
