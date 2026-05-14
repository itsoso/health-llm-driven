import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import {
  pickPrimaryTrajectoryRisks,
  type HealthTrajectorySnapshot,
  type TrajectoryRisk,
} from '../../services/trajectory';

const LEVEL_LABEL: Record<string, string> = {
  high: '高',
  attention: '关注',
  unknown: '缺数据',
  ok: '稳定',
};

const LEVEL_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  metabolic_health: 'pulse-outline',
  recovery_capacity: 'battery-charging-outline',
  aging_pace: 'hourglass-outline',
};

function riskColor(level: string, c: ReturnType<typeof useTheme>['c']) {
  if (level === 'high') return { bg: c.tintRed, fg: c.red };
  if (level === 'attention') return { bg: c.tintAmber, fg: c.amber };
  if (level === 'ok') return { bg: c.tintGreen, fg: c.green };
  return { bg: c.fill, fg: c.labelSecondary };
}

function RiskRow({ risk }: { risk: TrajectoryRisk }) {
  const { c } = useTheme();
  const color = riskColor(risk.level, c);
  return (
    <View style={[styles.riskRow, { borderColor: c.separator }]}>
      <View style={[styles.riskIcon, { backgroundColor: color.bg }]}>
        <Ionicons name={LEVEL_ICON[risk.domain] ?? 'analytics-outline'} size={15} color={color.fg} />
      </View>
      <View style={styles.riskText}>
        <Text style={[styles.riskTitle, { color: c.labelPrimary }]} numberOfLines={1}>
          {risk.title}
        </Text>
        {risk.primary_action ? (
          <Text style={[styles.riskAction, { color: c.labelSecondary }]} numberOfLines={2}>
            {risk.primary_action}
          </Text>
        ) : null}
      </View>
      <Text style={[styles.level, { color: color.fg }]}>{LEVEL_LABEL[risk.level] ?? risk.level}</Text>
    </View>
  );
}

export default function TrajectorySnapshotPanel({
  snapshot,
  loading,
  onPress,
}: {
  snapshot?: HealthTrajectorySnapshot | null;
  loading?: boolean;
  onPress?: () => void;
}) {
  const { c } = useTheme();
  const risks = pickPrimaryTrajectoryRisks(snapshot?.trajectory_risks ?? [], 3);
  const gapCount = snapshot?.data_gaps?.length ?? 0;

  return (
    <TouchableOpacity
      style={[styles.container, { backgroundColor: c.bgCard, borderColor: c.separator }]}
      activeOpacity={0.82}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel="健康轨迹"
    >
      <View style={styles.header}>
        <View style={[styles.headerIcon, { backgroundColor: c.tintPurple }]}>
          <Ionicons name="git-branch-outline" size={17} color={c.purple} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: c.labelPrimary }]}>健康轨迹</Text>
          <Text style={[styles.subtitle, { color: c.labelTertiary }]}>
            {loading ? '正在读取轨迹' : '疾病上游 · 90 天视角'}
          </Text>
        </View>
        {gapCount > 0 ? (
          <Text style={[styles.gap, { color: c.labelSecondary }]}>{gapCount} 个缺口</Text>
        ) : null}
      </View>

      {risks.length === 0 ? (
        <Text style={[styles.empty, { color: c.labelTertiary }]}>暂无轨迹快照, 下拉刷新后重试。</Text>
      ) : (
        <View style={styles.list}>
          {risks.map(risk => (
            <RiskRow key={`${risk.domain}-${risk.level}`} risk={risk} />
          ))}
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  headerIcon: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerText: { flex: 1, gap: 2 },
  title: { fontSize: 16, fontWeight: '700' },
  subtitle: { fontSize: 12, fontWeight: '500' },
  gap: { fontSize: 12, fontWeight: '700' },
  list: { gap: spacing.sm },
  riskRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    padding: spacing.sm,
    gap: spacing.sm,
  },
  riskIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  riskText: { flex: 1, gap: 2 },
  riskTitle: { fontSize: 14, fontWeight: '700' },
  riskAction: { fontSize: 12, lineHeight: 16 },
  level: { fontSize: 12, fontWeight: '800' },
  empty: { fontSize: 13, textAlign: 'center', paddingVertical: spacing.sm },
});
