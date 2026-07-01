import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { BodyStatsValues } from './BodyStatsRow';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';
import { SectionLabel } from '../reva/RevaKit';

export type TodaySignalKey =
  | 'sleep'
  | 'hrv'
  | 'body_battery'
  | 'blood_pressure'
  | 'spo2'
  | 'bmi'
  | 'body_fat';

interface Props {
  sleep?: number | null;
  sleepScore?: number | null;
  hrv?: number | null;
  bodyBatteryCurrent?: number | null;
  bodyStats: BodyStatsValues;
  actionSignal?: string | null;
  onSignalPress?: (signal: TodaySignalKey) => void;
}

interface SignalTile {
  key: TodaySignalKey;
  label: string;
  value: string;
  sub: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  tint: string;
  pending: boolean;
  attention: boolean;
}

const HUES = {
  purple: { color: '#7C5CBF', tint: '#EDE7F6' },
  teal: { color: '#2F9E8F', tint: '#E0EFEC' },
  green: { color: C.green500, tint: C.green50 },
  pink: { color: '#C2487A', tint: '#F7E4EC' },
  blue: { color: C.blue500, tint: C.blue50 },
  orange: { color: '#C97A2E', tint: '#F6E9DA' },
} as const;

export default function TodaySignalsPanel({
  sleep,
  sleepScore,
  hrv,
  bodyBatteryCurrent,
  bodyStats,
  actionSignal,
  onSignalPress,
}: Props) {
  const tiles = useMemo(
    () => [
      sleepSignal(sleep, sleepScore),
      hrvSignal(hrv),
      batterySignal(bodyBatteryCurrent),
      bodySignal(actionSignal, bodyStats),
    ],
    [actionSignal, bodyBatteryCurrent, bodyStats, hrv, sleep, sleepScore],
  );
  const hasActionSignal = Boolean(actionSignal?.trim());
  const hasAnyObservedSignal = tiles.some((tile) => !tile.pending);
  const attentionTiles = tiles.filter((tile) => tile.attention);
  const visibleTiles = hasActionSignal
    ? (!hasAnyObservedSignal ? [tiles[tiles.length - 1]] : tiles)
    : attentionTiles;

  if (visibleTiles.length === 0) return null;

  return (
    <View>
      <SectionLabel>身体信号</SectionLabel>
      <View style={styles.card}>
        {visibleTiles.map((tile) => (
          <SignalButton key={tile.key} tile={tile} onPress={onSignalPress} />
        ))}
      </View>
    </View>
  );
}

function SignalButton({
  tile,
  onPress,
}: {
  tile: SignalTile;
  onPress?: (signal: TodaySignalKey) => void;
}) {
  return (
    <Pressable
      style={({ pressed }) => [styles.tile, pressed && { opacity: 0.76 }]}
      onPress={() => onPress?.(tile.key)}
      accessibilityRole="button"
      accessibilityLabel={`${tile.label} ${tile.value}`}
    >
      <View style={[styles.iconWrap, { backgroundColor: tile.tint }]}>
        <Ionicons name={tile.icon} size={13} color={tile.color} />
      </View>
      <View style={styles.tileText}>
        <Text
          maxFontSizeMultiplier={1.18}
          style={[txt.value, tile.pending && txt.pending]}
          numberOfLines={1}
        >
          {tile.value}
        </Text>
        <Text maxFontSizeMultiplier={1.18} style={txt.label} numberOfLines={1}>
          {tile.label}
        </Text>
        <Text maxFontSizeMultiplier={1.18} style={txt.sub} numberOfLines={1}>
          {tile.sub}
        </Text>
      </View>
    </Pressable>
  );
}

function sleepSignal(sleep: number | null | undefined, sleepScore: number | null | undefined): SignalTile {
  const hasValue = sleep != null && Number.isFinite(sleep);
  const scoreNeedsAttention = sleepScore != null && sleepScore < 60;
  return {
    key: 'sleep',
    label: '睡眠',
    value: hasValue ? `${sleep.toFixed(1)}h` : '待同步',
    sub: sleepScore != null ? `评分 ${sleepScore}` : '昨晚恢复',
    icon: 'moon',
    color: HUES.purple.color,
    tint: HUES.purple.tint,
    pending: !hasValue,
    attention: hasValue && (sleep < 6 || scoreNeedsAttention),
  };
}

