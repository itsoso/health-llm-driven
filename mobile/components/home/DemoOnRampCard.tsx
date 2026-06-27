import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';
import { Icon } from '../reva/RevaKit';
import type { DemoOnRampRuntime } from '../../services/demoOnRamp';

interface DemoOnRampCardProps {
  runtime: DemoOnRampRuntime;
  onOpenDemo: () => void;
  onConnectHealthKit: () => void;
}

const MILESTONE_ICON: Record<string, string> = {
  safety_brain: 'shield',
  evidence_card: 'file-text',
  top_action: 'check-circle-2',
};

export default function DemoOnRampCard({
  runtime,
  onOpenDemo,
  onConnectHealthKit,
}: DemoOnRampCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.titleBlock}>
          <Text style={styles.overline}>5 分钟示例体验</Text>
          <Text style={styles.title}>先看 Reva 如何运行</Text>
          <Text style={styles.subtitle}>{runtime.sourceLabel}</Text>
        </View>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>DEMO</Text>
        </View>
      </View>

      <View style={styles.milestones}>
        {runtime.milestones.map(item => (
          <View key={item.key} style={styles.milestone}>
            <View style={styles.milestoneIcon}>
              <Icon name={MILESTONE_ICON[item.key] ?? 'sparkles'} size={16} color={C.green600} />
            </View>
            <View style={styles.milestoneCopy}>
              <Text style={styles.milestoneTitle}>{item.title}</Text>
              <Text style={styles.milestoneDescription} numberOfLines={2}>{item.description}</Text>
            </View>
          </View>
        ))}
      </View>

      <View style={styles.actionRow}>
        <Pressable
          onPress={onOpenDemo}
          accessibilityRole="button"
          accessibilityLabel="打开 Reva 示例体验"
          style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
        >
          <Icon name="messages-square" size={16} color={C.greenOn} />
          <Text style={styles.primaryButtonText}>打开示例体验</Text>
        </Pressable>
        <Pressable
          onPress={onConnectHealthKit}
          accessibilityRole="button"
          accessibilityLabel="连接 HealthKit"
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
        >
          <Text style={styles.secondaryButtonText}>连接 HealthKit</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.xl,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 18,
    gap: revaSpacing.s4,
    ...revaShadows.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s3,
  },
  titleBlock: { flex: 1, minWidth: 0 },
  overline: {
    fontFamily: 'IBMPlexMono',
    fontSize: 10.5,
    letterSpacing: 0.9,
    color: C.green600,
  },
  title: {
    fontFamily: 'Manrope',
    fontSize: 19,
    lineHeight: 24,
    fontWeight: '800',
    color: C.ink1,
    marginTop: 3,
  },
  subtitle: { fontSize: 13, lineHeight: 18, color: C.ink2, marginTop: 4 },
  badge: {
    borderRadius: revaRadii.pill,
    backgroundColor: revaSemantic.info.bg,
    borderWidth: 1,
    borderColor: revaSemantic.info.line,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  badgeText: {
    fontFamily: 'IBMPlexMono',
    fontSize: 10.5,
    fontWeight: '700',
    color: revaSemantic.info.fg,
  },
  milestones: { gap: revaSpacing.s2 },
  milestone: {
    flexDirection: 'row',
    gap: revaSpacing.s2,
    alignItems: 'center',
    borderRadius: revaRadii.md,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 12,
  },
  milestoneIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  milestoneCopy: { flex: 1, minWidth: 0 },
  milestoneTitle: { fontSize: 14, lineHeight: 18, fontWeight: '800', color: C.ink1 },
  milestoneDescription: { fontSize: 12.5, lineHeight: 17, color: C.ink2, marginTop: 2 },
  actionRow: { flexDirection: 'row', gap: revaSpacing.s2 },
  primaryButton: {
    flex: 1.1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: revaRadii.md,
    backgroundColor: C.green500,
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  secondaryButton: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  pressed: { opacity: 0.78 },
  primaryButtonText: { color: C.greenOn, fontSize: 14, fontWeight: '800' },
  secondaryButtonText: { color: C.green600, fontSize: 14, fontWeight: '800' },
});
