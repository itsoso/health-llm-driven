/**
 * TodayTimelineBlock —— 首页最顶部「今日时间线」区块(范式翻转第一刀)。
 *
 * 结构:
 *   结果归因(outcome,放大器,顶部高亮)
 *   未来/现在区(items,最多 5 条 + 折叠;action 可完成,advisory/checkup 走 deep_link)
 *   过去区(折叠,今天已完成 N 件,observation 只读)
 *
 * 自己内部取数(useTodayTimeline),不往 index.tsx 堆查询逻辑。
 * 空态(items 空且 past 空)→ 轻量引导,不渲染空卡。
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
  ViewStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';

import HealthCard from '../design-system/HealthCard';
import { radii, spacing, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import {
  useCompleteAgendaItem,
  useTodayTimeline,
} from '../../hooks/useTodayTimeline';
import type {
  TimelineCompleteRef,
  TodayTimelineItem,
} from '../../services/todayTimeline';

const MAX_VISIBLE_ITEMS = 5;

export default function TodayTimelineBlock() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data, isLoading, isError } = useTodayTimeline();
  const complete = useCompleteAgendaItem();

  const [expandItems, setExpandItems] = useState(false);
  const [expandPast, setExpandPast] = useState(false);
  // action-lock: 防双击,同一条只允许一个在途完成请求
  const [pendingRef, setPendingRef] = useState<string | null>(null);

  const openDeepLink = useCallback(
    (link: string | null) => {
      if (!link) return;
      const path = link.startsWith('/') ? link : `/${link}`;
      router.push(path as any);
    },
    [router],
  );

  // R17:运动 action 项点「开始」→ 引导式执行屏(裁决③:用户主动进,不自动打开)。
  // 带上 complete_ref,让引导屏完成时走 /agenda/complete 双轨写真实记录。
  const onStart = useCallback(
    (item: TodayTimelineItem, domain: string) => {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      const ref = item.complete_ref;
      const q = ref
        ? `&completeType=${encodeURIComponent(ref.object_type)}&completeId=${ref.object_id}`
        : '';
      router.push(`/guided-task?domain=${encodeURIComponent(domain)}${q}` as any);
    },
    [router],
  );

  const onComplete = useCallback(
    (item: TodayTimelineItem) => {
      const ref = item.complete_ref;
      if (!ref) return;
      const key = refKey(ref);
      if (pendingRef) return; // action-lock
      setPendingRef(key);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      complete.mutate(ref, {
        onSuccess: () => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          setPendingRef(null);
        },
        onError: () => {
          // 失败不静默:震动 + 提示,让用户感知
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
          Alert.alert('完成失败', '没有保存成功,请稍后重试。');
          setPendingRef(null);
        },
      });
    },
    [complete, pendingRef],
  );

  if (isLoading) {
    return (
      <HealthCard title="今日时间线" icon="time-outline">
        <View style={styles.loading}>
          <ActivityIndicator color={c.brand} />
        </View>
      </HealthCard>
    );
  }

  // 网络错误 → 不渲染空卡,静默让位给下方看板(下方各卡自带错误态)
  if (isError || !data) return null;

  const items = data.items ?? [];
  const past = data.past ?? { completed_count: 0, events: [] };
  const counts = data.counts ?? { actionable: 0, overdue: 0, info: 0 };

  // 空态:无未来项 + 无已完成 → 轻量引导
  if (items.length === 0 && past.completed_count === 0) {
    return (
      <HealthCard title="今日时间线" icon="time-outline">
        <Text style={styles.emptyText}>
          今天还没有安排,去记录或问问 AI。
        </Text>
        <View style={styles.emptyActions}>
          <TouchableOpacity
            style={styles.emptyBtn}
            onPress={() => router.push('/(tabs)/record' as any)}
          >
            <Ionicons name="add-circle-outline" size={16} color={c.brand} />
            <Text style={styles.emptyBtnText}>去记录</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.emptyBtn}
            onPress={() => router.push('/(tabs)/chat' as any)}
          >
            <Ionicons name="chatbubbles-outline" size={16} color={c.brand} />
            <Text style={styles.emptyBtnText}>问问 AI</Text>
          </TouchableOpacity>
        </View>
      </HealthCard>
    );
  }

  // outcome 提到顶部高亮,其余按原顺序
  const outcomes = items.filter((i) => i.kind === 'outcome');
  const rest = items.filter((i) => i.kind !== 'outcome');
  const visibleRest = expandItems ? rest : rest.slice(0, MAX_VISIBLE_ITEMS);
  const hiddenCount = rest.length - visibleRest.length;

  const countsLabel = `待办 ${counts.actionable} · 逾期 ${counts.overdue}`;

  return (
    <HealthCard
      title="今日时间线"
      icon="time-outline"
      rightAccessory={<Text style={styles.countsLabel}>{countsLabel}</Text>}
    >
      {outcomes.map((item) => (
        <OutcomeRow key={item.id} item={item} styles={styles} s={s} onPress={openDeepLink} />
      ))}

      {visibleRest.map((item) => (
        <ItemRow
          key={item.id}
          item={item}
          styles={styles}
          c={c}
          pending={pendingRef === (item.complete_ref ? refKey(item.complete_ref) : '')}
          locked={Boolean(pendingRef)}
          onComplete={onComplete}
          onStart={onStart}
          onPressRow={openDeepLink}
        />
      ))}

      {hiddenCount > 0 && (
        <TouchableOpacity style={styles.moreRow} onPress={() => setExpandItems(true)}>
          <Text style={styles.moreText}>还有 {hiddenCount} 项</Text>
          <Ionicons name="chevron-down" size={14} color={c.labelSecondary} />
        </TouchableOpacity>
      )}

      {past.completed_count > 0 && (
        <View style={styles.pastSection}>
          <TouchableOpacity
            style={styles.pastHeader}
            onPress={() => setExpandPast((v) => !v)}
          >
            <Ionicons name="checkmark-done-outline" size={15} color={c.brand} />
            <Text style={styles.pastHeaderText}>今天已完成 {past.completed_count} 件</Text>
            <Ionicons
              name={expandPast ? 'chevron-up' : 'chevron-down'}
              size={14}
              color={c.labelSecondary}
            />
          </TouchableOpacity>
          {expandPast &&
            (past.events ?? []).map((item) => (
              <PastRow key={item.id} item={item} styles={styles} c={c} onPress={openDeepLink} />
            ))}
        </View>
      )}
    </HealthCard>
  );
}

function refKey(ref: TimelineCompleteRef): string {
  // F5b:键并入 slot —— 真多剂(BID)两槽共享 object_type/object_id,action-lock 与
  // pending 态必须按槽区分,否则完成晨剂会把晚剂也锁住/标 pending。单剂无 slot → 键同改前。
  return ref.slot
    ? `${ref.object_type}-${ref.object_id}@${ref.slot}`
    : `${ref.object_type}-${ref.object_id}`;
}

// 运动域识别 → 给「开始」入口(R17 引导式执行)。
// 时间线 item 不直接带 domain,用 icon/标题关键词推断。
// 后端 GET /movement/guided-task 的 domain 只接受 Literal["strength","mobility"](其它 → 422),
// 所以返回必须收敛到这两档:拉伸/柔韧 → mobility;力量/泛运动 → strength。
// 纯有氧(跑步/健走/步行)v1 不给「开始」入口(返回 null,保留原完成/deep_link)。
const MOVEMENT_ICONS = ['barbell', 'fitness', 'body'];
const MOVEMENT_WORDS = ['训练', '运动', '拉伸', '柔韧', '力量', '锻炼', '俯卧撑'];
const MOBILITY_WORDS = ['拉伸', '柔韧'];
const CARDIO_ONLY_WORDS = ['跑步', '健走', '步行', '快走', '慢跑'];
function movementDomain(item: TodayTimelineItem): 'strength' | 'mobility' | null {
  if (item.kind !== 'action') return null;
  const icon = (item.icon || '').toLowerCase();
  const text = `${item.title} ${item.subtitle ?? ''}`;
  // 柔韧类优先归 mobility(即便文案里也含「运动」)。
  if (MOBILITY_WORDS.some((w) => text.includes(w))) return 'mobility';
  // 纯有氧项:无「开始」引导入口(v1 后端不支持 cardio domain)。
  const cardioHit = CARDIO_ONLY_WORDS.some((w) => text.includes(w));
  const strengthHit =
    MOVEMENT_ICONS.some((k) => icon.includes(k)) ||
    MOVEMENT_WORDS.some((w) => text.includes(w));
  if (cardioHit && !strengthHit) return null;
  // 力量 / 俯卧撑 / 泛运动 → strength。
  return strengthHit ? 'strength' : null;
}

// ── 结果归因(放大器:你的行动有用)─────────────────────
function OutcomeRow({
  item,
  styles,
  s,
  onPress,
}: {
  item: TodayTimelineItem;
  styles: ReturnType<typeof createStyles>;
  s: ReturnType<typeof useTheme>['s'];
  onPress: (link: string | null) => void;
}) {
  const arrow = item.proof?.direction === 'down' ? 'arrow-down' : 'arrow-up';
  return (
    <TouchableOpacity
      style={[styles.outcomeCard, { backgroundColor: s.success.bg }]}
      activeOpacity={item.deep_link ? 0.7 : 1}
      onPress={() => onPress(item.deep_link)}
    >
      <Ionicons name={item.icon as any} size={20} color={s.success.solid} />
      <View style={styles.outcomeBody}>
        <Text style={[styles.outcomeTitle, { color: s.success.fg }]} numberOfLines={2}>
          {item.title}
        </Text>
        {item.subtitle ? (
          <Text style={styles.outcomeSubtitle} numberOfLines={1}>
            {item.subtitle}
          </Text>
        ) : null}
      </View>
      {item.proof ? (
        <View style={styles.proofBox}>
          <View style={styles.proofDeltaRow}>
            <Ionicons name={arrow} size={18} color={s.success.solid} />
            <Text style={[styles.proofDelta, { color: s.success.solid }]}>
              {item.proof.delta}
            </Text>
          </View>
          <Text style={styles.proofLabel} numberOfLines={1}>
            {item.proof.label}
          </Text>
          {/* 归因诚实:delta 是相关性观察,非因果断言。对所有 outcome 行无条件显示。 */}
          <Text style={styles.proofCaution} numberOfLines={1}>
            相关,非因果
          </Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

