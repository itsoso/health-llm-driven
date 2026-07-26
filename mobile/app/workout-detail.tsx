import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator, Alert, StatusBar, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import MapView, { Polyline as MapPolyline, Marker } from 'react-native-maps';
import Markdown from 'react-native-markdown-display';
import { prepareSafeMarkdown, safeMarkdownIt } from '../utils/safeMarkdown';
import { useQuery } from '@tanstack/react-query';
import { useWorkoutDetail } from '../hooks/useWorkouts';
import { useWorkoutAutoAnalysis } from '../hooks/useWorkoutAutoAnalysis';
import { getPostWorkoutAnalysis, getWorkoutChart, getWorkoutVoiceCoach, type WorkoutChartData } from '../services/workouts';
import HealthCard from '../components/design-system/HealthCard';
import HeroMetrics from '../components/workout/HeroMetrics';
import HrChart from '../components/workout/HrChart';
import PaceBars from '../components/workout/PaceBars';
import HrZoneBar from '../components/workout/HrZoneBar';
import { synthesize as cloudSynthesize } from '../services/cloudTts';
import { getVoiceStyle, loadVoiceStyle } from '../services/voiceStyle';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { sharePlainText } from '../utils/share';
import { createWorkoutDetailAgentContext, pushChatWithContext } from '../utils/agentContext';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaFonts,
} from '../constants/revaTheme';

// 详细指标的类目装饰色(区分"哪个指标",非"好坏"):各指标一个 hue + tint。
const HUES = {
  red: { fg: '#D5503A', bg: '#F7E4E0' },
  orange: { fg: '#C97A2E', bg: '#F6E9DA' },
  teal: { fg: '#2F9E8F', bg: '#E0EFEC' },
  green: { fg: C.green500, bg: C.green50 },
  blue: { fg: C.blue500, bg: C.blue50 },
  amber: { fg: '#C98A1E', bg: '#F6ECD9' },
  purple: { fg: '#7C5CBF', bg: '#EDE7F6' },
} as const;

interface RoutePoint { lat: number; lng: number; time?: number }

function parseRoutePoints(raw: string | null): RoutePoint[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((p: any) => p && p.lat != null && p.lng != null);
  } catch { return []; }
}

