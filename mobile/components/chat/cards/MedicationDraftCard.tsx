import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../../constants/revaTheme';

const MED_ACCENT = '#7C5CBF';
const MED_TINT = '#F1ECFA';

const SOURCE_LABELS: Record<string, string> = {
  chat: '对话',
  voice: '语音',
  text: '文字',
  photo: '图片',
};

interface MedicationDraftData {
  medication_name?: unknown;
  dose?: unknown;
  taken_time?: unknown;
  confidence?: unknown;
  source?: unknown;
  suggestions?: unknown;
  boundary?: unknown;
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

export function MedicationDraftCardView(data: MedicationDraftData) {
  const medicationName = text(data.medication_name) || '待确认用药';
  const dose = text(data.dose);
  const takenAt = timeLabel(data.taken_time);
  const meta = [confidenceLabel(data.confidence), sourceLabel(data.source)].filter(Boolean).join(' · ');
  const suggestions = listText(data.suggestions);
  const boundary = text(data.boundary) || '确认后记录为已服用; 不替代医嘱, 不调整剂量。';

  return (
    <CardShell
      icon="flask"
      iconColor={MED_ACCENT}
      title="用药 · 待确认"
      badge="需核对"
      badgeColor={MED_ACCENT}
      bg={MED_TINT}
    >
      <Text maxFontSizeMultiplier={1.18} style={styles.medicationName}>
        {medicationName}
      </Text>

      {(dose || takenAt) ? (
        <View style={styles.chipRow}>
          {dose ? <Text maxFontSizeMultiplier={1.12} style={styles.chip}>{dose}</Text> : null}
          {takenAt ? <Text maxFontSizeMultiplier={1.12} style={styles.chip}>{takenAt}</Text> : null}
        </View>
      ) : null}

      {meta ? (
        <View style={styles.metaRow}>
          <Ionicons name="sparkles-outline" size={14} color={MED_ACCENT} />
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

export const MedicationDraftCardSpec: CardSpec<MedicationDraftData> = {
  type: 'medication_draft',
  label: '用药草稿',
  match() { return null; },
  build() { return null; },
  render: (data) => <MedicationDraftCardView {...data} />,
};

const styles = StyleSheet.create({
  medicationName: {
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
    color: MED_ACCENT,
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
