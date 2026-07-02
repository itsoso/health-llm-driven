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
  metrics?: unknown;
  progress?: unknown;
  primary_judgement?: unknown;
  personal_cautions?: unknown;
  next_action?: unknown;
  expanded_sections?: unknown;
  next_meal_detail?: unknown;
  boundary?: unknown;
}

interface MetricItem {
  label: string;
  value: string;
}

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function textList(value: unknown, limit = 2): string[] {
  const items = Array.isArray(value) ? value : value == null ? [] : [value];
  return items
    .map((item) => text(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, limit);
}

function metricList(value: unknown): MetricItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const raw = item as Record<string, unknown>;
      const label = text(raw.label);
      const metricValue = text(raw.value);
      return label && metricValue ? { label, value: metricValue } : null;
    })
    .filter((item): item is MetricItem => Boolean(item))
    .slice(0, 5);
}

function progressValue(progress: unknown, key: string): string | undefined {
  if (!progress || typeof progress !== 'object') return undefined;
  return text((progress as Record<string, unknown>)[key]);
}

function hasExpandedSection(value: unknown, section: string): boolean {
  return Array.isArray(value) && value.some((item) => text(item) === section);
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return undefined;
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
  const metrics = metricList(data.metrics);
  const proteinTotal = progressValue(data.progress, 'protein_total_g');
  const proteinTarget = progressValue(data.progress, 'protein_target_g');
  const remainingProtein = progressValue(data.progress, 'remaining_protein_g');
  const caloriesTotal = progressValue(data.progress, 'calories_total');
  const mealsCount = progressValue(data.progress, 'meals_count');
  const hasProgress = Boolean(proteinTotal && proteinTarget);
  const judgement = text(data.primary_judgement);
  const cautions = textList(data.personal_cautions);
  const nextAction = text(data.next_action);
  const nextMealDetail = objectValue(data.next_meal_detail);
  const showNextMealDetail = Boolean(hasExpandedSection(data.expanded_sections, 'next_meal') && nextMealDetail);
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

      {metrics.length > 0 ? (
        <View style={styles.metricRow}>
          {metrics.map((item) => (
            <View key={`${item.label}-${item.value}`} style={styles.metricPill}>
              <Text maxFontSizeMultiplier={1.1} style={styles.metricLabel}>
                {item.label}
              </Text>
              <Text maxFontSizeMultiplier={1.1} style={styles.metricValue}>
                {item.value}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {hasProgress ? (
        <View style={styles.progressBox}>
          <View style={styles.progressLine}>
            <Text maxFontSizeMultiplier={1.1} style={styles.progressLabel}>
              今日蛋白
            </Text>
            <Text maxFontSizeMultiplier={1.1} style={styles.progressValue}>
              {proteinTotal}/{proteinTarget}g
            </Text>
          </View>
          <Text maxFontSizeMultiplier={1.1} style={styles.progressHint}>
            {[
              caloriesTotal ? `已记 ${caloriesTotal} kcal` : null,
              mealsCount ? `${mealsCount} 餐` : null,
              remainingProtein ? `还差约 ${remainingProtein}g 蛋白` : null,
            ].filter(Boolean).join(' · ')}
          </Text>
        </View>
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

      {showNextMealDetail && nextMealDetail ? (
        <View style={styles.nextMealPanel}>
          <Text maxFontSizeMultiplier={1.15} style={styles.nextMealTitle}>
            {text(nextMealDetail.title) || '下一餐建议'}
          </Text>
          {text(nextMealDetail.context) ? (
            <Text maxFontSizeMultiplier={1.15} style={styles.nextMealContext}>
              {text(nextMealDetail.context)}
            </Text>
          ) : null}
          {text(nextMealDetail.summary) ? (
            <Text maxFontSizeMultiplier={1.18} style={styles.nextMealSummary}>
              {text(nextMealDetail.summary)}
            </Text>
          ) : null}
          {textList(nextMealDetail.options, 4).length > 0 ? (
            <View style={styles.nextMealList}>
              {textList(nextMealDetail.options, 4).map((item, index) => (
                <View key={`${item}-${index}`} style={styles.nextMealListItem}>
                  <Text maxFontSizeMultiplier={1.1} style={styles.nextMealIndex}>
                    {index + 1}
                  </Text>
                  <Text maxFontSizeMultiplier={1.18} style={styles.nextMealListText}>
                    {item}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
          {textList(nextMealDetail.rationale, 4).length > 0 ? (
            <View style={styles.rationaleBox}>
              {textList(nextMealDetail.rationale, 4).map((item, index) => (
                <View key={`${item}-${index}`} style={styles.rationaleItem}>
                  <Ionicons name="sparkles-outline" size={11} color={C.green600} />
                  <Text maxFontSizeMultiplier={1.15} style={styles.rationaleText}>
                    {item}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
          {text(nextMealDetail.continue_prompt) ? (
            <Text maxFontSizeMultiplier={1.15} style={styles.continuePrompt}>
              {text(nextMealDetail.continue_prompt)}
            </Text>
          ) : null}
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
  metricRow: {
    marginTop: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  metricPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: revaRadii.sm,
    backgroundColor: 'rgba(255,255,255,0.78)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  metricLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
  metricValue: {
    fontFamily: revaFonts.mono,
    fontSize: 11,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 14,
  } as TextStyle,
  progressBox: {
    marginTop: 8,
    gap: 3,
    paddingHorizontal: 9,
    paddingVertical: 8,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  progressLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  progressLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.green700,
    lineHeight: 15,
  } as TextStyle,
  progressValue: {
    fontFamily: revaFonts.mono,
    fontSize: 12,
    fontWeight: '900',
    color: C.green700,
    lineHeight: 15,
  } as TextStyle,
  progressHint: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
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
  nextMealPanel: {
    marginTop: 8,
    gap: 7,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  nextMealTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '900',
    color: C.ink1,
    lineHeight: 18,
  } as TextStyle,
  nextMealContext: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  nextMealSummary: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.green700,
    lineHeight: 17,
  } as TextStyle,
  nextMealList: {
    gap: 6,
  },
  nextMealListItem: {
    flexDirection: 'row',
    gap: 7,
    alignItems: 'flex-start',
  },
  nextMealIndex: {
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    overflow: 'hidden',
    textAlign: 'center',
    fontFamily: revaFonts.mono,
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 18,
    color: C.green700,
    backgroundColor: C.green50,
  } as TextStyle,
  nextMealListText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink1,
    lineHeight: 16,
  } as TextStyle,
  rationaleBox: {
    gap: 4,
    paddingTop: 6,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  rationaleItem: {
    flexDirection: 'row',
    gap: 5,
    alignItems: 'flex-start',
  },
  rationaleText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink2,
    lineHeight: 15,
  } as TextStyle,
  continuePrompt: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
});
