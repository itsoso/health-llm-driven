/**
 * ComposerSuggestionsRow — composer 上方的横向建议 chip 行 (State A, 2026-07)。
 *
 * 「小气候先开口」把 opener 抬成流里的开场气泡后, 建议 chip 从空状态卡片
 * 下沉到贴着输入框的一行, 让「想问别的」的动作离手最近。
 *
 * - 最多 2 颗去重后的动态 starter suggestion, 点击走既有 send handler。
 * - 拍照统一由附件菜单提供，兼容过滤旧后端返回的拍照推荐。
 * - chip 视觉: surface + hairline + pill, 13px ink2。
 * - 只在空对话且非多选态渲染(由 chat.tsx 门控), 本组件不做可见性判断。
 */
import React from 'react';
import { ScrollView, Pressable, Text, StyleSheet, TextStyle } from 'react-native';
import { selectHomeSuggestions } from '../../utils/homePrompts';
import type { EmptyStateSuggestion } from './EmptyStateHome';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaFonts,
} from '../../constants/revaTheme';

interface Props {
  suggestions: EmptyStateSuggestion[];
  onSuggestionPress: (s: EmptyStateSuggestion, position: number) => void;
}

export default function ComposerSuggestionsRow({
  suggestions,
  onSuggestionPress,
}: Props) {
  const starters = selectHomeSuggestions(suggestions);
  if (starters.length === 0) return null;
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={styles.row}
      style={styles.scroll}
    >
      {starters.map((s, position) => (
        <Pressable
          key={s.text.trim()}
          style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
          onPress={() => onSuggestionPress(s, position)}
          accessibilityRole="button"
          accessibilityLabel={`向小气候提问: ${s.text.trim()}`}
        >
          <Text style={txt.chip} numberOfLines={2}>{s.text.trim()}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 0,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    paddingHorizontal: revaSpacing.s4,
    paddingBottom: revaSpacing.s2,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minHeight: 44,
    paddingVertical: revaSpacing.s2,
    paddingHorizontal: revaSpacing.s3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    maxWidth: 260,
  },
  chipPressed: { opacity: 0.6 },
});

const txt = {
  chip: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 21,
    color: C.ink2,
    fontWeight: '600',
    flexShrink: 1,
  } as TextStyle,
};