/** 速度渐变轨迹: 按 pace_timeline 把路径分 N 段, 每段一个 Polyline, 颜色按配速. */
function RouteMap({
  routeJson,
  paceTimeline,
  onTouchStart, onTouchEnd,
}: {
  routeJson: string;
  paceTimeline?: { time: number; pace: number }[] | null;
  onTouchStart?: () => void;
  onTouchEnd?: () => void;
}) {
  const points = useMemo(() => parseRoutePoints(routeJson), [routeJson]);

  // 速度渐变分段: 把 points 切成 ~20 段, 用 pace_timeline 对每段取平均配速
  const coloredSegments = useMemo(() => {
    const coords = points.map(p => ({ latitude: p.lat, longitude: p.lng }));
    if (!paceTimeline || paceTimeline.length < 2 || !points[0]?.time) {
      return [{ coords, color: C.green500 }];
    }
    const paces = paceTimeline.map(p => p.pace);
    const minPace = Math.min(...paces);
    const maxPace = Math.max(...paces);
    const range = Math.max(10, maxPace - minPace);
    const barColor = (pace: number) => {
      const ratio = (pace - minPace) / range;
      if (ratio < 0.33) return '#4CAF50';
      if (ratio < 0.66) return '#FFB84D';
      return '#FF7043';
    };

    const nSeg = Math.min(24, Math.max(6, Math.floor(points.length / 10)));
    const pointsPerSeg = Math.max(2, Math.floor(points.length / nSeg));
    const segs: { coords: { latitude: number; longitude: number }[]; color: string }[] = [];
    for (let i = 0; i < points.length - 1; i += pointsPerSeg) {
      const end = Math.min(points.length, i + pointsPerSeg + 1);
      const slice = coords.slice(i, end);
      if (slice.length < 2) continue;
      const segStartTime = points[i].time || 0;
      const segEndTime = points[Math.min(points.length - 1, end - 1)].time || 0;
      const inRange = paceTimeline.filter(pt => pt.time >= segStartTime && pt.time <= segEndTime);
      const avgPace = inRange.length > 0
        ? inRange.reduce((s, p) => s + p.pace, 0) / inRange.length
        : (minPace + maxPace) / 2;
      segs.push({ coords: slice, color: barColor(avgPace) });
    }
    return segs.length > 0 ? segs : [{ coords, color: C.green500 }];
  }, [points, paceTimeline]);

  if (points.length < 2) return null;

  const lats = points.map(p => p.lat);
  const lngs = points.map(p => p.lng);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const padLat = (maxLat - minLat) * 0.15 || 0.002;
  const padLng = (maxLng - minLng) * 0.15 || 0.002;

  return (
    <HealthCard title="运动轨迹" icon="map-outline" iconColor={C.blue500} iconBg={C.blue50}>
      <View
        style={{ borderRadius: revaRadii.md, overflow: 'hidden', height: 220 }}
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
          {coloredSegments.map((s, i) => (
            <MapPolyline key={i} coordinates={s.coords} strokeColor={s.color} strokeWidth={4} />
          ))}
          <Marker coordinate={{ latitude: points[0].lat, longitude: points[0].lng }}>
            <View style={markerStyles.start}><Text style={markerStyles.startLabel}>起</Text></View>
          </Marker>
          <Marker coordinate={{ latitude: points[points.length - 1].lat, longitude: points[points.length - 1].lng }}>
            <View style={markerStyles.end}><Text style={markerStyles.endLabel}>终</Text></View>
          </Marker>
        </MapView>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 12, marginTop: 8 }}>
        <LegendDot color="#4CAF50" label="快" />
        <LegendDot color="#FFB84D" label="中" />
        <LegendDot color="#FF7043" label="慢" />
      </View>
    </HealthCard>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <View style={{ width: 10, height: 3, borderRadius: 2, backgroundColor: color }} />
      <Text style={{ fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 }}>{label}</Text>
    </View>
  );
}

const markerStyles = StyleSheet.create({
  start: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: '#4CAF50', borderWidth: 2, borderColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
  },
  end: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: '#FF5252', borderWidth: 2, borderColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
  },
  startLabel: { color: '#fff', fontSize: 10, fontWeight: '700' },
  endLabel: { color: '#fff', fontSize: 10, fontWeight: '700' },
});

