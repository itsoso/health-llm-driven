/**
 * BodyStatsRow —— 首页"基础体征"四宫格 (2026-05-28 重设计加回).
 *
 * 显示血压 / SpO2 / BMI / 体脂; 单卡可点击进入对应历史页.
 * 数据缺失时显示"待记录", 引导用户去补 — 不掩盖空状态.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../hooks/useTheme';
import { spacing, radii } from '../../constants/theme';

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
  const { c, isDark } = useTheme();

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
      color: c.pink,
      tint: c.tintPink,
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
      color: c.blue,
      tint: c.tintBlue,
      route: '/sleep-spo2-analysis',
      pending: !hasSpo2,
    },
    {
      key: 'bmi',
      label: 'BMI',
      value: hasBmi ? fmt(values.bmi) : '待记录',
      hint: hasBmi ? bmiLabel(values.bmi!) : '体重 / 身高',
      icon: 'body-outline',
      color: c.green,
      tint: c.tintGreen,
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
      color: c.orange,
      tint: c.tintOrange,
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
            {
              backgroundColor: c.bgCard,
              borderColor: c.separator,
              opacity: pressed ? 0.78 : 1,
            },
            isDark
              ? null
              : {
                  shadowColor: '#000',
                  shadowOffset: { width: 0, height: 1 },
                  shadowOpacity: 0.05,
                  shadowRadius: 3,
                  elevation: 1,
                },
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
              styles.value,
              {
                color: t.pending ? c.labelTertiary : c.labelPrimary,
                fontSize: t.pending ? 12 : t.value.length > 5 ? 14 : 17,
              },
            ]}
            numberOfLines={1}
          >
            {t.value}
            {t.unit && !t.pending ? (
              <Text style={[styles.unit, { color: c.labelTertiary }]}> {t.unit}</Text>
            ) : null}
          </Text>
          <Text
            maxFontSizeMultiplier={1.18}
            style={[styles.label, { color: c.labelSecondary }]}
            numberOfLines={1}
          >
            {t.label}
          </Text>
          <Text
            maxFontSizeMultiplier={1.18}
            style={[styles.hint, { color: c.labelTertiary }]}
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

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  tile: {
    flex: 1,
    minWidth: 0,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 10,
    paddingVertical: 11,
    gap: 4,
    alignItems: 'flex-start',
  },
  iconWrap: {
    width: 24,
    height: 24,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
  value: {
    fontWeight: '800',
    letterSpacing: -0.3,
    fontVariant: ['tabular-nums'],
  },
  unit: { fontSize: 10, fontWeight: '700' },
  label: { fontSize: 11, fontWeight: '700' },
  hint: { fontSize: 10, fontWeight: '500' },
});
