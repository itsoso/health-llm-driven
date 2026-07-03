import React, { useCallback, useState, useMemo } from 'react';
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
import { scoreGrade } from '../constants/theme'
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import { createSleepAgentContext, pushChatWithContext } from '../utils/agentContext';

// 睡眠相关类目装饰色(区分"哪类",非"好坏"):睡眠/时长蓝、AI 深度分析紫。
const SLEEP_HUE = { fg: C.blue500, bg: C.blue50 } as const;
const ANALYSIS_HUE = { fg: '#7C5CBF', bg: '#EDE7F6' } as const;

// 睡眠质量分 → 三步临床语义(好不好)。
function scoreSemanticColor(score: number): string {
  if (score >= 80) return revaSemantic.normal.fg;
  if (score >= 60) return revaSemantic.caution.fg;
  return revaSemantic.risk.fg;
}

export default function SleepScreen() {
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
  const handleChatSleep = useCallback(() => {
    if (!stats) return;
    pushChatWithContext(router, {
      prompt: `请基于我近 ${period} 天睡眠数据, 分析睡眠质量、睡眠债务和今晚最该调整的 3 件事。`,
      context: createSleepAgentContext({
        periodDays: period,
        stats,
        debt,
      }),
      badge: `基于近 ${period} 天睡眠`,
    });
  }, [debt, period, router, stats]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>睡眠</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={C.green500} />}
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
          <ActivityIndicator color={C.green500} style={{ marginTop: 40 }} />
        ) : (
          <>
            {/* Metrics */}
            <View style={styles.metricsRow}>
              <MetricTile label="平均时长" value={(avgDuration || 0).toFixed(1)} unit="h"
                icon="moon" color={SLEEP_HUE.fg} tintColor={SLEEP_HUE.bg} />
              <MetricTile label="睡眠质量" value={avgScore > 0 ? Math.round(avgScore).toString() : '--'} unit=""
                subtitle={avgScore > 0 ? scoreGrade(avgScore) : undefined}
                icon="star" color={scoreSemanticColor(avgScore)} tintColor={`${scoreSemanticColor(avgScore)}20`} />
            </View>
            {stats && (
              <TouchableOpacity
                style={[styles.agentLink, { borderColor: C.line }]}
                onPress={handleChatSleep}
                activeOpacity={0.75}
                accessibilityRole="button"
                accessibilityLabel="跟阿衡详细聊睡眠"
              >
                <Ionicons name="chatbubble-ellipses-outline" size={16} color={C.green500} />
                <Text style={[txt.agentLinkText, { color: C.green500 }]}>跟阿衡详细聊睡眠</Text>
                <Ionicons name="chevron-forward" size={15} color={C.green500} style={{ marginLeft: 'auto' }} />
              </TouchableOpacity>
            )}

            {/* Sleep debt */}
            {debt && debt.status === 'success' && (
              <View style={styles.metricsRow}>
                <MetricTile label="睡眠债务" value={(debt.cumulative_debt_hours ?? 0).toFixed(1)} unit="h"
                  icon="trending-down" color={(debt.cumulative_debt_hours ?? 0) > 3 ? revaSemantic.risk.fg : revaSemantic.caution.fg}
                  tintColor={(debt.cumulative_debt_hours ?? 0) > 3 ? revaSemantic.risk.bg : revaSemantic.caution.bg} />
                <MetricTile label="推荐时长" value={(debt.target_hours ?? 0).toFixed(1)} unit="h"
                  icon="bed" color={C.green500} tintColor={C.green50} />
              </View>
            )}

            {/* Chart */}
            {stats?.daily_trend && stats.daily_trend.length > 0 && (
              <HealthCard title="周趋势" icon="bar-chart-outline" iconColor={SLEEP_HUE.fg} iconBg={SLEEP_HUE.bg}>
                <SleepWeeklyChart data={stats.daily_trend} />
              </HealthCard>
            )}

            {/* SpO2 Overnight */}
            {spo2Data && spo2Data.timeline.length > 0 && (
              <HealthCard title="夜间血氧" icon="pulse-outline" iconColor={C.blue500} iconBg={C.blue50}
                rightAccessory={
                  <TouchableOpacity
                    onPress={() => router.push('/sleep-spo2-analysis')}
                    style={styles.osaBadge}
                    activeOpacity={0.7}
                  >
                    <Ionicons name="analytics-outline" size={12} color={C.green500} />
                    <Text style={[txt.osaBadgeText, { color: C.green500 }]}>根因分析</Text>
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
            <HealthCard title="AI 深度分析" icon="sparkles-outline" iconColor={ANALYSIS_HUE.fg} iconBg={ANALYSIS_HUE.bg}
              rightAccessory={
                !analysis && !analysisLoading ? (
                  <TouchableOpacity onPress={loadAnalysis} activeOpacity={0.7}>
                    <Text style={txt.analyzeBtn}>分析</Text>
                  </TouchableOpacity>
                ) : null
              }>
              {analysisLoading ? (
                <ActivityIndicator color={ANALYSIS_HUE.fg} />
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

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-md / 数字等宽 mono。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2 },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: revaSpacing.s4 },
  periodRow: { flexDirection: 'row', gap: 8, marginBottom: revaSpacing.s4 },
  periodBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: revaRadii.pill, backgroundColor: C.surface },
  periodBtnActive: { backgroundColor: C.green500 },
  metricsRow: { flexDirection: 'row', gap: revaSpacing.s3, marginBottom: revaSpacing.s3 },
  osaBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: C.green50, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    marginBottom: revaSpacing.s3,
  },
});

// 数字/计数/指标走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1, textAlign: 'center' } as TextStyle,
  periodText: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '500', color: C.ink2 } as TextStyle,
  periodTextActive: { color: '#fff', fontWeight: '600' } as TextStyle,
  analyzeBtn: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: ANALYSIS_HUE.fg } as TextStyle,
  analysisText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink1, lineHeight: 21 } as TextStyle,
  placeholder: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink3, textAlign: 'center', paddingVertical: 12 } as TextStyle,
  osaBadgeText: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '600', color: C.green500 } as TextStyle,
  agentLinkText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600' } as TextStyle,
};
