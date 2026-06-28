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
  title?: unknown;
  severity?: unknown;
  summary?: unknown;
  recommendations?: unknown;
  boundary?: unknown;
  requires_medical_attention?: unknown;
}

const DEFAULT_BOUNDARY = '这不是诊断；如出现急性不适或持续症状，请及时就医。';

function optionalText(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const text = value.trim();
    return text || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return undefined;
}

function normalizeSeverity(severity?: unknown): SafetySeverity {
  if (typeof severity !== 'string') return 'info';
  const normalized = severity.trim().toLowerCase();
  return ['info', 'low', 'medium', 'high', 'critical'].includes(normalized)
    ? normalized
    : 'info';
}

function normalizeRecommendations(value: unknown): string[] {
  const items = Array.isArray(value) ? value : value == null ? [] : [value];
  return items
    .map((item) => optionalText(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, 3);
}

function severityMeta(severity?: unknown): { label: string; fg: string; bg: string; icon: string } {
  const normalized = normalizeSeverity(severity);
  switch (normalized) {
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
  recommendations,
  boundary,
  requires_medical_attention,
}: SafetyCardData) {
  const normalizedSeverity = normalizeSeverity(severity);
  const meta = severityMeta(normalizedSeverity);
  const safeTitle = optionalText(title) || '安全提醒';
  const safeSummary = optionalText(summary);
  const safeBoundary = optionalText(boundary) || DEFAULT_BOUNDARY;
  const visibleRecommendations = normalizeRecommendations(recommendations);
  const requiresAttention = requires_medical_attention === true || normalizedSeverity === 'critical';

  return (
    <CardShell
      icon={meta.icon}
      iconColor={meta.fg}
      title={safeTitle}
      badge={meta.label}
      badgeColor={meta.fg}
      bg={meta.bg}
    >
      {safeSummary ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.summary}>
          {safeSummary}
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

      {requiresAttention ? (
        <View style={styles.attention}>
          <Ionicons name="medkit-outline" size={12} color={revaSemantic.risk.fg} />
          <Text maxFontSizeMultiplier={1.3} style={styles.attentionText}>
            需要关注
          </Text>
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.3} style={styles.boundary}>
        {safeBoundary}
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
