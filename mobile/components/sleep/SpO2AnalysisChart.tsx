// SpO2 根因分析专用图表（P1b）
// - SpO2 主曲线
// - 氧降事件红色标记
// - 睡眠分期背景色带
// - 可选叠加 HR / 呼吸率
import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, Dimensions, LayoutChangeEvent, TextStyle } from 'react-native';
import Svg, { Line, Polyline, Rect, G, Text as SvgText, Circle, Path } from 'react-native-svg';
import { colors, spacing } from '@/constants/theme';

interface TsPoint {
  sample_time: string; // HH:MM or HH:MM:SS
  value: number | null;
  epoch_ms: number | null;
}

interface Event {
  start_ts: string;
  end_ts: string;
  min_spo2: number;
  sleep_stage: string | null;
  drop_magnitude: number;
}

interface SleepStage {
  start_ms: number;
  end_ms: number;
  level: string; // awake | light | deep | rem
}

interface Props {
  spo2Series: TsPoint[];
  hrSeries?: TsPoint[];
  respirationSeries?: TsPoint[];
  events?: Event[];
  sleepStages?: SleepStage[];
  height?: number;
  showOverlay?: 'hr' | 'respiration' | 'none';
}

const PAD = { top: 18, right: 12, bottom: 28, left: 36 };
const SPO2_Y_MIN = 60;
const SPO2_Y_MAX = 100;
const SPO2_Y_TICKS = [70, 80, 85, 90, 95, 100];

const STAGE_COLORS: Record<string, string> = {
  deep: '#4338CA',     // 深睡 靛蓝
  light: '#60A5FA',    // 浅睡 浅蓝
  rem: '#A78BFA',      // REM 紫
  awake: '#FCD34D',    // 清醒 黄
};

function timeToMinutes(s: string): number {
  const [h, m] = s.split(':').map(Number);
  return h * 60 + (m || 0);
}

function toLocalMinutesFromMs(ms: number): number {
  const d = new Date(ms);
  return d.getHours() * 60 + d.getMinutes();
}

// 把时间映射到"夜"的连续轴：>=18h 的归到昨夜（减 24）
function normalizeMin(m: number): number {
  return m >= 18 * 60 ? m - 24 * 60 : m;
}

