import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useWorkoutDetail } from '@/hooks/useWorkouts';
import { analyzeWorkout, type WorkoutAnalysis } from '@/services/workouts';
import MetricTile from '@/components/design-system/MetricTile';
import HealthCard from '@/components/design-system/HealthCard';
import { colors, spacing, radii, shadows, metricColors } from '@/constants/theme';

export default function WorkoutDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const workoutId = parseInt(id || '0');
  const { data: workout, isLoading } = useWorkoutDetail(workoutId);
  const [analysis, setAnalysis] = useState<WorkoutAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const handleAnalyze = async () => {
    if (!workoutId) return;
    setAnalyzing(true);
    try {
      const res = await analyzeWorkout(workoutId);
      setAnalysis(res);
    } catch {
      setAnalysis({ summary: '分析暂时不可用', intensity_assessment: '', recovery_suggestion: '', improvement_tips: [] });
    } finally {
      setAnalyzing(false);
    }
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ActivityIndicator color={colors.brand} style={{ marginTop: 60 }} />
      </SafeAreaView>
    );
  }

  if (!workout) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
          </TouchableOpacity>
          <Text style={txt.title}>运动详情</Text>
          <View style={{ width: 40 }} />
        </View>
        <Text style={txt.empty}>运动记录不存在</Text>
      </SafeAreaView>
    );
  }

  const dateStr = new Date(workout.start_time).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>{workout.activity_type}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={txt.date}>{dateStr}</Text>

        {/* Key metrics */}
        <View style={styles.metricsRow}>
          <MetricTile label="时长" value={String(workout.duration_minutes)} unit="min"
            icon="time-outline" color={colors.brand} tintColor={colors.brandLight} />
          <MetricTile label="卡路里" value={String(workout.calories ?? '--')} unit="kcal"
            icon="flame-outline" color={metricColors.calories.main} tintColor={metricColors.calories.tint} />
        </View>
        <View style={styles.metricsRow}>
          {workout.avg_heart_rate != null && (
            <MetricTile label="平均心率" value={String(workout.avg_heart_rate)} unit="bpm"
              icon="heart-outline" color={metricColors.heartRate.main} tintColor={metricColors.heartRate.tint} />
          )}
          {workout.distance_km != null && (
            <MetricTile label="距离" value={workout.distance_km.toFixed(2)} unit="km"
              icon="navigate-outline" color={colors.blue} tintColor={colors.tintBlue} />
          )}
        </View>

        {/* Extra details */}
        <HealthCard title="详细指标" icon="analytics-outline" iconColor={colors.brand} iconBg={colors.brandLight}>
          <DetailRow label="最大心率" value={workout.max_heart_rate != null ? `${workout.max_heart_rate} bpm` : '--'} />
          <DetailRow label="有氧训练效果" value={workout.training_effect_aerobic?.toFixed(1) ?? '--'} />
          <DetailRow label="无氧训练效果" value={workout.training_effect_anaerobic?.toFixed(1) ?? '--'} />
          {workout.vo2max != null && <DetailRow label="VO2max" value={workout.vo2max.toFixed(1)} />}
          {workout.steps != null && <DetailRow label="步数" value={String(workout.steps)} />}
        </HealthCard>

        {/* AI analysis */}
        <HealthCard title="AI 分析" icon="sparkles-outline" iconColor={colors.purple} iconBg={colors.tintPurple}
          rightAccessory={
            !analysis && !analyzing ? (
              <TouchableOpacity onPress={handleAnalyze} activeOpacity={0.7}>
                <Text style={txt.analyzeBtn}>分析</Text>
              </TouchableOpacity>
            ) : null
          }>
          {analyzing ? (
            <ActivityIndicator color={colors.purple} />
          ) : analysis ? (
            <View style={{ gap: 8 }}>
              <Text style={txt.analysisText}>{analysis.summary}</Text>
              {analysis.intensity_assessment ? <Text style={txt.analysisText}>{analysis.intensity_assessment}</Text> : null}
              {analysis.recovery_suggestion ? (
                <View style={styles.tipBox}>
                  <Ionicons name="leaf-outline" size={14} color={colors.green} />
                  <Text style={txt.tipText}>{analysis.recovery_suggestion}</Text>
                </View>
              ) : null}
              {analysis.improvement_tips.map((t, i) => (
                <View key={i} style={styles.tipBox}>
                  <Ionicons name="bulb-outline" size={14} color={colors.amber} />
                  <Text style={txt.tipText}>{t}</Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={txt.placeholder}>点击"分析"获取 AI 运动分析</Text>
          )}
        </HealthCard>

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detailRow}>
      <Text style={txt.detailLabel}>{label}</Text>
      <Text style={txt.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  metricsRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  tipBox: { flexDirection: 'row', gap: 6, alignItems: 'flex-start', backgroundColor: colors.bgPrimary, borderRadius: radii.sm, padding: spacing.sm },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  date: { fontSize: 14, color: colors.labelSecondary, marginBottom: spacing.lg } as TextStyle,
  detailLabel: { fontSize: 14, color: colors.labelSecondary } as TextStyle,
  detailValue: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  analyzeBtn: { fontSize: 14, fontWeight: '600', color: colors.purple } as TextStyle,
  analysisText: { fontSize: 14, color: colors.labelPrimary, lineHeight: 21 } as TextStyle,
  tipText: { fontSize: 13, color: colors.labelPrimary, lineHeight: 20, flex: 1 } as TextStyle,
  placeholder: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center', paddingVertical: 12 } as TextStyle,
  empty: { fontSize: 14, color: colors.labelTertiary, textAlign: 'center', marginTop: 40 } as TextStyle,
};
