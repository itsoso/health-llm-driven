/**
 * RevaTimelineStrip —— 首页「接下来」行动条(Reva 重设计第 3 块)。
 *
 * 复用 useTodayTimeline 的真实条目(训练 / 补水 / 血氧 / 设备待核对…),
 * 用 RevaKit 的 Card + PlanItem 重排。每行一眼扫:title 单行截断,subtitle 只取
 * 第一个分句(shortSubtitle)单行 + 省略号,完整内容留给点击进详情(deep_link)。
 *   - 顶部 SectionLabel「接下来」+ 右侧「待办 N · 已完成 M」。
 *   - 已完成项 done 打勾;血氧偏低这类 severity=critical/high 的 advisory 用 risk Chip 标红。
 *   - action 项点「开始」→ 引导式执行屏(R17);可完成项点行勾走 /agenda/complete 双轨。
 *
 * 自己取数,失败 / 空态诚实退化,不渲染空卡(让位给下方分组)。
 */
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';

import { revaColors as C, revaDriver, type RevaDriver } from '../../constants/revaTheme';
import { Card, Chip, Icon, PlanItem, SectionLabel } from '../reva/RevaKit';
import {
  useCompleteAgendaItem,
  useSkipAgendaItem,
  useTodayTimeline,
} from '../../hooks/useTodayTimeline';
import type { AgendaSkipReason } from '../../services/agenda';
import type {
  TimelineCompleteRef,
  TodayTimelineItem,
} from '../../services/todayTimeline';
import SkipReasonSheet from './SkipReasonSheet';
import { formatHealthActionTitle } from '../../utils/actionCopy';

const MAX_VISIBLE = 3;
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
  // F5b:键并入 slot —— 真多剂(BID)两槽共享 object_type/object_id,action-lock 与
  // pending 态必须按槽区分,否则完成晨剂会把晚剂也锁住/标 pending。单剂无 slot → 键同改前。
  return ref.slot
    ? `${ref.object_type}-${ref.object_id}@${ref.slot}`
    : `${ref.object_type}-${ref.object_id}`;
}

function isRisk(item: TodayTimelineItem): boolean {
  return item.severity === 'critical' || item.severity === 'high';
}

// 「为什么这项在这」:工作块(kind==='work')优先归 work;否则映射 item.driver。
// driver 缺省/null(observation / outcome / 设备核对等)→ 返回 null,不画驱动标记(优雅降级)。
function driverKey(item: TodayTimelineItem): RevaDriver | null {
  if (item.kind === 'work') return 'work';
  const d = item.driver;
  if (d === 'plan_driven' || d === 'time_driven' || d === 'event_driven') return d;
  return null;
}

