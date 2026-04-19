import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import MetricTile from '@/components/design-system/MetricTile';
import SectionHeader from '@/components/design-system/SectionHeader';
import HealthCard from '@/components/design-system/HealthCard';
import SleepWeeklyChart from '@/components/sleep/SleepWeeklyChart';
import { useSleepStats, useSleepDebt } from '@/hooks/useSleepData';
import { getDeepAnalysis } from '@/services/sleep';
import { colors, spacing, radii, shadows, scoreColor, scoreGrade, metricColors } from '@/constants/theme';

export default function SleepScreen() {
  const router = useRouter();
  const [period, setPeriod] = useState(7);
  const { data: stats, isLoading, refetch, isRefetching } = useSleepStats(period);
  const { data: debt } = useSleepDebt();
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

  const avgDuration = stats?.avg_duration ?? 0;
  const avgScore = stats?.avg_score ?? 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>睡眠</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
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
          <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
        ) : (
          <>
            {/* Metrics */}
            <View style={styles.metricsRow}>
              <MetricTile label="平均时长" value={avgDuration.toFixed(1)} unit="h"
                icon="moon" color={metricColors.sleep.main} tintColor={metricColors.sleep.tint} />
              <MetricTile label="平均分数" value={avgScore > 0 ? Math.round(avgScore).toString() : '--'} unit=""
                subtitle={avgScore > 0 ? scoreGrade(avgScore) : undefined}
                icon="star" color={scoreColor(avgScore)} tintColor={`${scoreColor(avgScore)}20`} />
            </View>

            {/* Sleep debt */}
            {debt && (
              <View style={styles.metricsRow}>
                <MetricTile label="睡眠债务" value={debt.current_debt_hours.toFixed(1)} unit="h"
                  icon="trending-down" color={debt.current_debt_hours > 3 ? colors.red : colors.amber}
                  tintColor={debt.current_debt_hours > 3 ? colors.tintRed : colors.tintAmber} />
                <MetricTile label="推荐时长" value={debt.recommended_hours.toFixed(1)} unit="h"
                  icon="bed" color={colors.brand} tintColor={colors.brandLight} />
              </View>
            )}

            {/* Chart */}
            {stats?.trend && stats.trend.length > 0 && (
              <HealthCard title="周趋势" icon="bar-chart-outline" iconColor={metricColors.sleep.main} iconBg={metricColors.sleep.tint}>
                <SleepWeeklyChart data={stats.trend} />
              </HealthCard>
            )}

            {/* Deep analysis */}
            <HealthCard title="AI 深度分析" icon="sparkles-outline" iconColor={colors.purple} iconBg={colors.tintPurple}
              rightAccessory={
                !analysis && !analysisLoading ? (
                  <TouchableOpacity onPress={loadAnalysis} activeOpacity={0.7}>
                    <Text style={txt.analyzeBtn}>分析</Text>
                  </TouchableOpacity>
                ) : null
              }>
              {analysisLoading ? (
                <ActivityIndicator color={colors.purple} />
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

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  periodRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.lg },
  periodBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: radii.full, backgroundColor: colors.bgCard },
  periodBtnActive: { backgroundColor: colors.brand },
  metricsRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  periodText: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary } as TextStyle,
  periodTextActive: { color: '#fff', fontWeight: '600' } as TextStyle,
  analyzeBtn: { fontSize: 14, fontWeight: '600', color: colors.purple } as TextStyle,
  analysisText: { fontSize: 14, color: colors.labelPrimary, lineHeight: 21 } as TextStyle,
  placeholder: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center', paddingVertical: 12 } as TextStyle,
};