// ── 未来/现在区一行 ──────────────────────────────────────
function ItemRow({
  item,
  styles,
  c,
  pending,
  locked,
  onComplete,
  onStart,
  onPressRow,
}: {
  item: TodayTimelineItem;
  styles: ReturnType<typeof createStyles>;
  c: ColorPalette;
  pending: boolean;
  locked: boolean;
  onComplete: (item: TodayTimelineItem) => void;
  onStart: (item: TodayTimelineItem, domain: string) => void;
  onPressRow: (link: string | null) => void;
}) {
  const domain = movementDomain(item);
  return (
    <TouchableOpacity
      style={styles.itemRow}
      activeOpacity={item.deep_link ? 0.7 : 1}
      onPress={() => onPressRow(item.deep_link)}
    >
      <View style={[styles.iconCircle, { backgroundColor: tint(item.color) }]}>
        <Ionicons name={item.icon as any} size={16} color={item.color} />
      </View>
      <View style={styles.itemBody}>
        <Text style={styles.itemTitle} numberOfLines={1}>
          {item.title}
        </Text>
        {item.subtitle ? (
          <Text style={styles.itemSubtitle} numberOfLines={1}>
            {item.subtitle}
          </Text>
        ) : null}
      </View>
      {domain ? (
        <TouchableOpacity
          style={styles.startBtn}
          disabled={locked}
          onPress={() => onStart(item, domain)}
        >
          <Ionicons name="play" size={13} color="#fff" />
          <Text style={styles.startText}>开始</Text>
        </TouchableOpacity>
      ) : null}
      {item.can_complete && item.complete_ref ? (
        <TouchableOpacity
          style={[styles.completeBtn, (pending || locked) && styles.completeBtnDisabled]}
          disabled={pending || locked}
          onPress={() => onComplete(item)}
        >
          {pending ? (
            <ActivityIndicator size="small" color={c.brand} />
          ) : (
            <>
              <Ionicons name="checkmark" size={14} color={c.brand} />
              <Text style={styles.completeText}>完成</Text>
            </>
          )}
        </TouchableOpacity>
      ) : !domain && item.deep_link ? (
        <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />
      ) : null}
    </TouchableOpacity>
  );
}

