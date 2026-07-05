import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import LlmModelPicker from './LlmModelPicker';
import type { ModelOption } from '../../services/llmPreference';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

// header 里只露品牌名/压缩模型名 — 去掉尾部速度档 + 「· 供应商」后缀。
export function compactLlmHeaderLabel(label: string): string {
  return label
    .split(' · ')[0]
    .replace(/\s+(推理|均衡|快速)$/u, '')
    .trim();
}

interface ChatHeaderProps {
  activeLlmLabel: string;
  llmModelId: string | null;
  llmOptions: ModelOption[];
  llmSaving: string | null;
  llmError: string | null;
  isStreaming: boolean;
  onSelectModel: (modelId: string | null) => void;
  onNewChat: () => void;
  onOpenHistory: () => void;
  onOpenToolMenu: () => void;
}

/**
 * 会诊页顶部 header surface：模型选择器 (小巴 ⌄) + 回复中徽标 + 新建/历史/工具三个动作。
 * 纯 props 驱动, 无本地状态。testID 「chat-header-surface」+ a11y 标签保持稳定 (测试引用)。
 */
export default function ChatHeader({
  activeLlmLabel,
  llmModelId,
  llmOptions,
  llmSaving,
  llmError,
  isStreaming,
  onSelectModel,
  onNewChat,
  onOpenHistory,
  onOpenToolMenu,
}: ChatHeaderProps) {
  const headerLlmLabel = compactLlmHeaderLabel(activeLlmLabel);
  return (
    <View style={styles.headerWrap}>
      <View testID="chat-header-surface" style={styles.headerSurface}>
        {/* 「阿」头像已删（与标题「小巴」重复）——「我」入口挪进右侧「…」工具 sheet。 */}
        <LlmModelPicker
          variant="header"
          currentLabel={headerLlmLabel}
          currentModelId={llmModelId}
          options={llmOptions}
          savingModelId={llmSaving}
          error={llmError}
          onSelect={onSelectModel}
        />
        <View style={styles.headerRight}>
          {isStreaming && (
            <View style={styles.streamingBadge} accessibilityLabel="回复中">
              <View style={styles.streamingDot} />
              <Text style={txt.streamingBadge}>回复中</Text>
            </View>
          )}
          <TouchableOpacity
            onPress={onNewChat}
            hitSlop={8}
            style={styles.headerAction}
            accessibilityLabel="新建对话"
            accessibilityRole="button"
          >
            <Ionicons name="add" size={18} color={C.ink1} />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={onOpenHistory}
            hitSlop={8}
            style={styles.headerActionAccent}
            accessibilityLabel="对话历史"
            accessibilityHint="查看和切换历史对话"
            accessibilityRole="button"
          >
            <Ionicons name="time-outline" size={17} color={C.green500} />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={onOpenToolMenu}
            hitSlop={8}
            style={styles.headerMenuAction}
            accessibilityLabel="更多会诊操作"
            accessibilityRole="button"
          >
            <Ionicons name="ellipsis-horizontal" size={18} color={C.ink1} />
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  headerWrap: {
    paddingHorizontal: revaSpacing.s3,
    // founder 2026-07-05: 0 让 header 顶着状态栏时钟, 显得挤。给一指呼吸,
    // 时钟与「小巴」标题之间留清晰间隔(SafeAreaView 已托底 notch inset)。
    paddingTop: 8,
    paddingBottom: 2,
  },
  headerSurface: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingLeft: 8,
    paddingRight: 2,
    paddingVertical: 2,
    borderRadius: 17,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  headerAction: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  headerActionAccent: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.normal.line,
    ...revaShadows.sm,
  },
  headerMenuAction: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  streamingBadge: {
    minHeight: 26,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.normal.line,
  },
  streamingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: C.green500,
  },
});

const txt = {
  streamingBadge: { fontFamily: revaFonts.sans, fontSize: 11, color: C.green500, fontWeight: '700' } as TextStyle,
};
