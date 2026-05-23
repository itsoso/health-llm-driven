import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: 'fast' | 'balanced' | 'reasoning' | string;
  note?: string;
}

const TIER_LABEL: Record<string, string> = {
  fast: '快',
  balanced: '均衡',
  reasoning: '推理',
};

const TIER_COLOR: Record<string, string> = {
  fast: '#30D158',
  balanced: '#0A84FF',
  reasoning: '#BF5AF2',
};

export default function LlmModelPicker({
  currentLabel,
  currentModelId,
  options,
  savingModelId,
  error,
  onSelect,
}: {
  currentLabel: string;
  currentModelId: string | null;
  options: ModelOption[];
  savingModelId: string | null;
  disabled?: boolean;
  error?: string | null;
  onSelect: (modelId: string | null) => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [visible, setVisible] = useState(false);

  const selectModel = (modelId: string | null) => {
    setVisible(false);
    onSelect(modelId);
  };

  return (
    <View style={styles.root}>
      <TouchableOpacity
        style={styles.trigger}
        onPress={() => setVisible(true)}
        activeOpacity={0.75}
        accessibilityRole="button"
        accessibilityLabel={`切换 AI 模型，当前 ${currentLabel}`}
      >
        <Ionicons name="hardware-chip-outline" size={15} color={c.brand} />
        <Text style={txt.triggerTitle} numberOfLines={1}>健康 Agent</Text>
        <Text style={txt.triggerModel} numberOfLines={1}>
          {savingModelId ? '切换中...' : currentLabel}
        </Text>
        {savingModelId ? (
          <ActivityIndicator size="small" color={c.labelTertiary} />
        ) : (
          <Ionicons name="chevron-down" size={15} color={c.labelTertiary} />
        )}
      </TouchableOpacity>

      <Modal
        visible={visible}
        transparent
        animationType="fade"
        onRequestClose={() => setVisible(false)}
      >
        <Pressable style={styles.backdrop} onPress={() => setVisible(false)}>
          <Pressable style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <View>
                <Text style={txt.sheetTitle}>切换 AI 模型</Text>
                <Text style={txt.sheetSub}>下一条消息立即使用新模型</Text>
              </View>
              <TouchableOpacity
                onPress={() => setVisible(false)}
                hitSlop={8}
                accessibilityLabel="关闭模型选择"
              >
                <Ionicons name="close" size={22} color={c.labelSecondary} />
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={[styles.option, currentModelId === null && styles.optionActive]}
              onPress={() => selectModel(null)}
              activeOpacity={0.75}
            >
              <View style={styles.optionBody}>
                <Text style={txt.optionTitle}>系统默认</Text>
                <Text style={txt.optionMeta} numberOfLines={1}>使用管理员全局配置或服务器默认模型</Text>
              </View>
              {currentModelId === null && <Ionicons name="checkmark-circle" size={18} color={c.brand} />}
            </TouchableOpacity>

            <View style={styles.divider} />

            <ScrollView style={styles.optionList} showsVerticalScrollIndicator={false}>
              {options.length === 0 ? (
                <View style={styles.empty}>
                  <Text style={txt.empty}>暂无可用模型</Text>
                </View>
              ) : options.map(option => {
                const active = option.id === currentModelId;
                const tierColor = TIER_COLOR[option.speed_tier] || c.labelTertiary;
                return (
                  <TouchableOpacity
                    key={option.id}
                    style={[styles.option, active && styles.optionActive]}
                    onPress={() => selectModel(option.id)}
                    activeOpacity={0.75}
                  >
                    <View style={styles.optionBody}>
                      <View style={styles.optionTitleRow}>
                        <Text style={txt.optionTitle} numberOfLines={1}>{option.label}</Text>
                        <View style={[styles.tierBadge, { backgroundColor: `${tierColor}22` }]}>
                          <Text style={[txt.tierText, { color: tierColor }]}>
                            {TIER_LABEL[option.speed_tier] || option.speed_tier}
                          </Text>
                        </View>
                      </View>
                      <Text style={txt.optionMeta} numberOfLines={1}>{option.provider} · {option.model}</Text>
                      {!!option.note && <Text style={txt.optionNote} numberOfLines={2}>{option.note}</Text>}
                    </View>
                    {active && <Ionicons name="checkmark-circle" size={18} color={c.brand} />}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>

            {!!error && (
              <View style={styles.errorBox}>
                <Text style={txt.error}>{error}</Text>
              </View>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    root: { flexShrink: 1, maxWidth: '72%' },
    trigger: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      minHeight: 36,
      paddingHorizontal: 10,
      paddingVertical: 7,
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      ...shadows.subtle,
    },
    backdrop: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.36)',
      justifyContent: 'flex-start',
      paddingHorizontal: spacing.lg,
      paddingTop: 72,
    },
    sheet: {
      borderRadius: radii.xl,
      backgroundColor: c.bgPrimary,
      padding: spacing.md,
      ...shadows.heavy,
    },
    sheetHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: spacing.md,
      paddingHorizontal: 4,
      paddingBottom: spacing.sm,
    },
    option: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: spacing.sm,
      borderRadius: radii.lg,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
    },
    optionActive: { backgroundColor: c.brandLight },
    optionBody: { flex: 1, minWidth: 0 },
    optionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    tierBadge: { borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
    divider: { height: StyleSheet.hairlineWidth, backgroundColor: c.separator, marginVertical: spacing.sm },
    optionList: { maxHeight: 390 },
    empty: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      borderRadius: radii.lg,
      paddingVertical: spacing.xl,
      alignItems: 'center',
    },
    errorBox: {
      marginTop: spacing.sm,
      borderRadius: radii.md,
      backgroundColor: '#FF3B3020',
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    triggerTitle: { color: c.labelPrimary, fontSize: 15, fontWeight: '700' } as TextStyle,
    triggerModel: { color: c.labelTertiary, fontSize: 13, flexShrink: 1 } as TextStyle,
    sheetTitle: { color: c.labelPrimary, fontSize: 17, fontWeight: '700' } as TextStyle,
    sheetSub: { color: c.labelTertiary, fontSize: 12, marginTop: 2 } as TextStyle,
    optionTitle: { color: c.labelPrimary, fontSize: 15, fontWeight: '600', flexShrink: 1 } as TextStyle,
    optionMeta: { color: c.labelTertiary, fontSize: 11, marginTop: 3 } as TextStyle,
    optionNote: { color: c.labelSecondary, fontSize: 12, lineHeight: 16, marginTop: 4 } as TextStyle,
    tierText: { fontSize: 10, fontWeight: '700' } as TextStyle,
    empty: { color: c.labelTertiary, fontSize: 13 } as TextStyle,
    error: { color: c.red, fontSize: 12, lineHeight: 16 } as TextStyle,
  };
}
