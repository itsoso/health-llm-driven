/**
 * 日历(Calendar v2 / C2)—— 只读单日时间轴视图。
 * 一条 24h 垂直时间轴聚合两层:① 外部日历事件(GET /calendar/events,按源着色,
 * 真实 start→end 块);② 健康日程(GET /schedule/today 的药/补剂/餐/运动时点,
 * movement 用处方 duration_min,其余时点渲成细 marker)。
 * 进入即同步(POST /calendar/sync)再拉事件;下拉刷新同。
 * 全天事件 → 顶部 strip;"现在"线仅今天。点块 → 底部展开明细。
 * 多日:日期左右翻页(每天 = 这条时间轴)。只读:不建/不改/不写回(那是 C3)。
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
import DayTimeline, { type TimelineEntry } from '../components/calendar/DayTimeline';
import {
  clampDayMinute, hhmmToMinutes, isoToMinutesOfDay,
} from '../components/calendar/timelineLayout';

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

// 时点(无真实时长)默认块时长:点类(药/补剂)→ 细 marker;其余(餐/复查)→ 30min。
const POINT_DOMAINS = new Set(['medication', 'supplement']);
const DEFAULT_BLOCK_MIN = 30;
const MARKER_MIN = 10;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function hhmm(iso: string | null): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '--:--';
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
function hhmmFromMin(min: number): string {
  const m = clampDayMinute(min);
  const h = Math.floor(m / 60) % 24;
  return `${String(h).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}
function dateLabel(d: Date): string {
  const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
  return `${d.getMonth() + 1}月${d.getDate()}日 ${wd}`;
}

/** 统一行模型 —— 用于详情展开(timeline 块按 key 对回此表)。 */
type Row =
  | { kind: 'event'; key: string; ev: CalendarEvent; color: string; sourceName: string }
  | { kind: 'health'; key: string; it: ScheduleItem };

