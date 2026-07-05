import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { supplementApi } from '../../services/records';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

// 补剂分区的装饰性 hue (紫) —— 「区分类目」的色码,不是「指标好坏」三步语义,故为局部字面量。
const SUPP_HUE = { color: '#7C5CBF', bg: '#EDE7F6' } as const;

const timingLabels: Record<string, string> = { morning: '早晨', noon: '中午', evening: '晚上', bedtime: '睡前' };
const timingOrder = ['morning', 'noon', 'evening', 'bedtime'];

interface Props {
  supplements: any[];
  onToggle?: () => void;
  onChat?: () => void;
}

export default function SupplementCheckin({ supplements, onToggle, onChat }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [localState, setLocalState] = useState<Record<number, boolean>>({});

  if (!supplements || supplements.length === 0) return null;

  const total = supplements.length;
  const taken = supplements.filter((s: any) => {
    const id = s.supplement?.id || s.id;
    if (id in localState) return localState[id];
    return s.record?.taken || s.is_taken || s.checked;
  }).length;

  // Group by timing
  const grouped: Record<string, any[]> = {};
  for (const s of supplements) {
    const timing = s.supplement?.timing || s.timing || 'morning';
    if (!grouped[timing]) grouped[timing] = [];
    grouped[timing].push(s);
  }

  const flat = timingOrder.flatMap(t => (grouped[t] || []).map((s: any) => ({ ...s, _timing: t })));
  // Show completed first (with strikethrough), then uncompleted
  const completedItems = flat.filter((s: any) => {
    const id = s.supplement?.id || s.id;
    return id in localState ? localState[id] : (s.record?.taken || s.is_taken || s.checked);
  });
  const uncompletedItems = flat.filter((s: any) => {
    const id = s.supplement?.id || s.id;
    return !(id in localState ? localState[id] : (s.record?.taken || s.is_taken || s.checked));
  });
  const sorted = [...completedItems, ...uncompletedItems];
  const visible = expanded ? sorted : sorted.slice(0, 6);

  const today = (() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  })();

  const toggleSupp = async (suppId: number, currentTaken: boolean) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const newTaken = !currentTaken;
    setLocalState(prev => ({ ...prev, [suppId]: newTaken }));
    try {
      await supplementApi.batchCheckin(today, suppId, newTaken);
      // Don't refetch immediately — local state is sufficient
    } catch {
      // Revert on error
      setLocalState(prev => ({ ...prev, [suppId]: currentTaken }));
    }
  };

  let lastTiming = '';

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={[styles.iconCircle, { backgroundColor: SUPP_HUE.bg }]}>
          <Ionicons name="medical" size={14} color={SUPP_HUE.color} />
        </View>
        <Text style={txt.title}>补剂打卡</Text>
        <View style={styles.badge}>
          <Text style={txt.badge}>{taken}/{total}</Text>
        </View>
      </View>
      {visible.map((s: any) => {
        const id = s.supplement?.id || s.id;
        const name = s.supplement?.name || s.name;
        const isTaken = id in localState ? localState[id] : (s.record?.taken || s.is_taken || s.checked);
        const timing = s._timing;
        const showTimingLabel = timing !== lastTiming;
        lastTiming = timing;

        return (
          <React.Fragment key={`${id}-${timing}`}>
            {showTimingLabel && (
              <Text style={txt.timingLabel}>{timingLabels[timing] || timing}</Text>
            )}
            <Pressable style={styles.row} onPress={() => toggleSupp(id, isTaken)}>
              <View style={[styles.checkbox, isTaken && styles.checkboxChecked]}>
                {isTaken && <Ionicons name="checkmark" size={12} color="#fff" />}
              </View>
              <Text style={[txt.name, isTaken && txt.nameChecked]} numberOfLines={1}>{name}</Text>
            </Pressable>
          </React.Fragment>
        );
      })}
      {sorted.length > 6 && (
        <Pressable onPress={() => setExpanded(!expanded)} style={styles.expandBtn}>
          <Text style={txt.expand}>{expanded ? '收起' : `展开全部 (${total})`}</Text>
        </Pressable>
      )}
      {onChat && (
        <Pressable
          onPress={onChat}
          style={styles.agentLink}
          accessibilityRole="button"
          accessibilityLabel="跟小巴调整补剂安排"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={15} color={C.green500} />
          <Text style={txt.agentLink}>跟小巴调整补剂安排</Text>
          <Ionicons name="chevron-forward" size={14} color={C.green500} />
        </Pressable>
      )}
    </View>
  );
}

// Reva 设计语言:暖白 surface / r-lg 18 / light-first 软阴影。补剂紫为类目装饰色。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    marginBottom: revaSpacing.s3,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: revaSpacing.s3,
  },
  iconCircle: {
    width: 28, height: 28, borderRadius: revaRadii.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  badge: {
    backgroundColor: SUPP_HUE.bg,
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: revaRadii.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 6,
  },
  checkbox: {
    width: 22, height: 22, borderRadius: 11,
    borderWidth: 2, borderColor: C.ink4,
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: {
    backgroundColor: C.green500,
    borderColor: C.green500,
  },
  expandBtn: {
    alignItems: 'center',
    paddingTop: revaSpacing.s2,
  },
  agentLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: revaSpacing.s3,
    paddingTop: revaSpacing.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
});

// 数字(打卡计数)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1 } as TextStyle,
  badge: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '600', color: SUPP_HUE.color } as TextStyle,
  timingLabel: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '600', color: C.ink3, marginTop: 8, marginBottom: 4 } as TextStyle,
  name: { fontFamily: revaFonts.sans, fontSize: 15, color: C.ink1, flex: 1 } as TextStyle,
  nameChecked: { color: C.ink3, textDecorationLine: 'line-through' } as TextStyle,
  expand: { fontFamily: revaFonts.sans, fontSize: 13, color: C.green500, fontWeight: '500' } as TextStyle,
  agentLink: { fontFamily: revaFonts.sans, fontSize: 13, color: C.green500, fontWeight: '600', flex: 1 } as TextStyle,
};
