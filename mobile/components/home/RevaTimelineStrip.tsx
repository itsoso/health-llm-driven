/**
 * RevaTimelineStrip —— 首页今日时间线(Reva 重设计第 3 块)。
 *
 * 复用 useTodayTimeline 的真实条目(训练 / 补水 / 血氧 / 设备待核对…),
 * 用 RevaKit 的 Card + PlanItem 重排。每行一眼扫:title 单行截断,subtitle 只取
 * 第一个分句(shortSubtitle)单行 + 省略号,完整内容留给点击进详情(deep_link)。
 *   - 顶部 SectionLabel「今日时间线」+ 右侧「待办 N · 已完成 M」。
 *   - 已完成项 done 打勾;血氧偏低这类 severity=critical/high 的 advisory 用 risk Chip 标红。
 *   - action 项点「开始」→ 引导式执行屏(R17);可完成项点行勾走 /agenda/complete 双轨。
 *
 * 自己取数,失败 / 空态诚实退化,不渲染空卡(让位给下方分组)。
 */
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';

import { revaColors as C } from '../../constants/revaTheme';
import { Card, Chip, Icon, PlanItem, SectionLabel } from '../reva/RevaKit';
import { useCompleteAgendaItem, useTodayTimeline } from '../../hooks/useTodayTimeline';
import type {
  TimelineCompleteRef,
  TodayTimelineItem,
} from '../../services/todayTimeline';

const MAX_VISIBLE = 6;
const MOBILITY_WORDS = ['拉伸', '柔韧'];
const CARDIO_ONLY_WORDS = ['跑步', '健走', '步行', '快走', '慢跑'];
const MOVEMENT_ICONS = ['barbell', 'fitness', 'body'];
const MOVEMENT_WORDS = ['训练', '运动', '拉伸', '柔韧', '力量', '锻炼', '俯卧撑'];

// 与 TodayTimelineBlock 同源的运动域识别:返回 strength/mobility 才给「开始」引导入口。
function movementDomain(item: TodayTimelineItem): 'strength' | 'mobility' | null {
  if (item.kind !== 'action') return null;
  const icon = (item.icon || '').toLowerCase();
  const text = `${item.title} ${item.subtitle ?? ''}`;
  if (MOBILITY_WORDS.some((w) => text.includes(w))) return 'mobility';
  const cardioHit = CARDIO_ONLY_WORDS.some((w) => text.includes(w));
  const strengthHit =
    MOVEMENT_ICONS.some((k) => icon.includes(k)) || MOVEMENT_WORDS.some((w) => text.includes(w));
  if (cardioHit && !strengthHit) return null;
  return strengthHit ? 'strength' : null;
}

function refKey(ref: TimelineCompleteRef): string {
  return `${ref.object_type}-${ref.object_id}`;
}

function isRisk(item: TodayTimelineItem): boolean {
  return item.severity === 'critical' || item.severity === 'high';
}

// Ionicons name → RevaKit Icon (Lucide-ish) name; 缺映射时回退原名(Icon 内再兜底)。
const ICON_BACK: Record<string, string> = {
  'barbell-outline': 'activity',
  'fitness-outline': 'activity',
  'body-outline': 'activity',
  'water-outline': 'droplet',
  'moon-outline': 'moon',
  'restaurant-outline': 'utensils',
  'medical-outline': 'pill',
  'walk-outline': 'footprints',
  'pulse-outline': 'activity',
  'heart-outline': 'heart',
  'warning-outline': 'alert-triangle',
  'watch-outline': 'watch',
};
function planIcon(item: TodayTimelineItem): string {
  return ICON_BACK[item.icon] ?? item.icon ?? 'sparkles';
}

// 时间线一眼扫:subtitle 只取第一个分句(到首个 ; ; , , 。 . 止),完整内容留给点击进详情。
// 同时清洗后端把 unknown / 空来源名糊进文案的情况(「unknown 的步数窗口…」→「某设备 …」)。
function shortSubtitle(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  let s = raw.trim();
  if (!s) return undefined;
  // 来源名 unknown / 空 泄漏:替换为「某设备」,不把 unknown 直接显示给用户。
  s = s.replace(/\bunknown\b/gi, '某设备').replace(/未知设备|未知来源/g, '某设备');
  // 取第一个分句:首个分隔符之前。中英文分号/逗号/句号都断。
  const cut = s.search(/[;；,，。.]/);
  if (cut > 0) s = s.slice(0, cut);
  return s.trim() || undefined;
}

