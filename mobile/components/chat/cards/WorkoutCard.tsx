import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { colors } from '@/constants/theme';
import type { CardSpec } from './types';

interface WorkoutData {
  activity_type?: string;
  duration_min?: number;
  distance_km?: number;
  calories?: number;
  avg_hr?: number;
  max_hr?: number;
  avg_pace?: string;
  steps?: number;
}

function Stat({ icon, color, label, value }: { icon: string; color: string; label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon as any} size={12} color={color} />
      <Text style={txt.statLabel}>{label}</Text>
      <Text style={[txt.statVal, { color }]}>{value}</Text>
    </View>
  );
}

export function WorkoutCardView(d: WorkoutData) {
  const title = d.activity_type ? `${d.activity_type}分析` : '运动分析';
  return (
    <CardShell icon="fitness" iconColor="#FF375F" title={title} bg="#FFF5F5">
      <View style={styles.grid}>
        {d.duration_min != null && <Stat icon="time-outline" color="#0A8F8F" label="时长" value={`${d.duration_min}min`} />}
        {d.distance_km != null && <Stat icon="navigate-outline" color="#64D2FF" label="距离" value={`${d.distance_km.toFixed(2)}km`} />}
        {d.calories != null && <Stat icon="flame-outline" color="#FF6723" label="消耗" value={`${d.calories}kcal`} />}
        {d.avg_hr != null && <Stat icon="heart-outline" color="#FF375F" label="均心率" value={`${d.avg_hr}bpm`} />}
        {d.max_hr != null && <Stat icon="heart" color="#FF453A" label="最大心率" value={`${d.max_hr}bpm`} />}
        {d.avg_pace && <Stat icon="speedometer-outline" color="#BF5AF2" label="配速" value={d.avg_pace} />}
        {d.steps != null && <Stat icon="footsteps-outline" color="#FF9F0A" label="步数" value={d.steps.toLocaleString()} />}
      </View>
    </CardShell>
  );
}

export const WorkoutCardSpec: CardSpec<WorkoutData> = {
  type: 'workout',
  label: '运动分析',
  match({ query_lower }) {
    if (/记录|打卡/.test(query_lower)) return null;
    if (/跑步|运动|锻炼|健身|训练|跑了|游泳|骑行|骑车|hiking|workout/.test(query_lower)) return 20;
    if (/配速|心率区间|有氧|无氧|训练效果|卡路里消耗/.test(query_lower)) return 15;
    return null;
  },
  async build({ data, api: apiClient }) {
    const g = data.garmin;
    const cardData: WorkoutData = {};

    try {
      const { data: workouts } = await apiClient.get('/workout/me', { params: { limit: 1 } });
      if (Array.isArray(workouts) && workouts.length > 0) {
        const w = workouts[0];
        cardData.activity_type = w.workout_name || w.workout_type;
        if (w.duration_seconds) cardData.duration_min = Math.round(w.duration_seconds / 60);
        if (w.distance_meters) cardData.distance_km = w.distance_meters / 1000;
        if (w.calories) cardData.calories = w.calories;
        if (w.avg_heart_rate) cardData.avg_hr = w.avg_heart_rate;
        if (w.max_heart_rate) cardData.max_hr = w.max_heart_rate;
        if (w.steps) cardData.steps = w.steps;
        if (w.distance_meters && w.duration_seconds) {
          const distKm = w.distance_meters / 1000;
          const durMin = w.duration_seconds / 60;
          const paceMin = durMin / distKm;
          const m = Math.floor(paceMin);
          const s = Math.round((paceMin - m) * 60);
          cardData.avg_pace = `${m}'${String(s).padStart(2, '0')}"/km`;
        }
        return cardData;
      }
    } catch {}

    // Fallback: use garmin daily data
    if (g) {
      if (g.active_minutes) cardData.duration_min = g.active_minutes;
      if (g.active_calories) cardData.calories = g.active_calories;
      if (g.steps) cardData.steps = g.steps;
      if (Object.keys(cardData).length > 0) return cardData;
    }

    return null;
  },
  render: (d) => <WorkoutCardView {...d} />,
};

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  stat: { alignItems: 'center', gap: 2, minWidth: 60 },
});

const txt = {
  statLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  statVal: { fontSize: 14, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
};
