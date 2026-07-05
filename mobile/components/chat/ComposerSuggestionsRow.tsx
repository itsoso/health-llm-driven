/**
 * ComposerSuggestionsRow — composer 上方的横向建议 chip 行 (State A, 2026-07)。
 *
 * 「阿衡先开口」把 opener 抬成流里的开场气泡后, 建议 chip 从空状态卡片
 * 下沉到贴着输入框的一行, 让「想问别的」的动作离手最近。
 *
 * - 第一颗 FIXED「拍照记一餐」(相机图标) → router.push('/diet?capture=photo')(proven route)。
 * - 其后最多 2 颗动态 starter suggestion, 单行 numberOfLines 1, 点击走既有 send handler。
 * - chip 视觉: surface + hairline + pill, 13px ink2; 相机 chip 图标 green600。
 * - 只在空对话且非多选态渲染(由 chat.tsx 门控), 本组件不做可见性判断。
 */
import React from 'react';
import { ScrollView, Pressable, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { EmptyStateSuggestion } from './EmptyStateHome';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaFonts,
} from '../../constants/revaTheme';

interface Props {
  suggestions: EmptyStateSuggestion[];
  onCapturePhoto: () => void;
  onSuggestionPress: (s: EmptyStateSuggestion, position: number) => void;
}

export default function ComposerSuggestionsRow({
  suggestions,
  onCapturePhoto,
  onSuggestionPress,
}: Props) {
  const starters = suggestions.slice(0, 2);
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={styles.row}
      style={styles.scroll}
    >
      <Pressable
        style={({ pressed }) => [styles.chip, styles.chipCamera, pressed && styles.chipPressed]}
        onPress={onCapturePhoto}
        accessibilityRole="button"
        accessibilityLabel="拍照记一餐"
      >
        <Ionicons name="camera-outline" size={15} color={C.green600} />
        <Text style={txt.chip} numberOfLines={1}>拍照记一餐</Text>
      </Pressable>
      {starters.map((s, position) => (
        <Pressable
          key={s.text}
          style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
          onPress={() => onSuggestionPress(s, position)}
          accessibilityRole="button"
          accessibilityLabel={`向阿衡提问: ${s.text}`}
        >
          <Text style={txt.chip} numberOfLines={1}>{s.text}</Text>
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
    height: 36,
    paddingHorizontal: revaSpacing.s3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    maxWidth: 260,
  },
  chipCamera: {
    gap: 6,
  },
  chipPressed: { opacity: 0.6 },
});

const txt = {
  chip: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink2,
    fontWeight: '600',
    flexShrink: 1,
  } as TextStyle,
};
