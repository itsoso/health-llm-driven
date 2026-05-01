import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, spacing } from '../../constants/theme';
import type { TodayCoachFocus } from '../../services/todayCoach';
import DashboardCard from './DashboardCard';

interface Props {
  focus?: TodayCoachFocus;
  isLoading?: boolean;
  onAction: (focus: TodayCoachFocus) => void;
}

const STATUS_META: Record<TodayCoachFocus['status'], {
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  label: string;
}> = {
  ok:           { icon: 'checkmark-circle', color: '#0A8F8F', bg: '#E6F5F5', label: '稳定' },
  attention:    { icon: 'radio-button-on',  color: '#007AFF', bg: '#E6F0FF', label: '执行中' },
  risk:         { icon: 'alert-circle',     color: '#FF453A', bg: '#FFE8E6', label: '优先处理' },
  missing_data: { icon: 'cloud-offline',    color: '#FF9F0A', bg: '#FFF5E6', label: '补数据' },
};

export default function TodayCoachPanel({ focus, isLoading, onAction }: Props) {
  if (isLoading && !focus) {
    return (
      <DashboardCard
        icon="hourglass-outline"
        kicker="今日重点"
        title="判断中…"
      >
        <ActivityIndicator size="small" color={colors.brand} />
      </DashboardCard>
    );
  }
  if (!focus) return null;

  const meta = STATUS_META[focus.status];
  const trailing = focus.verifyBy ? (
    <Text style={txt.verify}>{focus.verifyBy.slice(5, 10)}</Text>
  ) : undefined;

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
      <Text style={txt.reason} numberOfLines={3}>{focus.reason}</Text>

      {/* evidence: 至少 2 个有 tone 的数据点才展示 */}
      {focus.evidence.filter(e => e.tone).length >= 2 ? (
        <View style={styles.evidenceRow}>
          {focus.evidence.filter(e => e.tone).slice(0, 3).map(item => (
            <View key={`${item.label}-${item.value}`} style={styles.evidencePill}>
              <Text style={txt.evidenceLabel} numberOfLines={1}>{item.label}</Text>
              <Text
                style={[
                  txt.evidenceValue,
                  item.tone === 'bad'  && { color: '#FF453A' },
                  item.tone === 'warn' && { color: '#FF9F0A' },
                  item.tone === 'good' && { color: '#0A8F8F' },
                ]}
                numberOfLines={1}
              >{item.value}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* 短 CTA: 直接按钮; 长建议: 拆成 advice box + 短按钮 */}
      {focus.actionLabel && focus.actionLabel.length <= 20 ? (
        <Pressable
          style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
          onPress={() => onAction(focus)}
          accessibilityRole="button"
          accessibilityLabel={focus.actionLabel}
        >
          <Text style={txt.action} numberOfLines={1}>{focus.actionLabel}</Text>
          <Ionicons name="arrow-forward" size={15} color="#fff" />
        </Pressable>
      ) : focus.actionLabel ? (
        <>
          <View style={styles.adviceBox}>
            <Text style={txt.adviceLabel}>💡 建议</Text>
            <Text style={txt.adviceBody}>{focus.actionLabel}</Text>
          </View>
          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
            onPress={() => onAction(focus)}
            accessibilityRole="button"
            accessibilityLabel="查看详情"
          >
            <Text style={txt.action}>查看详情</Text>
            <Ionicons name="arrow-forward" size={15} color="#fff" />
          </Pressable>
        </>
      ) : null}
    </DashboardCard>
  );
}

const styles = StyleSheet.create({
  evidenceRow: { flexDirection: 'row', gap: 8 },
  evidencePill: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: colors.bgPrimary,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  actionBtn: {
    minHeight: 40,
    borderRadius: radii.md,
    backgroundColor: colors.brand,
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
    backgroundColor: colors.bgPrimary,
    borderRadius: radii.sm,
    borderLeftWidth: 3,
    borderLeftColor: colors.brand,
  },
});

const txt = {
  verify: { fontSize: 11, color: colors.labelTertiary, fontWeight: '600' as const } as TextStyle,
  reason: { fontSize: 13, color: colors.labelSecondary, lineHeight: 19 } as TextStyle,
  evidenceLabel: { fontSize: 10, color: colors.labelTertiary, marginBottom: 2 } as TextStyle,
  evidenceValue: { fontSize: 13, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  action: { fontSize: 14, fontWeight: '700', color: '#fff', flexShrink: 1 } as TextStyle,
  adviceLabel: { fontSize: 11, fontWeight: '700', color: colors.brand, marginBottom: 4 } as TextStyle,
  adviceBody: { fontSize: 13, color: colors.labelPrimary, lineHeight: 19 } as TextStyle,
};
