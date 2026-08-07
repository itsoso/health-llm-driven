import React from 'react';
import { StyleSheet, Text, TextStyle, TouchableOpacity, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../constants/revaTheme';
import type { TodayFocusContextTone, TodayFocusModel } from './todayFocus';

export interface ChatTurnStatus {
  label: string;
  tone: 'active' | 'error';
  retryable?: boolean;
}

export default function ChatTodayFocusCard({
  model,
  onOpenToday,
  turnStatus,
  onRetry,
  onDismiss,
}: {
  model: TodayFocusModel;
  onOpenToday?: () => void;
  turnStatus?: ChatTurnStatus;
  onRetry?: () => void;
  onDismiss?: () => void;
}) {
  const context = model.contextStrip;
  const visibleTurnStatus = context?.tone === 'risk' ? undefined : turnStatus;
  if (!visibleTurnStatus && !context) return null;

  const tone: TodayFocusContextTone = visibleTurnStatus?.tone === 'error'
    ? 'risk'
    : context?.tone ?? 'normal';
  const palette = tonePalette(tone);
  const isTurnStatus = !!visibleTurnStatus;
  const iconName = visibleTurnStatus
    ? (visibleTurnStatus.tone === 'error' ? 'alert-circle-outline' : 'sparkles-outline')
    : (tone === 'risk' ? 'alert-circle-outline' : 'time-outline');

  return (
    <View
      testID="chat-today-focus-card"
      accessibilityLabel={visibleTurnStatus?.label ?? `${context?.label}，${context?.title}`}
      style={[
        styles.strip,
        isTurnStatus ? styles.turnStatusStrip : styles.contextStrip,
        { backgroundColor: palette.background, borderColor: palette.border },
      ]}
    >
      {!isTurnStatus ? (
        <View
          testID="chat-today-focus-accent"
          style={[styles.contextAccent, { backgroundColor: palette.foreground }]}
        />
      ) : null}
      <View
        testID="chat-today-focus-icon"
        style={[
          styles.iconWrap,
          isTurnStatus ? styles.turnStatusIconWrap : styles.contextIconWrap,
          { backgroundColor: palette.iconBackground },
        ]}
      >
        <Ionicons name={iconName} size={16} color={palette.foreground} />
      </View>

      {visibleTurnStatus ? (
        <Text
          maxFontSizeMultiplier={1.15}
          style={[txt.status, { color: palette.foreground }]}
          numberOfLines={1}
        >
          {visibleTurnStatus.label}
        </Text>
      ) : (
        <TouchableOpacity
          style={styles.contextButton}
          onPress={onOpenToday}
          disabled={!onOpenToday}
          activeOpacity={0.74}
          accessibilityRole="button"
          accessibilityLabel="打开今日计划"
        >
          <Text
            maxFontSizeMultiplier={1.15}
            style={[txt.label, { color: palette.foreground }]}
            numberOfLines={1}
          >
            {context?.label}
          </Text>
          <View style={[styles.separator, { backgroundColor: palette.foreground }]} />
          <Text maxFontSizeMultiplier={1.15} style={txt.title} numberOfLines={1}>
            {context?.title}
          </Text>
          {onOpenToday ? <Ionicons name="chevron-forward" size={16} color={C.ink3} /> : null}
        </TouchableOpacity>
      )}

      {visibleTurnStatus?.retryable && onRetry ? (
        <TouchableOpacity
          style={[styles.retryButton, { borderColor: palette.border }]}
          onPress={onRetry}
          activeOpacity={0.74}
          accessibilityRole="button"
          accessibilityLabel="重试上一轮"
        >
          <Ionicons name="refresh" size={16} color={palette.foreground} />
          <Text maxFontSizeMultiplier={1.1} style={[txt.retry, { color: palette.foreground }]}>重试</Text>
        </TouchableOpacity>
      ) : null}

      {!visibleTurnStatus && onDismiss ? (
        <TouchableOpacity
          style={styles.iconButton}
          hitSlop={4}
          onPress={onDismiss}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel="关闭当前提示"
        >
          <Ionicons name="close" size={17} color={C.ink3} />
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

function tonePalette(tone: TodayFocusContextTone) {
  if (tone === 'risk') {
    return {
      background: revaSemantic.risk.bg,
      border: revaSemantic.risk.line,
      foreground: revaSemantic.risk.fg,
      iconBackground: C.surface,
    };
  }
  if (tone === 'caution') {
    return {
      background: C.surface2,
      border: C.line,
      foreground: revaSemantic.caution.fg,
      iconBackground: 'transparent',
    };
  }
  return {
    background: C.surface2,
    border: C.line,
    foreground: C.green600,
    iconBackground: 'transparent',
  };
}

const styles = StyleSheet.create({
  strip: {
    marginHorizontal: revaSpacing.s4,
    marginTop: 2,
    marginBottom: 6,
    paddingRight: 4,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: revaRadii.xs,
    borderWidth: StyleSheet.hairlineWidth,
    shadowOpacity: 0,
    elevation: 0,
  } as ViewStyle,
  contextStrip: {
    minHeight: 44,
    paddingLeft: 4,
    gap: 6,
  },
  turnStatusStrip: {
    minHeight: 44,
    paddingLeft: revaSpacing.s2,
    gap: revaSpacing.s2,
  },
  contextAccent: {
    width: 2,
    height: 22,
    borderRadius: 1,
  },
  iconWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.xs,
  },
  contextIconWrap: {
    width: 28,
    height: 28,
  },
  turnStatusIconWrap: {
    width: 28,
    height: 28,
  },
  contextButton: {
    flex: 1,
    minWidth: 0,
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  separator: {
    width: 3,
    height: 3,
    borderRadius: 2,
    opacity: 0.5,
  },
  iconButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  retryButton: {
    minWidth: 62,
    minHeight: 34,
    paddingHorizontal: revaSpacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    borderRadius: revaRadii.xs,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: C.surface,
  },
});

const txt = {
  label: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 19,
    fontWeight: '800',
  } as TextStyle,
  title: {
    flex: 1,
    minWidth: 0,
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  status: {
    flex: 1,
    minWidth: 0,
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 19,
    fontWeight: '700',
  } as TextStyle,
  retry: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  } as TextStyle,
};
