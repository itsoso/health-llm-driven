import React, { useEffect, useRef, useState, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, TextStyle, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';
import { createAudioPlayer } from 'expo-audio';
import { spacing, radii } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import {
  VOICE_STYLES, type VoiceStyle,
  loadVoiceStyle, saveVoiceStyle, resolveIosSpeechOptions, getVoiceStyle,
} from '../services/voiceStyle';
import { synthesize as cloudSynthesize } from '../services/cloudTts';
import { shouldFinishAudioPlayback } from '../utils/audioPlayback';

const PREVIEW_TEXT = '你好，我是阿衡。今天血氧不错，建议继续保持。';

export default function VoiceStyleScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const [current, setCurrent] = useState<VoiceStyle | null>(null);
  const [previewing, setPreviewing] = useState<VoiceStyle | null>(null);
  const previewPlayerRef = useRef<{ cancel: () => void } | null>(null);

  useEffect(() => {
    loadVoiceStyle().then(setCurrent);
    return () => {
      previewPlayerRef.current?.cancel();
      Speech.stop();
    };
  }, []);

  const stopPreview = () => {
    try { Speech.stop(); } catch {}
    previewPlayerRef.current?.cancel();
    previewPlayerRef.current = null;
  };

  const pick = async (style: VoiceStyle) => {
    Haptics.selectionAsync();
    stopPreview();
    setCurrent(style);
    await saveVoiceStyle(style);

    const opt = getVoiceStyle(style);
    setPreviewing(style);
    if (opt.provider === 'cloud') {
      try {
        const voiceKey = opt.cloudVoiceKey ?? 'soft_hk_female';
        const { localUri } = await cloudSynthesize({ text: PREVIEW_TEXT, voiceKey });
        const player = createAudioPlayer({ uri: localUri });
        const done = () => {
          setPreviewing((cur) => (cur === style ? null : cur));
          try { player.remove(); } catch {}
          previewPlayerRef.current = null;
        };
        previewPlayerRef.current = {
          cancel: () => {
            try { player.pause(); } catch {}
            done();
          },
        };
        const sub = player.addListener('playbackStatusUpdate', (s: any) => {
          if (shouldFinishAudioPlayback(s)) {
            sub?.remove?.();
            done();
          }
        });
        player.play();
      } catch {
        setPreviewing(null);
        // 云端失败, 用 iOS 默认念一下提示 (安静降级)
        Speech.speak(PREVIEW_TEXT, { language: 'zh-CN' });
      }
    } else {
      const speechOpts = await resolveIosSpeechOptions(style);
      Speech.speak(PREVIEW_TEXT, {
        ...speechOpts,
        onDone: () => setPreviewing((cur) => (cur === style ? null : cur)),
        onStopped: () => setPreviewing(null),
        onError: () => setPreviewing(null),
      });
    }
  };

  const cloudStyles = VOICE_STYLES.filter((v) => v.provider === 'cloud');
  const iosStyles = VOICE_STYLES.filter((v) => v.provider === 'ios');

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>语音风格</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Text style={txt.hint}>
          选择语音助理的声音风格。点击选项立即试听。
        </Text>

        <Text style={txt.sectionLabel}>真人级音色 · 联网</Text>
        <View style={styles.card}>
          {cloudStyles.map((opt, idx) => (
            <Row
              key={opt.key}
              opt={opt}
              selected={current === opt.key}
              previewing={previewing === opt.key}
              onPress={() => pick(opt.key)}
              divider={idx < cloudStyles.length - 1}
            />
          ))}
        </View>

        <Text style={txt.sectionLabel}>iOS 内置 · 离线</Text>
        <View style={styles.card}>
          {iosStyles.map((opt, idx) => (
            <Row
              key={opt.key}
              opt={opt}
              selected={current === opt.key}
              previewing={previewing === opt.key}
              onPress={() => pick(opt.key)}
              divider={idx < iosStyles.length - 1}
            />
          ))}
        </View>

        <Text style={txt.footerHint}>
          联网音色走阿里云 CosyVoice 合法声库。Siri 语音记录不受此设置影响。
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({
  opt, selected, previewing, onPress, divider,
}: {
  opt: typeof VOICE_STYLES[number];
  selected: boolean;
  previewing: boolean;
  onPress: () => void;
  divider: boolean;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <TouchableOpacity
      style={[styles.row, divider && styles.rowDivider]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={txt.label}>{opt.label}</Text>
          {opt.badge ? (
            <View style={styles.badge}>
              <Text style={txt.badgeText}>{opt.badge}</Text>
            </View>
          ) : null}
        </View>
        <Text style={txt.desc}>{opt.description}</Text>
      </View>
      {previewing ? (
        <ActivityIndicator size="small" color={c.brand} />
      ) : selected ? (
        <Ionicons name="checkmark" size={22} color={c.brand} />
      ) : (
        <View style={{ width: 22 }} />
      )}
    </TouchableOpacity>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  card: {
    backgroundColor: c.bgCard, borderRadius: radii.md,
    marginTop: 8, overflow: 'hidden',
  },
  row: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: spacing.md, paddingHorizontal: spacing.md, gap: spacing.sm,
  },
  rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator },
  badge: {
    backgroundColor: c.brandLight,
    paddingHorizontal: 6, paddingVertical: 1,
    borderRadius: radii.sm,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  hint: { fontSize: 13, color: c.labelSecondary, lineHeight: 19 } as TextStyle,
  sectionLabel: { fontSize: 12, color: c.labelTertiary, marginTop: spacing.md, marginBottom: 2, textTransform: 'uppercase', letterSpacing: 0.5 } as TextStyle,
  label: { fontSize: 15, color: c.labelPrimary, fontWeight: '500' } as TextStyle,
  badgeText: { fontSize: 10, fontWeight: '600', color: c.brand } as TextStyle,
  desc: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  footerHint: { fontSize: 12, color: c.labelTertiary, lineHeight: 18, marginTop: spacing.md } as TextStyle,
});
