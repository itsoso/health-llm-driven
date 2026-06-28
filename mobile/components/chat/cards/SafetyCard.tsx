import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';

type SafetySeverity = 'info' | 'low' | 'medium' | 'high' | 'critical' | string;

interface SafetyCardData {
  title?: string;
  severity?: SafetySeverity;
  summary?: string;
  recommendations?: string[];
  boundary?: string;
  requires_medical_attention?: boolean;
}

function severityMeta(severity?: SafetySeverity): { label: string; fg: string; bg: string; icon: string } {
  switch (severity) {
    case 'critical':
      return { label: '紧急风险', fg: revaSemantic.risk.fg, bg: revaSemantic.risk.bg, icon: 'warning-outline' };
    case 'high':
      return { label: '高风险', fg: revaSemantic.risk.fg, bg: revaSemantic.risk.bg, icon: 'alert-circle-outline' };
    case 'medium':
      return { label: '注意', fg: revaSemantic.caution.fg, bg: revaSemantic.caution.bg, icon: 'shield-half-outline' };
    case 'low':
      return { label: '低风险', fg: C.blue500, bg: C.blue50, icon: 'information-circle-outline' };
    case 'info':
    default:
      return { label: '安全提示', fg: C.blue500, bg: C.blue50, icon: 'shield-checkmark-outline' };
  }
}

export function SafetyCardView({
  title,
  severity = 'info',
  summary,
  recommendations = [],
  boundary,
  requires_medical_attention,
}: SafetyCardData) {
  const meta = severityMeta(severity);
  const visibleRecommendations = recommendations.filter(Boolean).slice(0, 3);

  return (
    <CardShell
      icon={meta.icon}
      iconColor={meta.fg}
      title={title || '安全提醒'}
      badge={meta.label}
      badgeColor={meta.fg}
      bg={meta.bg}
    >
      {summary ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.summary}>
          {summary}
        </Text>
      ) : null}

      {visibleRecommendations.length > 0 ? (
        <View style={styles.recommendations}>
          {visibleRecommendations.map((item, index) => (
            <View key={`${item}-${index}`} style={styles.recommendationItem}>
              <Ionicons name="checkmark-circle-outline" size={12} color={meta.fg} />
              <Text maxFontSizeMultiplier={1.3} style={styles.recommendationText} numberOfLines={2}>
                {item}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {requires_medical_attention ? (
        <View style={styles.attention}>
          <Ionicons name="medkit-outline" size={12} color={revaSemantic.risk.fg} />
          <Text maxFontSizeMultiplier={1.3} style={styles.attentionText}>
            需要关注
          </Text>
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.3} style={styles.boundary}>
        {boundary || '这不是诊断；如出现急性不适或持续症状，请及时就医。'}
      </Text>
    </CardShell>
  );
}

export const SafetyCardSpec: CardSpec<SafetyCardData> = {
  type: 'safety',
  label: '安全提醒',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <SafetyCardView {...data} />,
};

const styles = StyleSheet.create({
  summary: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '700',
    color: C.ink1,
    lineHeight: 19,
  } as TextStyle,
  recommendations: {
    marginTop: 9,
    gap: 6,
  },
  recommendationItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  recommendationText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink2,
    lineHeight: 16,
  } as TextStyle,
  attention: {
    alignSelf: 'flex-start',
    marginTop: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
  },
  attentionText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '800',
    color: revaSemantic.risk.fg,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
});
