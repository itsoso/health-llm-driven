import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, Dimensions, LayoutChangeEvent, TextStyle } from 'react-native';
import Svg, { Line, Polyline, Rect, G, Text as SvgText, Circle } from 'react-native-svg';
import { colors, spacing } from '../../constants/theme';
import type { SpO2Point } from '../../services/spo2';

interface Props {
  data: SpO2Point[];
  sleepStart?: string | null;
  sleepEnd?: string | null;
  height?: number;
}

const PAD = { top: 16, right: 12, bottom: 28, left: 36 };
const Y_MIN = 60;
const Y_MAX = 100;
const Y_TICKS = [60, 70, 80, 90, 95, 100];
// 相邻数据点超过此分钟数 → 断开折线 (避免白天稀疏点被错误连成一条直线).
// Garmin 默认白天 spot-check 模式间隔 1-2 小时, 30 min 是稳定的阈值.
const GAP_BREAK_MINUTES = 30;

function lttbDownsample(data: SpO2Point[], threshold: number): SpO2Point[] {
  if (data.length <= threshold) return data;
  const sampled: SpO2Point[] = [data[0]];
  const bucketSize = (data.length - 2) / (threshold - 2);

  let prevIdx = 0;
  for (let i = 0; i < threshold - 2; i++) {
    const avgRangeStart = Math.floor((i + 1) * bucketSize) + 1;
    const avgRangeEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, data.length);
    let avgX = 0, avgY = 0;
    for (let j = avgRangeStart; j < avgRangeEnd; j++) {
      avgX += j;
      avgY += data[j].value;
    }
    avgX /= (avgRangeEnd - avgRangeStart);
    avgY /= (avgRangeEnd - avgRangeStart);

    const rangeStart = Math.floor(i * bucketSize) + 1;
    const rangeEnd = Math.min(Math.floor((i + 1) * bucketSize) + 1, data.length);

    let maxArea = -1, maxIdx = rangeStart;
    for (let j = rangeStart; j < rangeEnd; j++) {
      const area = Math.abs(
        (prevIdx - avgX) * (data[j].value - data[prevIdx].value) -
        (prevIdx - j) * (avgY - data[prevIdx].value)
      );
      if (area > maxArea) {
        maxArea = area;
        maxIdx = j;
      }
    }
    sampled.push(data[maxIdx]);
    prevIdx = maxIdx;
  }
  sampled.push(data[data.length - 1]);
  return sampled;
}

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

