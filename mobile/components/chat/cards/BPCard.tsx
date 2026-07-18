import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { CardShell } from './CardShell';
import { revaColors as C, revaSemantic, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

interface BPData {
  systolic: number;
  diastolic: number;
  pulse?: number;
  measured_at?: string;
  category?: string;
  category_color?: string;
  safety_guidance?: BPSafetyGuidance | null;
}

interface BPSafetyGuidance {
  severity: 'high';
  title?: string;
  recheck_instruction: string;
  emergency_instruction: string;
  action_path: string;
}

const BP_FALLBACK_COLOR = '#64748B';

export function BPCardView({ systolic, diastolic, pulse, measured_at, category, category_color, safety_guidance }: BPData) {
  const router = useRouter();
  const displayCategory = category || '未分类';
  const displayColor = category_color || BP_FALLBACK_COLOR;
  return (
    <CardShell
      icon="heart"
      iconColor={revaSemantic.risk.fg}
      title="血压"
      badge={displayCategory}
      badgeColor={displayColor}
      bg={revaSemantic.risk.bg}
      onPress={() => router.push(safety_guidance ? '/(tabs)/record' : { pathname: '/indicator-history', params: { type: 'blood_pressure' } })}
    >
      <View style={styles.row}>
        <View style={styles.bpBlock}>
          <Text maxFontSizeMultiplier={1.3} style={[styles.bpNum, { color: displayColor }]}>
            {systolic}
            <Text style={styles.bpSlash}> / </Text>
            {diastolic}
          </Text>
          <Text maxFontSizeMultiplier={1.3} style={styles.unit}>mmHg</Text>
        </View>
        {pulse != null && (
          <View style={styles.pulseBlock}>
            <Text maxFontSizeMultiplier={1.3} style={styles.pulseNum}>{pulse}</Text>
            <Text maxFontSizeMultiplier={1.3} style={styles.pulseLabel}>脉搏 bpm</Text>
          </View>
        )}
      </View>
      {measured_at && (
        <Text maxFontSizeMultiplier={1.3} style={styles.time}>{measured_at}</Text>
      )}
      {safety_guidance && (
        <View accessibilityRole="alert" style={styles.safetyGuidance}>
          <Text maxFontSizeMultiplier={1.3} style={styles.safetyText}>{safety_guidance.recheck_instruction}</Text>
          <Text maxFontSizeMultiplier={1.3} style={styles.safetyText}>{safety_guidance.emergency_instruction}</Text>
          <Text maxFontSizeMultiplier={1.3} style={styles.safetyLink}>点此复测后记录</Text>
        </View>
      )}
    </CardShell>
  );
}

export const BPCardSpec: CardSpec<BPData> = {
  type: 'blood_pressure',
  label: '血压',
  match({ query_lower }) {
    if (/血压|bp|收缩压|舒张压|高压|低压/.test(query_lower)) return 15;
    return null;
  },
  async build({ api }) {
    try {
      const res = await api.get('/blood-pressure/records/me', { params: { limit: 1 } });
      const list = res.data;
      if (!Array.isArray(list) || list.length === 0) return null;
      const r = list[0];
      if (!r || r.systolic == null || r.diastolic == null) return null;
      return {
        systolic: r.systolic,
        diastolic: r.diastolic,
        pulse: r.pulse,
        measured_at: r.record_date ? String(r.record_date) : undefined,
        category: r.category || undefined,
        category_color: r.category_color || undefined,
        safety_guidance: r.safety_guidance || undefined,
      } as BPData;
    } catch {
      return null;
    }
  },
  render: (d) => <BPCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  bpBlock: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  pulseBlock: { alignItems: 'flex-end' },
  bpNum: { fontFamily: revaFonts.mono, fontSize: 22, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  bpSlash: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '400', color: C.ink3 } as TextStyle,
  unit: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3 } as TextStyle,
  pulseNum: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '700', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  pulseLabel: { fontFamily: revaFonts.sans, fontSize: 9, color: C.ink3 } as TextStyle,
  time: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3, marginTop: 4 } as TextStyle,
  safetyGuidance: { marginTop: 10, padding: 9, borderRadius: 6, backgroundColor: '#FEE2E2', gap: 4 },
  safetyText: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 17, color: '#991B1B' } as TextStyle,
  safetyLink: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700', color: '#991B1B', marginTop: 2 } as TextStyle,
});
