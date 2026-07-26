/**
 * Record tab 的症状总览卡. 显示今日已记症状, 提供"+ 记症状"入口.
 * 点一条 chip 可展开备注, 长按可删除 (轻量用户自助).
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useQuery } from '@tanstack/react-query';
import { BODY_PARTS, listMySymptoms, type SymptomEntry } from '../../services/symptoms';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import { todayStr } from '../../utils/dietDate';

const PART_EMOJI: Record<string, string> = Object.fromEntries(
  BODY_PARTS.map(p => [p.value, p.emoji]),
);

export default function SymptomCard() {
  const todayYmd = todayStr();
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
          <Ionicons name="add-circle-outline" size={18} color={C.ink2} />
          <Text style={txt.addBigText}>记一条 — 眼睛痒 / 膝盖疼 / 嗓子不舒服…</Text>
        </TouchableOpacity>
      ) : (
        <View style={{ gap: 6 }}>
          {entries.slice(0, 5).map(e => (
            <View key={e.id} style={styles.entryRow}>
              <Text style={{ fontSize: 16 }}>{PART_EMOJI[e.body_part] || '•'}</Text>
              <Text style={txt.entryText} numberOfLines={1}>{e.description}</Text>
              {e.severity != null && (
                <View style={[styles.sevTag, { backgroundColor: severityColor(e.severity) + '22' }]}>
                  <Text style={[txt.sevTagText, { color: severityColor(e.severity) }]}>
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
            <Ionicons name="add" size={16} color={C.green500} />
            <Text style={txt.addSmallText}>继续记</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

// 症状严重度 = 真正的「好坏」语义 → Reva 三步临床色 risk/caution/normal。
function severityColor(sev: number): string {
  if (sev >= 7) return revaSemantic.risk.fg;
  if (sev >= 4) return revaSemantic.caution.fg;
  return revaSemantic.normal.fg;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch { return ''; }
}

// Reva 设计语言:暖白 surface / paper2 recessed 行底 / r-lg 18 / light-first 软阴影。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s3, marginBottom: revaSpacing.s3,
    ...revaShadows.sm,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  addBig: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    paddingVertical: 14, backgroundColor: C.paper2, borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.line,
    borderStyle: 'dashed' as any,
  },
  entryRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: C.paper2, borderRadius: revaRadii.md,
  },
  sevTag: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
  },
  addSmall: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
    paddingVertical: 8,
  },
});

// 数字(今日条数 / 严重度值 / 时间)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.ink1 } as TextStyle,
  count: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3 } as TextStyle,
  addBigText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2 } as TextStyle,
  entryText: { flex: 1, fontFamily: revaFonts.sans, fontSize: 14, color: C.ink1 } as TextStyle,
  entryTime: { fontFamily: revaFonts.mono, fontSize: 11, color: C.ink3, fontVariant: ['tabular-nums'] as const } as TextStyle,
  sevTagText: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '700' } as TextStyle,
  moreHint: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, textAlign: 'center', paddingVertical: 4 } as TextStyle,
  addSmallText: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.green500 } as TextStyle,
};
