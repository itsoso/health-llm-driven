import React, { useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { TodayCoachFocus } from '../../services/todayCoach';
import DataBasisLine, { type FreshnessBucket } from '../common/DataBasisLine';
import DashboardCard from './DashboardCard';

interface Props {
  focus?: TodayCoachFocus;
  isLoading?: boolean;
  onAction: (focus: TodayCoachFocus) => void;
}

// status 元数据 — 颜色在 dark mode 下用同色但 tint 走暗
function statusMeta(status: TodayCoachFocus['status'], c: ColorPalette) {
  switch (status) {
    case 'ok':
      return { icon: 'checkmark-circle' as const, color: c.brand,  bg: c.brandLight, label: '稳定' };
    case 'attention':
      return { icon: 'radio-button-on' as const, color: '#0A84FF', bg: c.tintBlue,   label: '执行中' };
    case 'risk':
      return { icon: 'alert-circle' as const,    color: c.red,     bg: c.tintRed,    label: '优先处理' };
    case 'missing_data':
      return { icon: 'cloud-offline' as const,   color: c.amber,   bg: c.tintAmber,  label: '补数据' };
  }
}

export default function TodayCoachPanel({ focus, isLoading, onAction }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  if (isLoading && !focus) {
    return (
      <DashboardCard
        icon="hourglass-outline"
        kicker="今日重点"
        title="判断中…"
      >
        <ActivityIndicator size="small" color={c.brand} />
      </DashboardCard>
    );
  }
  if (!focus) return null;

  const meta = statusMeta(focus.status, c);
  const trailing = focus.verifyBy ? (
    <Text style={[styles.verify, { color: c.labelTertiary }]}>{focus.verifyBy.slice(5, 10)}</Text>
  ) : undefined;

  // T1.3 数据可信度: 按 status 启发式选 bucket. 缺数据态去掉 (没有"基于"可言)
  const dataBasisBucket: FreshnessBucket | null =
    focus.status === 'missing_data' ? null : 'garmin';

  return (
    <DashboardCard
      icon={meta.icon}
      iconTint={meta.bg}
      iconColor={meta.color}
      kicker={meta.label}
      kickerColor={meta.color}
      title={focus.title}
      collapsible
      defaultCollapsed={false}
      trailing={trailing}
      accessibilityLabel="今日重点"
    >
      <Text style={[styles.reason, { color: c.labelSecondary }]} numberOfLines={3}>{focus.reason}</Text>

      {focus.evidence.filter(e => e.tone).length >= 2 ? (
        <View style={styles.evidenceRow}>
          {focus.evidence.filter(e => e.tone).slice(0, 3).map(item => (
            <View key={`${item.label}-${item.value}`} style={[styles.evidencePill, { backgroundColor: c.bgPrimary }]}>
              <Text style={[styles.evidenceLabel, { color: c.labelTertiary }]} numberOfLines={1}>{item.label}</Text>
              <Text
                style={[
                  styles.evidenceValue,
                  { color: c.labelPrimary },
                  item.tone === 'bad'  && { color: c.red },
                  item.tone === 'warn' && { color: c.amber },
                  item.tone === 'good' && { color: c.brand },
                ]}
                numberOfLines={1}
              >{item.value}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {focus.actionLabel && focus.actionLabel.length <= 20 ? (
        <Pressable
          style={({ pressed }) => [styles.actionBtn, { backgroundColor: c.brand }, pressed && styles.actionBtnPressed]}
          onPress={() => onAction(focus)}
          accessibilityRole="button"
          accessibilityLabel={focus.actionLabel}
        >
          <Text style={styles.action} numberOfLines={1}>{focus.actionLabel}</Text>
          <Ionicons name="arrow-forward" size={15} color="#fff" />
        </Pressable>
      ) : focus.actionLabel ? (
        <>
          <View style={[styles.adviceBox, { backgroundColor: c.bgPrimary, borderLeftColor: c.brand }]}>
            <Text style={[styles.adviceLabel, { color: c.brand }]}>💡 建议</Text>
            <Text style={[styles.adviceBody, { color: c.labelPrimary }]}>{focus.actionLabel}</Text>
          </View>
          <Pressable
            style={({ pressed }) => [styles.actionBtn, { backgroundColor: c.brand }, pressed && styles.actionBtnPressed]}
            onPress={() => onAction(focus)}
            accessibilityRole="button"
            accessibilityLabel="查看详情"
          >
            <Text style={styles.action}>查看详情</Text>
            <Ionicons name="arrow-forward" size={15} color="#fff" />
          </Pressable>
        </>
      ) : null}

      {dataBasisBucket && <DataBasisLine bucket={dataBasisBucket} />}
    </DashboardCard>
  );
}

function createStyles(_c: ColorPalette) {
  return StyleSheet.create({
    evidenceRow: { flexDirection: 'row', gap: 8 },
    evidencePill: {
      flex: 1,
      minHeight: 44,
      borderRadius: radii.sm,
      paddingHorizontal: 10,
      paddingVertical: 7,
    },
    actionBtn: {
      minHeight: 40,
      borderRadius: radii.md,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      paddingHorizontal: spacing.md,
      paddingVertical: 8,
      overflow: 'hidden',
      alignSelf: 'stretch',
    },
    actionBtnPressed: { opacity: 0.82 },
    adviceBox: {
      padding: spacing.sm + 2,
      borderRadius: radii.sm,
      borderLeftWidth: 3,
    },
    verify: { fontSize: 11, fontWeight: '600' as const } as TextStyle,
    reason: { fontSize: 13, lineHeight: 19 } as TextStyle,
    evidenceLabel: { fontSize: 10, marginBottom: 2 } as TextStyle,
    evidenceValue: { fontSize: 13, fontWeight: '700' } as TextStyle,
    action: { fontSize: 14, fontWeight: '700', color: '#fff', flexShrink: 1 } as TextStyle,
    adviceLabel: { fontSize: 11, fontWeight: '700', marginBottom: 4 } as TextStyle,
    adviceBody: { fontSize: 13, lineHeight: 19 } as TextStyle,
  });
}
