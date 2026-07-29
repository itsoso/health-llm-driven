import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { EvidenceRefsRow } from './EvidenceRefsRow';
import type { EvidenceRef } from './EvidenceRefsRow';
import { revaColors as C, revaFonts, revaRadii } from '../../../constants/revaTheme';
import type { CardSpec } from './types';
import { formatLocalDate } from '../../../utils/dietDate';

interface WorkoutData {
  activity_type?: string;
  workout_date?: string;  // YYYY-MM-DD, 显示在卡片顶部, 让"什么时候的运动"一目了然
  duration_min?: number;
  distance_km?: number;
  calories?: number;
  avg_hr?: number;
  max_hr?: number;
  avg_pace?: string;
  steps?: number;
  evidence_refs?: EvidenceRef[];
}

/**
 * 从 query 里抽取时间窗口. 命中"昨天/前天/今天/上周/本周/最近 X 天"时返回日期范围,
 * 没命中返回 null (= 用户问"最近"或泛化, 可兜底拉 latest).
 *
 * 关键: 如果命中了时间词但按该范围拉不到运动 → build 返回 null, 不渲染卡片.
 * 避免 "昨天没有运动数据" 的 LLM 回答下面并排一张前几天运动卡片 (badcase 2026-05-08).
 */
function parseDateWindow(q: string): { start: string; end: string } | null {
  const today = new Date();
  const toYMD = formatLocalDate;
  const shift = (d: Date, n: number) => { const nd = new Date(d); nd.setDate(d.getDate() + n); return nd; };

  if (/今天|今日/.test(q)) {
    const s = toYMD(today);
    return { start: s, end: s };
  }
  if (/昨天|昨日/.test(q)) {
    const s = toYMD(shift(today, -1));
    return { start: s, end: s };
  }
  if (/前天/.test(q)) {
    const s = toYMD(shift(today, -2));
    return { start: s, end: s };
  }
  if (/大前天/.test(q)) {
    const s = toYMD(shift(today, -3));
    return { start: s, end: s };
  }
  if (/本周|这周/.test(q)) {
    const day = today.getDay() || 7;
    return { start: toYMD(shift(today, -(day - 1))), end: toYMD(today) };
  }
  if (/上周|上礼拜/.test(q)) {
    const day = today.getDay() || 7;
    return { start: toYMD(shift(today, -(day - 1 + 7))), end: toYMD(shift(today, -day)) };
  }
  const m = q.match(/最近\s*(\d+)\s*天/);
  if (m) {
    const n = Math.max(1, Math.min(90, Number(m[1])));
    return { start: toYMD(shift(today, -(n - 1))), end: toYMD(today) };
  }
  return null;
}

function Stat({
  icon, label, value,
}: { icon: string; label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <View style={styles.statHeader}>
        <Ionicons name={icon as any} size={12} color={C.green500} />
        <Text maxFontSizeMultiplier={1.3} style={styles.statLabel}>{label}</Text>
      </View>
      <Text maxFontSizeMultiplier={1.3} style={styles.statVal}>{value}</Text>
    </View>
  );
}

export function WorkoutCardView(d: WorkoutData) {
  const baseTitle = d.activity_type ? `${d.activity_type}分析` : '运动分析';
  const title = d.workout_date ? `${baseTitle} · ${humanizeDate(d.workout_date)}` : baseTitle;
  return (
    <CardShell
      icon="fitness"
      iconColor={C.green500}
      title={title}
      bg={C.surface2}
      style={styles.card}
    >
      <View style={styles.grid}>
        {d.duration_min != null && <Stat icon="time-outline" label="时长" value={`${d.duration_min}min`} />}
        {d.distance_km != null && <Stat icon="navigate-outline" label="距离" value={`${d.distance_km.toFixed(2)}km`} />}
        {d.calories != null && <Stat icon="flame-outline" label="消耗" value={`${d.calories}kcal`} />}
        {d.avg_hr != null && <Stat icon="heart-outline" label="均心率" value={`${d.avg_hr}bpm`} />}
        {d.max_hr != null && <Stat icon="heart" label="最大心率" value={`${d.max_hr}bpm`} />}
        {d.avg_pace && <Stat icon="speedometer-outline" label="配速" value={d.avg_pace} />}
        {d.steps != null && <Stat icon="footsteps-outline" label="步数" value={d.steps.toLocaleString()} />}
      </View>
      <EvidenceRefsRow refs={d.evidence_refs} />
    </CardShell>
  );
}

function humanizeDate(ymd: string): string {
  const today = new Date();
  const toYMD = formatLocalDate;
  const t = toYMD(today);
  if (ymd === t) return '今天';
  const yest = new Date(today); yest.setDate(today.getDate() - 1);
  if (ymd === toYMD(yest)) return '昨天';
  const dBefore = new Date(today); dBefore.setDate(today.getDate() - 2);
  if (ymd === toYMD(dBefore)) return '前天';
  // 更早的直接显示 MM-DD
  return ymd.slice(5);
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
  async build({ query_lower, data, api: apiClient }) {
    const g = data.garmin;
    const cardData: WorkoutData = {};
    const window = parseDateWindow(query_lower);

    try {
      const params: any = window
        ? { start_date: window.start, end_date: window.end }
        : { limit: 1 };
      const { data: workouts } = await apiClient.get('/workout/me', { params });

      if (Array.isArray(workouts) && workouts.length > 0) {
        // 有时间窗: 拿该窗口内最近的一条; 无时间窗: API 已按 limit 返回 latest
        const w = workouts[0];
        cardData.activity_type = w.workout_name || w.workout_type;
        if (w.workout_date) cardData.workout_date = w.workout_date;
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

      // 有时间窗但无匹配数据 → 不要兜底拉 latest (会渲染错日期的运动, 与 LLM 文本矛盾)
      if (window) return null;
    } catch {
      // 旁路: 主路径失败 → 走下面 fallback (garmin daily). 真正错误下面 fallback 也会失败.
    }

    // Fallback: 仅在泛化问题(无时间窗)时, 用 garmin daily data
    if (!window && g) {
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
  card: {
    borderRadius: revaRadii.md,
    borderLeftWidth: 3,
    borderLeftColor: C.green300,
    shadowOpacity: 0,
    elevation: 0,
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', rowGap: 12 },
  stat: { flexBasis: '33.333%', minWidth: 82, paddingRight: 8 },
  statHeader: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 3 },
  statLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3 } as TextStyle,
  statVal: {
    fontFamily: revaFonts.mono,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '600',
    color: C.ink1,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
});
