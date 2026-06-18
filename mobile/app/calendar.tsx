/**
 * 日历(Calendar v2 / C2)—— 只读日程视图。
 * 一条时间轴聚合两层:① 外部日历事件(GET /calendar/events,按源着色);
 * ② 健康日程(GET /schedule/today 的药/补剂/餐/运动时点,含 cut-A 处方)。
 * 进入即同步(POST /calendar/sync)再拉事件;下拉刷新同。
 * 点条目 → 展开明细。只读:不建/不改/不写回(那是 C3)。
 */
import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, router } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { revaColors as C } from '../constants/revaTheme';
import {
  getCalendarEvents, listCalendarSources, syncCalendar,
  type CalendarEvent, type CalendarSource,
} from '../services/calendar';
import { getTodaySchedule, type ScheduleItem, type TodaySchedule } from '../services/schedule';

const DOMAIN_LABEL: Record<string, string> = {
  medication: '药', supplement: '补剂', diet: '饮食',
  movement: '运动', sleep: '睡眠', checkup: '复查',
};
const DOMAIN_COLOR: Record<string, string> = {
  medication: C.green500, supplement: '#1F8A5B', diet: '#C98A1E',
  movement: '#2A6FDB', sleep: '#7A5AF0', checkup: '#D5503A',
};
// 源缺自定义色时按 id 轮转一组温和色。
const SOURCE_FALLBACK = ['#2A6FDB', '#7A5AF0', '#C98A1E', '#1F8A5B', '#D5503A', '#0E7C86'];

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function hhmm(iso: string | null): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '--:--';
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
function dateLabel(d: Date): string {
  const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
  return `${d.getMonth() + 1}月${d.getDate()}日 ${wd}`;
}

/** 时间轴统一行模型(外部事件 + 健康日程合并)。 */
type Row =
  | { kind: 'event'; key: string; time: string; sortKey: string; ev: CalendarEvent; color: string; sourceName: string }
  | { kind: 'health'; key: string; time: string; sortKey: string; it: ScheduleItem };

