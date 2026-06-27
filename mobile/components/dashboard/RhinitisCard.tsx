import React, { useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { updateCheckin } from '../../services/records';
import api from '../../services/api';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

// 鼻炎计数器的装饰性 hue (洗鼻青 / 喷嚏琥珀) —— 「区分类目」的色码,不是「好坏」三步语义,故为局部字面量。
const RHIN_HUE = { wash: '#2F9E8F', sneeze: '#C98A1E' } as const;

interface Props {
  checkin: any;
  medications?: any[];
  onUpdate?: () => void;
}

async function ensureAndLogMed(
  aliases: string[],
  create: { name: string; dosage: string; frequency: string; category: string; purpose: string; notes?: string },
  actualDosage: string,
) {
  const medsRes = await api.get('/medication/medications/me');
  const meds: any[] = medsRes.data || [];
  let med = meds.find((m: any) => aliases.includes(m.name));
  if (!med) {
    const r = await api.post('/medication/medications', { times_per_day: 1, ...create });
    med = r.data;
  }
  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  await api.post('/medication/logs', {
    medication_id: med.id,
    taken_time: timeStr,
    status: 'taken',
    actual_dosage: actualDosage,
  });
}

export default function RhinitisCard({ checkin, medications, onUpdate }: Props) {
  const sneezeCount = checkin?.sneeze_count || 0;
  const washCount = checkin?.nasal_wash_count || 0;

  const doAction = useCallback(async (field: string, value: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await updateCheckin(field, value);
      onUpdate?.();
    } catch { /* ignore */ }
  }, [onUpdate]);

  const logMed = useCallback(async (
    aliases: string[],
    create: { name: string; dosage: string; frequency: string; category: string; purpose: string; notes?: string },
    dosage: string,
  ) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await ensureAndLogMed(aliases, create, dosage);
      onUpdate?.();
    } catch { /* ignore */ }
  }, [onUpdate]);

  const ipratropiumTaken = (medications || []).some(
    (m: any) => ['异丙托溴铵', '异丙托溴铵鼻喷雾剂'].includes(m.name) && m.taken_count > 0
  );
  // 莫米松同样从 medications 拉, 不再写到 health_checkin (没那个列, 老代码静默 422)
  const mometasoneTaken = (medications || []).some(
    (m: any) => ['糠酸莫米松鼻喷雾剂', '糠酸莫米松', '莫米松', 'Mometasone'].includes(m.name) && m.taken_count > 0
  );

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={{ fontSize: 14 }}>🤧</Text>
        <Text style={txt.title}>鼻炎</Text>
      </View>
      <View style={styles.row}>
        <TouchableOpacity style={styles.chip} onPress={() => doAction('nasal_wash_count', washCount + 1)} activeOpacity={0.7}>
          <Text style={[txt.chipVal, { color: RHIN_HUE.wash }]}>{washCount}</Text>
          <Text style={txt.chipLabel}>洗鼻</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.chip} onPress={() => doAction('sneeze_count', sneezeCount + 1)} activeOpacity={0.7}>
          <Text style={[txt.chipVal, { color: RHIN_HUE.sneeze }]}>{sneezeCount}</Text>
          <Text style={txt.chipLabel}>喷嚏</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.chip, mometasoneTaken && { backgroundColor: C.green50 }]}
          onPress={() => logMed(
            ['糠酸莫米松鼻喷雾剂', '糠酸莫米松', '莫米松', 'Mometasone'],
            { name: '糠酸莫米松鼻喷雾剂', dosage: '每侧2喷', frequency: '每日1次', category: 'prescription', purpose: '过敏性鼻炎', notes: '鼻喷糖皮质激素' },
            '每侧2喷',
          )}
          activeOpacity={0.7}
        >
          <Ionicons name={mometasoneTaken ? 'checkmark-circle' : 'ellipse-outline'} size={16} color={mometasoneTaken ? C.green500 : C.ink3} />
          <Text style={txt.chipLabel}>莫米松</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.chip, ipratropiumTaken && { backgroundColor: C.green50 }]}
          onPress={() => logMed(
            ['异丙托溴铵', '异丙托溴铵鼻喷雾剂', 'Ipratropium Bromide'],
            { name: '异丙托溴铵鼻喷雾剂', dosage: '每侧2喷', frequency: '每日3-4次', category: 'prescription', purpose: '过敏性鼻炎/流涕', notes: '抗胆碱能鼻喷，缓解流涕' },
            '每侧2喷',
          )}
          activeOpacity={0.7}
        >
          <Ionicons name={ipratropiumTaken ? 'checkmark-circle' : 'ellipse-outline'} size={16} color={ipratropiumTaken ? C.green500 : C.ink3} />
          <Text style={txt.chipLabel}>异丙托</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// Reva 设计语言:暖白 surface / paper2 recessed chip 底 / r-lg 18 / light-first 软阴影。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s3, marginBottom: revaSpacing.s3,
    ...revaShadows.sm,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  row: { flexDirection: 'row', gap: revaSpacing.s2 },
  chip: {
    flex: 1, backgroundColor: C.paper2, borderRadius: revaRadii.md,
    paddingVertical: 8, alignItems: 'center', gap: 2,
  },
});

// 数字(洗鼻/喷嚏计数)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.ink1 } as TextStyle,
  chipVal: { fontFamily: revaFonts.mono, fontSize: 20, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  chipLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
};