function formatTime(isoStr: string | null): string | null {
  if (!isoStr) return null;
  try {
    return new Date(isoStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch { return null; }
}

const WORKOUT_TYPE_LABEL: Record<string, string> = {
  running: '跑步',
  cycling: '骑行',
  walking: '步行',
  swimming: '游泳',
  yoga: '瑜伽',
  strength_training: '力量',
  hiit: 'HIIT',
};

export default function WorkoutDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const workoutId = parseInt(id || '0');
  const { data: workout, isLoading } = useWorkoutDetail(workoutId);

  // Chart data — 心率/配速/海拔时序
  const { data: chart } = useQuery<WorkoutChartData>({
    queryKey: ['workout-chart', workoutId],
    queryFn: () => getWorkoutChart(workoutId),
    enabled: !!workoutId,
    staleTime: 300_000,
  });

  const [postAnalyzing, setPostAnalyzing] = useState(false);
  const [mapActive, setMapActive] = useState(false);
  const {
    analysis,
    postAnalysis,
    setPostAnalysis,
    fromCache,
    setFromCache,
  } = useWorkoutAutoAnalysis({ workoutId, workout });

  const handlePostAnalysis = useCallback(async (forceRegenerate = false) => {
    if (!workoutId) return;
    setPostAnalyzing(true);
    try {
      const res = await getPostWorkoutAnalysis(workoutId, forceRegenerate, false);
      if (res.success) {
        setPostAnalysis(res);
        setFromCache(!!res.from_cache);
      } else {
        // 后端返回 success:false 时也让用户知道
        const msg = (res as any)?.message || (res as any)?.error || '分析生成失败，请稍后重试';
        Alert.alert('分析失败', String(msg));
      }
    } catch (e: any) {
      if (__DEV__) console.warn('[workout-detail] post-analysis error', e);
      const msg = e?.response?.data?.detail || e?.message || '网络异常，请稍后重试';
      Alert.alert('分析失败', String(msg));
    } finally {
      setPostAnalyzing(false);
    }
  }, [setFromCache, setPostAnalysis, workoutId]);

  // '听一下'按钮 — 私享女声读 150-200 字教练短稿
  const [speaking, setSpeaking] = useState(false);
  const playerRef = React.useRef<ReturnType<typeof createAudioPlayer> | null>(null);
  const finishPlaybackRef = React.useRef<(() => void) | null>(null);
  const handleSpeakCoach = useCallback(async () => {
    if (!workoutId || speaking) return;
    setSpeaking(true);
    try {
      // 确保音频走外放 — 不是从 voice-chat 进来, session 可能还在 recording mode
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording: false,
      }).catch(() => {});

      const { script } = await getWorkoutVoiceCoach(workoutId);
      if (!script || !script.trim()) {
        Alert.alert('暂无可播报的内容', '等 AI 分析完成后再来听');
        return;
      }
      const styleKey = await loadVoiceStyle();
      const voiceKey = getVoiceStyle(styleKey).cloudVoiceKey ?? 'cloned_private_female';
      const { localUri } = await cloudSynthesize({ text: script, voiceKey });
      const player = createAudioPlayer({ uri: localUri });
      playerRef.current = player;
      await new Promise<void>((resolve) => {
        let finished = false;
        let timeout: ReturnType<typeof setTimeout> | null = null;
        const finish = () => {
          if (finished) return;
          finished = true;
          if (timeout) clearTimeout(timeout);
          timeout = null;
          try { player.remove(); } catch {}
          playerRef.current = null;
          finishPlaybackRef.current = null;
          resolve();
        };
        finishPlaybackRef.current = finish;
        const sub = player.addListener('playbackStatusUpdate', (status: any) => {
          if (status?.didJustFinish || status?.finished) {
            sub?.remove?.();
            finish();
          }
        });
        // 兜底 30s 硬超时
        timeout = setTimeout(() => { if (!finished) { try { sub?.remove?.(); } catch {}; finish(); } }, 30000);
        player.play();
      });
    } catch (e: any) {
      if (__DEV__) console.warn('[workout-detail] voice-coach error', e);
      Alert.alert('播报失败', e?.message || '网络异常');
    } finally {
      setSpeaking(false);
    }
  }, [workoutId, speaking]);

  // 退出页面确保停止播放, 避免后台继续念
  useEffect(() => {
    return () => {
      finishPlaybackRef.current?.();
      try { playerRef.current?.pause(); playerRef.current?.remove(); } catch {}
      playerRef.current = null;
    };
  }, []);

  // 分享: RN 内置 Share, 拉教练短稿 + 数据拼一段文字 (微信粘贴)
  // 截屏图片分享走下一个 build (需要 react-native-view-shot)
  const handleShare = useCallback(async () => {
    if (!workoutId) return;
    try {
      // 拉短稿 (复用 voice-coach 那 67 字)
      const { script } = await getWorkoutVoiceCoach(workoutId).catch(() => ({ script: '' } as any));
      const w = workout;
      const bits: string[] = [];
      if (w?.workout_type) bits.push(w.workout_type === 'running' ? '🏃 跑步' : `🏋 ${w.workout_type}`);
      if (w?.distance_meters) bits.push(`${(w.distance_meters / 1000).toFixed(1)} km`);
      if (w?.duration_seconds) bits.push(`${Math.round(w.duration_seconds / 60)} 分钟`);
      if (w?.avg_pace_seconds_per_km) {
        const m = Math.floor(w.avg_pace_seconds_per_km / 60);
        const s = w.avg_pace_seconds_per_km % 60;
        bits.push(`配速 ${m}'${String(s).padStart(2, '0')}"/km`);
      }
      if (w?.avg_heart_rate) bits.push(`平均心率 ${w.avg_heart_rate}`);
      const summary = bits.join(' · ');
      const text = [
        summary,
        script ? `\n${script}` : '',
        '\n— 小巴',
      ].filter(Boolean).join('');
      await sharePlainText({ title: '运动记录', message: text });
    } catch (e: any) {
      Alert.alert('分享失败', e?.message || '请稍后重试');
    }
  }, [workoutId, workout]);

  const postContent = useMemo(() => {
    if (!postAnalysis) return null;
    const a = postAnalysis as Record<string, any>;

    // 老格式 fallback (markdown / content / summary 字段)
    const direct = a.analysis || a.content || a.markdown || a.summary;
    if (typeof direct === 'string' && direct.trim()) return direct;

    // 新格式 — 后端返回结构化对象, 拼成 markdown 给 react-native-markdown-display 渲染
    const lines: string[] = [];

    if (a.overall_rating) {
      const o = a.overall_rating;
      lines.push(`## ${o.emoji || '⭐'} 总评 — ${o.rating || ''} (${o.score ?? '-'} / 10)`);
      if (o.message) lines.push(o.message);
      lines.push('');
    }

    if (a.intensity_assessment) {
      const i = a.intensity_assessment;
      lines.push(`### ${i.emoji || '💪'} 强度评估: ${i.level || i.intensity || ''}`);
      if (Array.isArray(i.factors) && i.factors.length) {
        for (const f of i.factors) lines.push(`- ${f}`);
      }
      lines.push('');
    }

    if (a.hr_analysis?.zones) {
      lines.push('### ❤️ 心率区间分布');
      const zones = a.hr_analysis.zones as Record<string, any>;
      for (const key of Object.keys(zones)) {
        const z = zones[key];
        if (z?.percentage > 0) {
          lines.push(`- ${z.name}: ${z.percentage.toFixed(1)}%`);
        }
      }
      lines.push('');
    }

    if (Array.isArray(a.recovery_tips) && a.recovery_tips.length) {
      lines.push('### 🌿 恢复建议');
      for (const t of a.recovery_tips) lines.push(`- ${t}`);
      lines.push('');
    }

    if (Array.isArray(a.improvement_tips) && a.improvement_tips.length) {
      lines.push('### 📈 改进建议');
      for (const t of a.improvement_tips) lines.push(`- ${t}`);
      lines.push('');
    }

    if (Array.isArray(a.knowledge_points) && a.knowledge_points.length) {
      lines.push('### 💡 知识点');
      for (const k of a.knowledge_points) {
        if (typeof k === 'string') lines.push(`- ${k}`);
        else if (k?.title) lines.push(`- **${k.title}**: ${k.content || ''}`);
      }
      lines.push('');
    }

    const md = lines.join('\n').trim();
    return md || null;
  }, [postAnalysis]);

  const workoutTypeLabelForAgent = workout
    ? WORKOUT_TYPE_LABEL[workout.workout_type] || workout.workout_type || '运动'
    : '运动';
  const agentBadge = workout
    ? [
        `本次${workoutTypeLabelForAgent}`,
        workout.distance_meters != null ? `${(workout.distance_meters / 1000).toFixed(1)}km` : null,
        workout.duration_seconds != null ? `${Math.round(workout.duration_seconds / 60)}min` : null,
      ].filter(Boolean).join(' · ')
    : '本次运动';

  const handleChatWorkoutReview = useCallback(() => {
    if (!workout) return;
    pushChatWithContext(router, {
      prompt: `请基于这次${workoutTypeLabelForAgent}做一次运动复盘: 总结表现和风险, 给出跑后拉伸/恢复建议, 并安排下一次训练。最后请指出你还需要我反馈哪些体感信息。`,
      context: createWorkoutDetailAgentContext({
        workout,
        chart,
        analysis,
        postAnalysis,
        postAnalysisMarkdown: postContent,
      }),
      badge: agentBadge,
    });
  }, [agentBadge, analysis, chart, postAnalysis, postContent, router, workout, workoutTypeLabelForAgent]);

  if (isLoading) {
    return (
      <SafeAreaView style={S.safe} edges={['top']}>
        <StatusBar barStyle="dark-content" backgroundColor={C.paper} translucent={false} />
        <ActivityIndicator color={C.green500} style={{ marginTop: 60 }} />
      </SafeAreaView>
    );
  }

  if (!workout) {
    return (
      <SafeAreaView style={S.safe} edges={['top']}>
        <StatusBar barStyle="dark-content" backgroundColor={C.paper} translucent={false} />
        <View style={S.header}>
          <TouchableOpacity onPress={() => router.back()} style={S.backBtn}>
            <Ionicons name="chevron-back" size={24} color={C.ink1} />
          </TouchableOpacity>
          <Text style={T.title}>运动详情</Text>
          <View style={{ width: 40 }} />
        </View>
        <Text style={T.empty}>运动记录不存在</Text>
      </SafeAreaView>
    );
  }

  const durationMin = workout.duration_seconds ? Math.round(workout.duration_seconds / 60) : 0;
  const distanceKm = workout.distance_meters ? (workout.distance_meters / 1000) : null;
  const dateStr = workout.workout_date
    ? new Date(workout.workout_date).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })
    : '';
  const startStr = formatTime(workout.start_time);
  const endStr = formatTime(workout.end_time);
  const timeRange = startStr && endStr ? `${startStr} - ${endStr}` : startStr || null;

  const avgPaceDisplay = chart?.avg_pace_display || null;
  const workoutTypeLabel = WORKOUT_TYPE_LABEL[workout.workout_type] || workout.workout_type || '运动';

  const hasAnalysis = !!(analysis || postAnalysis);

  return (
    <SafeAreaView style={S.safe} edges={['top']}>
      <StatusBar barStyle="dark-content" backgroundColor={C.paper} translucent={false} />
      <View style={S.header}>
        <TouchableOpacity onPress={() => router.back()} style={S.backBtn} hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </TouchableOpacity>
        <Text style={T.title} numberOfLines={1}>{workout.workout_name || workoutTypeLabel}</Text>
        <TouchableOpacity onPress={handleShare} style={S.backBtn} hitSlop={8} accessibilityLabel="分享">
          <Ionicons name="share-outline" size={22} color={C.ink1} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={S.content} showsVerticalScrollIndicator={false} scrollEnabled={!mapActive}>
        <HeroMetrics
          distanceKm={distanceKm}
          durationMin={durationMin}
          avgPaceDisplay={avgPaceDisplay}
          avgHr={workout.avg_heart_rate ?? null}
          workoutTypeLabel={workoutTypeLabel}
          dateLabel={dateStr + (timeRange ? ` · ${timeRange}` : '')}
        />

        {/* HR 曲线 */}
        {chart?.heart_rate_timeline && chart.heart_rate_timeline.length > 1 && (
          <HealthCard title="心率变化" icon="heart-outline" iconColor="#FF5252" iconBg="#FFE5E5">
            <HrChart
              samples={chart.heart_rate_timeline}
              hrMax={chart.max_heart_rate || workout.max_heart_rate}
            />
          </HealthCard>
        )}

        {/* HR zones */}
        {chart?.heart_rate_zones && chart.heart_rate_zones.length > 0 && (
          <HealthCard title="心率区间" icon="stats-chart-outline" iconColor={C.green500} iconBg={C.green50}>
            <HrZoneBar zones={chart.heart_rate_zones} />
          </HealthCard>
        )}

        {/* 配速分段 */}
        {chart?.pace_timeline && chart.pace_timeline.length > 1 && distanceKm && distanceKm >= 1 && (
          <HealthCard title="公里配速" icon="speedometer-outline" iconColor={HUES.purple.fg} iconBg={HUES.purple.bg}>
            <PaceBars
              paceTimeline={chart.pace_timeline}
              totalDistanceKm={distanceKm}
              durationSec={workout.duration_seconds || null}
            />
          </HealthCard>
        )}

        {/* Route */}
        {workout.route_data && (
          <RouteMap
            routeJson={workout.route_data}
            paceTimeline={chart?.pace_timeline || null}
            onTouchStart={() => setMapActive(true)}
            onTouchEnd={() => setMapActive(false)}
          />
        )}

        {/* 详细指标 — 2 列 grid, 有数据才展示 chip, 全空 fallback 提示 */}
        <HealthCard title="详细指标" icon="analytics-outline" iconColor={C.green500} iconBg={C.green50}>
          {(() => {
            const metrics: { label: string; value: string; icon: keyof typeof Ionicons.glyphMap; color: string; bg: string }[] = [];
            if (workout.calories != null) metrics.push({ label: '卡路里', value: `${workout.calories}`, icon: 'flame-outline', color: HUES.red.fg, bg: HUES.red.bg });
            if (workout.max_heart_rate != null) metrics.push({ label: '最大心率', value: `${workout.max_heart_rate} bpm`, icon: 'heart-outline', color: '#FF5252', bg: '#FFE5E5' });
            if (workout.avg_cadence != null) metrics.push({ label: '平均步频', value: `${workout.avg_cadence} spm`, icon: 'walk-outline', color: HUES.orange.fg, bg: HUES.orange.bg });
            if (workout.avg_stride_length_cm != null) metrics.push({ label: '平均步幅', value: `${workout.avg_stride_length_cm.toFixed(0)} cm`, icon: 'resize-outline', color: HUES.teal.fg, bg: HUES.teal.bg });
            if (workout.elevation_gain_meters != null) metrics.push({ label: '累计爬升', value: `${workout.elevation_gain_meters.toFixed(0)} m`, icon: 'trending-up-outline', color: HUES.green.fg, bg: HUES.green.bg });
            if (workout.training_effect_aerobic != null) metrics.push({ label: '有氧训练', value: workout.training_effect_aerobic.toFixed(1), icon: 'pulse-outline', color: HUES.blue.fg, bg: HUES.blue.bg });
            if (workout.training_effect_anaerobic != null) metrics.push({ label: '无氧训练', value: workout.training_effect_anaerobic.toFixed(1), icon: 'flash-outline', color: HUES.amber.fg, bg: HUES.amber.bg });
            if (workout.vo2max != null) metrics.push({ label: 'VO2max', value: workout.vo2max.toFixed(1), icon: 'fitness-outline', color: HUES.purple.fg, bg: HUES.purple.bg });
            if (workout.training_load != null) metrics.push({ label: '训练负荷', value: String(workout.training_load), icon: 'barbell-outline', color: HUES.green.fg, bg: HUES.green.bg });
            if (workout.steps != null) metrics.push({ label: '步数', value: String(workout.steps), icon: 'footsteps-outline', color: HUES.orange.fg, bg: HUES.orange.bg });

            if (metrics.length === 0) {
              return (
                <View style={S.emptyMetrics}>
                  <Ionicons name="information-circle-outline" size={24} color={C.ink3} />
                  <Text style={T.placeholder}>这次运动没有记录额外指标</Text>
                </View>
              );
            }
            return (
              <View style={S.metricGrid}>
                {metrics.map((m, idx) => (
                  <View key={idx} style={S.metricChip}>
                    <View style={[S.metricIcon, { backgroundColor: m.bg }]}>
                      <Ionicons name={m.icon} size={14} color={m.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={T.metricLabel} numberOfLines={1}>{m.label}</Text>
                      <Text style={T.metricValue} numberOfLines={1}>{m.value}</Text>
                    </View>
                  </View>
                ))}
              </View>
            );
          })()}
        </HealthCard>

        {/* AI Analysis */}
        <HealthCard
          title="AI 分析"
          icon="sparkles-outline"
          iconColor={HUES.purple.fg}
          iconBg={HUES.purple.bg}
          rightAccessory={
            // 只放一个 badge, 按钮移到内容上方 toolbar (避免 header 过挤)
            hasAnalysis ? (
              <View style={[S.cacheBadge, fromCache ? null : { backgroundColor: C.blue50 }]}>
                <Text style={[T.cacheBadgeText, fromCache ? null : { color: C.blue500 }]}>
                  {fromCache ? '已保存' : '新生成'}
                </Text>
              </View>
            ) : null
          }
        >
          {/* 操作工具条 — 横向 scroll, 防按钮挤压标题 */}
          {(hasAnalysis || !postAnalyzing) && (
            <View style={S.aiToolbar}>
              <TouchableOpacity
                onPress={handleChatWorkoutReview}
                activeOpacity={0.75}
                style={[S.aiToolBtn, S.agentReviewBtn]}
                accessibilityRole="button"
                accessibilityLabel="跟小巴复盘本次运动"
              >
                <Ionicons name="chatbubble-ellipses-outline" size={15} color={C.green500} />
                <Text style={[T.agentReviewBtn, { marginLeft: 4 }]}>跟小巴复盘这次</Text>
              </TouchableOpacity>
              {hasAnalysis && !postAnalyzing && (
                <TouchableOpacity
                  onPress={handleSpeakCoach}
                  activeOpacity={0.7}
                  disabled={speaking}
                  style={S.aiToolBtn}
                >
                  {speaking ? (
                    <ActivityIndicator size="small" color={HUES.purple.fg} />
                  ) : (
                    <Ionicons name="volume-high-outline" size={15} color={HUES.purple.fg} />
                  )}
                  <Text style={[T.reanalyzeBtn, { marginLeft: 4 }]}>
                    {speaking ? '播报中' : '听一下'}
                  </Text>
                </TouchableOpacity>
              )}
              {hasAnalysis && !postAnalyzing && (
                <TouchableOpacity
                  onPress={() => handlePostAnalysis(true)}
                  activeOpacity={0.7}
                  style={S.aiToolBtn}
                >
                  <Ionicons name="refresh-outline" size={15} color={C.green500} />
                  <Text style={[T.reanalyzeBtn, { marginLeft: 4 }]}>重新分析</Text>
                </TouchableOpacity>
              )}
              {!hasAnalysis && !postAnalyzing && (
                <TouchableOpacity
                  onPress={() => handlePostAnalysis(false)}
                  activeOpacity={0.7}
                  style={[S.aiToolBtn, { backgroundColor: C.green50 }]}
                >
                  <Ionicons name="sparkles-outline" size={15} color={C.green500} />
                  <Text style={[T.analyzeBtn, { marginLeft: 4 }]}>开始分析</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          {postAnalyzing ? (
            <View style={{ alignItems: 'center', paddingVertical: 16, gap: 8 }}>
              <ActivityIndicator color={HUES.purple.fg} />
              <Text style={T.placeholder}>AI 正在分析运动数据...</Text>
            </View>
          ) : postContent ? (
            <Markdown style={MD} markdownit={safeMarkdownIt}>{prepareSafeMarkdown(postContent)}</Markdown>
          ) : analysis ? (
            <View style={{ gap: 8 }}>
              <Text style={T.analysisText}>{analysis.intensity_assessment}</Text>
              {analysis.heart_rate_analysis ? <Text style={T.analysisText}>{analysis.heart_rate_analysis}</Text> : null}
              {analysis.training_effect_summary ? <Text style={T.analysisText}>{analysis.training_effect_summary}</Text> : null}
              {analysis.recovery_recommendation ? (
                <View style={S.tipBox}>
                  <Ionicons name="leaf-outline" size={14} color={C.green500} />
                  <Text style={T.tipText}>{analysis.recovery_recommendation}</Text>
                </View>
              ) : null}
              {analysis.next_workout_suggestion ? (
                <View style={S.tipBox}>
                  <Ionicons name="fitness-outline" size={14} color={C.green500} />
                  <Text style={T.tipText}>{analysis.next_workout_suggestion}</Text>
                </View>
              ) : null}
              {(analysis.key_insights || []).map((t, i) => (
                <View key={`insight-${i}`} style={S.tipBox}>
                  <Ionicons name="sparkles-outline" size={14} color={HUES.purple.fg} />
                  <Text style={T.tipText}>{t}</Text>
                </View>
              ))}
              {(analysis.improvement_tips || []).map((t, i) => (
                <View key={`tip-${i}`} style={S.tipBox}>
                  <Ionicons name="bulb-outline" size={14} color={HUES.amber.fg} />
                  <Text style={T.tipText}>{t}</Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={T.placeholder}>点击"分析"获取 AI 运动分析</Text>
          )}
        </HealthCard>

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={S.detailRow}>
      <Text style={T.detailLabel}>{label}</Text>
      <Text style={T.detailValue}>{value}</Text>
    </View>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-md / 指标值走等宽 mono。
const S = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s2,
    // 顶部多垫一点, 让 status bar 时间和 back 按钮不挤在一起
    paddingTop: Platform.OS === 'ios' ? 4 : revaSpacing.s2,
    backgroundColor: C.paper,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: revaSpacing.s4 },
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line,
  },
  // 详细指标 2 列 grid
  metricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: revaSpacing.s2,
  },
  metricChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    // (100% - gap) / 2 — flex: '48%' 在 RN 上不稳, 直接 minWidth
    flexBasis: '48%',
    flexGrow: 1,
    backgroundColor: C.paper2,
    borderRadius: revaRadii.md,
    paddingHorizontal: 10,
    paddingVertical: 10,
    minHeight: 52,
  },
  metricIcon: {
    width: 32, height: 32, borderRadius: revaRadii.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  emptyMetrics: {
    alignItems: 'center',
    paddingVertical: revaSpacing.s4,
    gap: 6,
  },
  tipBox: { flexDirection: 'row', gap: 6, alignItems: 'flex-start', backgroundColor: C.paper2, borderRadius: revaRadii.sm, padding: revaSpacing.s2 },
  cacheBadge: {
    backgroundColor: C.green50, borderRadius: revaRadii.pill,
    paddingHorizontal: 8, paddingVertical: 2,
  },
  aiToolbar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingBottom: revaSpacing.s2,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
    marginBottom: revaSpacing.s2,
  },
  aiToolBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
  },
  agentReviewBtn: {
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green500,
  },
});

// 指标值走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const T = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1, textAlign: 'center' } as TextStyle,
  detailLabel: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink2 } as TextStyle,
  detailValue: { fontFamily: revaFonts.mono, fontSize: 14, fontWeight: '600', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  metricLabel: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginBottom: 2 } as TextStyle,
  metricValue: { fontFamily: revaFonts.mono, fontSize: 14, fontWeight: '700', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  analyzeBtn: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: HUES.purple.fg } as TextStyle,
  agentReviewBtn: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.green500 } as TextStyle,
  reanalyzeBtn: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '500', color: C.ink3 } as TextStyle,
  cacheBadgeText: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '500', color: C.green500 } as TextStyle,
  analysisText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink1, lineHeight: 21 } as TextStyle,
  tipText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1, lineHeight: 20, flex: 1 } as TextStyle,
  placeholder: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink3, textAlign: 'center', paddingVertical: 12 } as TextStyle,
  empty: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3, textAlign: 'center', marginTop: 40 } as TextStyle,
};

// Markdown 样式(AI 分析渲染)—— 走 Reva sans / ink。
const MD = StyleSheet.create({
  body: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 21, color: C.ink1 },
  heading2: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '600', color: C.ink1, marginTop: 8, marginBottom: 4 },
  heading3: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.ink1, marginTop: 6, marginBottom: 2 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 2 },
  list_item: { flexDirection: 'row', marginVertical: 1 },
  paragraph: { marginVertical: 2 },
});
