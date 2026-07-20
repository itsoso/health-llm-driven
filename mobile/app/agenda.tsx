/**
 * 今日行动管理页。
 *
 * 只消费 /agenda/today，并通过 /agenda/complete 记录完成或跳过。
 * 历史行动卡、Safety 告警、推理回放不在此页混排。
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  ActionSheetIOS,
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';

import { useAgendaToday, useCompleteAgendaItem } from '../hooks/useAgenda';
import { useToast } from '../hooks/useToast';
import {
  type AgendaItem,
  type AgendaSkipReason,
} from '../services/agenda';
import { agendaItemPresentation } from '../utils/agendaPresentation';
import {
  agendaItemKey,
  canActOnAgendaItem,
  cleanAgendaTitle,
  groupTodayAgendaItems,
  resolveAgendaBackAction,
} from '../utils/todayAgendaManagement';
import { pushChatWithContext } from '../utils/agentContext';
import { SKIP_REASONS } from '../constants/skipReasons';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSpacing,
  revaSemantic,
} from '../constants/revaTheme';

type SectionKey = 'now' | 'review' | 'later' | 'handled';

interface AgendaSection {
  key: SectionKey;
  title: string;
  hint: string;
  count: number;
  data: AgendaItem[];
}

const ACTION_MENU_OPTIONS = ['移到稍后', '跳过', '调整计划', '问小巴', '取消'];

export default function AgendaScreen() {
  const router = useRouter();
  const toast = useToast();
  const { data, isLoading, isError, isRefetching, refetch } = useAgendaToday();
  const complete = useCompleteAgendaItem();
  const [snoozedKeys, setSnoozedKeys] = useState<Set<string>>(() => new Set());
  const [handledExpanded, setHandledExpanded] = useState(false);

  const groups = useMemo(
    () => groupTodayAgendaItems(data?.items ?? [], { snoozedKeys }),
    [data?.items, snoozedKeys],
  );

  const sections = useMemo<AgendaSection[]>(() => {
    const candidates: AgendaSection[] = [
      {
        key: 'now',
        title: '现在做',
        hint: groups.now.length > 0 ? '按优先级排列' : '当前没有紧急事项',
        count: groups.now.length,
        data: groups.now,
      },
      {
        key: 'review',
        title: '需要确认',
        hint: '先问清，再决定怎么处理',
        count: groups.review.length,
        data: groups.review,
      },
      {
        key: 'later',
        title: '稍后',
        hint: groups.later.length > 0 ? '到时间再处理' : '暂无后续事项',
        count: groups.later.length,
        data: groups.later,
      },
      {
        key: 'handled',
        title: '已处理',
        hint: groups.handled.length > 0 ? (handledExpanded ? '点击收起' : '点击查看') : '今天还没有完成记录',
        count: groups.handled.length,
        data: handledExpanded ? groups.handled : [],
      },
    ];
    return candidates.filter(section => section.count > 0);
  }, [groups, handledExpanded]);

  const pendingCount = groups.now.length + groups.review.length + groups.later.length;

  const handleBack = useCallback(() => {
    const action = resolveAgendaBackAction(router.canGoBack());
    if (action.type === 'back') {
      router.back();
      return;
    }
    router.navigate(action.route);
  }, [router]);

  const markComplete = useCallback((item: AgendaItem, skipReason?: AgendaSkipReason) => {
    const title = cleanAgendaTitle(item.title);
    const skipped = Boolean(skipReason);
    complete.mutate(
      {
        source: item.source,
        ...(skipped ? { status: 'skipped' as const, skipReason } : {}),
      },
      {
        onSuccess: () => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          toast.show(skipped ? '已记录为跳过' : '已完成', 'success');
        },
        onError: () => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
          toast.show(`未能更新“${title}”，请重试`, 'error');
        },
      },
    );
  }, [complete, toast]);

  const snooze = useCallback((item: AgendaItem) => {
    const key = agendaItemKey(item);
    setSnoozedKeys(current => {
      const next = new Set(current);
      next.add(key);
      return next;
    });
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    toast.showUndoable('已放到稍后', () => {
      setSnoozedKeys(current => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
    });
  }, [toast]);

  const askXiaoba = useCallback((item: AgendaItem, intent: 'adjust' | 'ask') => {
    const title = cleanAgendaTitle(item.title);
    pushChatWithContext(router, {
      prompt: intent === 'adjust'
        ? `请帮我调整今天这条行动：“${title}”。先问清我当前不方便执行的原因，再给一个更容易完成的替代安排。`
        : `请解释今天这条行动：“${title}”。告诉我为什么现在做、怎么做，以及什么情况下不适合做。`,
      badge: intent === 'adjust' ? `调整 · ${title}` : `今日行动 · ${title}`,
      context: {
        from: 'agenda/today',
        intent,
        agenda_item: {
          type: item.type,
          title,
          status: item.status,
          time_window: item.time_window ?? null,
          priority: item.priority,
          detail: item.detail ?? null,
          source: {
            object_type: item.source.object_type,
            object_id: String(item.source.object_id),
            slot: item.source.slot ?? null,
          },
        },
      },
    });
  }, [router]);

  const chooseSkipReason = useCallback((item: AgendaItem) => {
    if (Platform.OS === 'ios') {
      const cancelButtonIndex = SKIP_REASONS.length;
      ActionSheetIOS.showActionSheetWithOptions(
        {
          title: '为什么跳过？',
          message: '这会帮助小巴减少不合适的安排。',
          options: [...SKIP_REASONS.map(reason => reason.label), '取消'],
          cancelButtonIndex,
        },
        index => {
          const reason = SKIP_REASONS[index];
          if (reason) markComplete(item, reason.value);
        },
      );
      return;
    }
    Alert.alert(
      '为什么跳过？',
      '这会帮助小巴减少不合适的安排。',
      [
        ...SKIP_REASONS.map(reason => ({
          text: reason.label,
          onPress: () => markComplete(item, reason.value),
        })),
        { text: '取消', style: 'cancel' as const },
      ],
    );
  }, [markComplete]);

  const handleMenuSelection = useCallback((item: AgendaItem, index: number) => {
    if (index === 0) snooze(item);
    if (index === 1) chooseSkipReason(item);
    if (index === 2) askXiaoba(item, 'adjust');
    if (index === 3) askXiaoba(item, 'ask');
  }, [askXiaoba, chooseSkipReason, snooze]);

  const openItemMenu = useCallback((item: AgendaItem) => {
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          title: cleanAgendaTitle(item.title),
          options: ACTION_MENU_OPTIONS,
          cancelButtonIndex: 4,
        },
        index => handleMenuSelection(item, index),
      );
      return;
    }
    Alert.alert(
      cleanAgendaTitle(item.title),
      undefined,
      [
        { text: '移到稍后', onPress: () => snooze(item) },
        { text: '跳过', onPress: () => chooseSkipReason(item) },
        { text: '调整计划', onPress: () => askXiaoba(item, 'adjust') },
        { text: '问小巴', onPress: () => askXiaoba(item, 'ask') },
        { text: '取消', style: 'cancel' },
      ],
    );
  }, [askXiaoba, chooseSkipReason, handleMenuSelection, snooze]);

  const renderSectionHeader = useCallback(({ section }: { section: AgendaSection }) => {
    const content = (
      <>
        <View style={styles.sectionTitleRow}>
          <Text style={styles.sectionTitle}>{section.title}</Text>
          <View style={[styles.sectionCount, section.key === 'now' && styles.sectionCountActive]}>
            <Text style={[styles.sectionCountText, section.key === 'now' && styles.sectionCountTextActive]}>
              {section.count}
            </Text>
          </View>
        </View>
        <Text style={styles.sectionHint}>{section.hint}</Text>
        {section.key === 'handled' && section.count > 0 ? (
          <Ionicons name={handledExpanded ? 'chevron-up' : 'chevron-down'} size={17} color={C.ink3} />
        ) : null}
      </>
    );
    if (section.key !== 'handled' || section.count === 0) {
      return <View style={styles.sectionHeader}>{content}</View>;
    }
    return (
      <Pressable
        onPress={() => setHandledExpanded(value => !value)}
        style={({ pressed }) => [styles.sectionHeader, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel={`${handledExpanded ? '收起' : '展开'}已处理行动`}
      >
        {content}
      </Pressable>
    );
  }, [handledExpanded]);

  const renderItem = useCallback(({ item, section }: { item: AgendaItem; section: AgendaSection }) => (
    <AgendaRow
      item={item}
      handled={section.key === 'handled'}
      pending={complete.isPending && complete.variables?.source
        ? agendaItemKey({ ...item, source: complete.variables.source }) === agendaItemKey(item)
        : false}
      onComplete={() => markComplete(item)}
      onMenu={() => openItemMenu(item)}
      onAsk={() => askXiaoba(item, 'ask')}
    />
  ), [askXiaoba, complete.isPending, complete.variables, markComplete, openItemMenu]);

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Pressable
          onPress={handleBack}
          hitSlop={10}
          style={({ pressed }) => [styles.headerButton, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="返回小巴"
          accessibilityHint="回到与小巴的对话"
        >
          <Ionicons name="chevron-back" size={23} color={C.ink1} />
        </Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>今日行动</Text>
          <Text style={styles.headerMeta}>
            待处理 {pendingCount} · 已处理 {groups.handled.length}
          </Text>
        </View>
        <Pressable
          onPress={() => refetch()}
          hitSlop={10}
          style={({ pressed }) => [styles.headerButton, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="刷新今日行动"
        >
          <Ionicons name="refresh-outline" size={20} color={C.ink2} />
        </Pressable>
      </View>

      {isLoading ? (
        <StateView icon="hourglass-outline" title="正在整理今天的行动" loading />
      ) : isError ? (
        <StateView icon="cloud-offline-outline" title="暂时无法加载" actionLabel="重试" onAction={() => refetch()} />
      ) : (data?.items.length ?? 0) === 0 ? (
        <StateView icon="checkmark-circle-outline" title="今天没有待处理行动" actionLabel="返回小巴" onAction={handleBack} />
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={agendaItemKey}
          renderSectionHeader={renderSectionHeader}
          renderItem={renderItem}
          stickySectionHeadersEnabled={false}
          contentInsetAdjustmentBehavior="automatic"
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={() => <View style={styles.rowSeparator} />}
          SectionSeparatorComponent={() => <View style={styles.sectionSeparator} />}
          refreshControl={(
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={C.green500} />
          )}
        />
      )}
    </SafeAreaView>
  );
}

function AgendaRow({
  item,
  handled,
  pending,
  onComplete,
  onMenu,
  onAsk,
}: {
  item: AgendaItem;
  handled: boolean;
  pending: boolean;
  onComplete: () => void;
  onMenu: () => void;
  onAsk: () => void;
}) {
  const title = cleanAgendaTitle(item.title);
  const presentation = agendaItemPresentation(item);
  const canComplete = !handled && canActOnAgendaItem(item);
  const tint = item.status === 'overdue'
    ? revaSemantic.risk.fg
    : handled
      ? C.green500
      : C.green600;

  return (
    <View style={[styles.row, handled && styles.rowHandled]}>
      <View style={[styles.rowIcon, { backgroundColor: `${tint}12` }]}>
        <Ionicons
          name={(handled ? 'checkmark' : presentation.icon) as keyof typeof Ionicons.glyphMap}
          size={19}
          color={tint}
        />
      </View>
      <View style={styles.rowBody}>
        <Text style={styles.rowTitle} numberOfLines={2}>{title}</Text>
        <Text style={styles.rowMeta} numberOfLines={1}>
          {formatTimeWindow(item.time_window)} · {presentation.statusLabel}
        </Text>
        {item.detail ? <Text style={styles.rowDetail} numberOfLines={2}>{item.detail}</Text> : null}
      </View>
      <View style={styles.rowActions}>
        {canComplete ? (
          <Pressable
            onPress={onComplete}
            disabled={pending}
            style={({ pressed }) => [styles.completeButton, pressed && styles.pressed, pending && styles.disabled]}
            accessibilityRole="button"
            accessibilityLabel={`完成 ${title}`}
          >
            {pending ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Ionicons name="checkmark" size={15} color="#fff" />
                <Text style={styles.completeButtonText}>完成</Text>
              </>
            )}
          </Pressable>
        ) : !handled ? (
          <Pressable
            onPress={onAsk}
            style={({ pressed }) => [styles.askButton, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={`询问小巴 ${title}`}
          >
            <Text style={styles.askButtonText}>问小巴</Text>
          </Pressable>
        ) : null}
        {!handled ? (
          <Pressable
            onPress={onMenu}
            hitSlop={8}
            style={({ pressed }) => [styles.moreButton, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={`管理 ${title}`}
          >
            <Ionicons name="ellipsis-horizontal" size={19} color={C.ink2} />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

function StateView({
  icon,
  title,
  loading = false,
  actionLabel,
  onAction,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  loading?: boolean;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.state}>
      <View style={styles.stateIcon}>
        {loading ? <ActivityIndicator color={C.green500} /> : <Ionicons name={icon} size={24} color={C.green500} />}
      </View>
      <Text style={styles.stateTitle}>{title}</Text>
      {actionLabel && onAction ? (
        <Pressable onPress={onAction} style={({ pressed }) => [styles.stateButton, pressed && styles.pressed]}>
          <Text style={styles.stateButtonText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function formatTimeWindow(value: string | undefined): string {
  const labels: Record<string, string> = {
    morning: '早晨',
    noon: '午间',
    afternoon: '下午',
    evening: '晚间',
    bedtime: '睡前',
    anytime: '今天',
    today: '今天',
  };
  return labels[value ?? 'anytime'] ?? '今天';
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.paper },
  header: {
    minHeight: 58,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
    backgroundColor: C.paper,
  },
  headerButton: {
    width: 40,
    height: 40,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerCopy: { flex: 1, alignItems: 'center', paddingHorizontal: revaSpacing.s2 },
  headerTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 18, fontWeight: '800' },
  headerMeta: { fontFamily: revaFonts.mono, color: C.ink3, fontSize: 11, marginTop: 2 },
  listContent: { paddingBottom: 32 },
  sectionHeader: {
    minHeight: 58,
    paddingHorizontal: revaSpacing.s4,
    paddingTop: revaSpacing.s4,
    paddingBottom: revaSpacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: C.paper,
  },
  sectionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  sectionTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 16, fontWeight: '800' },
  sectionCount: {
    minWidth: 22,
    height: 22,
    paddingHorizontal: 6,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
  },
  sectionCountActive: { backgroundColor: C.green50 },
  sectionCountText: { fontFamily: revaFonts.mono, color: C.ink3, fontSize: 11, fontWeight: '800' },
  sectionCountTextActive: { color: C.green600 },
  sectionHint: {
    flex: 1,
    marginLeft: revaSpacing.s2,
    fontFamily: revaFonts.sans,
    color: C.ink3,
    fontSize: 12,
    textAlign: 'right',
  },
  row: {
    minHeight: 86,
    marginHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s3,
    backgroundColor: C.paper,
  },
  rowHandled: { opacity: 0.62 },
  rowIcon: {
    width: 38,
    height: 38,
    borderRadius: revaRadii.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowBody: { flex: 1, minWidth: 0 },
  rowTitle: { fontFamily: revaFonts.sans, color: C.ink1, fontSize: 15, lineHeight: 20, fontWeight: '700' },
  rowMeta: { fontFamily: revaFonts.sans, color: C.ink3, fontSize: 12, marginTop: 3 },
  rowDetail: { fontFamily: revaFonts.sans, color: C.ink2, fontSize: 12, lineHeight: 17, marginTop: 5 },
  rowActions: { flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 0 },
  completeButton: {
    height: 34,
    minWidth: 66,
    paddingHorizontal: 11,
    borderRadius: revaRadii.pill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: C.green600,
  },
  completeButtonText: { fontFamily: revaFonts.sans, color: '#fff', fontSize: 13, fontWeight: '800' },
  askButton: {
    height: 34,
    paddingHorizontal: 10,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  askButtonText: { fontFamily: revaFonts.sans, color: C.green600, fontSize: 12, fontWeight: '800' },
  moreButton: {
    width: 34,
    height: 34,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
  },
  rowSeparator: { height: StyleSheet.hairlineWidth, marginLeft: 76, marginRight: revaSpacing.s4, backgroundColor: C.line },
  sectionSeparator: { height: 4 },
  state: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32, gap: 12 },
  stateIcon: {
    width: 52,
    height: 52,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  stateTitle: { fontFamily: revaFonts.sans, color: C.ink2, fontSize: 15, fontWeight: '700' },
  stateButton: { paddingHorizontal: 18, paddingVertical: 9, borderRadius: revaRadii.pill, backgroundColor: C.green50 },
  stateButtonText: { fontFamily: revaFonts.sans, color: C.green600, fontSize: 14, fontWeight: '800' },
  pressed: { opacity: 0.58 },
  disabled: { opacity: 0.55 },
});
