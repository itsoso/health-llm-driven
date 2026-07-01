import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { SafetyAlert } from '../../services/safety';
import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaShadows,
} from '../../constants/revaTheme';
import { Icon } from '../reva/RevaKit';

export default function TodaySafetyAlertCard({
  alert,
  alertCount = 1,
  onPress,
}: {
  alert: SafetyAlert;
  alertCount?: number;
  onPress: () => void;
}) {
  const severity = severityKey(alert.severity);
  const urgent = severity === 'critical';
  return (
    <Pressable
      style={({ pressed }) => [styles.card, urgent && styles.criticalCard, pressed && styles.pressed]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel="查看安全提醒详情"
    >
      <View style={styles.header}>
        <View style={[styles.iconWrap, urgent && styles.criticalIconWrap]}>
          <Icon name="alert-triangle" size={16} color={urgent ? revaSemantic.risk.fg : revaSemantic.caution.fg} />
        </View>
        <Text style={[styles.overline, urgent && styles.criticalOverline]}>安全提醒</Text>
        {alertCount > 1 ? (
          <View style={styles.countPill}>
            <Text style={styles.countText}>{alertCount} 条</Text>
          </View>
        ) : null}
      </View>

      <Text style={styles.title} numberOfLines={2}>{alert.title}</Text>
      {alert.message ? (
        <Text style={styles.message} numberOfLines={2}>{alert.message}</Text>
      ) : null}
      {alert.action ? (
        <View style={styles.actionRow}>
          <Icon name="chevron-right" size={14} color={C.green600} />
          <Text style={styles.actionText} numberOfLines={2}>{alert.action}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

function severityKey(value: unknown): string {
  return typeof value === 'string' ? value : (value as { label?: string } | null)?.label ?? 'info';
}

const styles = StyleSheet.create({
  card: {
    borderRadius: revaRadii.lg,
    backgroundColor: revaSemantic.caution.bg,
    borderWidth: 1,
    borderColor: revaSemantic.caution.line,
    padding: 16,
    gap: 9,
    ...revaShadows.sm,
  },
  criticalCard: {
    backgroundColor: revaSemantic.risk.bg,
    borderColor: revaSemantic.risk.line,
  },
  pressed: { opacity: 0.86 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  iconWrap: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
  },
  criticalIconWrap: { backgroundColor: 'rgba(255,255,255,0.72)' },
  overline: {
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
    color: revaSemantic.caution.fg,
  },
  criticalOverline: { color: revaSemantic.risk.fg },
  countPill: {
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.72)',
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  countText: { fontSize: 11, fontWeight: '900', color: C.ink2 },
  title: { fontSize: 17, lineHeight: 23, fontWeight: '900', color: C.ink1 },
  message: { fontSize: 13, lineHeight: 19, color: C.ink2 },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  actionText: { flex: 1, fontSize: 13, lineHeight: 18, fontWeight: '800', color: C.green700 },
});
