import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, TextStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';
import { colors, spacing, radii } from '../constants/theme';
import {
  VOICE_STYLES, type VoiceStyle,
  loadVoiceStyle, saveVoiceStyle, resolveSpeechOptions,
} from '../services/voiceStyle';

const PREVIEW_TEXT = '你好，我是你的健康助理。今天血氧不错，建议继续保持。';

export default function VoiceStyleScreen() {
  const router = useRouter();
  const [current, setCurrent] = useState<VoiceStyle | null>(null);

  useEffect(() => {
    loadVoiceStyle().then(setCurrent);
    return () => { Speech.stop(); };
  }, []);

  const pick = async (style: VoiceStyle) => {
    Haptics.selectionAsync();
    setCurrent(style);
    await saveVoiceStyle(style);
    // 立即试听
    Speech.stop();
    const opts = await resolveSpeechOptions(style);
    Speech.speak(PREVIEW_TEXT, opts);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>语音风格</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Text style={txt.hint}>
          选择语音助理的声音风格。点击选项会立即试听。
        </Text>

        <View style={styles.card}>
          {VOICE_STYLES.map((opt, idx) => {
            const selected = current === opt.key;
            return (
              <TouchableOpacity
                key={opt.key}
                style={[styles.row, idx < VOICE_STYLES.length - 1 && styles.rowDivider]}
                onPress={() => pick(opt.key)}
                activeOpacity={0.7}
              >
                <View style={{ flex: 1 }}>
                  <Text style={txt.label}>{opt.label}</Text>
                  <Text style={txt.desc}>{opt.description}</Text>
                </View>
                {selected ? (
                  <Ionicons name="checkmark" size={22} color={colors.brand} />
                ) : (
                  <View style={{ width: 22 }} />
                )}
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={txt.footerHint}>
          注：设备不支持的语音会自动回退到系统默认。Siri 语音记录不受此设置影响。
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  card: {
    backgroundColor: colors.bgCard, borderRadius: radii.md,
    marginTop: spacing.md, overflow: 'hidden',
  },
  row: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: spacing.md, paddingHorizontal: spacing.md, gap: spacing.sm,
  },
  rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  hint: { fontSize: 13, color: colors.labelSecondary, lineHeight: 19 } as TextStyle,
  label: { fontSize: 15, color: colors.labelPrimary, fontWeight: '500' } as TextStyle,
  desc: { fontSize: 12, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  footerHint: { fontSize: 12, color: colors.labelTertiary, lineHeight: 18, marginTop: spacing.md, paddingHorizontal: spacing.xs } as TextStyle,
};