export default function CalendarScreen() {
  const qc = useQueryClient();
  const [dayOffset, setDayOffset] = useState(0); // 0=今天;7-day toggle 用 0/+7 区间
  const [span, setSpan] = useState<1 | 7>(1); // 1=单日;7=未来 7 天
  const [expanded, setExpanded] = useState<string | null>(null);

  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() + dayOffset);
  const to = new Date(from);
  to.setDate(from.getDate() + (span - 1));
  const fromStr = ymd(from);
  const toStr = ymd(to);

  // 进入即同步,再拉事件(同步失败不阻断读已存事件 —— fail-soft)。
  const eventsQ = useQuery<CalendarEvent[]>({
    queryKey: ['calendar', 'events', fromStr, toStr],
    queryFn: async () => {
      try { await syncCalendar(); } catch { /* 同步失败仍读已存事件,UI 提示在 sourcesQ.last_error */ }
      return getCalendarEvents(fromStr, toStr);
    },
  });
  const sourcesQ = useQuery<CalendarSource[]>({ queryKey: ['calendar', 'sources'], queryFn: listCalendarSources });
  // 健康日程仅当日有意义(timing-solver 是「今日」端点),仅 span=1 且 offset=0 时并入。
  const isToday = dayOffset === 0 && span === 1;
  const schedQ = useQuery<TodaySchedule>({
    queryKey: ['schedule', 'today'],
    queryFn: getTodaySchedule,
    enabled: isToday,
  });

  const sourceColor = useMemo(() => {
    const map: Record<number, { color: string; name: string }> = {};
    (sourcesQ.data ?? []).forEach((s, i) => {
      map[s.id] = { color: s.color || SOURCE_FALLBACK[i % SOURCE_FALLBACK.length], name: s.name };
    });
    return map;
  }, [sourcesQ.data]);

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    (eventsQ.data ?? []).forEach((ev) => {
      const meta = sourceColor[ev.source_id];
      out.push({
        kind: 'event', key: `ev:${ev.id}`,
        time: ev.all_day ? '全天' : hhmm(ev.start),
        sortKey: ev.all_day ? '00:00' : (ev.start ?? '99:99'),
        ev, color: meta?.color ?? C.ink3, sourceName: meta?.name ?? '日历',
      });
    });
    if (isToday) {
      (schedQ.data?.scheduled ?? []).forEach((it) => {
        out.push({ kind: 'health', key: `hs:${it.id}`, time: it.time, sortKey: it.time, it });
      });
    }
    return out.sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  }, [eventsQ.data, schedQ.data, sourceColor, isToday]);

  const refreshing = eventsQ.isFetching && !eventsQ.isLoading;
  const onRefresh = () => {
    qc.invalidateQueries({ queryKey: ['calendar', 'events'] });
    qc.invalidateQueries({ queryKey: ['calendar', 'sources'] });
    if (isToday) qc.invalidateQueries({ queryKey: ['schedule', 'today'] });
  };

  const erroredSources = (sourcesQ.data ?? []).filter((s) => s.last_error);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
      <Stack.Screen
        options={{
          title: '日历',
          headerRight: () => (
            <Pressable onPress={() => router.push('/calendar-sources' as any)} hitSlop={8}>
              <Text style={{ color: C.green500, fontWeight: '600', fontSize: 14 }}>管理源</Text>
            </Pressable>
          ),
        }}
      />
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.green500} />}
      >
        {/* 日期 + 区间切换 */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 17, color: C.ink1 }}>
            {span === 7 ? `未来 7 天` : dateLabel(from)}
          </Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Toggle label="今日" active={span === 1} onPress={() => { setSpan(1); setDayOffset(0); }} />
            <Toggle label="7 天" active={span === 7} onPress={() => { setSpan(7); setDayOffset(0); }} />
          </View>
        </View>

        {/* 源同步错误提示(fail-loud,不假装成功)*/}
        {erroredSources.length > 0 ? (
          <View style={{ backgroundColor: '#FBE8E4', borderRadius: 10, padding: 10, marginBottom: 12 }}>
            <Text style={{ fontSize: 12.5, color: '#D5503A', lineHeight: 18 }}>
              {erroredSources.length} 个日历源同步出错(显示的是上次成功的数据)。
              <Text onPress={() => router.push('/calendar-sources' as any)} style={{ fontWeight: '700' }}> 去检查 ›</Text>
            </Text>
          </View>
        ) : null}

        {/* 时间轴 */}
        {eventsQ.isLoading || (isToday && schedQ.isLoading) ? (
          <ActivityIndicator style={{ marginTop: 24 }} />
        ) : eventsQ.isError ? (
          <Text style={{ color: C.ink2, fontSize: 13, lineHeight: 20 }}>
            暂时取不到日历,下拉重试。
          </Text>
        ) : rows.length === 0 ? (
          <EmptyState hasSources={(sourcesQ.data?.length ?? 0) > 0} />
        ) : (
          <View style={{ backgroundColor: C.surface, borderRadius: 14, overflow: 'hidden' }}>
            {rows.map((r, i) => (
              <TimelineRow
                key={r.key}
                row={r}
                first={i === 0}
                open={expanded === r.key}
                onToggle={() => setExpanded(expanded === r.key ? null : r.key)}
              />
            ))}
          </View>
        )}

        {/* 健康日程 disclaimer(后端随响应带出)*/}
        {isToday && schedQ.data?.disclaimer ? (
          <Text style={{ fontSize: 11, color: C.ink3, lineHeight: 16, marginTop: 18 }}>{schedQ.data.disclaimer}</Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Toggle({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [{
        borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6,
        backgroundColor: active ? C.green500 : C.surface,
        borderWidth: 1, borderColor: active ? C.green500 : C.line, opacity: pressed ? 0.8 : 1,
      }]}
    >
      <Text style={{ fontSize: 13, fontWeight: '600', color: active ? '#fff' : C.ink2 }}>{label}</Text>
    </Pressable>
  );
}

function TimelineRow({ row, first, open, onToggle }: {
  row: Row; first: boolean; open: boolean; onToggle: () => void;
}) {
  const dotColor = row.kind === 'event' ? row.color : (DOMAIN_COLOR[row.it.domain] ?? C.ink3);
  const title = row.kind === 'event' ? (row.ev.title || '(无标题)') : row.it.title;
  const tag = row.kind === 'event' ? row.sourceName : (DOMAIN_LABEL[row.it.domain] ?? row.it.domain);

  return (
    <Pressable
      onPress={onToggle}
      style={({ pressed }) => [{
        paddingVertical: 12, paddingHorizontal: 14,
        borderTopWidth: first ? 0 : 1, borderTopColor: C.line,
        backgroundColor: pressed ? C.surface2 : C.surface,
      }]}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 14, fontWeight: '700', color: C.ink1, width: 52 }}>
          {row.time}
        </Text>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dotColor }} />
        <Text style={{ flex: 1, fontSize: 14, color: C.ink1 }} numberOfLines={open ? undefined : 1}>{title}</Text>
        <Text style={{ fontSize: 11, color: C.ink3 }} numberOfLines={1}>{tag}</Text>
      </View>
      {open ? <RowDetail row={row} /> : null}
    </Pressable>
  );
}

