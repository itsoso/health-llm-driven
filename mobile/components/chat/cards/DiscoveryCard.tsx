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

type DiscoveryLevel = 'observation' | 'hypothesis' | 'validated_effect' | 'clinician_review' | string;

interface DiscoveryCardData {
  title?: string;
  level?: DiscoveryLevel;
  summary?: string;
  evidence?: string[];
  boundary?: string;
}

function levelMeta(level?: DiscoveryLevel): { label: string; fg: string; bg: string; icon: string } {
  switch (level) {
    case 'validated_effect':
      return { label: '已验证', fg: C.green500, bg: C.green50, icon: 'checkmark-circle-outline' };
    case 'clinician_review':
      return { label: '需复核', fg: revaSemantic.caution.fg, bg: revaSemantic.caution.bg, icon: 'medkit-outline' };
    case 'hypothesis':
      return { label: '待验证', fg: revaSemantic.caution.fg, bg: revaSemantic.caution.bg, icon: 'flask-outline' };
    case 'observation':
    default:
      return { label: '观察', fg: C.blue500, bg: C.blue50, icon: 'analytics-outline' };
  }
}

export function DiscoveryCardView({
  title,
  level = 'observation',
  summary,
  evidence = [],
  boundary,
}: DiscoveryCardData) {
  const meta = levelMeta(level);
  const visibleEvidence = evidence.filter(Boolean).slice(0, 3);

  return (
    <CardShell
      icon="sparkles-outline"
      iconColor={meta.fg}
      title={title || '新的健康发现'}
      badge={meta.label}
      badgeColor={meta.fg}
      bg={meta.bg}
    >
      {summary ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.summary}>
          {summary}
        </Text>
      ) : null}

      {visibleEvidence.length > 0 ? (
        <View style={styles.evidenceList}>
          {visibleEvidence.map((item, index) => (
            <View key={`${item}-${index}`} style={styles.evidenceItem}>
              <Ionicons name={meta.icon as any} size={12} color={meta.fg} />
              <Text maxFontSizeMultiplier={1.3} style={styles.evidenceText} numberOfLines={2}>
                {item}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.3} style={styles.boundary}>
        {boundary || defaultBoundary(level)}
      </Text>
    </CardShell>
  );
}

function defaultBoundary(level?: DiscoveryLevel): string {
  if (level === 'validated_effect') {
    return '基于已记录数据的个人模式，仍不替代医疗判断。';
  }
  if (level === 'clinician_review') {
    return '涉及医疗判断或高风险指标，需要专业人员复核。';
  }
  return '观察性线索，不代表因果已经验证。';
}

export const DiscoveryCardSpec: CardSpec<DiscoveryCardData> = {
  type: 'discovery',
  label: '健康发现',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <DiscoveryCardView {...data} />,
};

const styles = StyleSheet.create({
  summary: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '700',
    color: C.ink1,
    lineHeight: 19,
  } as TextStyle,
  evidenceList: {
    marginTop: 9,
    gap: 6,
  },
  evidenceItem: {
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
  evidenceText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink2,
    lineHeight: 16,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
});
