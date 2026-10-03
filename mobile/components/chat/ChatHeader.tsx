import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import LlmModelPicker from './LlmModelPicker';
import XiaoBaAvatar from './XiaoBaAvatar';
import type { ModelOption } from '../../services/llmPreference';
import {
  revaColors as C,
  revaSpacing,
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
  onBack?: () => void;
  onSelectModel: (modelId: string | null) => void;
  onOpenVoice?: () => void;
  onOpenHistory: () => void;
  onOpenToolMenu: () => void;
}

/**
 * 会诊页顶部：模型选择器 (小巴 ⌄) + 历史/更多 + 突出的语音入口。
 * 当前轮运行状态只在 assistant turn 内展示，避免顶部和消息区重复。
 * 纯 props 驱动, 无本地状态。testID 「chat-header-surface」+ a11y 标签保持稳定 (测试引用)。
 */
export default function ChatHeader({
  activeLlmLabel,
  llmModelId,
  llmOptions,
  llmSaving,
  llmError,
  onBack,
  onSelectModel,
  onOpenVoice,
  onOpenHistory,
  onOpenToolMenu,
}: ChatHeaderProps) {
  const headerLlmLabel = compactLlmHeaderLabel(activeLlmLabel);
  return (
    <View testID="chat-header-wrap" style={styles.headerWrap}>
      <View testID="chat-header-surface" style={styles.headerSurface}>
        {onBack ? (
          <Pressable
            onPress={onBack}
            hitSlop={8}
            style={({ pressed }) => [styles.backAction, pressed && styles.headerActionPressed]}
            accessibilityLabel="返回上一页"
            accessibilityHint="返回发起这次健康讨论的页面"
            accessibilityRole="button"
          >
            <Ionicons name="chevron-back" size={21} color={C.ink1} />
          </Pressable>
        ) : (
          <XiaoBaAvatar size={22} />
        )}
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
          <View testID="chat-header-action-group" style={styles.headerActionGroup}>
            <Pressable
              onPress={onOpenHistory}
              hitSlop={8}
              style={({ pressed }) => [styles.headerAction, pressed && styles.headerActionPressed]}
              accessibilityLabel="对话历史"
              accessibilityHint="查看和切换历史对话"
              accessibilityRole="button"
            >
              <Ionicons name="time-outline" size={18} color={C.ink2} />
            </Pressable>
            <Pressable
              onPress={onOpenToolMenu}
              hitSlop={8}
              style={({ pressed }) => [styles.headerAction, pressed && styles.headerActionPressed]}
              accessibilityLabel="更多会诊操作"
              accessibilityHint="打开更多会诊操作"
              accessibilityRole="button"
            >
              <Ionicons name="ellipsis-horizontal" size={18} color={C.ink2} />
            </Pressable>
          </View>
          {onOpenVoice && (
            <Pressable
              testID="chat-header-voice"
              onPress={onOpenVoice}
              hitSlop={8}
              style={({ pressed }) => [styles.voiceAction, pressed && styles.voiceActionPressed]}
              accessibilityRole="button"
              accessibilityLabel="实时语音"
              accessibilityHint="打开语音对话页面，点击麦克风后开始，不是语音转文字"
            >
              <Ionicons name="pulse" size={18} color={C.greenOn} />
              <Text style={styles.voiceLabel} maxFontSizeMultiplier={1.2}>语音</Text>
            </Pressable>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  headerWrap: {
    paddingHorizontal: revaSpacing.s4,
    // 与状态栏时钟留清晰呼吸(页面根用动态 top inset 托底 notch)。
    paddingTop: 8,
    paddingBottom: 2,
  },
  // 平铺 header(2026-07-06 重设计):去掉带边框的「卡片」外壳 —— 它紧贴状态栏
  // 时钟显得挤、且和奶油底色打架。标题与操作直接落在 paper 背景上,更干净。
  headerSurface: {
    minHeight: 40,
    paddingVertical: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 'auto',
    gap: 6,
  },
  // 历史与更多保持中性分组，语音独立突出；新建对话收进更多。
  headerActionGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 40,
    gap: 0,
    padding: 2,
    backgroundColor: C.paper2,
    borderRadius: revaSpacing.s6,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  headerAction: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    borderWidth: 0,
  },
  backAction: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerActionPressed: {
    backgroundColor: C.green50,
  },
  voiceAction: {
    minHeight: 44,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: C.green600,
    borderWidth: 0,
  },
  voiceActionPressed: { backgroundColor: C.green700 },
  voiceLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    fontWeight: '600',
    color: C.greenOn,
  },
});
