import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../constants/revaTheme';

interface Props {
  sources?: readonly string[];
  onOpenMemory?: () => void;
}

interface DetailsProps extends Props {
  maxVisible?: number;
}

type SourceKind = 'memory' | 'genetic' | 'lab' | 'medication' | 'trend' | 'record' | 'knowledge' | 'data';

interface StructuredSource {
  label: string;
  kind: SourceKind;
}

const MAX_VISIBLE = 4;

function sourceKind(label: string): SourceKind {
  if (/记忆/.test(label)) return 'memory';
  if (/基因/.test(label)) return 'genetic';
  if (/化验|检验|体征/.test(label)) return 'lab';
  if (/药物|用药|补剂/.test(label)) return 'medication';
  if (/Garmin|HRV|睡眠|RHR|趋势/.test(label)) return 'trend';
  if (/打卡|记录/.test(label)) return 'record';
  if (/知识库|wiki/i.test(label)) return 'knowledge';
  return 'data';
}

function normalizeSources(sources: readonly string[] | undefined): StructuredSource[] {
  const seen = new Set<string>();
  const normalized: StructuredSource[] = [];
  for (const source of sources || []) {
    const label = String(source || '').replace(/\s+/g, ' ').trim().slice(0, 96);
    if (!label || seen.has(label)) continue;
    seen.add(label);
    normalized.push({ label, kind: sourceKind(label) });
  }
  return normalized;
}

export function normalizedAttributionCount(sources: readonly string[] | undefined): number {
  return normalizeSources(sources).length;
}

function sourceMeta(kind: SourceKind) {
  switch (kind) {
    case 'memory':
      return { icon: 'bookmark-outline' as const, color: C.green600, bg: C.green50 };
    case 'genetic':
      return { icon: 'git-branch-outline' as const, color: '#7C5CBF', bg: '#EDE7F6' };
    case 'lab':
      return { icon: 'flask-outline' as const, color: C.green600, bg: C.green50 };
    case 'medication':
      return { icon: 'medical-outline' as const, color: revaSemantic.risk.fg, bg: revaSemantic.risk.bg };
    case 'trend':
      return { icon: 'trending-up-outline' as const, color: '#3069A8', bg: '#E4ECF8' };
    case 'record':
      return { icon: 'checkmark-circle-outline' as const, color: '#9A6814', bg: '#F6ECD9' };
    case 'knowledge':
      return { icon: 'library-outline' as const, color: C.ink2, bg: C.paper2 };
    default:
      return { icon: 'server-outline' as const, color: C.ink2, bg: C.paper2 };
  }
}

export default function AttributionChips({ sources, onOpenMemory }: Props) {
  const [expanded, setExpanded] = useState(false);
  const items = useMemo(() => normalizeSources(sources), [sources]);
  if (items.length === 0) return null;

  return (
    <View style={styles.wrap} accessibilityLabel="AI 用到了你的数据">
      <Pressable
        style={({ pressed }) => [styles.summaryRow, pressed && styles.summaryPressed]}
        onPress={() => setExpanded(value => !value)}
        accessibilityRole="button"
        accessibilityLabel={expanded ? '收起使用数据' : '展开使用数据'}
        accessibilityState={{ expanded }}
      >
        <Ionicons name="layers-outline" size={12} color={C.ink3} />
        <Text style={txt.prefix}>使用数据 · {items.length} 项</Text>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={12} color={C.ink3} />
      </Pressable>
      {expanded ? (
        <AttributionDetails sources={sources} onOpenMemory={onOpenMemory} maxVisible={MAX_VISIBLE} />
      ) : null}
    </View>
  );
}

export function AttributionDetails({ sources, onOpenMemory, maxVisible = 8 }: DetailsProps) {
  const items = useMemo(() => normalizeSources(sources), [sources]);
  const visible = items.slice(0, maxVisible);
  const hiddenCount = items.length - visible.length;
  if (items.length === 0) return null;

  return (
    <View style={styles.chipsRow} testID="assistant-attribution-details">
      {visible.map(item => (
        <SourceChip
          key={item.label}
          item={item}
          onOpenMemory={item.kind === 'memory' ? onOpenMemory : undefined}
        />
      ))}
      {hiddenCount > 0 ? (
        <View style={[styles.chip, { backgroundColor: C.paper2 }]}>
          <Text style={txt.chipMore}>+{hiddenCount}</Text>
        </View>
      ) : null}
    </View>
  );
}

function SourceChip({ item, onOpenMemory }: { item: StructuredSource; onOpenMemory?: () => void }) {
  const meta = sourceMeta(item.kind);
  const content = (
    <>
      <Ionicons name={meta.icon} size={11} color={meta.color} />
      <Text style={[styles.chipLabel, { color: meta.color }]}>
        {item.label}
      </Text>
    </>
  );
  if (onOpenMemory) {
    return (
      <Pressable
        onPress={onOpenMemory}
        accessibilityRole="button"
        accessibilityLabel={`查看 AI 记忆来源：${item.label}`}
        style={({ pressed }) => [
          styles.chip,
          styles.chipInteractive,
          { backgroundColor: meta.bg },
          pressed && styles.chipPressed,
        ]}
      >
        {content}
        <Ionicons name="chevron-forward" size={11} color={meta.color} />
      </Pressable>
    );
  }
  return <View style={[styles.chip, { backgroundColor: meta.bg }]}>{content}</View>;
}

const styles = StyleSheet.create({
  wrap: {
    marginTop: revaSpacing.s2,
    paddingTop: revaSpacing.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.paper2,
    gap: revaSpacing.s1,
  },
  summaryRow: {
    alignSelf: 'flex-start',
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
  },
  summaryPressed: { opacity: 0.74 },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  chip: {
    minHeight: 26,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 3,
    borderRadius: revaRadii.pill,
    maxWidth: 280,
  },
  chipInteractive: { minHeight: 44 },
  chipPressed: { opacity: 0.7 },
  chipLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '600',
    flexShrink: 1,
  } as TextStyle,
});

const txt = {
  prefix: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, fontWeight: '600' } as TextStyle,
  chipMore: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink2 } as TextStyle,
};
