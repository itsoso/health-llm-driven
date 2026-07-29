import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { EvidenceRefsRow } from './EvidenceRefsRow';
import type { EvidenceRef } from './EvidenceRefsRow';
import { revaColors as C, revaSemantic, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';
import { todayStr } from '../../../utils/dietDate';

// 补剂类目 accent (紫) + 卡底 tint = 装饰色, 保留字面量 (= legacy purple/tintPurple).
const SUPP_ACCENT = '#7C5CBF';
const SUPP_TINT = '#EDE7F6';

interface SupplementData {
  checked: number;
  total: number;
  pending_names: string[];
  evidence_refs?: EvidenceRef[];
}

export function SupplementCardView({ checked, total, pending_names, evidence_refs }: SupplementData) {
  const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
  // 进度 = 完成度「好坏」语义 → Reva 三步临床色 normal/caution/risk
  const barColor = pct >= 80 ? revaSemantic.normal.fg : pct >= 50 ? revaSemantic.caution.fg : revaSemantic.risk.fg;
  return (
    <CardShell
      icon="medical"
      iconColor={SUPP_ACCENT}
      title="补剂打卡"
      badge={`${checked}/${total}`}
      badgeColor={barColor}
      bg={SUPP_TINT}
    >
      <View style={[styles.progressTrack, { backgroundColor: C.paper2 }]}>
        <View style={[styles.progressFill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      {pending_names.length > 0 && (
        <View style={styles.pendingWrap}>
          <Text maxFontSizeMultiplier={1.3} style={styles.pendingLabel}>
            未打卡：
          </Text>
          <View style={styles.chips}>
            {pending_names.slice(0, 4).map((n) => (
              <View key={n} style={[styles.chip, { backgroundColor: C.paper }]}>
                <Ionicons name="time-outline" size={9} color={C.ink3} />
                <Text maxFontSizeMultiplier={1.3} style={styles.chipText} numberOfLines={1}>
                  {n}
                </Text>
              </View>
            ))}
            {pending_names.length > 4 && (
              <Text maxFontSizeMultiplier={1.3} style={styles.more}>
                +{pending_names.length - 4}
              </Text>
            )}
          </View>
        </View>
      )}
      {pending_names.length === 0 && total > 0 && (
        <Text maxFontSizeMultiplier={1.3} style={styles.allDone}>
          ✅ 今日补剂已全部打卡
        </Text>
      )}
      <EvidenceRefsRow refs={evidence_refs} />
    </CardShell>
  );
}

export const SupplementCardSpec: CardSpec<SupplementData> = {
  type: 'supplement_status',
  label: '补剂打卡',
  match({ query_lower }) {
    if (/补剂吃了吗|补剂进度|今天吃了什么补剂|补剂状态|补剂打卡|未吃的补剂/.test(query_lower)) return 15;
    return null;
  },
  async build({ api }) {
    try {
      const today = todayStr();
      const res = await api.get(`/supplements/me/date/${today}`);
      const list: any[] = res.data || [];
      if (list.length === 0) return null;
      const seen = new Set<string>();
      const dedup = list.filter((s) => {
        const key = `${s.supplement?.name || s.supplement_name || s.name}_${s.supplement?.timing || s.timing || 'morning'}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      const checked = dedup.filter((s) => s.record?.taken || s.is_taken || s.checked).length;
      const pending_names = dedup
        .filter((s) => !(s.record?.taken || s.is_taken || s.checked))
        .map((s) => s.supplement?.name || s.supplement_name || s.name || '未知');
      return { checked, total: dedup.length, pending_names };
    } catch {
      return null;
    }
  },
  render: (d) => <SupplementCardView {...d} />,
};

const styles = StyleSheet.create({
  progressTrack: { height: 6, borderRadius: 3, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 3 },
  pendingWrap: { marginTop: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 8,
  },
  pendingLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
  chipText: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink1, maxWidth: 80 } as TextStyle,
  more: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3, alignSelf: 'center' } as TextStyle,
  allDone: { fontFamily: revaFonts.sans, fontSize: 11, color: C.green500, marginTop: 6, fontWeight: '600' } as TextStyle,
});
