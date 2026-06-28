import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';

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
  return value.map(text).filter((item): item is string => Boolean(item)).slice(0, 3);
}

function days(value: RuntimeAgendaData['days']): RuntimeAgendaDay[] {
  if (!Array.isArray(value)) return [];
  return value.filter(Boolean).slice(0, 7);
}

export function RuntimeAgendaCardView(data: RuntimeAgendaData) {
  const horizon = numberText(data.horizon_days) || '7';
  const action = data.next_action || {};
  const actionTitle = text(action.title) || '今日暂无明确行动';
  const stateSummary = text(action.current_state_summary);
  const visibleMetrics = metrics(action.verification_metrics);
  const visibleDays = days(data.days);
  const boundary = text(data.safety_boundary) || '这是健康管理建议,不替代医生诊断。';

  return (
    <CardShell
      icon="calendar-clear-outline"
      iconColor={C.green500}
      title={`${horizon}天健康运行时`}
      badge="动态编排"
      badgeColor={C.green500}
      bg={C.green50}
    >
      <View style={styles.hero}>
        <View style={styles.heroIcon}>
          <Ionicons name="navigate-circle-outline" size={18} color={C.green500} />
        </View>
        <View style={styles.heroBody}>
          <Text maxFontSizeMultiplier={1.3} style={styles.actionTitle} numberOfLines={3}>
            {actionTitle}
          </Text>
          {stateSummary ? (
            <Text maxFontSizeMultiplier={1.3} style={styles.summary} numberOfLines={3}>
              {stateSummary}
            </Text>
          ) : null}
        </View>
      </View>

      <View style={styles.chips}>
        {text(action.time_window) ? <Chip label={text(action.time_window)!} /> : null}
        {text(action.priority_tier) ? <Chip label={text(action.priority_tier)!} tone="strong" /> : null}
        {text(action.replan_reason) ? <Chip label={text(action.replan_reason)!} /> : null}
        {numberText(action.verification_window_days) ? (
          <Chip label={`${numberText(action.verification_window_days)}天验证`} />
        ) : null}
      </View>

      {visibleMetrics.length > 0 ? (
        <View style={styles.metrics}>
          {visibleMetrics.map((metric) => (
            <View key={metric} style={styles.metric}>
              <Ionicons name="checkmark-circle-outline" size={11} color={C.green500} />
              <Text maxFontSizeMultiplier={1.2} style={styles.metricText} numberOfLines={1}>
                {metric}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {visibleDays.length > 0 ? (
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
      ) : null}

      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        {boundary}
      </Text>
    </CardShell>
  );
}

function Chip({ label, tone = 'soft' }: { label: string; tone?: 'soft' | 'strong' }) {
  return (
    <View style={[styles.chip, tone === 'strong' && styles.chipStrong]}>
      <Text
        maxFontSizeMultiplier={1.2}
        style={[styles.chipText, tone === 'strong' && styles.chipTextStrong]}
        numberOfLines={1}
      >
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
  const visibleTitle = dayTitle === currentTitle ? '当前重点行动' : dayTitle || '待运行时重排';
  return (
    <View style={styles.day}>
      <Text maxFontSizeMultiplier={1.2} style={styles.dayDate}>
        {text(day.date) || `D${index + 1}`}
      </Text>
      <Text maxFontSizeMultiplier={1.2} style={styles.dayTitle} numberOfLines={1}>
        {visibleTitle}
      </Text>
      <Text maxFontSizeMultiplier={1.2} style={styles.dayCount}>
        {numberText(day.items_count) || '0'}项
      </Text>
    </View>
  );
}

export const RuntimeAgendaCardSpec: CardSpec<RuntimeAgendaData> = {
  type: 'runtime_agenda',
  label: '7天健康运行时',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <RuntimeAgendaCardView {...data} />,
};

const styles = StyleSheet.create({
  hero: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 9,
  },
  heroIcon: {
    width: 30,
    height: 30,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.normal.line,
  },
  heroBody: {
    flex: 1,
    minWidth: 0,
  },
  actionTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 20,
  } as TextStyle,
  summary: {
    marginTop: 3,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 17,
  } as TextStyle,
  chips: {
    marginTop: 10,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  chip: {
    maxWidth: '100%',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  chipStrong: {
    backgroundColor: C.green500,
    borderColor: C.green500,
  },
  chipText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.ink2,
    lineHeight: 13,
  } as TextStyle,
  chipTextStrong: {
    color: C.greenOn,
  } as TextStyle,
  metrics: {
    marginTop: 9,
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
    borderRadius: revaRadii.sm,
    backgroundColor: C.surface,
  },
  metricText: {
    fontFamily: revaFonts.mono,
    fontSize: 10,
    color: C.ink2,
  } as TextStyle,
  days: {
    marginTop: 10,
    gap: 5,
  },
  day: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    minHeight: 28,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: revaRadii.sm,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  dayDate: {
    width: 74,
    fontFamily: revaFonts.mono,
    fontSize: 10,
    color: C.ink3,
  } as TextStyle,
  dayTitle: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    color: C.ink2,
  } as TextStyle,
  dayCount: {
    fontFamily: revaFonts.mono,
    fontSize: 10,
    color: C.ink3,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
});