export default function SpO2NightChart({ data, height = 180 }: Props) {
  const [chartWidth, setChartWidth] = useState(Dimensions.get('window').width - 32);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  const onLayout = (e: LayoutChangeEvent) => setChartWidth(e.nativeEvent.layout.width);

  const plotW = chartWidth - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const downsampled = useMemo(() => lttbDownsample(data, 150), [data]);

  const timeRange = useMemo(() => {
    if (data.length === 0) return { min: 0, max: 1 };
    const mins = data.map(d => {
      let m = timeToMinutes(d.time);
      if (m > 18 * 60) m -= 24 * 60;
      return m;
    });
    return { min: Math.min(...mins), max: Math.max(...mins) };
  }, [data]);

  const toX = (time: string) => {
    let m = timeToMinutes(time);
    if (m > 18 * 60) m -= 24 * 60;
    const ratio = (m - timeRange.min) / (timeRange.max - timeRange.min || 1);
    return PAD.left + ratio * plotW;
  };

  const toY = (v: number) => {
    const clamped = Math.max(Y_MIN, Math.min(Y_MAX, v));
    return PAD.top + (1 - (clamped - Y_MIN) / (Y_MAX - Y_MIN)) * plotH;
  };

  // 把 downsampled 切成多段 segments — 相邻两点 wall-clock 间隔 > GAP_BREAK_MINUTES
  // 就断开. 单点 segments 当成 scatter dot 渲染.
  const segments = useMemo(() => {
    if (downsampled.length === 0) return [] as SpO2Point[][];
    const segs: SpO2Point[][] = [[downsampled[0]]];
    for (let i = 1; i < downsampled.length; i++) {
      const prev = downsampled[i - 1];
      const cur = downsampled[i];
      let prevM = timeToMinutes(prev.time);
      let curM = timeToMinutes(cur.time);
      // 跨午夜归一化 (与 toX 同逻辑)
      if (prevM > 18 * 60) prevM -= 24 * 60;
      if (curM > 18 * 60) curM -= 24 * 60;
      const gap = curM - prevM;
      if (gap > GAP_BREAK_MINUTES) {
        segs.push([cur]);
      } else {
        segs[segs.length - 1].push(cur);
      }
    }
    return segs;
  }, [downsampled]);

  const xLabels = useMemo(() => {
    if (data.length < 2) return [];
    const first = data[0].time;
    const last = data[data.length - 1].time;
    const mid = data[Math.floor(data.length / 2)].time;
    return [first, mid, last];
  }, [data]);

  const handlePress = (evt: any) => {
    const x = evt.nativeEvent.locationX - PAD.left;
    if (x < 0 || x > plotW) { setSelectedIdx(null); return; }
    const ratio = x / plotW;
    const idx = Math.round(ratio * (data.length - 1));
    setSelectedIdx(Math.max(0, Math.min(data.length - 1, idx)));
  };

  if (data.length === 0) return null;

  const selected = selectedIdx !== null ? data[selectedIdx] : null;

  return (
    <View onLayout={onLayout} style={styles.container}>
      <View onTouchEnd={handlePress}>
        <Svg width={chartWidth} height={height}>
          {/* Y grid + labels */}
          {Y_TICKS.map(v => (
            <G key={v}>
              <Line
                x1={PAD.left} y1={toY(v)} x2={chartWidth - PAD.right} y2={toY(v)}
                stroke={v === 90 ? '#FF453A40' : v === 95 ? '#FF9F0A30' : colors.separator}
                strokeWidth={v === 90 || v === 95 ? 1 : 0.5}
                strokeDasharray={v === 90 || v === 95 ? '4,3' : undefined}
              />
              <SvgText x={PAD.left - 6} y={toY(v) + 4} textAnchor="end" fontSize={10} fill={colors.labelTertiary}>
                {v}
              </SvgText>
            </G>
          ))}

          {/* Reference bands */}
          <Rect x={PAD.left} y={toY(Y_MAX)} width={plotW} height={toY(95) - toY(Y_MAX)} fill="#30D15808" />
          <Rect x={PAD.left} y={toY(95)} width={plotW} height={toY(90) - toY(95)} fill="#FF9F0A08" />
          <Rect x={PAD.left} y={toY(90)} width={plotW} height={toY(Y_MIN) - toY(90)} fill="#FF453A08" />

          {/* SpO2 line — 多段 polyline + 单点散点
              (gap > 30min 自动断开, 避免白天稀疏点连成长直线 misleading) */}
          {segments.map((seg, i) => {
            if (seg.length === 1) {
              // 孤立散点 (白天偶发测量) — 用空心圆区分于连续监测段
              const p = seg[0];
              return (
                <Circle key={`pt-${i}`}
                  cx={toX(p.time)} cy={toY(p.value)} r={2}
                  fill="#fff" stroke="#007AFF" strokeWidth={1.2} />
              );
            }
            const pts = seg.map(p => `${toX(p.time).toFixed(1)},${toY(p.value).toFixed(1)}`).join(' ');
            return (
              <Polyline key={`seg-${i}`} points={pts} fill="none"
                stroke="#007AFF" strokeWidth={1.5} strokeLinejoin="round" />
            );
          })}

          {/* X labels */}
          {xLabels.map((t, i) => (
            <SvgText key={i} x={toX(t)} y={height - 6} textAnchor="middle" fontSize={10} fill={colors.labelTertiary}>
              {t}
            </SvgText>
          ))}

          {/* Selected point */}
          {selected && (
            <>
              <Line x1={toX(selected.time)} y1={PAD.top} x2={toX(selected.time)} y2={PAD.top + plotH} stroke="#007AFF40" strokeWidth={1} />
              <Circle cx={toX(selected.time)} cy={toY(selected.value)} r={4} fill="#007AFF" stroke="#fff" strokeWidth={1.5} />
            </>
          )}
        </Svg>
      </View>

      {/* Tooltip */}
      {selected && (
        <View style={styles.tooltip}>
          <Text style={txt.tooltipTime}>{selected.time}</Text>
          <Text style={[txt.tooltipValue, { color: selected.value < 90 ? '#FF453A' : selected.value < 95 ? '#FF9F0A' : '#30D158' }]}>
            {selected.value}%
          </Text>
        </View>
      )}

      {/* Legend */}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#30D158' }]} />
          <Text style={txt.legendText}>≥95 正常</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#FF9F0A' }]} />
          <Text style={txt.legendText}>90-94 偏低</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#FF453A' }]} />
          <Text style={txt.legendText}>&lt;90 低氧</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 4 },
  tooltip: {
    position: 'absolute', top: 0, right: 12,
    flexDirection: 'row', alignItems: 'baseline', gap: 6,
    backgroundColor: colors.bgCard, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4,
    shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 4, shadowOffset: { width: 0, height: 2 },
  },
  legend: { flexDirection: 'row', justifyContent: 'center', gap: 12, marginTop: 4 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendDot: { width: 6, height: 6, borderRadius: 3 },
});

const txt = {
  tooltipTime: { fontSize: 12, color: colors.labelSecondary } as TextStyle,
  tooltipValue: { fontSize: 18, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  legendText: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
};
