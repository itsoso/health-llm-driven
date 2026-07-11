/**
 * 矛盾裁决横幅 — 小巴对同一件事记了两个方向互斥的说法时, 并排让用户留下对的那条 (走 supersede).
 * 从 app/memory.tsx 抽出, 保持屏文件精简。
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { factSentence, type ContradictionPair, type MemoryFact } from '../../services/memoryFacts';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, SemanticPalette } from '../../hooks/useTheme';

interface Props {
  pairs: ContradictionPair[];
  onKeep: (keepId: number, dropId: number) => void;
  onCollapse: () => void;
  disabled: boolean;
  c: ColorPalette;
  s: SemanticPalette;
}

export default function ContradictionBanner({ pairs, onKeep, onCollapse, disabled, c, s }: Props) {
  const tone = s.warning;
  return (
    <View style={[styles.card, { backgroundColor: tone.bg, borderColor: tone.solid }]}>
      <View style={styles.headerRow}>
        <Ionicons name="git-compare-outline" size={16} color={tone.fg} />
        <Text style={[txt.title, { color: tone.fg }]}>发现 {pairs.length} 处可能矛盾的记忆</Text>
        <Pressable onPress={onCollapse} hitSlop={8} accessibilityLabel="暂时收起矛盾提示">
          <Ionicons name="close" size={16} color={tone.fg} />
        </Pressable>
      </View>
      <Text style={[txt.hint, { color: tone.fg }]}>
        小巴对同一件事记了两个说法，帮它留下对的那个。
      </Text>
      {pairs.map((pair) => (
        <View key={`${pair.a.id}:${pair.b.id}`} style={[styles.pairWrap, { borderTopColor: tone.solid }]}>
          <ConflictOption fact={pair.a} onKeep={() => onKeep(pair.a.id, pair.b.id)} disabled={disabled} c={c} s={s} />
          <Text style={[txt.vs, { color: c.labelTertiary }]}>对</Text>
          <ConflictOption fact={pair.b} onKeep={() => onKeep(pair.b.id, pair.a.id)} disabled={disabled} c={c} s={s} />
        </View>
      ))}
    </View>
  );
}

function ConflictOption({ fact, onKeep, disabled, c, s }: {
  fact: MemoryFact; onKeep: () => void; disabled: boolean; c: ColorPalette; s: SemanticPalette;
}) {
  return (
    <View style={styles.option}>
      <Text style={[txt.option, { color: c.labelPrimary }]} numberOfLines={3}>{factSentence(fact)}</Text>
      <Pressable
        testID={`memory-keep-${fact.id}`}
        onPress={onKeep}
        disabled={disabled}
        style={({ pressed }) => [
          styles.keepBtn,
          { backgroundColor: s.success.solid },
          pressed && { opacity: 0.7 },
          disabled && { opacity: 0.4 },
        ]}
        accessibilityRole="button"
        accessibilityLabel="保留这条记忆"
      >
        <Text style={styles.keepText}>保留这条</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.md, borderWidth: 1, padding: spacing.md, gap: spacing.sm },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  pairWrap: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    paddingTop: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth,
  },
  option: { flex: 1, gap: 6 },
  keepBtn: { paddingVertical: 6, borderRadius: radii.full, alignItems: 'center' },
  keepText: { fontSize: 12, fontWeight: '600', color: '#FFFFFF' },
});

const txt = {
  title: { flex: 1, fontSize: 14, fontWeight: '700' } as TextStyle,
  hint: { fontSize: 12, lineHeight: 17 } as TextStyle,
  option: { fontSize: 13, lineHeight: 18 } as TextStyle,
  vs: { fontSize: 11 } as TextStyle,
};
