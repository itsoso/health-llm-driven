/**
 * DayTimeline —— 单日 24h 垂直时间轴(只读)。
 * 左侧时刻刻度(每小时一条标注线),右侧按 start→end 绝对定位事件块;
 * 重叠块用泳道并排(timelineLayout.assignLanes);全天事件不进网格(由父组件单独渲染)。
 * "现在"指示线仅当 isToday。点块 → onPressBlock(回父组件展开明细)。
 *
 * 设计语言:Reva(revaColors / 卡片 / mono 刻度数字)。纯展示,无数据获取。
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { LayoutChangeEvent, Pressable, ScrollView, Text, View } from 'react-native';
import { revaColors as C } from '../../constants/revaTheme';
import {
  assignLanes, clampDayMinute, DAY_MINUTES, type TimelineBlock,
} from './timelineLayout';

const PX_PER_MIN = 56 / 60; // 56px / 小时
const HOUR_PX = 60 * PX_PER_MIN;
const MIN_BLOCK_PX = 22; // 短事件最小高度,保持可点
const GUTTER_W = 52; // 左侧时刻刻度列宽
const BLOCK_GAP = 3; // 同簇相邻列间隙
const POINT_THRESHOLD_MIN = 15; // ≤ 此时长视为"时点 marker"(细条 chip)

/** 时间轴渲染用块:布局字段 + 展示字段。 */
export interface TimelineEntry extends TimelineBlock {
  title: string;
  timeLabel: string; // "HH:MM–HH:MM" 或 "HH:MM"
  subtitle?: string; // 地点 / 处方摘要
  color: string;
  isPoint: boolean; // 时点(药/补剂)→ 细 marker
}

function hourLabel(h: number): string {
  return `${String(h).padStart(2, '0')}:00`;
}

export default function DayTimeline({
  entries, isToday, onPressBlock, activeKey,
}: {
  entries: TimelineEntry[];
  isToday: boolean;
  onPressBlock: (key: string) => void;
  activeKey: string | null;
}) {
  const scrollRef = useRef<ScrollView>(null);
  const [trackWidth, setTrackWidth] = React.useState(0);

  const placed = useMemo(() => assignLanes(entries), [entries]);

  // 进入时自动滚到首个事件前 ~1h,或今天滚到"现在"。
  const firstStart = useMemo(
    () => (entries.length ? Math.min(...entries.map((e) => e.startMin)) : null),
    [entries],
  );
  const nowMin = isToday ? new Date().getHours() * 60 + new Date().getMinutes() : null;

  useEffect(() => {
    const target = nowMin ?? (firstStart != null ? firstStart - 60 : null);
    if (target == null) return;
    const y = Math.max(0, clampDayMinute(target) * PX_PER_MIN - 24);
    const t = setTimeout(() => scrollRef.current?.scrollTo({ y, animated: false }), 60);
    return () => clearTimeout(t);
    // 仅在数据/视角变化时滚一次
  }, [firstStart, nowMin]);

  const onTrackLayout = (e: LayoutChangeEvent) => setTrackWidth(e.nativeEvent.layout.width);

  const totalHeight = DAY_MINUTES * PX_PER_MIN;

  return (
    <ScrollView
      ref={scrollRef}
      style={{ backgroundColor: C.surface, borderRadius: 14 }}
      contentContainerStyle={{ paddingVertical: 8 }}
      showsVerticalScrollIndicator
    >
      <View style={{ height: totalHeight, flexDirection: 'row' }}>
        {/* 左:时刻刻度列 */}
        <View style={{ width: GUTTER_W }}>
          {Array.from({ length: 25 }, (_, h) => (
            <Text
              key={h}
              style={{
                position: 'absolute', top: h * HOUR_PX - 7, right: 8,
                fontFamily: 'IBMPlexMono', fontSize: 11, color: C.ink3,
              }}
            >
              {h < 24 ? hourLabel(h) : ''}
            </Text>
          ))}
        </View>

        {/* 右:网格 + 事件块 */}
        <View style={{ flex: 1, position: 'relative' }} onLayout={onTrackLayout}>
          {/* 每小时一条 hairline */}
          {Array.from({ length: 25 }, (_, h) => (
            <View
              key={h}
              style={{
                position: 'absolute', top: h * HOUR_PX, left: 0, right: 8,
                height: 1, backgroundColor: C.line,
              }}
            />
          ))}

          {/* 事件块 */}
          {trackWidth > 0
            ? placed.map(({ block, lane, lanes }) => {
                const e = block as TimelineEntry;
                const usable = trackWidth - 8; // 右边留 8 给刻度线收尾
                const colW = (usable - BLOCK_GAP * (lanes - 1)) / lanes;
                const top = e.startMin * PX_PER_MIN;
                const height = Math.max((e.endMin - e.startMin) * PX_PER_MIN, MIN_BLOCK_PX);
                const left = lane * (colW + BLOCK_GAP);
                const active = activeKey === e.key;
                return (
                  <Pressable
                    key={e.key}
                    onPress={() => onPressBlock(e.key)}
                    style={({ pressed }) => [{
                      position: 'absolute', top, left, width: colW, height,
                      borderRadius: 8, overflow: 'hidden',
                      backgroundColor: tint(e.color),
                      borderLeftWidth: 3, borderLeftColor: e.color,
                      borderWidth: active ? 1 : 0, borderColor: e.color,
                      opacity: pressed ? 0.85 : 1,
                      paddingHorizontal: 7, paddingVertical: e.isPoint ? 2 : 5,
                      justifyContent: e.isPoint ? 'center' : 'flex-start',
                    }]}
                  >
                    <Text
                      numberOfLines={e.isPoint ? 1 : 2}
                      style={{
                        fontFamily: 'NotoSansSC', fontSize: e.isPoint ? 11.5 : 12.5,
                        fontWeight: '600', color: C.ink1,
                      }}
                    >
                      {e.title}
                    </Text>
                    {!e.isPoint && height >= 34 ? (
                      <Text
                        numberOfLines={1}
                        style={{ fontFamily: 'IBMPlexMono', fontSize: 10.5, color: C.ink2, marginTop: 1 }}
                      >
                        {e.timeLabel}
                      </Text>
                    ) : null}
                    {!e.isPoint && e.subtitle && height >= 52 ? (
                      <Text numberOfLines={1} style={{ fontSize: 10.5, color: C.ink3, marginTop: 1 }}>
                        {e.subtitle}
                      </Text>
                    ) : null}
                  </Pressable>
                );
              })
            : null}

          {/* "现在"指示线 */}
          {nowMin != null ? (
            <View
              pointerEvents="none"
              style={{
                position: 'absolute', top: nowMin * PX_PER_MIN, left: -3, right: 8,
                flexDirection: 'row', alignItems: 'center',
              }}
            >
              <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: C.green500 }} />
              <View style={{ flex: 1, height: 1.5, backgroundColor: C.green500 }} />
            </View>
          ) : null}
        </View>
      </View>
    </ScrollView>
  );
}

/** 把源色调成淡背景(块底色),保持文字对比。简单 hex→低透明叠加。 */
function tint(hex: string): string {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex);
  if (!m) return C.surface2;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},0.12)`;
}
