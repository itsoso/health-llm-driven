import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, TextStyle, TouchableOpacity, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';
import type { TodayFocusModel, TodayFocusPrimary } from './todayFocus';

export interface ChatTurnStatus {
  label: string;
  tone: 'active' | 'error';
  retryable?: boolean;
}

export default function ChatTodayFocusCard({
  model,
  onExecute,
  onAsk,
  onOpenToday,
  variant = 'full',
  turnStatus,
  onRetry,
  onDismiss,
  onRestore,
}: {
  model: TodayFocusModel;
  onExecute?: (primary: TodayFocusPrimary) => void;
  onAsk?: (primary: TodayFocusPrimary) => void;
  onOpenToday?: () => void;
  variant?: 'full' | 'compact' | 'launcher';
  turnStatus?: ChatTurnStatus;
  onRetry?: () => void;
  onDismiss?: () => void;
  onRestore?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const primary = model.primary;

  useEffect(() => {
    if (variant === 'compact') setExpanded(false);
  }, [variant]);

  if (variant === 'launcher') {
    return (
      <TouchableOpacity
        testID="chat-today-focus-card"
        accessibilityRole="button"
        accessibilityLabel="展开今日重点"
        style={[styles.card, styles.launcherCard]}
        activeOpacity={0.78}
        onPress={onRestore}
        disabled={!onRestore}
      >
        <View style={[styles.iconWrap, styles.launcherIconWrap]}>
          <Ionicons name="calendar-outline" size={15} color={C.green500} />
        </View>
        <View style={styles.titleWrap}>
          <Text maxFontSizeMultiplier={1.15} style={txt.compactEyebrow} numberOfLines={1}>
            今日重点
          </Text>
          <Text maxFontSizeMultiplier={1.15} style={txt.compactMeta} numberOfLines={1}>
            已隐藏，点此展开
          </Text>
        </View>
        <Ionicons name="chevron-down" size={16} color={C.ink3} />
      </TouchableOpacity>
    );
  }

  if (variant === 'compact') {
    const summaryParts = [`接下来 ${model.status.actionable}`];
    if (model.status.overdue > 0) summaryParts.push(`已过时段 ${model.status.overdue}`);
    summaryParts.push(`已完成 ${model.status.completed}`);
    return (
      <View
        testID="chat-today-focus-card"
        accessibilityLabel="今日重点，已收起"
        style={[styles.card, styles.compactCard]}
      >
        <View style={styles.compactRow}>
          <View style={[styles.iconWrap, styles.compactIconWrap]}>
            <Ionicons
              name={turnStatus ? (turnStatus.tone === 'error' ? 'alert-circle-outline' : 'sparkles-outline') : 'calendar-outline'}
              size={15}
              color={turnStatus?.tone === 'error' ? revaSemantic.risk.fg : C.green500}
            />
          </View>
          <View style={styles.titleWrap}>
            <Text maxFontSizeMultiplier={1.15} style={txt.compactEyebrow} numberOfLines={1}>
              {turnStatus ? '小巴状态' : '今日重点'}
            </Text>
            <Text maxFontSizeMultiplier={1.15} style={txt.compactTitle} numberOfLines={1}>
              {primary?.title ?? model.emptyTitle}
            </Text>
            <Text
              maxFontSizeMultiplier={1.15}
              style={[
                txt.compactMeta,
                turnStatus?.tone === 'error' && { color: revaSemantic.risk.fg },
              ]}
              numberOfLines={1}
            >
              {turnStatus?.label ?? summaryParts.join(' · ')}
            </Text>
          </View>
          {turnStatus?.retryable && onRetry ? (
            <TouchableOpacity
              style={styles.retryButton}
              onPress={onRetry}
              activeOpacity={0.74}
              accessibilityRole="button"
              accessibilityLabel="重试上一轮"
            >
              <Ionicons name="refresh" size={16} color={C.green600} />
              <Text maxFontSizeMultiplier={1.1} style={txt.retryButton}>重试</Text>
            </TouchableOpacity>
          ) : (
            <View style={styles.compactTrailingActions}>
              {onDismiss ? (
                <TouchableOpacity
                  style={styles.compactIconButton}
                  onPress={onDismiss}
                  activeOpacity={0.74}
                  accessibilityRole="button"
                  accessibilityLabel="关闭今日重点"
                >
                  <Ionicons name="close" size={17} color={C.ink3} />
                </TouchableOpacity>
              ) : null}
              <TouchableOpacity
                style={styles.compactIconButton}
                onPress={onOpenToday}
                disabled={!onOpenToday}
                activeOpacity={0.74}
                accessibilityRole="button"
                accessibilityLabel="打开今日详情"
              >
                <Ionicons name="chevron-forward" size={18} color={C.ink3} />
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>
    );
  }

  return (
    <View
      testID="chat-today-focus-card"
      accessibilityLabel="今日重点，已展开"
      style={styles.card}
    >
      <View style={styles.headerRow}>
        <View style={styles.iconWrap}>
          <Ionicons name="sparkles-outline" size={15} color={C.green500} />
        </View>
        <View style={styles.titleWrap}>
          <Text maxFontSizeMultiplier={1.15} style={txt.eyebrow}>
            现在最重要
          </Text>
          <Text maxFontSizeMultiplier={1.15} style={txt.title} numberOfLines={2}>
            {primary?.title ?? model.emptyTitle}
          </Text>
        </View>
        {onDismiss ? (
          <TouchableOpacity
            style={styles.dismissButton}
            onPress={onDismiss}
            activeOpacity={0.72}
            accessibilityRole="button"
            accessibilityLabel="关闭今日重点"
          >
            <Ionicons name="close" size={16} color={C.ink3} />
          </TouchableOpacity>
        ) : null}
      </View>

      {primary ? (
        <>
          {primary.reason ? (
            <Text maxFontSizeMultiplier={1.15} style={txt.reason} numberOfLines={2}>
              {primary.reason}
            </Text>
          ) : null}

          <View style={styles.actionRow}>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={() => onExecute?.(primary)}
              activeOpacity={0.82}
              accessibilityRole="button"
              accessibilityLabel={`执行今日重点：${primary.title}`}
            >
              <Ionicons name="play" size={14} color={C.greenOn} />
              <Text maxFontSizeMultiplier={1.1} style={txt.primaryButton}>去执行</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={() => setExpanded(value => !value)}
              activeOpacity={0.76}
              accessibilityRole="button"
              accessibilityLabel="查看今日重点依据"
            >
              <Ionicons
                name={expanded ? 'chevron-up' : 'help-circle-outline'}
                size={15}
                color={C.green600}
              />
              <Text maxFontSizeMultiplier={1.1} style={txt.secondaryButton}>为什么</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.askButton}
              onPress={() => onAsk?.(primary)}
              activeOpacity={0.76}
              accessibilityRole="button"
              accessibilityLabel={`问小巴：${primary.title}`}
            >
              <Ionicons name="chatbubble-ellipses-outline" size={15} color={C.green600} />
              <Text maxFontSizeMultiplier={1.1} style={txt.askButton}>问小巴</Text>
            </TouchableOpacity>
          </View>

          {expanded ? (
            <View style={styles.evidencePanel}>
              <EvidenceList title="依据" items={primary.evidence} fallback={primary.reason ?? '来自今日计划和时间线。'} />
              <EvidenceList title="验证" items={primary.verification} fallback="完成后观察身体反馈。" />
            </View>
          ) : null}
        </>
      ) : (
        <View style={styles.emptyRow}>
          <Text maxFontSizeMultiplier={1.15} style={txt.emptyCopy}>
            今天没有可执行重点。可以打开今日页查看身体信号和待办。
          </Text>
          <TouchableOpacity
            style={styles.openTodayButton}
            onPress={onOpenToday}
            activeOpacity={0.76}
            accessibilityRole="button"
            accessibilityLabel="打开今日详情"
          >
            <Text maxFontSizeMultiplier={1.1} style={txt.openTodayButton}>查看今日</Text>
            <Ionicons name="chevron-forward" size={14} color={C.green600} />
          </TouchableOpacity>
        </View>
      )}

      <View style={styles.statusRow}>
        <StatusPill label={`接下来 ${model.status.actionable}`} tone="normal" />
        {model.status.overdue > 0 ? (
          <StatusPill label={`已过时段 ${model.status.overdue}`} tone="caution" />
        ) : null}
        <StatusPill label={`已完成 ${model.status.completed}`} tone="muted" />
      </View>
    </View>
  );
}

function EvidenceList({
  title,
  items,
  fallback,
}: {
  title: string;
  items: string[];
  fallback: string;
}) {
  const visibleItems = items.length > 0 ? items : [fallback];
  return (
    <View style={styles.evidenceBlock}>
      <Text maxFontSizeMultiplier={1.15} style={txt.evidenceTitle}>{title}</Text>
      {visibleItems.slice(0, 3).map(item => (
        <View key={`${title}:${item}`} style={styles.evidenceLine}>
          <View style={styles.evidenceDot} />
          <Text maxFontSizeMultiplier={1.15} style={txt.evidenceText}>{item}</Text>
        </View>
      ))}
    </View>
  );
}

function StatusPill({
  label,
  tone,
}: {
  label: string;
  tone: 'normal' | 'caution' | 'muted';
}) {
  const toneStyle = tone === 'normal'
    ? { backgroundColor: C.green50, borderColor: C.green100 }
    : tone === 'caution'
      ? { backgroundColor: revaSemantic.caution.bg, borderColor: revaSemantic.caution.line }
      : { backgroundColor: C.paper2, borderColor: C.line };
  const textColor = tone === 'normal'
    ? C.green600
    : tone === 'caution'
      ? revaSemantic.caution.fg
      : C.ink2;
  return (
    <View style={[styles.statusPill, toneStyle]}>
      <Text maxFontSizeMultiplier={1.1} style={[txt.statusPill, { color: textColor }]}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: revaSpacing.s3,
    marginTop: 2,
    marginBottom: revaSpacing.s2,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s3,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  } as ViewStyle,
  compactCard: {
    marginHorizontal: revaSpacing.s4,
    marginBottom: 6,
    minHeight: 56,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: revaRadii.xs,
    backgroundColor: C.surface2,
    shadowOpacity: 0,
    elevation: 0,
  },
  compactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
  },
  compactIconWrap: {
    width: 26,
    height: 26,
    borderRadius: revaRadii.xs,
  },
  launcherCard: {
    minHeight: 48,
    marginHorizontal: revaSpacing.s4,
    marginBottom: 6,
    paddingVertical: 6,
    borderRadius: revaRadii.xs,
    backgroundColor: C.surface2,
    shadowOpacity: 0,
    elevation: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
  },
  launcherIconWrap: {
    width: 26,
    height: 26,
    borderRadius: revaRadii.xs,
  },
  compactTrailingActions: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: -6,
  },
  compactIconButton: {
    width: 34,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  retryButton: {
    minWidth: 64,
    minHeight: 40,
    paddingHorizontal: revaSpacing.s2,
    borderRadius: revaRadii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
  },
  iconWrap: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  titleWrap: {
    flex: 1,
    minWidth: 0,
  },
  dismissButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.paper2,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    marginTop: revaSpacing.s3,
  },
  primaryButton: {
    flex: 1,
    minHeight: 38,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s3,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
    backgroundColor: C.focusBg,
  },
  secondaryButton: {
    minHeight: 38,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s3,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 5,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  askButton: {
    minHeight: 38,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s3,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 5,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  evidencePanel: {
    marginTop: revaSpacing.s3,
    paddingTop: revaSpacing.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    gap: revaSpacing.s2,
  },
  evidenceBlock: {
    gap: 5,
  },
  evidenceLine: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
  },
  evidenceDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    marginTop: 7,
    backgroundColor: C.green500,
  },
  emptyRow: {
    marginTop: revaSpacing.s2,
    gap: revaSpacing.s2,
  },
  openTodayButton: {
    alignSelf: 'flex-start',
    minHeight: 34,
    paddingHorizontal: revaSpacing.s3,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 3,
    backgroundColor: C.green50,
  },
  statusRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: revaSpacing.s2,
    marginTop: revaSpacing.s3,
  },
  statusPill: {
    minHeight: 26,
    borderRadius: revaRadii.pill,
    paddingHorizontal: revaSpacing.s2,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
  },
});

const txt = {
  eyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '800',
    color: C.ink1,
    marginTop: 1,
  } as TextStyle,
  reason: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '500',
    color: C.ink2,
    marginTop: revaSpacing.s2,
  } as TextStyle,
  primaryButton: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '800',
    color: C.greenOn,
  } as TextStyle,
  secondaryButton: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  askButton: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  evidenceTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    color: C.ink2,
  } as TextStyle,
  evidenceText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '500',
    color: C.ink2,
  } as TextStyle,
  emptyCopy: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '500',
    color: C.ink2,
  } as TextStyle,
  openTodayButton: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  statusPill: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  } as TextStyle,
  compactEyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    lineHeight: 12,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  compactTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  compactMeta: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '600',
    color: C.ink2,
  } as TextStyle,
  retryButton: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
};
