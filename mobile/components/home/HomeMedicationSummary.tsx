import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import type { MedicationTodayItem } from '../../services/medications';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';

interface Props {
  items: MedicationTodayItem[] | null | undefined;
  /** 保留签名兼容首页调用;紧凑汇总不再逐项打卡,onChanged 不触发。 */
  onChanged?: () => void;
}

interface CategorySummary {
  key: 'medication' | 'supplement';
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  total: number; // 目标剂次总数(全部条目)
  taken: number; // 已服剂次(封顶到目标)
  pendingCount: number; // 未服满的条目数
  nextTime: string | null; // 派生的下一剂 HH:MM(> 当前时间的最早 pending),派生不了为 null
}

/** 当日目标次数 = max(total_count, 1),没配次数按 1 次算 */
function targetCount(item: MedicationTodayItem): number {
  return Math.max(item.total_count ?? 1, 1);
}

function nowHHMM(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * 从待服条目的 reminder_times 里派生"下一剂"——取严格大于当前时间的最早 HH:MM。
 * 没有任何 pending 条目带出未来的提醒时间就返回 null(不硬造)。
 */
function deriveNextTime(pendingItems: MedicationTodayItem[]): string | null {
  const now = nowHHMM();
  let next: string | null = null;
  for (const item of pendingItems) {
    for (const t of item.reminder_times ?? []) {
      if (t > now && (next === null || t < next)) next = t;
    }
  }
  return next;
}

function summarize(
  key: CategorySummary['key'],
  label: string,
  icon: keyof typeof Ionicons.glyphMap,
  items: MedicationTodayItem[],
): CategorySummary {
  let total = 0;
  let taken = 0;
  const pendingItems: MedicationTodayItem[] = [];
  for (const item of items) {
    const t = targetCount(item);
    const done = Math.min(item.taken_count, t);
    total += t;
    taken += done;
    if (done < t) pendingItems.push(item);
  }
  return {
    key,
    label,
    icon,
    total,
    taken,
    pendingCount: pendingItems.length,
    nextTime: deriveNextTime(pendingItems),
  };
}

function CategoryRow({ summary }: { summary: CategorySummary }) {
  const router = useRouter();
  const allDone = summary.pendingCount === 0;

  // 单节点字符串:RN <Text> 里插值 + 字面量会拆成多个 text 子节点,
  // 组好整串再渲染,保证 getByText 能整体匹配。
  const pendingLabel =
    `${summary.pendingCount} 项待服` +
    (summary.nextTime ? ` · 下一剂 ${summary.nextTime}` : '');
  const badgeLabel = `${summary.taken}/${summary.total} 已服`;

  return (
    <Pressable
      style={styles.row}
      onPress={() => router.push('/medications' as any)}
      accessibilityRole="button"
      accessibilityLabel={`${summary.label}:${badgeLabel},打开用药管理`}
    >
      <View style={styles.iconCircle}>
        <Ionicons name={summary.icon} size={14} color={revaSemantic.risk.fg} />
      </View>

      <View style={styles.mid}>
        <Text style={txt.label}>{summary.label}</Text>
        {allDone ? (
          <View style={styles.subRow}>
            <Ionicons name="checkmark-circle" size={13} color={C.green500} />
            <Text style={txt.doneSub}>今日已全部服用</Text>
          </View>
        ) : (
          <Text style={txt.pendingSub}>{pendingLabel}</Text>
        )}
      </View>

      <View style={styles.badge}>
        <Text style={txt.badge}>{badgeLabel}</Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={C.ink3} />
    </Pressable>
  );
}

export default function HomeMedicationSummary({ items }: Props) {
  const all = Array.isArray(items) ? items.filter(Boolean) : [];
  if (all.length === 0) return null;

  const medication = summarize(
    'medication',
    '用药',
    'medkit',
    all.filter((item) => item.category !== 'supplement'),
  );
  const supplement = summarize(
    'supplement',
    '补剂',
    'leaf',
    all.filter((item) => item.category === 'supplement'),
  );

  // 有目标剂次(total>0)才成行——空分类不渲染。
  const categories = [medication, supplement].filter((category) => category.total > 0);
  if (categories.length === 0) return null;

  return (
    <View style={styles.card}>
      {categories.map((category, i) => (
        <React.Fragment key={category.key}>
          {i > 0 ? <View style={styles.divider} /> : null}
          <CategoryRow summary={category} />
        </React.Fragment>
      ))}
    </View>
  );
}

// Reva 设计语言:暖白 surface / ink 文字 / 活力绿 / r-lg 18 / 数字等宽。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    paddingHorizontal: revaSpacing.s4,
    marginBottom: revaSpacing.s3,
    ...revaShadows.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    paddingVertical: revaSpacing.s3,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: C.line,
  },
  iconCircle: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: revaSemantic.risk.bg,
  },
  mid: {
    flex: 1,
  },
  subRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 1,
  },
  badge: {
    backgroundColor: revaSemantic.risk.bg,
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 2,
    borderRadius: revaRadii.sm,
  },
});

const txt = {
  label: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1 } as TextStyle,
  pendingSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 1 } as TextStyle,
  doneSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2 } as TextStyle,
  badge: {
    fontFamily: revaFonts.mono,
    fontSize: 12,
    fontWeight: '500',
    color: revaSemantic.risk.fg,
    letterSpacing: 0,
  } as TextStyle,
};