export default function RevaTimelineStrip() {
  const router = useRouter();
  const { data, isLoading, isError } = useTodayTimeline();
  const complete = useCompleteAgendaItem();
  const [expand, setExpand] = useState(false);
  const [pendingRef, setPendingRef] = useState<string | null>(null);

  const openDeepLink = useCallback(
    (link: string | null) => {
      if (!link) return;
      const path = link.startsWith('/') ? link : `/${link}`;
      router.push(path as any);
    },
    [router],
  );

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
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
          Alert.alert('完成失败', '没有保存成功,请稍后重试。');
          setPendingRef(null);
        },
      });
    },
    [complete, pendingRef],
  );

  const items = useMemo(() => data?.items ?? [], [data]);
  const past = data?.past ?? { completed_count: 0, events: [] };
  const counts = data?.counts ?? { actionable: 0, overdue: 0, info: 0 };

  if (isLoading) {
    return (
      <View>
        <SectionLabel>今日时间线</SectionLabel>
        <Card>
          <ActivityIndicator color={C.green500} />
        </Card>
      </View>
    );
  }

  // 网络错误 / 无数据 → 不渲染(下方分组各卡自带错误态)
  if (isError || !data) return null;

  // 时间线行:action / advisory / checkup(outcome 由结果归因区呈现,这里跳过)
  const rows = items.filter((i) => i.kind !== 'outcome');
  if (rows.length === 0 && past.completed_count === 0) return null;

  const visible = expand ? rows : rows.slice(0, MAX_VISIBLE);
  const hidden = rows.length - visible.length;
  const countsLabel = `待办 ${counts.actionable} · 已完成 ${past.completed_count}`;

  return (
    <View>
      <SectionLabel action={countsLabel}>今日时间线</SectionLabel>
      <Card pad={0}>
        {visible.map((item, i) => {
          const domain = movementDomain(item);
          const pending = pendingRef === (item.complete_ref ? refKey(item.complete_ref) : '');
          const done = item.status === 'completed';
          const last = i === visible.length - 1 && hidden === 0;
          const tag = item.subtitle && !done ? undefined : undefined; // sub carries detail; tag unused
          return (
            <View key={item.id}>
              <PlanItem
                icon={planIcon(item)}
                title={item.title}
                titleLines={1}
                sub={shortSubtitle(item.subtitle)}
                subLines={1}
                tag={tag}
                done={done}
                last={last && !(isRisk(item) || domain || (item.can_complete && item.complete_ref))}
                onToggle={
                  item.can_complete && item.complete_ref && !done
                    ? () => onComplete(item)
                    : () => openDeepLink(item.deep_link)
                }
              />
              {/* 行动子区:风险标红 chip / 「开始」引导 / 完成 pending 指示 */}
              {isRisk(item) || domain || pending ? (
                <View style={[styles.subRow, last && { borderBottomWidth: 0 }]}>
                  {isRisk(item) ? <Chip status="risk">需关注</Chip> : null}
                  {pending ? (
                    <View style={styles.pendingPill}>
                      <ActivityIndicator size="small" color={C.green500} />
                      <Text style={styles.pendingText}>保存中</Text>
                    </View>
                  ) : null}
                  {domain && !done ? (
                    <Pressable
                      style={styles.startBtn}
                      onPress={() => onStart(item, domain)}
                      accessibilityRole="button"
                      accessibilityLabel={`开始 ${item.title}`}
                    >
                      <Icon name="play" size={12} color={C.greenOn} />
                      <Text style={styles.startText}>开始</Text>
                    </Pressable>
                  ) : null}
                </View>
              ) : null}
            </View>
          );
        })}

        {hidden > 0 ? (
          <Pressable style={styles.moreRow} onPress={() => setExpand(true)}>
            <Text style={styles.moreText}>还有 {hidden} 项</Text>
            <Icon name="chevron-right" size={14} color={C.ink3} />
          </Pressable>
        ) : null}
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  subRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingBottom: 12,
    marginTop: -4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  startBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 999,
    backgroundColor: C.green500,
    marginLeft: 'auto',
  },
  startText: { color: C.greenOn, fontWeight: '700', fontSize: 12.5 },
  pendingPill: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  pendingText: { fontSize: 12, color: C.ink3 },
  moreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 13,
  },
  moreText: { fontSize: 13, color: C.ink3, fontWeight: '600' },
});
