import React from 'react';
import { View, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import LlmModelPicker from './LlmModelPicker';
import XiaoBaAvatar from './XiaoBaAvatar';
import type { ModelOption } from '../../services/llmPreference';
import {
  revaColors as C,
  revaSpacing,
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
 * 会诊页顶部 header surface：模型选择器 (小巴 ⌄) + 新建/历史/工具三个动作。
 * 当前轮运行状态只在 assistant turn 内展示，避免顶部和消息区重复。
 * 纯 props 驱动, 无本地状态。testID 「chat-header-surface」+ a11y 标签保持稳定 (测试引用)。
 */
export default function ChatHeader({
  activeLlmLabel,
  llmModelId,
  llmOptions,
  llmSaving,
  llmError,
  onSelectModel,
  onNewChat,
  onOpenHistory,
  onOpenToolMenu,
}: ChatHeaderProps) {
  const headerLlmLabel = compactLlmHeaderLabel(activeLlmLabel);
  return (
    <View style={styles.headerWrap}>
      <View testID="chat-header-surface" style={styles.headerSurface}>
        <XiaoBaAvatar size={30} />
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
            <TouchableOpacity
              onPress={onNewChat}
              hitSlop={8}
              style={styles.headerAction}
              activeOpacity={0.55}
              accessibilityLabel="新建对话"
              accessibilityRole="button"
            >
              <Ionicons name="pencil-outline" size={19} color={C.ink2} />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={onOpenHistory}
              hitSlop={8}
              style={styles.headerAction}
              activeOpacity={0.55}
              accessibilityLabel="对话历史"
              accessibilityHint="查看和切换历史对话"
              accessibilityRole="button"
            >
              <Ionicons name="time-outline" size={19} color={C.ink2} />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={onOpenToolMenu}
              hitSlop={8}
              style={styles.headerAction}
              activeOpacity={0.55}
              accessibilityLabel="更多会诊操作"
              accessibilityHint="打开设置与更多操作"
              accessibilityRole="button"
            >
              <Ionicons name="settings-outline" size={19} color={C.ink2} />
            </TouchableOpacity>
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
    paddingTop: 10,
    paddingBottom: 4,
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
  },
  // 三个一级动作收拢为同一组,让右上角像一个完整的控制器而不是三个散落的按钮。
  headerActionGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
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
});