// ── 过去区一行(只读 observation)───────────────────────
function PastRow({
  item,
  styles,
  c,
  onPress,
}: {
  item: TodayTimelineItem;
  styles: ReturnType<typeof createStyles>;
  c: ColorPalette;
  onPress: (link: string | null) => void;
}) {
  return (
    <TouchableOpacity
      style={styles.pastRow}
      activeOpacity={item.deep_link ? 0.7 : 1}
      onPress={() => onPress(item.deep_link)}
    >
      <Ionicons name={item.icon as any} size={14} color={item.color} />
      <Text style={styles.pastTitle} numberOfLines={1}>
        {item.title}
      </Text>
      {item.subtitle ? (
        <Text style={styles.pastSubtitle} numberOfLines={1}>
          {item.subtitle}
        </Text>
      ) : null}
    </TouchableOpacity>
  );
}

// item.color 是后端给的 hex 前景色;过低饱和的浅底用 18% alpha 叠加。
function tint(hex: string): string {
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) return `${hex}22`;
  return 'rgba(31, 138, 91, 0.13)';
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    loading: { paddingVertical: spacing.lg, alignItems: 'center' },
    countsLabel: {
      ...typography.bodySmall,
      color: c.labelSecondary,
    } as TextStyle,

    // empty
    emptyText: {
      ...typography.bodyMedium,
      color: c.labelSecondary,
    } as TextStyle,
    emptyActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
    emptyBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radii.full,
      backgroundColor: c.brandLight,
    } as ViewStyle,
    emptyBtnText: { ...typography.bodySmall, color: c.brand, fontWeight: '600' } as TextStyle,

    // outcome
    outcomeCard: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      padding: spacing.md,
      borderRadius: radii.md,
      marginBottom: spacing.sm,
    } as ViewStyle,
    outcomeBody: { flex: 1 },
    outcomeTitle: { ...typography.bodyMedium, fontWeight: '600' } as TextStyle,
    outcomeSubtitle: {
      ...typography.bodySmall,
      color: c.labelSecondary,
      marginTop: 2,
    } as TextStyle,
    proofBox: { alignItems: 'flex-end', minWidth: 56 },
    proofDeltaRow: { flexDirection: 'row', alignItems: 'center' },
    proofDelta: { ...typography.metricSmall } as unknown as TextStyle,
    proofLabel: {
      ...typography.caption,
      color: c.labelTertiary,
      marginTop: 2,
    } as TextStyle,
    proofCaution: {
      ...typography.caption,
      color: c.labelTertiary,
      marginTop: 1,
    } as TextStyle,

    // item row
    itemRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.sm,
    } as ViewStyle,
    iconCircle: {
      width: 32,
      height: 32,
      borderRadius: radii.full,
      alignItems: 'center',
      justifyContent: 'center',
    } as ViewStyle,
    itemBody: { flex: 1 },
    itemTitle: { ...typography.bodyMedium, color: c.labelPrimary } as TextStyle,
    itemSubtitle: {
      ...typography.bodySmall,
      color: c.labelSecondary,
      marginTop: 1,
    } as TextStyle,
    completeBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.xs,
      paddingHorizontal: spacing.md,
      borderRadius: radii.full,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.brand,
      minWidth: 64,
      justifyContent: 'center',
    } as ViewStyle,
    completeBtnDisabled: { opacity: 0.5 },
    completeText: { ...typography.bodySmall, color: c.brand, fontWeight: '600' } as TextStyle,
    startBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.xs,
      paddingHorizontal: spacing.md,
      borderRadius: radii.full,
      backgroundColor: c.brand,
      justifyContent: 'center',
    } as ViewStyle,
    startText: { ...typography.bodySmall, color: '#fff', fontWeight: '700' } as TextStyle,

    // more
    moreRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.sm,
    } as ViewStyle,
    moreText: { ...typography.bodySmall, color: c.labelSecondary } as TextStyle,

    // past
    pastSection: {
      marginTop: spacing.sm,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
      paddingTop: spacing.sm,
    } as ViewStyle,
    pastHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.xs,
    } as ViewStyle,
    pastHeaderText: {
      ...typography.bodySmall,
      color: c.labelPrimary,
      fontWeight: '600',
      flex: 1,
    } as TextStyle,
    pastRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.xs,
      paddingLeft: spacing.xs,
    } as ViewStyle,
    pastTitle: { ...typography.bodySmall, color: c.labelSecondary } as TextStyle,
    pastSubtitle: {
      ...typography.caption,
      color: c.labelTertiary,
      flex: 1,
    } as TextStyle,
  });
}
