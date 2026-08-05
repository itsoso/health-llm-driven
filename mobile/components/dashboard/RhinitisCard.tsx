import React, { useCallback } from 'react';
import { Alert, View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { updateCheckin } from '../../services/records';
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
  onUpdate?: () => void;
  onManageMedications?: () => void;
}

export default function RhinitisCard({ checkin, onUpdate, onManageMedications }: Props) {
  const sneezeCount = checkin?.sneeze_count || 0;
  const washCount = checkin?.nasal_wash_count || 0;

  const doAction = useCallback(async (field: string, value: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await updateCheckin(field, value);
      onUpdate?.();
    } catch {
      Alert.alert('记录失败', '请检查网络后重试。');
    }
  }, [onUpdate]);

  const openMedicationManager = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onManageMedications?.();
  }, [onManageMedications]);

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
          style={styles.chip}
          onPress={openMedicationManager}
          activeOpacity={0.7}
          accessibilityLabel="打开用药管理"
        >
          <Ionicons name="medkit-outline" size={16} color={C.ink3} />
          <Text style={txt.chipLabel}>用药管理</Text>
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
