/**
 * Record tab 的症状总览卡. 显示今日已记症状, 提供"+ 记症状"入口.
 * 点一条 chip 可展开备注, 长按可删除 (轻量用户自助).
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useQuery } from '@tanstack/react-query';
import { BODY_PARTS, listMySymptoms, type SymptomEntry } from '../../services/symptoms';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

const PART_EMOJI: Record<string, string> = Object.fromEntries(
  BODY_PARTS.map(p => [p.value, p.emoji]),
);

export default function SymptomCard() {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const todayYmd = new Date().toISOString().slice(0, 10);
  const { data: entries = [] } = useQuery<SymptomEntry[]>({
    queryKey: ['symptoms', 'today'],
    queryFn: () => listMySymptoms({ start_date: todayYmd, limit: 20 }),
    staleTime: 60_000,
  });

  const onAdd = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push('/symptom-record' as any);
  };

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={{ fontSize: 14 }}>🩺</Text>
        <Text style={txt.title}>症状</Text>
        <View style={{ flex: 1 }} />
        <Text style={txt.count}>今日 {entries.length} 条</Text>
      </View>

      {entries.length === 0 ? (
        <TouchableOpacity style={styles.addBig} onPress={onAdd} activeOpacity={0.7}>
          <Ionicons name="add-circle-outline" size={18} color={c.labelSecondary} />
          <Text style={txt.addBigText}>记一条 — 眼睛痒 / 膝盖疼 / 嗓子不舒服…</Text>
        </TouchableOpacity>
      ) : (
        <View style={{ gap: 6 }}>
          {entries.slice(0, 5).map(e => (
            <View key={e.id} style={styles.entryRow}>
              <Text style={{ fontSize: 16 }}>{PART_EMOJI[e.body_part] || '•'}</Text>
              <Text style={txt.entryText} numberOfLines={1}>{e.description}</Text>
              {e.severity != null && (
                <View style={[styles.sevTag, { backgroundColor: severityColor(e.severity, c) + '22' }]}>
                  <Text style={[txt.sevTagText, { color: severityColor(e.severity, c) }]}>
                    {e.severity}
                  </Text>
                </View>
              )}
              <Text style={txt.entryTime}>{formatTime(e.occurred_at)}</Text>
            </View>
          ))}
          {entries.length > 5 && (
            <Text style={txt.moreHint}>还有 {entries.length - 5} 条</Text>
          )}
          <TouchableOpacity style={styles.addSmall} onPress={onAdd} activeOpacity={0.7}>
            <Ionicons name="add" size={16} color={c.brand} />
            <Text style={txt.addSmallText}>继续记</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

function severityColor(sev: number, c: ColorPalette): string {
  if (sev >= 7) return c.red;
  if (sev >= 4) return c.amber;
  return c.green;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch { return ''; }
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.lg,
      padding: spacing.md, marginBottom: spacing.md,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, shadowRadius: 3, elevation: 1 }),
    },
    header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
    addBig: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
      paddingVertical: 14, backgroundColor: c.bgPrimary, borderRadius: radii.md,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
      borderStyle: 'dashed' as any,
    },
    entryRow: {
      flexDirection: 'row', alignItems: 'center', gap: 8,
      paddingVertical: 8, paddingHorizontal: 10,
      backgroundColor: c.bgPrimary, borderRadius: radii.md,
    },
    sevTag: {
      paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
    },
    addSmall: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
      paddingVertical: 8,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 14, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    count: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    addBigText: { fontSize: 13, color: c.labelSecondary } as TextStyle,
    entryText: { flex: 1, fontSize: 14, color: c.labelPrimary } as TextStyle,
    entryTime: { fontSize: 11, color: c.labelTertiary, fontVariant: ['tabular-nums'] as const } as TextStyle,
    sevTagText: { fontSize: 11, fontWeight: '700' } as TextStyle,
    moreHint: { fontSize: 12, color: c.labelTertiary, textAlign: 'center', paddingVertical: 4 } as TextStyle,
    addSmallText: { fontSize: 13, fontWeight: '600', color: c.brand } as TextStyle,
  };
}
