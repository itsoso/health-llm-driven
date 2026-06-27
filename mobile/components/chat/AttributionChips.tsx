/**
 * AttributionChips — AI 回答底部的"用了你的什么数据"chip 行.
 *
 * P4 (2026-05-04): orchestrator system prompt 强制 LLM 在用了用户差异化数据时
 * 标注 marker. 这个组件把 marker 提取出来呈现给用户, 让"AI 在用我的基因/化验/
 * 用药/历史/趋势" 不再是后台事实, 而是每次回答都看得见的差异化护城河.
 *
 * 设计:
 * - 只在 markers ≥ 1 时渲染, 0 个不显示
 * - 每个 source 一个图标 + 颜色 (基因/化验/用药/历史/趋势)
 * - 4 个以上折叠 "+N"
 * - 不可点 (v1) — v2 加点击跳到对应数据源页 (基因报告 / 化验单)
 */
import React, { useMemo } from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  extractAttributions,
  type AttributionItem,
  type AttributionSource,
} from '../../services/attributionExtract';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

interface Props {
  text: string;
}

const MAX_VISIBLE = 4;

// 每个数据源一套 accent/bg = 「是哪类来源」的装饰色码 (基因紫/化验绿/在服红/历史蓝/趋势琥珀).
// 区分来源, 非「好坏」临床语义, 故保留 Reva 亮色调色板字面量 → 无视觉回归.
function sourceMeta(source: AttributionSource) {
  switch (source) {
    case 'genetic':
      return { icon: 'git-branch-outline' as const, color: '#7C5CBF', bg: '#EDE7F6', label: '基因' };
    case 'lab':
      return { icon: 'flask-outline' as const, color: C.green500, bg: C.green50, label: '化验' };
    case 'medication':
      return { icon: 'medical-outline' as const, color: revaSemantic.risk.fg, bg: revaSemantic.risk.bg, label: '在服' };
    case 'history':
      return { icon: 'time-outline' as const, color: '#0A84FF', bg: '#E4ECF8', label: '历史' };
    case 'trend':
      return { icon: 'trending-up-outline' as const, color: '#C98A1E', bg: '#F6ECD9', label: '趋势' };
  }
}

export default function AttributionChips({ text }: Props) {
  const items = useMemo(() => extractAttributions(text), [text]);

  if (items.length === 0) return null;

  const visible = items.slice(0, MAX_VISIBLE);
  const hiddenCount = items.length - visible.length;

  return (
    <View style={styles.wrap} accessibilityLabel="AI 用到了你的数据">
      <Text style={txt.prefix}>📌 用了你的：</Text>
      <View style={styles.chipsRow}>
        {visible.map((item, idx) => (
          <Chip key={`${item.source}-${item.label}-${idx}`} item={item} />
        ))}
        {hiddenCount > 0 ? (
          <View style={[styles.chip, { backgroundColor: C.paper }]}>
            <Text style={txt.chipMore}>+{hiddenCount}</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

function Chip({ item }: { item: AttributionItem }) {
  const meta = sourceMeta(item.source);
  return (
    <View
      style={[chipStyles.chip, { backgroundColor: meta.bg }]}
      accessibilityLabel={`${meta.label}: ${item.label}`}
    >
      <Ionicons name={meta.icon} size={11} color={meta.color} />
      <Text style={[chipStyles.label, { color: meta.color }]} numberOfLines={1}>
        {item.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginTop: revaSpacing.s2,
    paddingTop: revaSpacing.s1,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.paper2,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: revaSpacing.s1,
  },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  chip: {
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 3,
    borderRadius: revaRadii.pill,
  },
});

const txt = {
  prefix: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 } as TextStyle,
  chipMore: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink2 } as TextStyle,
};

const chipStyles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 3,
    borderRadius: revaRadii.pill,
    maxWidth: 140,
  },
  label: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '500' } as TextStyle,
});
