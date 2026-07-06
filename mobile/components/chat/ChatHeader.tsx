import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import LlmModelPicker from './LlmModelPicker';
import type { ModelOption } from '../../services/llmPreference';
import {
  revaColors as C,
  revaRadii,
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
            activeOpacity={0.55}
            accessibilityLabel="新建对话"
            accessibilityRole="button"
          >
            <Ionicons name="create-outline" size={22} color={C.ink2} />
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
            <Ionicons name="time-outline" size={22} color={C.ink2} />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={onOpenToolMenu}
            hitSlop={8}
            style={styles.headerAction}
            activeOpacity={0.55}
            accessibilityLabel="更多会诊操作"
            accessibilityRole="button"
          >
            <Ionicons name="ellipsis-horizontal" size={22} color={C.ink2} />
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  headerWrap: {
    paddingHorizontal: revaSpacing.s4,
    // 与状态栏时钟留清晰呼吸(SafeAreaView 托底 notch inset)。
    paddingTop: 10,
    paddingBottom: 4,
  },
  // 平铺 header(2026-07-06 重设计):去掉带边框的「卡片」外壳 —— 它紧贴状态栏
  // 时钟显得挤、且和奶油底色打架。标题与操作直接落在 paper 背景上,更干净。
  headerSurface: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  // 三个动作统一为无边框图标钮(founder:加号/历史两个按钮不好看 → 去掉不一致的
  // 绿色底 + 描边圆圈,归一为极简同款,靠 hitSlop 保证触达)。
  headerAction: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  streamingBadge: {
    minHeight: 26,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 9,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    marginRight: 2,
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
