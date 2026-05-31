/**
 * MedicationSafetyAlerts —— 新增药物后的高危相互作用预警卡片 (Tier 0 ②).
 *
 * 后端在 POST /medication/medications 时即时跑 SafetyGuardian, 命中 DDI/DSI/PGx
 * high/critical 相互作用时把 safety_alerts 放进响应体. 本组件把它们显著展示出来,
 * 让用户在离开页面前就看到 —— 而不是等到 23:00 批量检测.
 *
 * 纯展示组件: 不含网络/导航逻辑, 便于单测. alerts 为空时返回 null.
 */
import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import { spacing, radii } from '../../constants/theme';
import type { MedicationSafetyAlert } from '../../services/medications';

function severityColor(label: string, c: ColorPalette): { fg: string; bg: string } {
  // critical 红, high 橙; 其余 (理论上不会传进来) 用 amber 兜底.
  if (label === 'critical') return { fg: c.red, bg: c.tintRed };
  if (label === 'high') return { fg: c.orange, bg: c.tintOrange };
  return { fg: c.amber, bg: c.tintAmber };
}

export default function MedicationSafetyAlerts({
  alerts,
}: {
  alerts: MedicationSafetyAlert[];
}) {
  const { c } = useTheme();
  const styles = createStyles(c);
  const txt = createTxt(c);

  if (!alerts || alerts.length === 0) return null;

  return (
    <View style={styles.wrap} accessibilityRole="alert" testID="med-safety-alerts">
      <View style={styles.bannerRow}>
        <Ionicons name="warning" size={20} color={c.red} />
        <Text style={txt.bannerTitle}>检测到 {alerts.length} 项用药相互作用风险</Text>
      </View>
      <Text style={txt.bannerHint}>药品已保存。以下风险请尽快与医生 / 药师确认，必要时调整方案。</Text>

      {alerts.map((a) => {
        const sc = severityColor(a.severity.label, c);
        return (
          <View key={a.rule_id} style={[styles.card, { borderLeftColor: sc.fg }]}>
            <View style={styles.cardHead}>
              <View style={[styles.badge, { backgroundColor: sc.bg }]}>
                <Text style={[txt.badgeText, { color: sc.fg }]}>{a.severity.label_zh}</Text>
              </View>
              <Text style={txt.cardTitle}>{a.title}</Text>
            </View>
            <Text style={txt.cardMsg}>{a.message}</Text>
            {!!a.action && <Text style={txt.cardAction}>建议：{a.action}</Text>}
            {a.requires_medical_attention && (
              <Text style={txt.medAttn}>⚠️ 建议联系医生评估</Text>
            )}
          </View>
        );
      })}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    wrap: {
      backgroundColor: c.tintRed,
      borderRadius: radii.md,
      padding: spacing.md,
      gap: spacing.sm,
    },
    bannerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      borderLeftWidth: 4,
      padding: spacing.md,
      gap: 6,
    },
    cardHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    badge: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: radii.sm,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    bannerTitle: { fontSize: 15, fontWeight: '700', color: c.red, flex: 1 } as TextStyle,
    bannerHint: { fontSize: 13, color: c.labelSecondary, lineHeight: 19 } as TextStyle,
    badgeText: { fontSize: 12, fontWeight: '700' } as TextStyle,
    cardTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    cardMsg: { fontSize: 13, color: c.labelSecondary, lineHeight: 19 } as TextStyle,
    cardAction: { fontSize: 13, color: c.labelPrimary, lineHeight: 19, fontWeight: '500' } as TextStyle,
    medAttn: { fontSize: 13, color: c.red, fontWeight: '600' } as TextStyle,
  };
}