// 内联驱动标记 chip(图标 + 中文短词),配色走 revaDriver token(非硬编码)。
function DriverChip({ driver }: { driver: RevaDriver }) {
  const d = revaDriver[driver];
  return (
    <View style={[styles.driverChip, { backgroundColor: d.bg, borderColor: d.line }]}>
      <Icon name={d.icon} size={11} color={d.fg} />
      <Text style={[styles.driverChipText, { color: d.fg }]}>{d.label}</Text>
    </View>
  );
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

function titleKey(raw: string | null | undefined): string {
  return formatHealthActionTitle(raw)
    .replace(/[：:]/gu, '')
    .replace(/\s+/gu, '')
    .toLowerCase();
}

export default function RevaTimelineStrip({
  excludeTitles = [],
}: {
  excludeTitles?: (string | null | undefined)[];
}) {
  const router = useRouter();
  const { data, isLoading, isError } = useTodayTimeline();
  const complete = useCompleteAgendaItem();
  const skip = useSkipAgendaItem();
  const [expand, setExpand] = useState(false);
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const [pendingRef, setPendingRef] = useState<string | null>(null);
  // 跳过原因抽屉:记住当前正在跳过的项(选完原因再发请求)。
  const [skipTarget, setSkipTarget] = useState<TodayTimelineItem | null>(null);

  const toggleOpen = useCallback((id: string) => {
    Haptics.selectionAsync().catch(() => {});
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

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

  // 「跳过」入口:打开原因抽屉(不立刻发请求,让用户先选/跳过原因)。
  const onSkipPress = useCallback(
    (item: TodayTimelineItem) => {
      if (!item.complete_ref) return;
      if (pendingRef) return; // action-lock:有在途完成请求时不开
      Haptics.selectionAsync().catch(() => {});
      setSkipTarget(item);
    },
    [pendingRef],
  );

  // 抽屉里选完原因(或「不填原因」→ undefined)→ 记录「没做 + 为什么」。
  const onSkipPick = useCallback(
    (reason: AgendaSkipReason | undefined) => {
      const item = skipTarget;
      setSkipTarget(null);
      const ref = item?.complete_ref;
      if (!ref) return;
      const key = refKey(ref);
      setPendingRef(key);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      skip.mutate(
        { source: ref, skipReason: reason },
        {
          onSuccess: () => {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
            setPendingRef(null);
          },
          onError: () => {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
            Alert.alert('跳过失败', '没有保存成功,请稍后重试。');
            setPendingRef(null);
          },
        },
      );
    },
    [skip, skipTarget],
  );

  const items = useMemo(() => data?.items ?? [], [data]);
  const past = data?.past ?? { completed_count: 0, events: [] };
  const excludedTitleKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const title of excludeTitles) {
      const key = titleKey(title);
      if (key) keys.add(key);
    }
    return keys;
  }, [excludeTitles]);

  if (isLoading) {
    return (
      <View>
        <SectionLabel>接下来</SectionLabel>
        <Card>
          <ActivityIndicator color={C.green500} />
        </Card>
      </View>
    );
  }

  // 网络错误 / 无数据 → 不渲染(下方分组各卡自带错误态)
  if (isError || !data) return null;

  // 接下来只展示未完成的健康 action / advisory / checkup;完成记录和 CalDAV work 块留给完整 agenda。
  const rows = items.filter(
    (i) =>
      (i.kind === 'action' || i.kind === 'advisory' || i.kind === 'checkup') &&
      i.status !== 'completed' &&
      !excludedTitleKeys.has(titleKey(i.title)),
  );
  if (rows.length === 0) return null;

  const visible = expand ? rows : rows.slice(0, MAX_VISIBLE);
  const hidden = rows.length - visible.length;
  const countsLabel = `待办 ${rows.length} · 已完成 ${past.completed_count}`;

  return (
    <View>
      <SectionLabel action={countsLabel} onAction={() => router.push('/agenda' as any)}>接下来</SectionLabel>
      <Card pad={0}>
        {visible.map((item, i) => {
          const isWork = item.kind === 'work';
          const dk = driverKey(item);
          const domain = movementDomain(item);
          const pending = pendingRef === (item.complete_ref ? refKey(item.complete_ref) : '');
          const done = item.status === 'completed';
          const last = i === visible.length - 1 && hidden === 0;
          // 工作块永不可完成(后端 can_complete=false),只是日程占位 → 视觉弱化、无勾。
          const completable = Boolean(item.can_complete && item.complete_ref && !done && !isWork);
          const isOpen = openIds.has(item.id);
          // 标记行是否要画:有驱动来源 / 风险 / 可完成 / 「开始」/ 在途 → 都需要一条下区。
          const showMarker = Boolean(dk) || isRisk(item) || domain || completable || pending;
          // 左色条颜色:有驱动 → 驱动色;否则透明(不画条,优雅降级)。
          const barColor = dk ? revaDriver[dk].fg : 'transparent';
          // 设备核对类信息行 → 跳设备一致性页(可操作);其余信息行 → 展开全文。
          const deviceLink = /设备|待核对/.test(`${item.title} ${item.subtitle ?? ''}`)
            ? '/device-sources'
            : null;
          // 可打卡→打卡;有深链→跳转;设备核对→设备页;否则点开展开全文。
          const onToggle = completable
            ? () => onComplete(item)
            : item.deep_link
              ? () => openDeepLink(item.deep_link)
              : deviceLink
                ? () => router.push(deviceLink as any)
                : () => toggleOpen(item.id);
          return (
            <View key={item.id} style={styles.rowWrap}>
              {/* 左 3px 驱动色条:一眼归类来源 */}
              <View style={[styles.bar, { backgroundColor: barColor }]} />
              <View style={[styles.rowMain, isWork && styles.workRow]}>
                <PlanItem
                  icon={planIcon(item)}
                  title={item.title}
                  titleLines={isOpen ? undefined : 1}
                  sub={isOpen ? item.subtitle ?? undefined : shortSubtitle(item.subtitle)}
                  subLines={isOpen ? undefined : 1}
                  done={done}
                  trailing={completable ? 'check' : 'chevron'}
                  last={last && !showMarker}
                  onToggle={onToggle}
                />
                {/* 标记/行动子区:驱动 chip(左) + 风险标红 + 「开始」/ 跳过 / 完成 pending(右) */}
                {showMarker ? (
                <View style={[styles.subRow, last && { borderBottomWidth: 0 }]}>
                  {dk ? <DriverChip driver={dk} /> : null}
                  {isRisk(item) ? <Chip status="risk">需关注</Chip> : null}
                  {pending ? (
                    <View style={styles.pendingPill}>
                      <ActivityIndicator size="small" color={C.green500} />
                      <Text style={styles.pendingText}>保存中</Text>
                    </View>
                  ) : null}
                  {/* 跳过:可完成项才给(没做 + 为什么 → P6 学习闭环)。靠右,「开始」之前。 */}
                  {completable && !pending ? (
                    <Pressable
                      style={[styles.skipBtn, !domain && styles.skipBtnRight]}
                      onPress={() => onSkipPress(item)}
                      accessibilityRole="button"
                      accessibilityLabel={`跳过 ${item.title}`}
                    >
                      <Text style={styles.skipText}>跳过</Text>
                    </Pressable>
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

      <SkipReasonSheet
        visible={skipTarget !== null}
        title={skipTarget?.title}
        onPick={onSkipPick}
        onClose={() => setSkipTarget(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  // 行容器:左色条 + 主体并排。色条贴左,主体 flex:1 占满其余。
  rowWrap: { flexDirection: 'row', alignItems: 'stretch' },
  bar: { width: 3 },
  rowMain: { flex: 1, minWidth: 0 },
  // 工作块:整体降低存在感(健康待办优先),做轻微透明弱化。
  workRow: { opacity: 0.78 },
  // 内联驱动 chip:图标 + 短词,小而克制(配色走 revaDriver token)。
  driverChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth,
  },
  driverChipText: { fontWeight: '700', fontSize: 11 },
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
  skipBtn: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
  },
  // 没有「开始」按钮时,跳过自己靠右(否则由 startBtn 的 marginLeft:auto 一起带到右侧)。
  skipBtnRight: { marginLeft: 'auto' },
  skipText: { color: C.ink2, fontWeight: '600', fontSize: 12.5 },
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
