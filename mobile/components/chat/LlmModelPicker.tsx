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

import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import { canonicalModelId, sanitizeModelOptions } from '../../services/llmModelCatalog';

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
  variant = 'default',
  onSelect,
}: {
  currentLabel: string;
  currentModelId: string | null;
  options: ModelOption[];
  savingModelId: string | null;
  disabled?: boolean;
  error?: string | null;
  variant?: 'default' | 'header';
  onSelect: (modelId: string | null) => void;
}) {
  const [visible, setVisible] = useState(false);
  const visibleOptions = useMemo(() => sanitizeModelOptions(options), [options]);
  const activeModelId = canonicalModelId(currentModelId);

  const selectModel = (modelId: string | null) => {
    setVisible(false);
    onSelect(canonicalModelId(modelId));
  };
  const isHeader = variant === 'header';

  return (
    <View style={[styles.root, isHeader && styles.rootHeader]}>
      <TouchableOpacity
        style={[styles.trigger, isHeader && styles.triggerHeader]}
        onPress={() => setVisible(true)}
        activeOpacity={0.75}
        accessibilityRole="button"
        accessibilityLabel={`切换 AI 模型，当前 ${currentLabel}`}
      >
        {isHeader ? (
          // Agent-native header: 只露品牌名 "小巴 ⌄"，模型名收进下拉 sheet。
          // 切换中给一个 ActivityIndicator 替代 chevron，保留可感知反馈。
          <View style={styles.headerTitleRow}>
            <Text maxFontSizeMultiplier={1.2} style={txt.headerTitle} numberOfLines={1}>小巴</Text>
            {savingModelId ? (
              <ActivityIndicator size="small" color={C.ink3} />
            ) : (
              <Ionicons name="chevron-down" size={13} color={C.ink3} />
            )}
          </View>
        ) : (
          <>
            <Ionicons name="hardware-chip-outline" size={15} color={C.green500} />
            <Text style={txt.triggerTitle} numberOfLines={1}>小巴</Text>
            <Text style={txt.triggerModel} numberOfLines={1}>
              {savingModelId ? '切换中...' : currentLabel}
            </Text>
            {savingModelId ? (
              <ActivityIndicator size="small" color={C.ink3} />
            ) : (
              <Ionicons name="chevron-down" size={15} color={C.ink3} />
            )}
          </>
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
                <Ionicons name="close" size={22} color={C.ink2} />
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={[styles.option, activeModelId === null && styles.optionActive]}
              onPress={() => selectModel(null)}
              activeOpacity={0.75}
            >
              <View style={styles.optionBody}>
                <Text style={txt.optionTitle}>系统默认 · 智能路由</Text>
                <Text style={txt.optionMeta} numberOfLines={2}>简单记录/查询自动用最快模型,分析建议用系统质量模型</Text>
              </View>
              {activeModelId === null && <Ionicons name="checkmark-circle" size={18} color={C.green500} />}
            </TouchableOpacity>

            <View style={styles.divider} />

            <ScrollView style={styles.optionList} showsVerticalScrollIndicator={false}>
              {visibleOptions.length === 0 ? (
                <View style={styles.empty}>
                  <Text style={txt.empty}>暂无可用模型</Text>
                </View>
              ) : visibleOptions.map(option => {
                const active = option.id === activeModelId;
                const tierColor = TIER_COLOR[option.speed_tier] || C.ink3;
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
                    {active && <Ionicons name="checkmark-circle" size={18} color={C.green500} />}
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

const styles = StyleSheet.create({
  root: { flexShrink: 1, maxWidth: '72%' },
  rootHeader: { flex: 1, maxWidth: undefined, minWidth: 0 },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    minHeight: 36,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    ...revaShadows.sm,
  },
  triggerHeader: {
    minHeight: 44,
    paddingHorizontal: 0,
    paddingVertical: 0,
    borderRadius: 0,
    backgroundColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'flex-start',
    flexDirection: 'row',
    gap: 0,
    shadowOpacity: 0,
    elevation: 0,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    maxWidth: '100%',
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.36)',
    justifyContent: 'flex-start',
    paddingHorizontal: revaSpacing.s4,
    paddingTop: 72,
  },
  sheet: {
    borderRadius: revaRadii.xl,
    backgroundColor: C.paper,
    padding: revaSpacing.s3,
    ...revaShadows.lg,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: revaSpacing.s3,
    paddingHorizontal: 4,
    paddingBottom: revaSpacing.s2,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
    borderRadius: revaRadii.lg,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s2,
  },
  optionActive: { backgroundColor: C.green50 },
  optionBody: { flex: 1, minWidth: 0 },
  optionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  tierBadge: { borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: C.line, marginVertical: revaSpacing.s2 },
  optionList: { maxHeight: 390 },
  empty: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.lg,
    paddingVertical: revaSpacing.s5,
    alignItems: 'center',
  },
  errorBox: {
    marginTop: revaSpacing.s2,
    borderRadius: revaRadii.md,
    backgroundColor: '#FF3B3020',
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s2,
  },
});

const txt = {
  headerTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 21, fontWeight: '800', lineHeight: 26 } as TextStyle,
  triggerTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 15, fontWeight: '700' } as TextStyle,
  triggerModel: { fontFamily: revaFonts.sans, color: C.ink3, fontSize: 13, flexShrink: 1 } as TextStyle,
  sheetTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 17, fontWeight: '700' } as TextStyle,
  sheetSub: { fontFamily: revaFonts.sans, color: C.ink3, fontSize: 12, marginTop: 2 } as TextStyle,
  optionTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 15, fontWeight: '600', flexShrink: 1 } as TextStyle,
  optionMeta: { fontFamily: revaFonts.sans, color: C.ink3, fontSize: 11, marginTop: 3 } as TextStyle,
  optionNote: { fontFamily: revaFonts.sans, color: C.ink2, fontSize: 12, lineHeight: 16, marginTop: 4 } as TextStyle,
  tierText: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '700' } as TextStyle,
  empty: { fontFamily: revaFonts.sans, color: C.ink3, fontSize: 13 } as TextStyle,
  error: { fontFamily: revaFonts.sans, color: revaSemantic.risk.fg, fontSize: 12, lineHeight: 16 } as TextStyle,
};
