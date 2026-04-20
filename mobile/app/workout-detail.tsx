import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import MapView, { Polyline as MapPolyline } from 'react-native-maps';
import Markdown from 'react-native-markdown-display';
import { useWorkoutDetail } from '@/hooks/useWorkouts';
import { analyzeWorkout, getPostWorkoutAnalysis, type WorkoutAnalysis, type PostWorkoutAnalysisResponse } from '@/services/workouts';
import MetricTile from '@/components/design-system/MetricTile';
import HealthCard from '@/components/design-system/HealthCard';
import { colors, spacing, radii, metricColors } from '@/constants/theme';

interface RoutePoint { lat: number; lng: number }

function RouteMap({ routeJson, onTouchStart, onTouchEnd }: { routeJson: string; onTouchStart?: () => void; onTouchEnd?: () => void }) {
  const points: RoutePoint[] = useMemo(() => {
    try {
      const parsed = JSON.parse(routeJson);
      if (!Array.isArray(parsed) || parsed.length < 2) return [];
      return parsed.filter((p: any) => p.lat != null && p.lng != null);
    } catch { return []; }
  }, [routeJson]);

  if (points.length < 2) return null;

  const coordinates = points.map(p => ({ latitude: p.lat, longitude: p.lng }));
  const lats = points.map(p => p.lat);
  const lngs = points.map(p => p.lng);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const padLat = (maxLat - minLat) * 0.15 || 0.002;
  const padLng = (maxLng - minLng) * 0.15 || 0.002;

  return (
    <HealthCard title="运动轨迹" icon="map-outline" iconColor={colors.blue} iconBg={colors.tintBlue}>
      <View
        style={{ borderRadius: radii.md, overflow: 'hidden', height: 220 }}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
      >
        <MapView
          style={{ flex: 1 }}
          initialRegion={{
            latitude: (minLat + maxLat) / 2,
            longitude: (minLng + maxLng) / 2,
            latitudeDelta: maxLat - minLat + padLat * 2,
            longitudeDelta: maxLng - minLng + padLng * 2,
          }}
          zoomEnabled rotateEnabled={false} pitchEnabled={false} mapType="standard"
        >
          <MapPolyline coordinates={coordinates} strokeColor={colors.brand} strokeWidth={3} />
        </MapView>
      </View>
    </HealthCard>
  );
}

