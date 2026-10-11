import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../../constants/revaTheme';

const SUPP_ACCENT = '#7C5CBF';
const SUPP_TINT = '#F3EEF8';

const SOURCE_LABELS: Record<string, string> = {
  chat: '对话',
  voice: '语音',
  text: '文字',
  photo: '图片',
};

interface SupplementDraftData {
  items?: unknown;
  taken_date?: unknown;
  decision_status?: unknown;
  supplement_name?: unknown;
  dose?: unknown;
  taken_time?: unknown;
  confidence?: unknown;
  source?: unknown;
  suggestions?: unknown;
  boundary?: unknown;
  presentation_state?: unknown;
}

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function listText(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : value == null ? [] : [value];
  return raw.map(text).filter((item): item is string => Boolean(item)).slice(0, 3);
}

function confidenceLabel(value: unknown): string | undefined {
  const confidence = numberValue(value);
  if (confidence == null) return undefined;
  const normalized = confidence <= 1 ? confidence * 100 : confidence;
  if (normalized <= 0) return undefined;
  return `置信度 ${Math.round(Math.min(100, normalized))}%`;
}

function sourceLabel(value: unknown): string | undefined {
  const source = text(value);
  if (!source) return undefined;
  return `来源: ${SOURCE_LABELS[source] || source}`;
}

function timeLabel(value: unknown): string | undefined {
  const raw = text(value);
  if (!raw) return undefined;
  const match = raw.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/);
  return match ? match[0] : raw;
}

export function SupplementDraftCardView(data: SupplementDraftData) {
  const items = Array.isArray(data.items) ? data.items.map((value) => {
    const item = value && typeof value === 'object' ? value as Record<string, unknown> : {};
    return {
      name: text(item.supplement_name) || '名称待核对',
      dosage: text(item.actual_dosage) || '数量待核对',
      strength: text(item.observed_strength),
    };
  }) : [];
  const takenDate = text(data.taken_date);
  const status = text(data.decision_status);
  const terminal = status === 'executed'
    ? { title: '已记录', badge: '已写入', boundary: '已按确认内容写入本次补剂记录。' }
    : status === 'dismissed'
      ? { title: '已取消', badge: '未写入', boundary: '已取消，这组记录没有写入。' }
      : status === 'expired'
        ? { title: '已过期', badge: '未写入', boundary: '确认已过期，这组记录没有写入；请重新发送。' }
        : undefined;
  const supplementName = text(data.supplement_name) || '待确认补剂';
  const dose = text(data.dose);
  const takenAt = timeLabel(data.taken_time);
  const meta = [confidenceLabel(data.confidence), sourceLabel(data.source)].filter(Boolean).join(' · ');
  const suggestions = listText(data.suggestions);
  const isSuggestion = text(data.presentation_state) === 'suggestion';
  const boundary = terminal?.boundary || text(data.boundary) || '确认后记录为已服用; 如正在用药或有慢病, 先核对相互作用。';

  return (
    <CardShell
      icon="leaf"
      iconColor={SUPP_ACCENT}
      title={terminal ? `补剂 · ${terminal.title}` : isSuggestion ? '补剂 · 待核对' : '补剂 · 待确认'}
      badge={terminal?.badge || (isSuggestion ? '去记录' : '需核对')}
      badgeColor={SUPP_ACCENT}
      bg={SUPP_TINT}
    >
      {items.length > 0 ? (
        <View style={styles.itemList}>
          {items.map((item, index) => (
            <View key={index} style={styles.itemRow}>
              <Text maxFontSizeMultiplier={1.18} style={styles.itemName}>{item.name}</Text>
              <Text maxFontSizeMultiplier={1.12} style={styles.chip}>本次 {item.dosage}</Text>
              {item.strength ? <Text style={styles.metaText}>规格 {item.strength}</Text> : null}
            </View>
          ))}
        </View>
      ) : (
        <Text maxFontSizeMultiplier={1.18} style={styles.supplementName}>
          {supplementName}
        </Text>
      )}
      {takenDate ? <Text style={styles.metaText}>记录日期 {takenDate}</Text> : null}

      {(dose || takenAt) ? (
        <View style={styles.chipRow}>
          {dose ? <Text maxFontSizeMultiplier={1.12} style={styles.chip}>{dose}</Text> : null}
          {takenAt ? <Text maxFontSizeMultiplier={1.12} style={styles.chip}>{takenAt}</Text> : null}
        </View>
      ) : null}

      {meta ? (
        <View style={styles.metaRow}>
          <Ionicons name="sparkles-outline" size={14} color={SUPP_ACCENT} />
          <Text maxFontSizeMultiplier={1.12} style={styles.metaText}>
            {meta}
          </Text>
        </View>
      ) : null}

      {suggestions.length > 0 ? (
        <View style={styles.suggestionBox}>
          {suggestions.map((item) => (
            <View key={item} style={styles.suggestionRow}>
              <Ionicons name="checkmark-circle-outline" size={14} color={revaSemantic.normal.fg} />
              <Text maxFontSizeMultiplier={1.15} style={styles.suggestionText}>
                {item}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.boundaryRow}>
        <Ionicons name="information-circle-outline" size={14} color={C.ink3} />
        <Text maxFontSizeMultiplier={1.12} style={styles.boundaryText}>
          {boundary}
        </Text>
      </View>
    </CardShell>
  );
}

export const SupplementDraftCardSpec: CardSpec<SupplementDraftData> = {
  type: 'supplement_draft',
  label: '补剂草稿',
  match() { return null; },
  build() { return null; },
  render: (data) => <SupplementDraftCardView {...data} />,
};

const styles = StyleSheet.create({
  itemList: { gap: 12, marginVertical: 10 },
  itemRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  itemName: {
    flexGrow: 1,
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 16,
    lineHeight: 23,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  supplementName: {
    fontFamily: revaFonts.sans,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '800',
    color: C.ink1,
    marginTop: 2,
  } as TextStyle,
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
  },
  chip: {
    overflow: 'hidden',
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#DED4F1',
    paddingHorizontal: 10,
    paddingVertical: 5,
    fontFamily: revaFonts.mono,
    fontSize: 13,
    color: SUPP_ACCENT,
    fontWeight: '700',
  } as TextStyle,
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 12,
  },
  metaText: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 18,
    color: C.ink2,
    fontWeight: '600',
  } as TextStyle,
  suggestionBox: {
    gap: 6,
    marginTop: 12,
    padding: 10,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  suggestionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
  },
  suggestionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 19,
    color: C.ink2,
    fontWeight: '600',
  } as TextStyle,
  boundaryRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginTop: 10,
  },
  boundaryText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink3,
  } as TextStyle,
});
