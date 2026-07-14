import React, { useEffect, useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Pressable, TextStyle, ScrollView, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import Animated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming, Easing, withSequence } from 'react-native-reanimated';
import Markdown from 'react-native-markdown-display';
import { prepareSafeMarkdown, safeMarkdownIt } from '../utils/safeMarkdown';
import { useVoiceConversation } from '../hooks/useVoiceConversation';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { createMdStylesChat } from '../constants/markdownStyles';
import { fetchBriefingVoiceScript, fetchWeeklyVoiceScript, fetchPreWorkoutVoiceScript, fetchClarificationOpener, extractMemoryFromDialog } from '../services/briefing';
import { sharePlainText } from '../utils/share';

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
 *   - 告警澄清推送:    `?intent=clarify&alert_id=X`  AI 主动开口问 follow-up → 接话
 *   - 周聊推送:        `?intent=weekly`       周日 20:00 推送, 本周回顾 + 询问下周计划
 *   - 跑前准备:        `?intent=preworkout&workout_type=running`  首页按钮触发, readiness 建议 + 接话
 *   - 声音笔记:        `?intent=journal`      AI 开口'说吧我帮你记', 用户说事实, agent 自动调 health_record
 *   - 默认:                                  待用户主动点球
 */
export default function VoiceChatScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const mdStyles = useMemo(() => createMdStylesChat(c), [c]);
  const params = useLocalSearchParams<{ autoStart?: string; prompt?: string; intent?: string; alert_id?: string; workout_type?: string; conversation_id?: string }>();
  const voice = useVoiceConversation();
  const scrollRef = React.useRef<ScrollView>(null);
  const [showHistory, setShowHistory] = React.useState(false);
  const [historyList, setHistoryList] = React.useState<Array<{ id: number; title: string; updated_at?: string }>>([]);

  // ?conversation_id=XXX 进来 → 加载该对话 turns, 供 review
  useEffect(() => {
    const cid = params.conversation_id ? Number(params.conversation_id) : null;
    if (cid && Number.isFinite(cid)) {
      voice.loadConversation(cid);
    }

  }, [params.conversation_id]);

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

  // intent=clarify&alert_id=X: AI 主动开口问 follow-up (Agent Native 闭环)
  // 推送 → 点开 → 私享女声直接读 opener → 进 listening 接你回答
  const clarifyTriggeredRef = React.useRef(false);
  useEffect(() => {
    if (params.intent !== 'clarify' || clarifyTriggeredRef.current) return;
    const alertIdNum = Number(params.alert_id);
    if (!alertIdNum || isNaN(alertIdNum)) return;
    clarifyTriggeredRef.current = true;
    (async () => {
      try {
        const { opener } = await fetchClarificationOpener(alertIdNum);
        if (opener && opener.trim()) {
          await voice.speakDirect(opener, { thenListen: true });
        }
      } catch (e) {
        if (__DEV__) console.warn('[voice-chat] clarify fetch failed:', e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.intent, params.alert_id]);

  // intent=weekly: 周日 20:00 推送进来, 私享女声播本周回顾 + 询问下周计划
  const weeklyTriggeredRef = React.useRef(false);
  useEffect(() => {
    if (params.intent !== 'weekly' || weeklyTriggeredRef.current) return;
    weeklyTriggeredRef.current = true;
    (async () => {
      try {
        const { script } = await fetchWeeklyVoiceScript();
        if (script && script.trim()) {
          await voice.speakDirect(script, { thenListen: true });
        }
      } catch (e) {
        if (__DEV__) console.warn('[voice-chat] weekly fetch failed:', e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.intent]);

  // intent=preworkout: 首页'马上要运动'按钮 → readiness 建议 + 接话
  const preworkoutTriggeredRef = React.useRef(false);
  useEffect(() => {
    if (params.intent !== 'preworkout' || preworkoutTriggeredRef.current) return;
    preworkoutTriggeredRef.current = true;
    (async () => {
      try {
        const { script } = await fetchPreWorkoutVoiceScript(params.workout_type);
        if (script && script.trim()) {
          await voice.speakDirect(script, { thenListen: true });
        }
      } catch (e) {
        if (__DEV__) console.warn('[voice-chat] preworkout fetch failed:', e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.intent, params.workout_type]);

  // intent=journal: 声音笔记模式 — AI 开口邀请用户说事实, agent 自动调 health_record 记录
  // 不需要后端拉稿 (固定 opener), 但会进 listening 等用户说
  const journalTriggeredRef = React.useRef(false);
  useEffect(() => {
    if (params.intent !== 'journal' || journalTriggeredRef.current) return;
    journalTriggeredRef.current = true;
    (async () => {
      const opener = '说吧，我帮你记。可以告诉我症状、用药、运动、心情，或者今天发生的事。';
      await voice.speakDirect(opener, { thenListen: true });
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
    } else if (voice.state === 'speaking' || voice.state === 'thinking') {
      // 打断 AI: startListening 自己会 stopCurrentSpeech + 清 TTS 队列 + abort LLM 请求
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      voice.startListening();
    } else if (voice.state === 'idle' || voice.state === 'error') {
      voice.startListening();
    }
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
        <TouchableOpacity
          onPress={() => {
            if (!voice.turns || voice.turns.length === 0) {
              Alert.alert('还没有内容可分享', '说几句再来');
              return;
            }
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            const dateStr = new Date().toLocaleString('zh-CN', {
              year: 'numeric', month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit',
            });
            const lines = voice.turns
              .filter(t => t.text && t.text.trim())
              .map(t => {
                const prefix = t.role === 'user' ? '我' : '小巴';
                // 去掉 markdown 粗/斜/code 符号, 分享出去纯文本更干净
                const clean = t.text
                  .replace(/\*\*(.+?)\*\*/g, '$1')
                  .replace(/\*(.+?)\*/g, '$1')
                  .replace(/`(.+?)`/g, '$1')
                  .replace(/#+\s*/g, '');
                return `${prefix}: ${clean}`;
              })
              .join('\n\n');
            const header = `小巴 · 语音对话 · ${dateStr}\n${'─'.repeat(20)}\n`;
            sharePlainText({
              title: '语音对话记录',
              message: header + lines,
            }).catch(() => {});
          }}
          style={{ padding: 6, marginRight: 4 }}
          accessibilityLabel="分享对话"
        >
          <Ionicons name="share-outline" size={22} color={c.labelSecondary} />
        </TouchableOpacity>
        <TouchableOpacity
          onPress={async () => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            try {
              const { getConversations } = await import('../services/chat');
              const convs = await getConversations();
              setHistoryList(convs.map((c: any) => ({
                id: c.id, title: c.title || '(未命名对话)', updated_at: c.updated_at || c.created_at,
              })));
              setShowHistory(true);
            } catch {
              Alert.alert('加载失败', '无法加载历史对话');
            }
          }}
          style={{ padding: 6, marginRight: 4 }}
          accessibilityLabel="历史对话"
        >
          <Ionicons name="time-outline" size={22} color={c.labelSecondary} />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => {
          // I Phase 2: 关闭前若本次对话有 health_record 录入, 弹 summary 卡让用户 review
          // (复用 RN Alert, 简单可靠 — 进阶版可做自定义 modal + 撤销按钮)
          const items = voice.recordedItemsRef?.current || [];
          const closeSequence = () => {
            // 旁路抽 fact 写 memory_facts (Karpathy "anterograde amnesia" 解药)
            // fire-and-forget, 不阻塞退出 — 失败也无所谓
            const userTurns = voice.turns.filter(t => t.role === 'user').map(t => t.text);
            if (userTurns.length > 0) {
              const alertId = params.alert_id ? Number(params.alert_id) : undefined;
              extractMemoryFromDialog(userTurns, alertId).catch(() => {});
            }
            voice.reset();
            router.back();
          };

          if (items.length > 0) {
            const list = items.map((it: any) => `• ${it.label}`).join('\n');
            Alert.alert(
              `本次记了 ${items.length} 项`,
              list,
              [
                { text: '都对', onPress: closeSequence, style: 'default' },
                { text: '关闭', onPress: closeSequence, style: 'cancel' },
              ],
            );
          } else {
            closeSequence();
          }
        }} hitSlop={12} accessibilityLabel="退出语音对话">
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
                <Markdown style={mdStyles} markdownit={safeMarkdownIt}>{prepareSafeMarkdown(t.text)}</Markdown>
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
          {voice.state === 'listening' ? '停 1 秒自动发，或再点一下立即结束'
            : voice.state === 'speaking' ? '点一下打断，换你说'
            : voice.state === 'thinking' ? '点一下打断，换你说'
            : voice.state === 'idle' ? '点一下开始说话'
            : ' '}
        </Text>
      </View>

      {/* 历史对话列表 — 与 home chat 共享 backend, 选中加载 turns 到当前页 */}
      {showHistory && (
        <View style={historyStyles.overlay}>
          <TouchableOpacity style={historyStyles.backdrop} onPress={() => setShowHistory(false)} />
          <View style={[historyStyles.sheet, { backgroundColor: c.bgCard }]}>
            <View style={historyStyles.sheetHeader}>
              <Text style={[historyStyles.sheetTitle, { color: c.labelPrimary }]}>历史对话</Text>
              <TouchableOpacity onPress={() => setShowHistory(false)}>
                <Ionicons name="close" size={24} color={c.labelSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ maxHeight: 500 }}>
              {historyList.length === 0 && (
                <Text style={{ textAlign: 'center', color: c.labelTertiary, padding: 24 }}>暂无历史</Text>
              )}
              {historyList.map(h => (
                <TouchableOpacity
                  key={h.id}
                  style={[historyStyles.row, { borderBottomColor: c.separator }]}
                  onPress={() => {
                    setShowHistory(false);
                    voice.reset();
                    voice.loadConversation(h.id);
                  }}
                >
                  <Text style={{ color: c.labelPrimary, fontSize: 15, fontWeight: '500' }} numberOfLines={1}>{h.title}</Text>
                  {h.updated_at && (
                    <Text style={{ color: c.labelTertiary, fontSize: 11, marginTop: 3 }}>{h.updated_at.slice(0, 16).replace('T', ' ')}</Text>
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>
      )}
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

const historyStyles = StyleSheet.create({
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'flex-end' },
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingTop: 16, paddingBottom: 32, paddingHorizontal: 16,
  },
  sheetHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 4, paddingBottom: 12,
  },
  sheetTitle: { fontSize: 17, fontWeight: '600' },
  row: {
    paddingVertical: 12, paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
});
