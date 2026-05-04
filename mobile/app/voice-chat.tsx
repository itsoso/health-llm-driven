import React, { useEffect, useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Pressable, TextStyle, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router } from 'expo-router';
import Animated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming, Easing, withSequence } from 'react-native-reanimated';
import Markdown from 'react-native-markdown-display';
import { useVoiceConversation } from '../hooks/useVoiceConversation';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { createMdStylesChat } from '../constants/markdownStyles';
import { fetchBriefingVoiceScript } from '../services/briefing';

/**
 * 语音连续对话页. MVP 版:
 *
 * - 点中央大球 → 开始录音 (listening)
 * - 说完自动停 → submit → speaking → 回 idle 等下一轮
 * - 说话时再点 → 立即停
 * - 底部有对话历史文字滚动
 * - 右上角关闭退出
 *
 * 启动入口:
 *   - Siri:           `?autoStart=1`        立即开始第一轮录音
 *   - 晨间简报推送:    `?intent=briefing`    拉短稿 → TTS 播 → 自动进 listening 等接话
 *   - 默认:                                  待用户主动点球
 */
export default function VoiceChatScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const mdStyles = useMemo(() => createMdStylesChat(c), [c]);
  const params = useLocalSearchParams<{ autoStart?: string; prompt?: string; intent?: string }>();
  const voice = useVoiceConversation();
  const scrollRef = React.useRef<ScrollView>(null);

  const scale = useSharedValue(1);
  useEffect(() => {
    if (voice.state === 'listening') {
      scale.value = withRepeat(withSequence(withTiming(1.15, { duration: 600, easing: Easing.inOut(Easing.quad) }), withTiming(1.0, { duration: 600, easing: Easing.inOut(Easing.quad) })), -1, false);
    } else if (voice.state === 'speaking') {
      scale.value = withRepeat(withSequence(withTiming(1.08, { duration: 300 }), withTiming(1.0, { duration: 300 })), -1, false);
    } else if (voice.state === 'thinking') {
      scale.value = withRepeat(withTiming(1.05, { duration: 800, easing: Easing.linear }), -1, true);
    } else {
      scale.value = withTiming(1.0, { duration: 200 });
    }
  }, [voice.state, scale]);

  const ballStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  useEffect(() => {
    if (params.autoStart === '1') {
      const t = setTimeout(() => voice.startListening(), 400);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.autoStart]);

  // intent=briefing: 拉今日短稿 → TTS 播 → 自动进 listening 等接话
  // 用 ref 锁防止 hot-reload / re-render 重复触发
  const briefingTriggeredRef = React.useRef(false);
  useEffect(() => {
    if (params.intent !== 'briefing' || briefingTriggeredRef.current) return;
    briefingTriggeredRef.current = true;
    (async () => {
      try {
        const { script } = await fetchBriefingVoiceScript();
        if (script && script.trim()) {
          await voice.speakDirect(script, { thenListen: true });
        }
      } catch (e) {
        // 失败静默 — 用户可以点球手动开始
        if (__DEV__) console.warn('[voice-chat] briefing fetch failed:', e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.intent]);

  useEffect(() => {
    // Auto-scroll 到最新 turn
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 200);
    return () => clearTimeout(t);
  }, [voice.turns.length]);

  const onBallPress = () => {
    if (voice.state === 'listening') {
      voice.stopListening();
    } else if (voice.state === 'idle' || voice.state === 'error') {
      voice.startListening();
    }
    // thinking / speaking 期间点击忽略; speaking 打断通过"再说"交互走 startListening
  };

  const statusText = (() => {
    switch (voice.state) {
      case 'listening': return voice.transcript ? `"${voice.transcript}"` : '正在听你说...';
      case 'thinking': return '正在思考...';
      case 'speaking': return '正在回答...';
      case 'error': return voice.error || '出错了';
      default: return '点一下开始说话';
    }
  })();

  const ballColor = voice.state === 'error' ? c.red : c.brand;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={txt.title}>语音对话</Text>
        <View style={{ flex: 1 }} />
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} accessibilityLabel="退出语音对话">
          <Ionicons name="close-circle" size={28} color={c.labelTertiary} />
        </TouchableOpacity>
      </View>

      <ScrollView
        ref={scrollRef}
        style={styles.historyScroll}
        contentContainerStyle={styles.historyContainer}
        showsVerticalScrollIndicator={false}
      >
        {voice.turns.length === 0 ? (
          <View style={styles.emptyHint}>
            <Text style={txt.emptyHint}>你可以直接跟我聊健康话题，我会连续听、连续答。</Text>
          </View>
        ) : (
          voice.turns.map((t, i) => (
            <View
              key={i}
              style={[styles.bubble, t.role === 'user' ? styles.bubbleUser : styles.bubbleAI]}
            >
              {t.role === 'user' ? (
                <Text style={[txt.bubbleText, { color: '#fff' }]}>{t.text}</Text>
              ) : t.text ? (
                <Markdown style={mdStyles}>{t.text}</Markdown>
              ) : null}
            </View>
          ))
        )}
      </ScrollView>

      <View style={styles.centerArea}>
        <Text style={txt.status} numberOfLines={2}>{statusText}</Text>
        <Pressable onPress={onBallPress} style={styles.ballTouch} accessibilityLabel="语音输入">
          <Animated.View style={[styles.ball, { backgroundColor: ballColor }, ballStyle]}>
            <Ionicons
              name={voice.state === 'listening' ? 'mic' : voice.state === 'speaking' ? 'volume-high' : voice.state === 'thinking' ? 'ellipsis-horizontal' : 'mic-outline'}
              size={52}
              color="#fff"
            />
          </Animated.View>
        </Pressable>
        <Text style={txt.hint}>
          {voice.state === 'listening' ? '再点一下提前结束' : voice.state === 'idle' ? '说完自动停' : ' '}
        </Text>
      </View>
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
    historyScroll: { flex: 1, paddingHorizontal: spacing.lg },
    historyContainer: { paddingVertical: spacing.md, gap: spacing.sm },
    emptyHint: { paddingTop: 40, paddingHorizontal: spacing.xl },
    bubble: {
      maxWidth: '88%', paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
      borderRadius: radii.lg, ...shadows.subtle,
    },
    bubbleUser: { alignSelf: 'flex-end', backgroundColor: c.brand, borderBottomRightRadius: 4 },
    bubbleAI: { alignSelf: 'flex-start', backgroundColor: c.bgCard, borderBottomLeftRadius: 4 },
    centerArea: {
      alignItems: 'center', paddingBottom: 48, paddingTop: spacing.lg,
      gap: 12, paddingHorizontal: spacing.xl,
    },
    ballTouch: { alignItems: 'center', justifyContent: 'center' },
    ball: {
      width: 140, height: 140, borderRadius: 70,
      alignItems: 'center', justifyContent: 'center',
      shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    status: { fontSize: 16, color: c.labelSecondary, textAlign: 'center', minHeight: 44, lineHeight: 22 } as TextStyle,
    hint: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    emptyHint: { fontSize: 14, color: c.labelSecondary, textAlign: 'center', lineHeight: 22 } as TextStyle,
    bubbleText: { fontSize: 15, color: c.labelPrimary, lineHeight: 21 } as TextStyle,
  };
}