function hrvSignal(hrv: number | null | undefined): SignalTile {
  const hasValue = hrv != null && Number.isFinite(hrv);
  return {
    key: 'hrv',
    label: 'HRV',
    value: hasValue ? `${Math.round(hrv)}ms` : '待同步',
    sub: '压力恢复',
    icon: 'pulse',
    color: HUES.teal.color,
    tint: HUES.teal.tint,
    pending: !hasValue,
    attention: false,
  };
}

function batterySignal(value: number | null | undefined): SignalTile {
  const hasValue = value != null && Number.isFinite(value);
  return {
    key: 'body_battery',
    label: '电量',
    value: hasValue ? `${Math.round(value)}` : '待同步',
    sub: '当前状态',
    icon: 'battery-charging',
    color: HUES.green.color,
    tint: HUES.green.tint,
    pending: !hasValue,
    attention: hasValue && value < 35,
  };
}

function bodySignal(actionSignal: string | null | undefined, values: BodyStatsValues): SignalTile {
  const normalized = (actionSignal ?? '').toLowerCase();
  const bpNeedsAttention =
    values.systolic != null &&
    values.diastolic != null &&
    (values.systolic >= 140 || values.diastolic >= 90);
  const spo2NeedsAttention = values.spo2 != null && values.spo2 < 94;

  if (/systolic|diastolic|blood|bp|血压/.test(normalized) || (!normalized && bpNeedsAttention)) {
    const hasValue = values.systolic != null && values.diastolic != null;
    return {
      key: 'blood_pressure',
      label: '血压',
      value: hasValue ? `${values.systolic}/${values.diastolic}mmHg` : '待记录',
      sub: '行动验证',
      icon: 'heart-outline',
      color: HUES.pink.color,
      tint: HUES.pink.tint,
      pending: !hasValue,
      attention: bpNeedsAttention,
    };
  }
  if (/spo2|oxygen|血氧/.test(normalized) || (!normalized && spo2NeedsAttention)) {
    const value = values.spo2;
    const hasValue = value != null;
    return {
      key: 'spo2',
      label: 'SpO2',
      value: hasValue ? `${formatNumber(value)}%` : '待同步',
      sub: '夜间均值',
      icon: 'water-outline',
      color: HUES.blue.color,
      tint: HUES.blue.tint,
      pending: !hasValue,
      attention: spo2NeedsAttention,
    };
  }
  if (/fat|体脂/.test(normalized)) {
    const value = values.bodyFatPct;
    const hasValue = value != null;
    return {
      key: 'body_fat',
      label: '体脂',
      value: hasValue ? `${formatNumber(value)}%` : '待记录',
      sub: '身体组成',
      icon: 'fitness-outline',
      color: HUES.orange.color,
      tint: HUES.orange.tint,
      pending: !hasValue,
      attention: false,
    };
  }
  const value = values.bmi;
  const hasValue = value != null;
  return {
    key: 'bmi',
    label: 'BMI',
    value: hasValue ? formatNumber(value) : '待记录',
    sub: /waist|weight|腰围|体重/.test(normalized) ? '代谢验证' : '身体组成',
    icon: 'body-outline',
    color: HUES.green.color,
    tint: HUES.green.tint,
    pending: !hasValue,
    attention: false,
  };
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: revaSpacing.s2,
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: revaSpacing.s3,
    ...revaShadows.sm,
  },
  tile: {
    flexBasis: '48%',
    flexGrow: 1,
    minWidth: 132,
    minHeight: 70,
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface2,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  iconWrap: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileText: { flex: 1, minWidth: 0 },
});

const txt = {
  value: {
    fontFamily: revaFonts.mono,
    fontSize: 17,
    lineHeight: 21,
    fontWeight: '800',
    color: C.ink1,
    letterSpacing: 0,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  pending: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink3 } as TextStyle,
  label: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 16,
    fontWeight: '800',
    color: C.ink2,
    marginTop: 1,
  } as TextStyle,
  sub: {
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 14,
    fontWeight: '600',
    color: C.ink3,
    marginTop: 1,
  } as TextStyle,
};
