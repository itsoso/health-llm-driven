import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadows, spacing } from '../../constants/theme';
import type { TodayCoachFocus } from '../../services/todayCoach';

interface Props {
  focus?: TodayCoachFocus;
  isLoading?: boolean;
  onAction: (focus: TodayCoachFocus) => void;
}

const STATUS_META: Record<TodayCoachFocus['status'], { icon: keyof typeof Ionicons.glyphMap; color: string; bg: string; label: string }> = {
  ok: { icon: 'checkmark-circle', color: '#0A8F8F', bg: '#E6F5F5', label: '稳定' },
  attention: { icon: 'radio-button-on', color: '#007AFF', bg: '#E6F0FF', label: '执行中' },
  risk: { icon: 'alert-circle', color: '#FF453A', bg: '#FFE8E6', label: '优先处理' },
  missing_data: { icon: 'cloud-offline', color: '#FF9F0A', bg: '#FFF5E6', label: '补数据' },
};

export default function TodayCoachPanel({ focus, isLoading, onAction }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  if (isLoading && !focus) {
    return (
      <View style={styles.panel}>
        <ActivityIndicator size="small" color={colors.brand} />
        <Text style={txt.loading}>正在判断今日重点...</Text>
      </View>
    );
  }

  if (!focus) return null;

  const meta = STATUS_META[focus.status];
  const toggle = () => {
    Haptics.selectionAsync();
    setCollapsed(v => !v);
  };

  // collapsed 态整卡片可点展开; expanded 态只头部可点 (留空间给 actionBtn)
  const CardWrapper: any = collapsed ? Pressable : View;
  const wrapperProps = collapsed
    ? { onPress: toggle, accessibilityRole: 'button' as const, accessibilityLabel: '展开今日重点' }
    : {};

  return (
    <CardWrapper style={styles.panel} {...wrapperProps}>
      <Pressable
        onPress={toggle}
        style={({ pressed }) => [styles.topRow, pressed && styles.topRowPressed]}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={collapsed ? '展开今日重点' : '收起今日重点'}
      >
        <View style={[styles.iconWrap, { backgroundColor: meta.bg }]}>
          <Ionicons name={meta.icon} size={18} color={meta.color} />
        </View>
        <View style={styles.titleBlock}>
          <View style={styles.kickerRow}>
            <Text style={[txt.kicker, { color: meta.color }]}>{meta.label}</Text>
            {focus.verifyBy ? <Text style={txt.verify}>验证 {focus.verifyBy.slice(0, 10)}</Text> : null}
          </View>
          <Text style={txt.title} numberOfLines={collapsed ? 1 : 2}>{focus.title}</Text>
        </View>
        {/* 明显的 chevron 按钮 — 圆形背景 + brand 色 */}
        <View style={styles.chevronBtn}>
          <Ionicons
            name={collapsed ? 'chevron-down' : 'chevron-up'}
            size={20}
            color={colors.brand}
          />
        </View>
      </Pressable>

      {!collapsed && (
        <>
          <Text style={txt.reason} numberOfLines={3}>{focus.reason}</Text>

          {focus.evidence.length > 0 ? (
            <View style={styles.evidenceRow}>
              {focus.evidence.slice(0, 3).map(item => (
                <View key={`${item.label}-${item.value}`} style={styles.evidencePill}>
                  <Text style={txt.evidenceLabel}>{item.label}</Text>
                  <Text style={[
                    txt.evidenceValue,
                    item.tone === 'bad' && { color: '#FF453A' },
                    item.tone === 'warn' && { color: '#FF9F0A' },
                    item.tone === 'good' && { color: '#0A8F8F' },
                  ]}>{item.value}</Text>
                </View>
              ))}
            </View>
          ) : null}

          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
            onPress={() => onAction(focus)}
            accessibilityRole="button"
            accessibilityLabel={focus.actionLabel}
          >
            <Text style={txt.action} numberOfLines={2}>{focus.actionLabel}</Text>
            <Ionicons name="arrow-forward" size={15} color="#fff" />
          </Pressable>
        </>
      )}
    </CardWrapper>
  );
}

const styles = StyleSheet.create({
  panel: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.md,
    ...shadows.subtle,
  },
  topRow: { flexDirection: 'row', gap: 10, alignItems: 'center', minHeight: 44 },
  topRowPressed: { opacity: 0.6 },
  iconWrap: { width: 34, height: 34, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  titleBlock: { flex: 1 },
  kickerRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 2 },
  chevronBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: 'rgba(10, 143, 143, 0.1)',
    alignItems: 'center', justifyContent: 'center',
  },
  evidenceRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  evidencePill: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: colors.bgPrimary,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  actionBtn: {
    marginTop: 12,
    minHeight: 40,
    borderRadius: radii.md,
    backgroundColor: colors.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
  actionBtnPressed: { opacity: 0.82 },
});

const txt = {
  loading: { marginTop: 8, fontSize: 13, color: colors.labelSecondary } as TextStyle,
  kicker: { fontSize: 11, fontWeight: '700' } as TextStyle,
  verify: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  title: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, lineHeight: 22 } as TextStyle,
  reason: { fontSize: 13, color: colors.labelSecondary, lineHeight: 19, marginTop: 10 } as TextStyle,
  evidenceLabel: { fontSize: 10, color: colors.labelTertiary, marginBottom: 2 } as TextStyle,
  evidenceValue: { fontSize: 13, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  action: { fontSize: 14, fontWeight: '700', color: '#fff', flexShrink: 1, textAlign: 'center' } as TextStyle,
};
