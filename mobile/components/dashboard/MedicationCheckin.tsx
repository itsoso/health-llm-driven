import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { logMedication, type MedicationTodayItem } from '../../services/medications';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

// 首页折叠:默认只渲染待服药(最多 N 条),其余收进「查看全部」。
const COLLAPSED_LIMIT = 3;

interface Props {
  /** 来自首页 dashboard 的 medicationToday (GET /medication/today/me),已按需过滤 */
  items: MedicationTodayItem[] | null | undefined;
  /** 打卡成功后让首页刷新 dashboard (qc.invalidateQueries) */
  onChanged?: () => void;
  /** 卡片标题(药品/补剂分区用),默认「今日用药」 */
  title?: string;
  /** 头部图标(Ionicons 名),默认 medkit */
  icon?: keyof typeof Ionicons.glyphMap;
}

function nowHHMM(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** 当日完成数 = max(total_count, 1), 没配次数的按 1 次算 */
function targetCount(item: MedicationTodayItem): number {
  return Math.max(item.total_count ?? 1, 1);
}

export default function MedicationCheckin({ items, onChanged, title = '今日用药', icon = 'medkit' }: Props) {
  const router = useRouter();

  // 乐观叠加: medication_id → 本地额外的 taken 次数 (尚未回写 dashboard 前)
  const [optimistic, setOptimistic] = useState<Record<number, number>>({});
  const [pending, setPending] = useState<Record<number, boolean>>({});
  // 首页折叠态:默认 false(只看待服 + 汇总),「查看全部」展开全部行。
  const [expanded, setExpanded] = useState(false);

  // 空态: 无在服药品时整卡不渲染
  if (!items || items.length === 0) return null;

  const effectiveTaken = (item: MedicationTodayItem) =>
    item.taken_count + (optimistic[item.medication_id] ?? 0);

  const totalTarget = items.reduce((acc, it) => acc + targetCount(it), 0);
  const totalTaken = items.reduce(
    (acc, it) => acc + Math.min(effectiveTaken(it), targetCount(it)),
    0,
  );

  // 折叠规则:默认只显示「待服」药(未服满),最多 COLLAPSED_LIMIT 条;展开后显示全部。
  const pendingItems = items.filter((it) => effectiveTaken(it) < targetCount(it));
  const collapsedItems = pendingItems.slice(0, COLLAPSED_LIMIT);
  const visibleItems = expanded ? items : collapsedItems;
  const hiddenCount = items.length - visibleItems.length;
  const allDone = pendingItems.length === 0;

  const handleTake = async (item: MedicationTodayItem) => {
    const id = item.medication_id;
    if (pending[id]) return;
    if (effectiveTaken(item) >= targetCount(item)) return; // 已服满

    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    // 乐观 +1
    setOptimistic((prev) => ({ ...prev, [id]: (prev[id] ?? 0) + 1 }));
    setPending((prev) => ({ ...prev, [id]: true }));

    try {
      await logMedication({
        medication_id: id,
        taken_time: nowHHMM(),
        status: 'taken',
      });
      onChanged?.();
    } catch {
      // 回滚乐观更新
      setOptimistic((prev) => ({ ...prev, [id]: Math.max((prev[id] ?? 1) - 1, 0) }));
    } finally {
      setPending((prev) => ({ ...prev, [id]: false }));
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.iconCircle}>
          <Ionicons name={icon} size={14} color={revaSemantic.risk.fg} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={txt.title}>{title}</Text>
          <Text style={txt.summarySub}>
            {allDone ? '今日已全部服用' : `${pendingItems.length} 项待服`}
          </Text>
        </View>
        <View style={styles.badge}>
          <Text style={txt.badge}>
            {totalTaken}/{totalTarget} 已服
          </Text>
        </View>
      </View>

      {allDone && !expanded ? (
        <Pressable
          style={styles.allDoneRow}
          onPress={() => setExpanded(true)}
          accessibilityRole="button"
          accessibilityLabel={`查看全部${title}`}
        >
          <Ionicons name="checkmark-circle" size={16} color={C.green500} />
          <Text style={txt.allDoneText}>{title}已全部完成</Text>
        </Pressable>
      ) : null}

      {visibleItems.map((item) => {
        const id = item.medication_id;
        const target = targetCount(item);
        const taken = effectiveTaken(item);
        const done = taken >= target;
        const isPending = !!pending[id];
        const reminderHint =
          item.reminder_times && item.reminder_times.length > 0
            ? item.reminder_times.join(' · ')
            : null;

        return (
          <View key={id} style={styles.row}>
            <View style={styles.rowMain}>
              <View style={styles.nameRow}>
                <Text style={[txt.name, done && txt.nameDone]} numberOfLines={1}>
                  {item.name}
                </Text>
                {item.dosage ? <Text style={txt.dosage}>{item.dosage}</Text> : null}
              </View>
              <View style={styles.metaRow}>
                <Text style={txt.progress}>
                  {Math.min(taken, target)}/{target} 次
                </Text>
                {reminderHint && (
                  <>
                    <Text style={txt.dot}>·</Text>
                    <Ionicons name="time-outline" size={11} color={C.ink3} />
                    <Text style={txt.reminder}>{reminderHint}</Text>
                  </>
                )}
              </View>
            </View>

            {done ? (
              <View style={[styles.takeBtn, styles.takeBtnDone]}>
                <Ionicons name="checkmark" size={16} color={C.green500} />
              </View>
            ) : (
              <Pressable
                style={styles.takeBtn}
                onPress={() => handleTake(item)}
                disabled={isPending}
                accessibilityRole="button"
                accessibilityLabel={`记录已服用 ${item.name}`}
              >
                {isPending ? (
                  <ActivityIndicator size="small" color={C.green500} />
                ) : (
                  <Text style={txt.takeBtnText}>已服</Text>
                )}
              </Pressable>
            )}
          </View>
        );
      })}

      {/* 折叠态:有隐藏行 → 展开;展开态 → 收起。完整列表也可跳用药页。 */}
      {hiddenCount > 0 ? (
        <Pressable
          style={styles.footerRow}
          onPress={() => setExpanded(true)}
          accessibilityRole="button"
          accessibilityLabel={`查看全部 ${items.length} 项用药`}
        >
          <Text style={txt.footerText}>查看全部 ({items.length})</Text>
          <Ionicons name="chevron-forward" size={15} color={C.ink3} />
        </Pressable>
      ) : expanded ? (
        <View style={styles.footerSplit}>
          <Pressable
            style={styles.footerRow}
            onPress={() => setExpanded(false)}
            accessibilityRole="button"
            accessibilityLabel="收起用药列表"
          >
            <Text style={txt.footerText}>收起</Text>
            <Ionicons name="chevron-up" size={15} color={C.ink3} />
          </Pressable>
          <Pressable
            style={styles.footerRow}
            onPress={() => router.push('/medications' as any)}
            accessibilityRole="button"
            accessibilityLabel="打开用药管理"
          >
            <Text style={txt.footerText}>用药管理</Text>
            <Ionicons name="chevron-forward" size={15} color={C.ink3} />
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

// Reva 设计语言(Claude Design handoff):暖白 surface / ink 文字 / 活力绿 / r-lg 18 / 数字等宽。
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
    gap: revaSpacing.s2,
    marginBottom: revaSpacing.s3,
  },
  iconCircle: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: revaSemantic.risk.bg,
  },
  badge: {
    backgroundColor: revaSemantic.risk.bg,
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 2,
    borderRadius: revaRadii.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: revaSpacing.s2,
  },
  rowMain: {
    flex: 1,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 2,
  },
  takeBtn: {
    minWidth: 56,
    height: 32,
    paddingHorizontal: revaSpacing.s3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  takeBtnDone: {
    backgroundColor: C.green50,
    minWidth: 36,
    paddingHorizontal: 0,
  },
  allDoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
  },
  footerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingTop: revaSpacing.s2,
    marginTop: 2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    flex: 1,
  },
  footerSplit: {
    flexDirection: 'row',
    gap: revaSpacing.s3,
  },
});

// 数字(已服计数 / 次数进度)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1 } as TextStyle,
  summarySub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 1 } as TextStyle,
  allDoneText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2 } as TextStyle,
  footerText: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.ink2 } as TextStyle,
  badge: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '500', color: revaSemantic.risk.fg } as TextStyle,
  name: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '500', color: C.ink1 } as TextStyle,
  nameDone: { color: C.ink3 } as TextStyle,
  dosage: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '400', color: C.ink3 } as TextStyle,
  progress: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink2 } as TextStyle,
  dot: { fontSize: 12, color: C.ink4 } as TextStyle,
  reminder: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3 } as TextStyle,
  takeBtnText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.green500 } as TextStyle,
};