export default function CalendarScreen() {
  const qc = useQueryClient();
  const [dayOffset, setDayOffset] = useState(0); // 相对今天的天数偏移(左右翻页)
  const [expanded, setExpanded] = useState<string | null>(null);

  const today = new Date();
  const day = new Date(today);
  day.setDate(today.getDate() + dayOffset);
  const dayStr = ymd(day);
  const isToday = dayOffset === 0;

  // 进入即同步,再拉当日事件(同步失败不阻断读已存事件 —— fail-soft)。
  const eventsQ = useQuery<CalendarEvent[]>({
    queryKey: ['calendar', 'events', dayStr],
    queryFn: async () => {
      try { await syncCalendar(); } catch { /* 同步失败仍读已存事件,UI 提示在 sourcesQ.last_error */ }
      return getCalendarEvents(dayStr, dayStr);
    },
  });
  const sourcesQ = useQuery<CalendarSource[]>({ queryKey: ['calendar', 'sources'], queryFn: listCalendarSources });
  // 健康日程仅当日有意义(timing-solver 是「今日」端点),仅看今天时并入。
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

  // 行表(用于明细)+ 全天 strip + 时间轴块。
  const { rowMap, allDay, entries } = useMemo(() => {
    const rowMap = new Map<string, Row>();
    const allDay: { key: string; title: string; color: string }[] = [];
    const entries: TimelineEntry[] = [];

    (eventsQ.data ?? []).forEach((ev) => {
      const meta = sourceColor[ev.source_id];
      const color = meta?.color ?? C.ink3;
      const sourceName = meta?.name ?? '日历';
      const key = `ev:${ev.id}`;
      rowMap.set(key, { kind: 'event', key, ev, color, sourceName });
      if (ev.all_day) {
        allDay.push({ key, title: ev.title || '(无标题)', color });
        return;
      }
      const startMin = isoToMinutesOfDay(ev.start);
      if (startMin == null) return; // 无有效开始时间 → 不放进网格
      const rawEnd = isoToMinutesOfDay(ev.end);
      const endMin = rawEnd != null && rawEnd > startMin ? rawEnd : startMin + DEFAULT_BLOCK_MIN;
      entries.push({
        key,
        startMin: clampDayMinute(startMin),
        endMin: clampDayMinute(endMin),
        title: ev.title || '(无标题)',
        timeLabel: `${hhmm(ev.start)}–${hhmm(ev.end)}`,
        subtitle: ev.location || undefined,
        color,
        isPoint: false,
      });
    });

    if (isToday) {
      (schedQ.data?.scheduled ?? []).forEach((it) => {
        const key = `hs:${it.id}`;
        rowMap.set(key, { kind: 'health', key, it });
        const startMin = hhmmToMinutes(it.time);
        if (startMin == null) return;
        const dur = it.prescription?.duration_min; // 仅 movement 有真实时长
        const isPoint = POINT_DOMAINS.has(it.domain) && !dur;
        const span = dur ?? (isPoint ? MARKER_MIN : DEFAULT_BLOCK_MIN);
        entries.push({
          key,
          startMin: clampDayMinute(startMin),
          endMin: clampDayMinute(startMin + span),
          title: it.title,
          timeLabel: dur ? `${it.time}–${hhmmFromMin(startMin + dur)}` : it.time,
          subtitle: it.prescription?.guidance || (DOMAIN_LABEL[it.domain] ?? it.domain),
          color: DOMAIN_COLOR[it.domain] ?? C.ink3,
          isPoint,
        });
      });
    }

    return { rowMap, allDay, entries };
  }, [eventsQ.data, schedQ.data, sourceColor, isToday]);

  const refreshing = eventsQ.isFetching && !eventsQ.isLoading;
  const onRefresh = () => {
    qc.invalidateQueries({ queryKey: ['calendar', 'events'] });
    qc.invalidateQueries({ queryKey: ['calendar', 'sources'] });
    if (isToday) qc.invalidateQueries({ queryKey: ['schedule', 'today'] });
  };

  const erroredSources = (sourcesQ.data ?? []).filter((s) => s.last_error);
  const loading = eventsQ.isLoading || (isToday && schedQ.isLoading);
  const isEmpty = entries.length === 0 && allDay.length === 0;
  const activeRow = expanded ? rowMap.get(expanded) ?? null : null;

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
      <View style={{ flex: 1, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 }}>
        {/* 日期 + 左右翻页 */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <PagerBtn label="‹" onPress={() => setDayOffset((o) => o - 1)} />
          <Pressable onPress={() => setDayOffset(0)} hitSlop={8} style={{ alignItems: 'center' }}>
            <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 17, color: C.ink1 }}>
              {dateLabel(day)}
            </Text>
            {!isToday ? <Text style={{ fontSize: 11, color: C.green500, marginTop: 1 }}>回到今天</Text> : null}
          </Pressable>
          <PagerBtn label="›" onPress={() => setDayOffset((o) => o + 1)} />
        </View>

        {/* 源同步错误提示(fail-loud,不假装成功)*/}
        {erroredSources.length > 0 ? (
          <View style={{ backgroundColor: '#FBE8E4', borderRadius: 10, padding: 10, marginBottom: 10 }}>
            <Text style={{ fontSize: 12.5, color: '#D5503A', lineHeight: 18 }}>
              {erroredSources.length} 个日历源同步出错(显示的是上次成功的数据)。
              <Text onPress={() => router.push('/calendar-sources' as any)} style={{ fontWeight: '700' }}> 去检查 ›</Text>
            </Text>
          </View>
        ) : null}

        {/* 全天事件 strip(不进网格)*/}
        {allDay.length > 0 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10, flexGrow: 0 }}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {allDay.map((a) => (
                <Pressable
                  key={a.key}
                  onPress={() => setExpanded(expanded === a.key ? null : a.key)}
                  style={({ pressed }) => [{
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                    backgroundColor: C.surface, borderRadius: 999, borderLeftWidth: 3, borderLeftColor: a.color,
                    paddingLeft: 8, paddingRight: 12, paddingVertical: 6, opacity: pressed ? 0.85 : 1,
                  }]}
                >
                  <Text style={{ fontSize: 10, color: C.ink3 }}>全天</Text>
                  <Text style={{ fontSize: 12.5, color: C.ink1, maxWidth: 160 }} numberOfLines={1}>{a.title}</Text>
                </Pressable>
              ))}
            </View>
          </ScrollView>
        ) : null}

        {/* 时间轴主体 */}
        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} />
        ) : eventsQ.isError ? (
          <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.green500} />}>
            <Text style={{ color: C.ink2, fontSize: 13, lineHeight: 20, marginTop: 8 }}>暂时取不到日历,下拉重试。</Text>
          </ScrollView>
        ) : isEmpty ? (
          <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.green500} />}>
            <EmptyState hasSources={(sourcesQ.data?.length ?? 0) > 0} isToday={isToday} />
          </ScrollView>
        ) : (
          <View style={{ flex: 1 }}>
            <DayTimeline
              entries={entries}
              isToday={isToday}
              activeKey={expanded}
              onPressBlock={(k) => setExpanded(expanded === k ? null : k)}
            />
          </View>
        )}

        {/* 明细抽屉(点块展开)*/}
        {activeRow ? (
          <View style={{
            position: 'absolute', left: 16, right: 16, bottom: 12,
            backgroundColor: C.surface, borderRadius: 14, padding: 14,
            shadowColor: '#142019', shadowOpacity: 0.12, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 8,
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Text style={{ flex: 1, fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 15, color: C.ink1 }}>
                {activeRow.kind === 'event' ? (activeRow.ev.title || '(无标题)') : activeRow.it.title}
              </Text>
              <Pressable onPress={() => setExpanded(null)} hitSlop={10}>
                <Text style={{ fontSize: 18, color: C.ink3, marginLeft: 12 }}>×</Text>
              </Pressable>
            </View>
            <View style={{ marginTop: 8, gap: 4 }}>
              <RowDetail row={activeRow} />
            </View>
          </View>
        ) : null}

        {/* 健康日程 disclaimer(后端随响应带出)*/}
        {isToday && !activeRow && schedQ.data?.disclaimer ? (
          <Text style={{ fontSize: 11, color: C.ink3, lineHeight: 16, marginTop: 8 }} numberOfLines={2}>
            {schedQ.data.disclaimer}
          </Text>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

function PagerBtn({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      hitSlop={10}
      style={({ pressed }) => [{
        width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center',
        backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, opacity: pressed ? 0.7 : 1,
      }]}
    >
      <Text style={{ fontSize: 20, color: C.ink2, lineHeight: 22 }}>{label}</Text>
    </Pressable>
  );
}

function RowDetail({ row }: { row: Row }) {
  if (row.kind === 'event') {
    const ev = row.ev;
    const timeText = ev.all_day ? '全天' : `${hhmm(ev.start)} – ${hhmm(ev.end)}`;
    return (
      <>
        <DetailLine label="时间" value={timeText} />
        <DetailLine label="来源" value={row.sourceName} />
        {ev.location ? <DetailLine label="地点" value={ev.location} /> : null}
        {ev.attendees?.length ? <DetailLine label="参会" value={ev.attendees.join('、')} /> : null}
        {ev.status ? <DetailLine label="状态" value={ev.status} /> : null}
        {ev.description ? (
          <Text style={{ fontSize: 12.5, color: C.ink2, lineHeight: 18, marginTop: 4 }}>{ev.description}</Text>
        ) : null}
      </>
    );
  }
  const p = row.it.prescription;
  return (
    <>
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
    </>
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

function EmptyState({ hasSources, isToday }: { hasSources: boolean; isToday: boolean }) {
  return (
    <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 20, alignItems: 'center', marginTop: 8 }}>
      <Text style={{ fontSize: 14, color: C.ink1, fontWeight: '600', marginBottom: 6 }}>
        {isToday ? '今天还没有日程' : '这天还没有日程'}
      </Text>
      <Text style={{ fontSize: 12.5, color: C.ink2, textAlign: 'center', lineHeight: 19 }}>
        {hasSources
          ? '已连接日历源,但这天没有事件。下拉可重新同步。'
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