function formatTime(isoStr: string | null): string | null {
  if (!isoStr) return null;
  try {
    return new Date(isoStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch { return null; }
}

function parseAnalysisJson(raw: string | null): Record<string, any> | null {
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export default function WorkoutDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const workoutId = parseInt(id || '0');
  const { data: workout, isLoading } = useWorkoutDetail(workoutId);

  const [analysis, setAnalysis] = useState<WorkoutAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [postAnalysis, setPostAnalysis] = useState<PostWorkoutAnalysisResponse | null>(null);
  const [postAnalyzing, setPostAnalyzing] = useState(false);
  const [fromCache, setFromCache] = useState(false);
  const [mapActive, setMapActive] = useState(false);

  // Auto-load cached analysis on mount
  useEffect(() => {
    if (!workout || !workoutId) return;

    // 1. Basic analysis from workout.ai_analysis
    if (workout.ai_analysis && !analysis) {
      const parsed = parseAnalysisJson(workout.ai_analysis);
      if (parsed) {
        setAnalysis(parsed as unknown as WorkoutAnalysis);
        setFromCache(true);
      }
    }

    // 2. Post-workout scientific analysis (cache_only)
    if (!postAnalysis) {
      getPostWorkoutAnalysis(workoutId, false, true)
        .then(res => {
          if (res.success) {
            setPostAnalysis(res);
            setFromCache(true);
          }
        })
        .catch(() => {});
    }
  }, [workout?.id]);

  const handleAnalyze = useCallback(async (forceRegenerate = false) => {
    if (!workoutId) return;
    setAnalyzing(true);
    try {
      const res = await analyzeWorkout(workoutId);
      setAnalysis(res);
      setFromCache(false);
    } catch {
      setAnalysis({
        workout_id: workoutId, overall_rating: '', intensity_assessment: '分析暂时不可用',
        heart_rate_analysis: null, hr_zone_assessment: null, pace_analysis: null,
        training_effect_summary: null, recovery_recommendation: '', next_workout_suggestion: '',
        comparison_with_history: null, key_insights: [], improvement_tips: [],
      });
    } finally {
      setAnalyzing(false);
    }
  }, [workoutId]);

  const handlePostAnalysis = useCallback(async (forceRegenerate = false) => {
    if (!workoutId) return;
    setPostAnalyzing(true);
    try {
      const res = await getPostWorkoutAnalysis(workoutId, forceRegenerate, false);
      if (res.success) {
        setPostAnalysis(res);
        setFromCache(!!res.from_cache);
      }
    } catch {} finally {
      setPostAnalyzing(false);
    }
  }, [workoutId]);

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

  const durationMin = workout.duration_seconds ? Math.round(workout.duration_seconds / 60) : 0;
  const distanceKm = workout.distance_meters ? (workout.distance_meters / 1000) : null;
  const dateStr = workout.workout_date
    ? new Date(workout.workout_date).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })
    : '';
  const startStr = formatTime(workout.start_time);
  const endStr = formatTime(workout.end_time);
  const timeRange = startStr && endStr ? `${startStr} - ${endStr}` : startStr || null;

  const hasAnalysis = !!(analysis || postAnalysis);

  // Extract post-analysis markdown content
  const postContent = useMemo(() => {
    if (!postAnalysis) return null;
    const a = postAnalysis as Record<string, any>;
    return a.analysis || a.content || a.markdown || a.summary || null;
  }, [postAnalysis]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>{workout.workout_name || workout.workout_type || '运动'}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false} scrollEnabled={!mapActive}>
        <Text style={txt.date}>{dateStr}</Text>
        {timeRange && <Text style={txt.timeRange}>{timeRange}</Text>}

        {/* Key metrics */}
        <View style={styles.metricsRow}>
          <MetricTile label="时长" value={String(durationMin)} unit="min"
            icon="time-outline" color={colors.brand} tintColor={colors.brandLight} />
          <MetricTile label="卡路里" value={String(workout.calories ?? '--')} unit="kcal"
            icon="flame-outline" color={metricColors.calories.main} tintColor={metricColors.calories.tint} />
        </View>
        <View style={styles.metricsRow}>
          {workout.avg_heart_rate != null && (
            <MetricTile label="平均心率" value={String(workout.avg_heart_rate)} unit="bpm"
              icon="heart-outline" color={metricColors.heartRate.main} tintColor={metricColors.heartRate.tint} />
          )}
          {distanceKm != null && (
            <MetricTile label="距离" value={distanceKm.toFixed(2)} unit="km"
              icon="navigate-outline" color={colors.blue} tintColor={colors.tintBlue} />
          )}
        </View>

        {/* Route map */}
        {workout.route_data && <RouteMap routeJson={workout.route_data} onTouchStart={() => setMapActive(true)} onTouchEnd={() => setMapActive(false)} />}

        {/* Extra details */}
        <HealthCard title="详细指标" icon="analytics-outline" iconColor={colors.brand} iconBg={colors.brandLight}>
          <DetailRow label="最大心率" value={workout.max_heart_rate != null ? `${workout.max_heart_rate} bpm` : '--'} />
          <DetailRow label="有氧训练效果" value={workout.training_effect_aerobic?.toFixed(1) ?? '--'} />
          <DetailRow label="无氧训练效果" value={workout.training_effect_anaerobic?.toFixed(1) ?? '--'} />
          {workout.vo2max != null && <DetailRow label="VO2max" value={workout.vo2max.toFixed(1)} />}
          {workout.steps != null && <DetailRow label="步数" value={String(workout.steps)} />}
        </HealthCard>

        {/* AI Analysis — cached or on-demand */}
        <HealthCard title="AI 分析" icon="sparkles-outline" iconColor={colors.purple} iconBg={colors.tintPurple}
          rightAccessory={
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              {fromCache && hasAnalysis && (
                <View style={styles.cacheBadge}>
                  <Text style={txt.cacheBadgeText}>已保存</Text>
                </View>
              )}
              {!fromCache && hasAnalysis && (
                <View style={[styles.cacheBadge, { backgroundColor: '#E8F0FE' }]}>
                  <Text style={[txt.cacheBadgeText, { color: colors.blue }]}>新生成</Text>
                </View>
              )}
              {hasAnalysis && !analyzing && !postAnalyzing && (
                <TouchableOpacity onPress={() => handleAnalyze(true)} activeOpacity={0.7}>
                  <Text style={txt.reanalyzeBtn}>重新分析</Text>
                </TouchableOpacity>
              )}
              {!hasAnalysis && !analyzing && !postAnalyzing && (
                <TouchableOpacity onPress={() => handlePostAnalysis(false)} activeOpacity={0.7}>
                  <Text style={txt.analyzeBtn}>分析</Text>
                </TouchableOpacity>
              )}
            </View>
          }>
          {(analyzing || postAnalyzing) ? (
            <View style={{ alignItems: 'center', paddingVertical: 16, gap: 8 }}>
              <ActivityIndicator color={colors.purple} />
              <Text style={txt.placeholder}>AI 正在分析运动数据...</Text>
            </View>
          ) : postContent ? (
            <Markdown style={mdStyles}>{postContent}</Markdown>
          ) : analysis ? (
            <View style={{ gap: 8 }}>
              <Text style={txt.analysisText}>{analysis.intensity_assessment}</Text>
              {analysis.heart_rate_analysis ? <Text style={txt.analysisText}>{analysis.heart_rate_analysis}</Text> : null}
              {analysis.training_effect_summary ? <Text style={txt.analysisText}>{analysis.training_effect_summary}</Text> : null}
              {analysis.recovery_recommendation ? (
                <View style={styles.tipBox}>
                  <Ionicons name="leaf-outline" size={14} color={colors.green} />
                  <Text style={txt.tipText}>{analysis.recovery_recommendation}</Text>
                </View>
              ) : null}
              {analysis.next_workout_suggestion ? (
                <View style={styles.tipBox}>
                  <Ionicons name="fitness-outline" size={14} color={colors.brand} />
                  <Text style={txt.tipText}>{analysis.next_workout_suggestion}</Text>
                </View>
              ) : null}
              {(analysis.key_insights || []).map((t, i) => (
                <View key={`insight-${i}`} style={styles.tipBox}>
                  <Ionicons name="sparkles-outline" size={14} color={colors.purple} />
                  <Text style={txt.tipText}>{t}</Text>
                </View>
              ))}
              {(analysis.improvement_tips || []).map((t, i) => (
                <View key={`tip-${i}`} style={styles.tipBox}>
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
  cacheBadge: {
    backgroundColor: '#E8FAF0', borderRadius: radii.full,
    paddingHorizontal: 8, paddingVertical: 2,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  date: { fontSize: 14, color: colors.labelSecondary, marginBottom: 2 } as TextStyle,
  timeRange: { fontSize: 13, color: colors.labelTertiary, marginBottom: spacing.lg, fontVariant: ['tabular-nums'] as const } as TextStyle,
  detailLabel: { fontSize: 14, color: colors.labelSecondary } as TextStyle,
  detailValue: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  analyzeBtn: { fontSize: 14, fontWeight: '600', color: colors.purple } as TextStyle,
  reanalyzeBtn: { fontSize: 13, fontWeight: '500', color: colors.labelTertiary } as TextStyle,
  cacheBadgeText: { fontSize: 11, fontWeight: '500', color: colors.green } as TextStyle,
  analysisText: { fontSize: 14, color: colors.labelPrimary, lineHeight: 21 } as TextStyle,
  tipText: { fontSize: 13, color: colors.labelPrimary, lineHeight: 20, flex: 1 } as TextStyle,
  placeholder: { fontSize: 13, color: colors.labelTertiary, textAlign: 'center', paddingVertical: 12 } as TextStyle,
  empty: { fontSize: 14, color: colors.labelTertiary, textAlign: 'center', marginTop: 40 } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 14, lineHeight: 21, color: colors.labelPrimary },
  heading2: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 8, marginBottom: 4 },
  heading3: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary, marginTop: 6, marginBottom: 2 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 2 },
  list_item: { flexDirection: 'row', marginVertical: 1 },
  paragraph: { marginVertical: 2 },
});
