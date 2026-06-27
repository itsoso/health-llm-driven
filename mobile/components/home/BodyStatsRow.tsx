/**
 * BodyStatsRow —— 首页"基础体征"四宫格 (2026-05-28 重设计加回).
 *
 * 显示血压 / SpO2 / BMI / 体脂; 单卡可点击进入对应历史页.
 * 数据缺失时显示"待记录", 引导用户去补 — 不掩盖空状态.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

// 每指标的装饰性 hue (血压粉 / SpO2 蓝 / BMI 绿 / 体脂橙) —— 区分指标的色码,
// 不是「指标好坏」的三步临床语义。值即 Reva 亮色调色板原值。
const HUES = {
  pink: { color: '#C2487A', tint: '#F7E4EC' },
  blue: { color: C.blue500, tint: C.blue50 },
  green: { color: C.green500, tint: C.green50 },
  orange: { color: '#C97A2E', tint: '#F6E9DA' },
} as const;

export interface BodyStatsValues {
  systolic?: number | null;
  diastolic?: number | null;
  spo2?: number | null;
  bmi?: number | null;
  bodyFatPct?: number | null;
}

interface Tile {
  key: 'bp' | 'spo2' | 'bmi' | 'fat';
  label: string;
  value: string;
  unit?: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  tint: string;
  route: string;
  pending: boolean;
}

function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return '—';
  return Number.isInteger(n) ? String(n) : n.toFixed(digits);
}

export default function BodyStatsRow({ values }: { values: BodyStatsValues }) {
  const router = useRouter();

  const hasBp = values.systolic != null && values.diastolic != null;
  const hasSpo2 = values.spo2 != null;
  const hasBmi = values.bmi != null;
  const hasFat = values.bodyFatPct != null;

  const tiles: Tile[] = [
    {
      key: 'bp',
      label: '血压',
      value: hasBp ? `${values.systolic}/${values.diastolic}` : '待记录',
      unit: hasBp ? 'mmHg' : undefined,
      hint: '心血管',
      icon: 'heart-outline',
      color: HUES.pink.color,
      tint: HUES.pink.tint,
      route: '/indicator-history?type=blood_pressure',
      pending: !hasBp,
    },
    {
      key: 'spo2',
      label: 'SpO2',
      value: hasSpo2 ? fmt(values.spo2) : '待同步',
      unit: hasSpo2 ? '%' : undefined,
      hint: '夜间均值',
      icon: 'water-outline',
      color: HUES.blue.color,
      tint: HUES.blue.tint,
      route: '/sleep-spo2-analysis',
      pending: !hasSpo2,
    },
    {
      key: 'bmi',
      label: 'BMI',
      value: hasBmi ? fmt(values.bmi) : '待记录',
      hint: hasBmi ? bmiLabel(values.bmi!) : '体重 / 身高',
      icon: 'body-outline',
      color: HUES.green.color,
      tint: HUES.green.tint,
      route: '/body-measurements?focus=morning',
      pending: !hasBmi,
    },
    {
      key: 'fat',
      label: '体脂',
      value: hasFat ? fmt(values.bodyFatPct) : '待记录',
      unit: hasFat ? '%' : undefined,
      hint: '身材反馈',
      icon: 'fitness-outline',
      color: HUES.orange.color,
      tint: HUES.orange.tint,
      route: '/body-measurements?focus=morning',
      pending: !hasFat,
    },
  ];

  return (
    <View style={styles.row}>
      {tiles.map((t) => (
        <Pressable
          key={t.key}
          onPress={() => router.push(t.route as any)}
          style={({ pressed }) => [
            styles.tile,
            { opacity: pressed ? 0.78 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel={`${t.label} ${t.value}${t.unit ?? ''}`}
        >
          <View style={[styles.iconWrap, { backgroundColor: t.tint }]}>
            <Ionicons name={t.icon} size={13} color={t.color} />
          </View>
          <Text
            maxFontSizeMultiplier={1.18}
            style={[
              txt.value,
              {
                color: t.pending ? C.ink3 : C.ink1,
                fontSize: t.pending ? 12 : t.value.length > 5 ? 14 : 17,
              },
            ]}
            numberOfLines={1}
          >
            {t.value}
            {t.unit && !t.pending ? (
              <Text style={[txt.unit, { color: C.ink3 }]}> {t.unit}</Text>
            ) : null}
          </Text>
          <Text
            maxFontSizeMultiplier={1.18}
            style={[txt.label, { color: C.ink2 }]}
            numberOfLines={1}
          >
            {t.label}
          </Text>
          <Text
            maxFontSizeMultiplier={1.18}
            style={[txt.hint, { color: C.ink3 }]}
            numberOfLines={1}
          >
            {t.hint}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function bmiLabel(bmi: number): string {
  if (bmi < 18.5) return '偏瘦';
  if (bmi < 24) return '正常';
  if (bmi < 28) return '偏重';
  return '肥胖';
}

// Reva 设计语言:暖白 surface / r-lg 18 / 数字等宽 mono / light-first 软阴影。
const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: revaSpacing.s2,
    marginBottom: revaSpacing.s3,
  },
  tile: {
    flex: 1,
    minWidth: 0,
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 10,
    paddingVertical: 11,
    gap: 4,
    alignItems: 'flex-start',
    ...revaShadows.sm,
  },
  iconWrap: {
    width: 24,
    height: 24,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
});

// 数字(指标值 / 围度 / 单位)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  value: {
    fontFamily: revaFonts.mono,
    fontWeight: '800',
    letterSpacing: 0,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  unit: { fontFamily: revaFonts.mono, fontSize: 10, fontWeight: '700', letterSpacing: 0 } as TextStyle,
  label: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700' } as TextStyle,
  hint: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '500' } as TextStyle,
};
