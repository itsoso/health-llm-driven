import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  fetchTaskLedger,
  type TaskLedgerFailedSource,
  type TaskLedgerItem,
} from '../../services/taskLedger';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../constants/revaTheme';

// 统一任务账本(Slice 4)对话页内联面板。v1 只读:无取消/重试。
// 分组只按后端 status 机械映射,不臆造进度。

const IN_PROGRESS_STATUSES = new Set(['queued', 'running', 'processing', 'in_progress']);
const UPCOMING_STATUSES = new Set(['scheduled', 'due', 'overdue', 'upcoming', 'emitted']);

const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  pending: '待确认',
  scheduled: '已排期',
  overdue: '已逾期',
  executed: '已执行',
  dismissed: '已忽略',
  failed: '失败',
  saved: '已就绪',
};

const SOURCE_LABELS: Record<string, string> = {
  write_intent: '写意图',
  desktop_job: '桌面任务',
  agenda: '议程',
  heartbeat: '心跳提醒',
  recipe: '配方',
};

export interface TaskLedgerGroups {
  inProgress: TaskLedgerItem[];
  pendingConfirm: TaskLedgerItem[];
  upcoming: TaskLedgerItem[];
  recentlyDecided: TaskLedgerItem[];
}

/** 按 status 机械分组:进行中 / 待确认 / 即将到来;终态(已执行/已忽略)归「最近动态」。 */
export function groupLedgerItems(items: TaskLedgerItem[]): TaskLedgerGroups {
  const groups: TaskLedgerGroups = {
    inProgress: [],
    pendingConfirm: [],
    upcoming: [],
    recentlyDecided: [],
  };
  for (const item of items) {
    if (IN_PROGRESS_STATUSES.has(item.status)) groups.inProgress.push(item);
    else if (item.status === 'pending') groups.pendingConfirm.push(item);
    else if (UPCOMING_STATUSES.has(item.status)) groups.upcoming.push(item);
    else groups.recentlyDecided.push(item);
  }
  return groups;
}

/** ISO when → 短展示。确定性字符串切片(不做时区换算,后端已按用户时区给日期)。 */
export function formatLedgerWhen(when: string | null): string {
  if (!when || when.length < 10) return '';
  const date = when.slice(5, 10).replace('-', '/');
  const time = when.length >= 16 && when.charAt(10) === 'T' ? ` ${when.slice(11, 16)}` : '';
  return `${date}${time}`;
}

function LedgerRow({ item }: { item: TaskLedgerItem }) {
  const statusLabel = STATUS_LABELS[item.status] || item.status;
  const sourceLabel = SOURCE_LABELS[item.source] || item.source;
  const whenLabel = formatLedgerWhen(item.when);
  return (
    <View style={styles.row} accessibilityLabel={`任务:${item.title}`}>
      <View style={styles.rowMain}>
        <Text maxFontSizeMultiplier={1.2} style={txt.rowTitle} numberOfLines={2}>
          {item.title}
        </Text>
        <Text maxFontSizeMultiplier={1.2} style={txt.rowMeta} numberOfLines={1}>
          {[sourceLabel, whenLabel].filter(Boolean).join(' · ')}
        </Text>
      </View>
      <View style={styles.statusBadge}>
        <Text maxFontSizeMultiplier={1.2} style={txt.statusBadge}>{statusLabel}</Text>
      </View>
    </View>
  );
}

function LedgerGroup({ title, items }: { title: string; items: TaskLedgerItem[] }) {
  if (items.length === 0) return null;
  return (
    <View style={styles.group}>
      <Text maxFontSizeMultiplier={1.2} style={txt.groupTitle}>
        {title} · {items.length}
      </Text>
      {items.map((item, index) => (
        <LedgerRow key={`${item.source}-${item.kind}-${item.title}-${item.when ?? index}`} item={item} />
      ))}
    </View>
  );
}

/**
 * 「小巴的任务」内联面板(agent-native:占据对话页消息区,不跳独立页)。
 * 加载失败显式呈现 + 重试;部分来源失败(failed_sources)也如实标出,不装全绿。
 */
