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

interface RecordQualityData {
  domain?: unknown;
  title?: unknown;
  summary?: unknown;
  primary_judgement?: unknown;
  personal_cautions?: unknown;
  next_action?: unknown;
  boundary?: unknown;
}

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function textList(value: unknown): string[] {
  const items = Array.isArray(value) ? value : value == null ? [] : [value];
  return items
    .map((item) => text(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, 2);
}

function domainMeta(domain?: unknown): { icon: string; fg: string; bg: string; badge: string } {
  if (text(domain) === 'exercise') {
    return { icon: 'fitness-outline', fg: '#C2487A', bg: '#F7E4EC', badge: '运动' };
  }
  return { icon: 'restaurant-outline', fg: '#C97A2E', bg: '#F6E9DA', badge: '饮食' };
}

export function RecordQualityCardView(data: RecordQualityData) {
  const meta = domainMeta(data.domain);
  const title = text(data.title) || '已记录';
  const summary = text(data.summary);
  const judgement = text(data.primary_judgement);
  const cautions = textList(data.personal_cautions);
  const nextAction = text(data.next_action);
  const boundary = text(data.boundary) || '健康管理建议，不替代医生诊断、处方或治疗。';

  return (
    <CardShell
      icon={meta.icon}
      iconColor={meta.fg}
      title={title}
      badge={meta.badge}
      badgeColor={meta.fg}
      bg={meta.bg}
    >
      {summary ? (
        <Text maxFontSizeMultiplier={1.2} style={styles.summary} numberOfLines={2}>
          {summary}
        </Text>
      ) : null}

      {judgement ? (
        <Text maxFontSizeMultiplier={1.25} style={styles.judgement}>
          {judgement}
        </Text>
      ) : null}

      {cautions.length > 0 ? (
        <View style={styles.cautionList}>
          {cautions.map((item, index) => (
            <View key={`${item}-${index}`} style={styles.cautionItem}>
              <Ionicons name="shield-checkmark-outline" size={12} color={revaSemantic.caution.fg} />
              <Text maxFontSizeMultiplier={1.2} style={styles.cautionText}>
                {item}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {nextAction ? (
        <View style={styles.nextAction}>
          <Ionicons name="arrow-forward-circle-outline" size={13} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={styles.nextActionText}>
            {nextAction}
          </Text>
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        {boundary}
      </Text>
    </CardShell>
  );
}

export const RecordQualityCardSpec: CardSpec<RecordQualityData> = {
  type: 'record_quality',
  label: '记录后建议',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <RecordQualityCardView {...data} />,
};

const styles = StyleSheet.create({
  summary: {
    fontFamily: revaFonts.mono,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 17,
  } as TextStyle,
  judgement: {
    marginTop: 8,
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 20,
  } as TextStyle,
  cautionList: {
    marginTop: 9,
    gap: 6,
  },
  cautionItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 7,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: C.surface,
  },
  cautionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 17,
  } as TextStyle,
  nextAction: {
    marginTop: 9,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 7,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  nextActionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
    color: C.green700,
    lineHeight: 17,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
});
