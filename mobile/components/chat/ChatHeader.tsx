import React from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import LlmModelPicker from './LlmModelPicker';
import XiaoBaAvatar from './XiaoBaAvatar';
import type { ModelOption } from '../../services/llmPreference';
import {
  revaColors as C,
  revaSpacing,
  revaRadii,
} from '../../constants/revaTheme';

// header 里只露品牌名/压缩模型名 — 去掉尾部速度档 + 「· 供应商」后缀。
export function compactLlmHeaderLabel(label: string): string {
  return label
    .split(' · ')[0]
    .replace(/\s+(推理|均衡|快速)$/u, '')
    .trim();
}

interface ChatHeaderProps {
  canSelectModel?: boolean;
  activeLlmLabel: string;
  llmModelId: string | null;
  llmOptions: ModelOption[];
  llmSaving: string | null;
  llmError: string | null;
  isStreaming: boolean;
  onBack?: () => void;
  onSelectModel: (modelId: string | null) => void;
  onNewChat: () => void;
  onOpenHistory: () => void;
  onOpenToolMenu: () => void;
}

/**
 * 会诊页顶部 header surface：模型选择器 (小气候 ⌄) + 新建/历史/工具三个动作。
 * 当前轮运行状态只在 assistant turn 内展示，避免顶部和消息区重复。
 * 纯 props 驱动, 无本地状态。testID 「chat-header-surface」+ a11y 标签保持稳定 (测试引用)。
 */
export default function ChatHeader({
  canSelectModel = false,
  activeLlmLabel,
  llmModelId,
  llmOptions,
  llmSaving,
  llmError,
  onBack,
  onSelectModel,
  onNewChat,
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
          <XiaoBaAvatar size={28} compact />
        )}
        <LlmModelPicker
          canSelectModel={canSelectModel}
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
              onPress={onNewChat}
              hitSlop={8}
              style={styles.headerAction}
              accessibilityLabel="新建对话"
              accessibilityHint="开始新对话，当前对话保留在历史中"
              accessibilityRole="button"
            >
              {({ pressed }) => (
                <View
                  testID="chat-header-new-visual"
                  style={[
                    styles.headerActionVisual,
                    styles.primaryHeaderAction,
                    pressed && styles.primaryHeaderActionPressed,
                  ]}
                >
                  <Ionicons name="create-outline" size={20} color={C.greenOn} />
                </View>
              )}
            </Pressable>
            <Pressable
              onPress={onOpenHistory}
              hitSlop={8}
              style={styles.headerAction}
              accessibilityLabel="对话历史"
              accessibilityHint="查看和切换历史对话"
              accessibilityRole="button"
            >
              {({ pressed }) => (
                <View
                  testID="chat-header-history-visual"
                  style={[styles.headerActionVisual, pressed && styles.headerActionPressed]}
                >
                  <Ionicons name="time-outline" size={20} color={C.green700} />
                </View>
              )}
            </Pressable>
            <Pressable
              onPress={onOpenToolMenu}
              hitSlop={8}
              style={styles.headerAction}
              accessibilityLabel="更多会诊操作"
              accessibilityHint="打开更多会诊操作"
              accessibilityRole="button"
            >
              {({ pressed }) => (
                <View
                  testID="chat-header-more-visual"
                  style={[styles.headerActionVisual, pressed && styles.headerActionPressed]}
                >
                  <Ionicons name="ellipsis-horizontal" size={20} color={C.green700} />
                </View>
              )}
            </Pressable>
          </View>
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
    paddingBottom: 6,
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
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 'auto',
  },
  // 三个动作共用一块浅绿「气候带」；新建作为主动作使用深绿实心面。
  // 统一尺寸、圆角和颜色语法，避免一个按钮像卡片、另外两个像裸图标。
  headerActionGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 46,
    gap: 2,
    padding: 1,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.green50,
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
  headerActionVisual: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  backAction: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerActionPressed: {
    backgroundColor: C.green100,
  },
  primaryHeaderAction: {
    borderRadius: 20,
    backgroundColor: C.green700,
  },
  primaryHeaderActionPressed: {
    backgroundColor: C.green600,
  },
});