function RowDetail({ row }: { row: Row }) {
  if (row.kind === 'event') {
    const ev = row.ev;
    const timeText = ev.all_day
      ? '全天'
      : `${hhmm(ev.start)} – ${hhmm(ev.end)}`;
    return (
      <View style={{ marginTop: 10, marginLeft: 64, gap: 4 }}>
        <DetailLine label="时间" value={timeText} />
        <DetailLine label="来源" value={row.sourceName} />
        {ev.location ? <DetailLine label="地点" value={ev.location} /> : null}
        {ev.attendees?.length ? <DetailLine label="参会" value={ev.attendees.join('、')} /> : null}
        {ev.status ? <DetailLine label="状态" value={ev.status} /> : null}
        {ev.description ? (
          <Text style={{ fontSize: 12.5, color: C.ink2, lineHeight: 18, marginTop: 4 }}>{ev.description}</Text>
        ) : null}
      </View>
    );
  }
  // 健康日程:复用 day-schedule 的处方渲染。
  const p = row.it.prescription;
  return (
    <View style={{ marginTop: 10, marginLeft: 64, gap: 4 }}>
      <DetailLine label="类型" value={DOMAIN_LABEL[row.it.domain] ?? row.it.domain} />
      <DetailLine label="时点" value={row.it.time} />
      {row.it.anchor ? <DetailLine label="锚点" value={row.it.anchor} /> : null}
      {p ? (
        <Text style={{ fontSize: 12.5, color: C.ink2, lineHeight: 18, marginTop: 4 }}>
          {[p.rpe ? `RPE ${p.rpe}` : null, p.guidance].filter(Boolean).join(' · ')}
          {p.gene_note ? `\n${p.gene_note}` : ''}
        </Text>
      ) : null}
      {row.it.warning ? (
        <Text style={{ fontSize: 12, color: '#C98A1E', lineHeight: 18, marginTop: 2 }}>{row.it.warning}</Text>
      ) : null}
    </View>
  );
}

function DetailLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', gap: 8 }}>
      <Text style={{ fontSize: 12.5, color: C.ink3, width: 36 }}>{label}</Text>
      <Text style={{ fontSize: 12.5, color: C.ink2, flex: 1, lineHeight: 18 }}>{value}</Text>
    </View>
  );
}

function EmptyState({ hasSources }: { hasSources: boolean }) {
  return (
    <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 20, alignItems: 'center' }}>
      <Text style={{ fontSize: 14, color: C.ink1, fontWeight: '600', marginBottom: 6 }}>这段时间还没有日程</Text>
      <Text style={{ fontSize: 12.5, color: C.ink2, textAlign: 'center', lineHeight: 19 }}>
        {hasSources
          ? '已连接日历源,但所选区间没有事件。下拉可重新同步。'
          : '还没连接外部日历。连接 CalDAV / ICS 源后,会议会和健康日程并在一条时间轴。'}
      </Text>
      {!hasSources ? (
        <Pressable
          onPress={() => router.push('/calendar-sources' as any)}
          style={({ pressed }) => [{
            marginTop: 14, backgroundColor: C.green500, borderRadius: 10,
            paddingHorizontal: 18, paddingVertical: 9, opacity: pressed ? 0.85 : 1,
          }]}
        >
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>添加日历</Text>
        </Pressable>
      ) : null}
    </View>
  );
}
