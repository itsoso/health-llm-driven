import React from 'react';
import { StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
} from '../../../constants/revaTheme';
import { formatHealthActionTitle } from '../../../utils/actionCopy';

interface RuntimeAgendaAction {
  title?: unknown;
  kind?: unknown;
  time_window?: unknown;
  priority_tier?: unknown;
  current_state_summary?: unknown;
  replan_reason?: unknown;
  verification_metrics?: unknown;
  verification_window_days?: unknown;
}

interface RuntimeAgendaDay {
  date?: unknown;
  next_action_title?: unknown;
  items_count?: unknown;
}

interface RuntimeAgendaData {
  generated_by?: unknown;
  horizon_days?: unknown;
  start?: unknown;
  end?: unknown;
  next_action?: RuntimeAgendaAction;
  days?: RuntimeAgendaDay[];
  safety_boundary?: unknown;
}

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function numberText(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string' && value.trim()) return value.trim();
  return undefined;
}

function metrics(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of value) {
    const item = text(raw);
    if (!item) continue;
    const label = formatMetricLabel(item);
    if (seen.has(label)) continue;
    seen.add(label);
    out.push(label);
    if (out.length >= 3) break;
  }
  return out;
}

function days(value: RuntimeAgendaData['days']): RuntimeAgendaDay[] {
  if (!Array.isArray(value)) return [];
  return value.filter(Boolean).slice(0, 7);
}