function isoToMinutes(iso: string): number {
  // 把 ISO 时间转换为本地时间（注意：后端是 +08:00 的 server-local 时间 naive 存储）
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

export default function SpO2AnalysisChart({
  spo2Series,
  hrSeries = [],
  respirationSeries = [],
  events = [],
  sleepStages = [],
  height = 220,
  showOverlay = 'none',
}: Props) {
  const [chartWidth, setChartWidth] = useState(Dimensions.get('window').width - 32);
  const onLayout = (e: LayoutChangeEvent) => setChartWidth(e.nativeEvent.layout.width);

  const plotW = chartWidth - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  // --- 时间域 ---
  const { xMin, xMax } = useMemo(() => {
    if (!spo2Series.length) return { xMin: 0, xMax: 1 };
    const mins = spo2Series
      .map((p) => normalizeMin(timeToMinutes(p.sample_time)))
      .filter((x) => !Number.isNaN(x));
    return { xMin: Math.min(...mins), xMax: Math.max(...mins) };
  }, [spo2Series]);

  const toX = (timeStr: string) => {
    const m = normalizeMin(timeToMinutes(timeStr));
    return PAD.left + ((m - xMin) / (xMax - xMin || 1)) * plotW;
  };

  const toXFromMs = (ms: number) => {
    const m = normalizeMin(toLocalMinutesFromMs(ms));
    return PAD.left + ((m - xMin) / (xMax - xMin || 1)) * plotW;
  };

  const toXFromIso = (iso: string) => {
    const m = normalizeMin(isoToMinutes(iso));
    return PAD.left + ((m - xMin) / (xMax - xMin || 1)) * plotW;
  };

  // --- Y 轴: SpO2 ---
  const toSpO2Y = (v: number) => {
    const clamped = Math.max(SPO2_Y_MIN, Math.min(SPO2_Y_MAX, v));
    return PAD.top + (1 - (clamped - SPO2_Y_MIN) / (SPO2_Y_MAX - SPO2_Y_MIN)) * plotH;
  };

  // --- overlay 二轴 ---
  const overlaySeries = showOverlay === 'hr' ? hrSeries : showOverlay === 'respiration' ? respirationSeries : [];
  const overlayRange = useMemo(() => {
    if (!overlaySeries.length) return { min: 0, max: 1 };
    const vals = overlaySeries.map((p) => p.value ?? 0).filter((v) => v > 0);
    return vals.length ? { min: Math.min(...vals), max: Math.max(...vals) } : { min: 0, max: 1 };
  }, [overlaySeries]);

  const toOverlayY = (v: number) => {
    const ratio = (v - overlayRange.min) / (overlayRange.max - overlayRange.min || 1);
    return PAD.top + (1 - ratio) * plotH;
  };

  // --- 主折线 ---
  const polylinePoints = useMemo(() => {
    return spo2Series
      .filter((p) => p.value != null)
      .map((p) => `${toX(p.sample_time).toFixed(1)},${toSpO2Y(p.value as number).toFixed(1)}`)
      .join(' ');
  }, [spo2Series, plotW, plotH]);

  const overlayPolyline = useMemo(() => {
    if (!overlaySeries.length) return '';
    return overlaySeries
      .filter((p) => p.value != null)
      .map((p) => `${toX(p.sample_time).toFixed(1)},${toOverlayY(p.value as number).toFixed(1)}`)
      .join(' ');
  }, [overlaySeries, plotW, plotH]);

  // --- 事件点（红色三角）---
  const eventMarkers = events.map((ev) => {
    const x = toXFromIso(ev.start_ts);
    const y = toSpO2Y(ev.min_spo2);
    return { x, y, spo2: ev.min_spo2, stage: ev.sleep_stage };
  });

  // --- 睡眠分期背景色带（按 normalize 后的分钟横跨）---
  const stageBands = useMemo(() => {
    return sleepStages
      .map((s) => {
        const x1 = toXFromMs(s.start_ms);
        const x2 = toXFromMs(s.end_ms);
        return { x1, w: Math.max(2, x2 - x1), color: STAGE_COLORS[s.level] || '#E5E7EB' };
      })
      .filter((b) => b.x1 + b.w > PAD.left && b.x1 < PAD.left + plotW);
  }, [sleepStages, plotW]);

  // --- 时间标签 ---
  const xLabels = useMemo(() => {
    if (!spo2Series.length) return [];
    const first = spo2Series[0].sample_time.slice(0, 5);
    const last = spo2Series[spo2Series.length - 1].sample_time.slice(0, 5);
    return [first, last];
  }, [spo2Series]);

  return (
    <View style={styles.container} onLayout={onLayout}>
      <Svg width={chartWidth} height={height}>
        {/* 睡眠分期背景色带（放最底） */}
        {stageBands.map((b, i) => (
          <Rect
            key={`stage-${i}`}
            x={b.x1}
            y={PAD.top}
            width={b.w}
            height={plotH}
            fill={b.color}
            opacity={0.12}
          />
        ))}

        {/* Y 轴参考线 + 刻度（SpO2）*/}
        {SPO2_Y_TICKS.map((v) => (
          <G key={`y-${v}`}>
            <Line
              x1={PAD.left}
              y1={toSpO2Y(v)}
              x2={PAD.left + plotW}
              y2={toSpO2Y(v)}
              stroke={v === 90 ? '#FCA5A5' : '#E5E7EB'}
              strokeWidth={v === 90 ? 1 : 0.5}
              strokeDasharray={v === 90 ? '3,3' : undefined}
            />
            <SvgText
              x={PAD.left - 6}
              y={toSpO2Y(v) + 3}
              fontSize="10"
              fill={colors.labelSecondary}
              textAnchor="end"
            >
              {v}
            </SvgText>
          </G>
        ))}

        {/* overlay 折线（HR/呼吸）*/}
        {overlayPolyline ? (
          <Polyline
            points={overlayPolyline}
            fill="none"
            stroke={showOverlay === 'hr' ? '#F97316' : '#10B981'}
            strokeWidth={1.2}
            strokeOpacity={0.8}
            strokeDasharray="2,3"
          />
        ) : null}

        {/* SpO2 主折线 */}
        <Polyline
          points={polylinePoints}
          fill="none"
          stroke={colors.brand}
          strokeWidth={1.6}
        />

        {/* 事件红三角 */}
        {eventMarkers.map((m, i) => (
          <G key={`ev-${i}`}>
            <Path
              d={`M ${m.x - 4} ${m.y - 8} L ${m.x + 4} ${m.y - 8} L ${m.x} ${m.y - 2} Z`}
              fill="#DC2626"
            />
            <Circle cx={m.x} cy={m.y} r={2.5} fill="#DC2626" />
          </G>
        ))}

        {/* X 轴时间标签 */}
        {xLabels.map((lbl, i) => (
          <SvgText
            key={`x-${i}`}
            x={i === 0 ? PAD.left : PAD.left + plotW}
            y={height - PAD.bottom + 16}
            fontSize="10"
            fill={colors.labelSecondary}
            textAnchor={i === 0 ? 'start' : 'end'}
          >
            {lbl}
          </SvgText>
        ))}
      </Svg>

      {/* 图例 */}
      <View style={styles.legend}>
        {[
          { color: STAGE_COLORS.deep, label: '深睡', op: 0.18 },
          { color: STAGE_COLORS.light, label: '浅睡', op: 0.18 },
          { color: STAGE_COLORS.rem, label: 'REM', op: 0.18 },
          { color: STAGE_COLORS.awake, label: '清醒', op: 0.18 },
          { color: '#DC2626', label: '氧降事件', op: 1 },
        ].map((l) => (
          <View key={l.label} style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: l.color, opacity: l.op }]} />
            <Text style={txt.legend}>{l.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { paddingVertical: spacing.sm },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    marginTop: 8,
    gap: 10,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendDot: { width: 12, height: 8, borderRadius: 2 },
});

const txt = {
  legend: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
};