export default function TaskLedgerPanel({ onClose }: { onClose?: () => void }) {
  const [items, setItems] = useState<TaskLedgerItem[] | null>(null);
  const [failedSources, setFailedSources] = useState<TaskLedgerFailedSource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTaskLedger();
      setItems(data.items);
      setFailedSources(data.failed_sources);
    } catch {
      setError('任务账本加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const groups = groupLedgerItems(items ?? []);
  const empty = !loading && !error && (items?.length ?? 0) === 0;

  return (
    <View style={styles.panel} testID="task-ledger-panel">
      <View style={styles.header}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text maxFontSizeMultiplier={1.2} style={txt.headerTitle}>小巴的任务</Text>
          <Text maxFontSizeMultiplier={1.2} style={txt.headerSub}>
            后台进行、待确认与即将到来的事(只读)
          </Text>
        </View>
        {onClose ? (
          <TouchableOpacity
            onPress={onClose}
            hitSlop={10}
            accessibilityRole="button"
            accessibilityLabel="收起任务面板"
          >
            <Ionicons name="chevron-down" size={20} color={C.ink2} />
          </TouchableOpacity>
        ) : null}
      </View>

      {loading ? (
        <View style={styles.centerBox} accessibilityLabel="正在加载任务账本">
          <ActivityIndicator size="small" color={C.green500} />
        </View>
      ) : error ? (
        <View style={styles.centerBox}>
          <Text maxFontSizeMultiplier={1.2} style={txt.error}>{error}</Text>
          <TouchableOpacity
            onPress={load}
            style={styles.retryButton}
            accessibilityRole="button"
            accessibilityLabel="重试加载任务账本"
          >
            <Text maxFontSizeMultiplier={1.2} style={txt.retry}>重试</Text>
          </TouchableOpacity>
        </View>
      ) : empty ? (
        <View style={styles.centerBox}>
          <Ionicons name="file-tray-outline" size={22} color={C.ink3} />
          <Text maxFontSizeMultiplier={1.2} style={txt.empty}>暂无进行中任务</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.listContent}>
          {failedSources.length > 0 && (
            <View style={styles.failedBanner}>
              <Ionicons name="warning-outline" size={13} color={revaSemantic.risk.fg} />
              <Text maxFontSizeMultiplier={1.2} style={txt.failedBanner} numberOfLines={2}>
                部分来源加载失败:{failedSources.map(f => SOURCE_LABELS[f.source] || f.source).join('、')}
              </Text>
            </View>
          )}
          <LedgerGroup title="进行中" items={groups.inProgress} />
          <LedgerGroup title="待确认" items={groups.pendingConfirm} />
          <LedgerGroup title="即将到来" items={groups.upcoming} />
          <LedgerGroup title="最近动态" items={groups.recentlyDecided} />
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    flex: 1,
    backgroundColor: C.paper,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: revaSpacing.s4,
    paddingTop: revaSpacing.s3,
    paddingBottom: revaSpacing.s2,
    gap: revaSpacing.s2,
  },
  centerBox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: revaSpacing.s4,
  },
  retryButton: {
    marginTop: 4,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  listContent: {
    paddingHorizontal: revaSpacing.s4,
    paddingBottom: revaSpacing.s6,
    gap: revaSpacing.s3,
  },
  failedBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: revaRadii.md,
    backgroundColor: revaSemantic.risk.bg,
  },
  group: {
    gap: 6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  rowMain: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
});

const txt = {
  headerTitle: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '800', color: C.ink1 } as TextStyle,
  headerSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 1 } as TextStyle,
  groupTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.ink2 } as TextStyle,
  rowTitle: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.ink1 } as TextStyle,
  rowMeta: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 } as TextStyle,
  statusBadge: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700', color: C.green600 } as TextStyle,
  empty: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3 } as TextStyle,
  error: { fontFamily: revaFonts.sans, fontSize: 14, color: revaSemantic.risk.fg } as TextStyle,
  retry: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.green600 } as TextStyle,
  failedBanner: { fontFamily: revaFonts.sans, fontSize: 12, color: revaSemantic.risk.fg, flex: 1 } as TextStyle,
};