export function RuntimeAgendaCardView(data: RuntimeAgendaData) {
  const horizon = numberText(data.horizon_days) || '7';
  const action = data.next_action || {};
  const actionTitle = formatHealthActionTitle(text(action.title) || '今日暂无明确行动');
  const stateSummary = text(action.current_state_summary);
  const visibleMetrics = metrics(action.verification_metrics);
  const visibleDays = days(data.days);
  const boundary = text(data.safety_boundary) || '这是健康管理建议,不替代医生诊断。';
  const timeWindow = formatTimeWindow(text(action.time_window));
  const priority = formatPriority(text(action.priority_tier));
  const replanReason = formatReplanReason(text(action.replan_reason));
  const verifyDays = numberText(action.verification_window_days);

  return (
    <CardShell
      icon="calendar-clear-outline"
      iconColor={C.green500}
      title={`${horizon}天验证节奏`}
      badge={replanReason ? '已重排' : '动态'}
      badgeColor={C.green500}
      bg={C.surface}
      style={styles.shell}
    >
      <View style={styles.heroCard}>
        <View style={styles.heroTop}>
          <View style={styles.heroIcon}>
            <Ionicons name="navigate-circle" size={20} color={C.green500} />
          </View>
          <View style={styles.heroBody}>
            <Text maxFontSizeMultiplier={1.2} style={styles.eyebrow}>
              未来节奏
            </Text>
            <Text maxFontSizeMultiplier={1.3} style={styles.actionTitle} numberOfLines={3}>
              围绕当前重点动态重排
            </Text>
          </View>
        </View>

        <View style={styles.heroMeta}>
          {timeWindow ? <SignalPill icon="time-outline" label={timeWindow} /> : null}
          {priority ? <SignalPill icon="flag-outline" label={priority} /> : null}
          {verifyDays ? <SignalPill icon="analytics-outline" label={`${verifyDays}天验证`} /> : null}
        </View>
      </View>

      {stateSummary || replanReason ? (
        <View style={styles.reasonBlock}>
          <Text maxFontSizeMultiplier={1.2} style={styles.sectionLabel}>
            为什么这样排
          </Text>
          {stateSummary ? (
            <Text maxFontSizeMultiplier={1.3} style={styles.summary} numberOfLines={3}>
              {stateSummary}
            </Text>
          ) : null}
          {replanReason ? (
            <View style={styles.reasonChip}>
              <Ionicons name="git-compare-outline" size={11} color={C.green500} />
              <Text maxFontSizeMultiplier={1.2} style={styles.reasonText} numberOfLines={1}>
                {replanReason}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}

      {visibleMetrics.length > 0 ? (
        <View style={styles.metricBlock}>
          <Text maxFontSizeMultiplier={1.2} style={styles.sectionLabel}>
            验证信号
          </Text>
          <View style={styles.metrics}>
            {visibleMetrics.map((metric) => (
              <View key={metric} style={styles.metric}>
                <Ionicons name="checkmark-circle" size={12} color={C.green500} />
                <Text maxFontSizeMultiplier={1.2} style={styles.metricText} numberOfLines={1}>
                  {metric}
                </Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {visibleDays.length > 0 ? (
        <View style={styles.daysBlock}>
          <View style={styles.sectionHeader}>
            <Text maxFontSizeMultiplier={1.2} style={styles.sectionLabel}>
              未来节奏
            </Text>
            <Text maxFontSizeMultiplier={1.2} style={styles.sectionHint}>
              随睡眠/记录自动重排
            </Text>
          </View>
          <View style={styles.days}>
            {visibleDays.map((day, index) => (
              <DayRow
                key={`${text(day.date) || index}`}
                day={day}
                index={index}
                currentTitle={actionTitle}
              />
            ))}
          </View>
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        {boundary}
      </Text>
    </CardShell>
  );
}

function SignalPill({
  icon,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
}) {
  return (
    <View style={styles.signalPill}>
      <Ionicons name={icon} size={11} color={C.ink2} />
      <Text maxFontSizeMultiplier={1.2} style={styles.signalText} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

function DayRow({
  day,
  index,
  currentTitle,
}: {
  day: RuntimeAgendaDay;
  index: number;
  currentTitle: string;
}) {
  const dayTitle = text(day.next_action_title);
  const formattedDayTitle = dayTitle ? formatHealthActionTitle(dayTitle) : null;
  const visibleTitle = formattedDayTitle === currentTitle ? '当前重点行动' : formattedDayTitle || '待运行时重排';
  const dayLabel = formatDayLabel(text(day.date), index);
  return (
    <View style={styles.day}>
      <View style={[styles.dayRail, index === 0 && styles.dayRailActive]} />
      <Text maxFontSizeMultiplier={1.2} style={[styles.dayDate, index === 0 && styles.dayDateActive]}>
        {dayLabel}
      </Text>
      <View style={styles.dayBody}>
        <Text maxFontSizeMultiplier={1.2} style={styles.dayTitle} numberOfLines={1}>
          {visibleTitle}
        </Text>
        <Text maxFontSizeMultiplier={1.2} style={styles.dayCount}>
          {numberText(day.items_count) || '0'}项待安排
        </Text>
      </View>
    </View>
  );
}

function formatTimeWindow(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const map: Record<string, string> = {
    morning: '早晨',
    noon: '午间',
    afternoon: '下午',
    evening: '晚间',
    bedtime: '睡前',
    anytime: '灵活',
    today: '今天',
  };
  return map[value] || value;
}

function formatPriority(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const normalized = value.toUpperCase();
  const map: Record<string, string> = {
    P0: '最高优先',
    P1: '重要',
    P2: '常规',
    P3: '低负担',
  };
  return map[normalized] || value;
}

function formatReplanReason(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const map: Record<string, string> = {
    today_smart_rank: '基于今日状态重排',
    daily_protocol_projection: '延续日常协议',
    scheduled_followup_projection: '复查到期',
    recent_protocol_feedback_projection: '根据近期反馈调整',
    runtime_anchor_projection: '补足低风险健康底座',
  };
  return map[value] || value.replace(/_/g, ' ');
}

function formatMetricLabel(value: string): string {
  const map: Record<string, string> = {
    weight: '体重',
    body_weight: '体重',
    waist: '腰围',
    waist_cm: '腰围',
    systolic_bp: '收缩压',
    diastolic_bp: '舒张压',
    blood_pressure: '血压',
    sleep_score: '睡眠分',
    sleep_duration: '睡眠时长',
    hrv: 'HRV',
    post_meal_walk_completed: '餐后步行完成',
    hydration_ml: '饮水量',
    water_ml: '饮水量',
  };
  return map[value] || value.replace(/_/g, ' ');
}

function formatDayLabel(value: string | undefined, index: number): string {
  if (index === 0) return '今天';
  if (index === 1) return '明天';
  if (!value) return `D${index + 1}`;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const date = new Date(`${value}T00:00:00`);
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getDay()];
  return `${Number(match[2])}/${Number(match[3])} ${week}`;
}

export const RuntimeAgendaCardSpec: CardSpec<RuntimeAgendaData> = {
  type: 'runtime_agenda',
  label: '7天验证节奏',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <RuntimeAgendaCardView {...data} />,
};

const styles = StyleSheet.create({
  shell: {
    paddingHorizontal: 13,
    paddingVertical: 12,
  },
  heroCard: {
    borderRadius: revaRadii.md,
    padding: 11,
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    ...revaShadows.sm,
  },
  heroTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  heroIcon: {
    width: 34,
    height: 34,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.focusBg2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
  },
  heroBody: {
    flex: 1,
    minWidth: 0,
  },
  eyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '800',
    color: C.greenBright,
    lineHeight: 13,
  } as TextStyle,
  actionTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 17,
    fontWeight: '800',
    color: C.focusInk1,
    lineHeight: 23,
    marginTop: 2,
  } as TextStyle,
  heroMeta: {
    marginTop: 10,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  signalPill: {
    minHeight: 24,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    maxWidth: '100%',
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: 'rgba(255,255,255,0.10)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,255,255,0.16)',
  },
  signalText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.focusInk1,
    lineHeight: 13,
  } as TextStyle,
  reasonBlock: {
    marginTop: 12,
    paddingTop: 2,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  sectionLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '900',
    color: C.ink1,
    lineHeight: 15,
  } as TextStyle,
  sectionHint: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.ink3,
    lineHeight: 13,
  } as TextStyle,
  summary: {
    marginTop: 5,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 18,
  } as TextStyle,
  reasonChip: {
    alignSelf: 'flex-start',
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  reasonText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.green500,
    lineHeight: 14,
  } as TextStyle,
  metricBlock: {
    marginTop: 12,
  },
  metrics: {
    marginTop: 7,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  metric: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    maxWidth: '100%',
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  metricText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 14,
  } as TextStyle,
  daysBlock: {
    marginTop: 13,
  },
  days: {
    marginTop: 8,
    gap: 6,
  },
  day: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 8,
    minHeight: 38,
    paddingHorizontal: 9,
    paddingVertical: 7,
    borderRadius: revaRadii.sm,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  dayRail: {
    width: 3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.lineStrong,
  },
  dayRailActive: {
    backgroundColor: C.green500,
  },
  dayDate: {
    width: 58,
    alignSelf: 'center',
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  dayDateActive: {
    color: C.green500,
  } as TextStyle,
  dayBody: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'center',
  } as ViewStyle,
  dayTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 16,
  } as TextStyle,
  dayCount: {
    marginTop: 2,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.ink3,
    lineHeight: 13,
  } as TextStyle,
  boundary: {
    marginTop: 10,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
});
