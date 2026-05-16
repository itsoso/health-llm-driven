/**
 * DataBasisLine — "基于 X · N 小时前" 一行小标签 (T1.3 数据可信度 UI).
 *
 * 思路: AI 给建议时, 把它"看到了什么数据"显式露出, 让用户判断是新数据还是
 * 陈旧推断. 一行文字, 颜色随数据陈旧度变化:
 *   - <12h: brand 色 (新鲜, 信任)
 *   - 12-72h: amber (有点旧, 还能参考)
 *   - >72h: red + 加 "建议先补数据" 提示 (太旧, 别太信)
 *
 * 默认读 Twin freshness bucket. bucket 缺省时按 status 启发式选 (risk/attention
 * 多看 garmin, missing_data 看缺什么).
 */
import React, { useMemo } from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { getMyTwin, type TwinFreshness } from '../../services/twin';
import { queryKeys } from '../../applib/queryKeys';
import { ageTone, formatAge } from './dataBasisHelpers';

export type FreshnessBucket = keyof TwinFreshness; // 'garmin' | 'weight' | 'waist' | 'blood_pressure' | 'sleep' | 'labs' | 'diet' | 'genetic' | 'medication'

const BUCKET_LABEL: Record<FreshnessBucket, string> = {
  garmin: 'Garmin',
  weight: '体重',
  waist: '腰围',
  blood_pressure: '血压',
  sleep: '睡眠',
  labs: '化验',
  diet: '饮食',
  genetic: '基因',
  medication: '用药',
};

interface Props {
  /** 显示哪个 bucket. 缺省 = 'garmin' (大多数 specialist 建议都基于 Garmin) */
  bucket?: FreshnessBucket;
  /** 强制隐藏的 bucket (e.g. 不想显示太旧的化验数据) */
  hideBuckets?: FreshnessBucket[];
  /** 仅在数据存在时渲染. true = 缺数据也渲染 "数据缺失" warning */
  showWhenMissing?: boolean;
}

export default function DataBasisLine({
  bucket = 'garmin',
  hideBuckets,
  showWhenMissing = false,
}: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data: twin } = useQuery({
    queryKey: queryKeys.twin,
    queryFn: () => getMyTwin(),
    staleTime: 60_000,
  });

  if (hideBuckets?.includes(bucket)) return null;
  if (!twin?.freshness) return null;

  const raw = twin.freshness[bucket];
  const { hours, pretty } = formatAge(raw);
  const t = ageTone(hours);

  if (t === 'missing' && !showWhenMissing) return null;

  const palette = {
    fresh: { color: c.brand, icon: 'pulse-outline' as const, suffix: '' },
    stale: { color: c.amber, icon: 'time-outline' as const, suffix: '' },
    missing: {
      color: c.red,
      icon: 'alert-circle-outline' as const,
      suffix: hours === null ? '' : ' · 数据偏旧, 仅供参考',
    },
  }[t];

  return (
    <View style={styles.row}>
      <Ionicons name={palette.icon} size={11} color={palette.color} />
      <Text style={[styles.text, { color: palette.color }]}>
        基于 {BUCKET_LABEL[bucket]} · {pretty}
        {palette.suffix}
      </Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    row: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      marginTop: 6,
    },
    text: { fontSize: 11, fontWeight: '500' as const } as TextStyle,
  });
}

// helpers re-exported from dataBasisHelpers — 老的 __testHelpers shim 不再需要
