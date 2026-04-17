import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { supplementApi } from '@/services/records';
import { colors, spacing, radii, shadows } from '@/constants/theme';

const timingLabels: Record<string, string> = { morning: '早晨', noon: '中午', evening: '晚上', bedtime: '睡前' };
const timingOrder = ['morning', 'noon', 'evening', 'bedtime'];

interface Props {
  supplements: any[];
  onToggle?: () => void;
}

export default function SupplementCheckin({ supplements, onToggle }: Props) {
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
  const visible = expanded ? flat : flat.slice(0, 6);

  const today = (() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  })();

  const toggleSupp = async (suppId: number, currentTaken: boolean) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setLocalState(prev => ({ ...prev, [suppId]: !currentTaken }));
    try {
      if (!currentTaken) {
        await supplementApi.recordSupplement(suppId, today);
      } else {
        await supplementApi.deleteSupplementRecord(suppId, today);
      }
      onToggle?.();
    } catch {
      setLocalState(prev => ({ ...prev, [suppId]: currentTaken }));
    }
  };

  let lastTiming = '';

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={[styles.iconCircle, { backgroundColor: '#F5E6FF' }]}>
          <Ionicons name="medical" size={14} color="#AF52DE" />
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
      {flat.length > 6 && (
        <Pressable onPress={() => setExpanded(!expanded)} style={styles.expandBtn}>
          <Text style={txt.expand}>{expanded ? '收起' : `展开全部 (${total})`}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    ...shadows.subtle,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: spacing.md,
  },
  iconCircle: {
    width: 28, height: 28, borderRadius: 8,
    alignItems: 'center', justifyContent: 'center',
  },
  badge: {
    backgroundColor: '#F5E6FF',
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: 10,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 6,
  },
  checkbox: {
    width: 22, height: 22, borderRadius: 11,
    borderWidth: 2, borderColor: colors.labelQuaternary,
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
  expandBtn: {
    alignItems: 'center',
    paddingTop: spacing.sm,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1 } as TextStyle,
  badge: { fontSize: 12, fontWeight: '600', color: '#AF52DE' } as TextStyle,
  timingLabel: { fontSize: 11, fontWeight: '600', color: colors.labelTertiary, marginTop: 8, marginBottom: 4 } as TextStyle,
  name: { fontSize: 15, color: colors.labelPrimary, flex: 1 } as TextStyle,
  nameChecked: { color: colors.labelTertiary, textDecorationLine: 'line-through' } as TextStyle,
  expand: { fontSize: 13, color: colors.brand, fontWeight: '500' } as TextStyle,
};
