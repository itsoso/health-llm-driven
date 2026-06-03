/**
 * 复元 Reva — Agent (分析对话) screen.
 *
 * New, self-contained screen built against the Reva design system
 * (`docs/design/reva/`, tokens in `constants/revaTheme.ts`). Faithfully recreates
 * the Reva `AgentScreen` (warm-paper blur header + recovery-ring brand mark +
 * green/right user bubbles + surface/left assistant bubbles + quick chips +
 * pill composer with round green send), powered by the real `useChatEngine`
 * streaming. Does NOT touch the existing chat tab. Route: /reva-agent
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Markdown from 'react-native-markdown-display';
import { useChatEngine, type UIMessage } from '../hooks/useChatEngine';
import { revaColors, revaRadii, revaShadows, revaSpacing } from '../constants/revaTheme';

const QUICKS = ['今天能跑步吗？', '解读我的血糖', '这周吃得怎么样？'];

/** Recovery-ring brand mark (the Reva motif): ring + a "today" node. */
function RevaMark() {
  return (
    <View style={styles.mark}>
      <View style={styles.markNode} />
      <View style={styles.markCore} />
    </View>
  );
}

function RevaBubble({ message }: { message: UIMessage }) {
  const me = message.role === 'user';
  if (me) {
    return (
      <View style={[styles.row, { justifyContent: 'flex-end' }]}>
        <View style={[styles.bubble, styles.bubbleMe]}>
          <Text style={styles.bubbleMeText}>{message.content}</Text>
        </View>
      </View>
    );
  }
  return (
    <View style={[styles.row, { justifyContent: 'flex-start' }]}>
      <View style={[styles.bubble, styles.bubbleAgent]}>
        {message.content ? (
          <Markdown style={mdStyles}>{message.content}</Markdown>
        ) : (
          <ActivityIndicator size="small" color={revaColors.green500} />
        )}
      </View>
    </View>
  );
}

export default function RevaAgentScreen() {
  const { messages, isStreaming, sendMessage } = useChatEngine();
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(t);
  }, [messages]);

  const submit = useCallback(
    (text?: string) => {
      const t = (text ?? draft).trim();
      if (!t || isStreaming) return;
      setDraft('');
      void sendMessage(t);
    },
    [draft, isStreaming, sendMessage],
  );

  const textMessages = messages.filter(m => !m.cardType);

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      {/* Header — warm paper, brand mark + status */}
      <View style={styles.header}>
        <RevaMark />
        <View style={{ flex: 1 }}>
          <Text style={styles.brand}>复元</Text>
          <View style={styles.statusRow}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>了解你的全部健康数据</Text>
          </View>
        </View>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={8}
      >
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={styles.scrollContent}
          keyboardDismissMode="interactive"
        >
          {textMessages.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>
                问问复元 —— 它了解你的体检异常项、手环数据和 90 天计划。
              </Text>
            </View>
          ) : (
            textMessages.map(m => <RevaBubble key={m.id} message={m} />)
          )}
        </ScrollView>

        {/* Composer */}
        <View style={styles.composer}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.quicks}
          >
            {QUICKS.map(q => (
              <Pressable key={q} onPress={() => submit(q)} style={styles.chip} disabled={isStreaming}>
                <Text style={styles.chipText}>{q}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <View style={styles.inputBar}>
            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder="问问复元…"
              placeholderTextColor={revaColors.ink3}
              style={styles.input}
              returnKeyType="send"
              onSubmitEditing={() => submit()}
              editable={!isStreaming}
            />
            <Pressable
              onPress={() => submit()}
              style={[styles.send, (!draft.trim() || isStreaming) && styles.sendDisabled]}
              disabled={!draft.trim() || isStreaming}
            >
              {isStreaming ? (
                <ActivityIndicator size="small" color={revaColors.greenOn} />
              ) : (
                <Ionicons name="arrow-up" size={20} color={revaColors.greenOn} />
              )}
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: revaColors.paper },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
    paddingHorizontal: revaSpacing.s5,
    paddingTop: revaSpacing.s3,
    paddingBottom: revaSpacing.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: revaColors.line,
    backgroundColor: revaColors.paper,
  },
  mark: {
    width: 32, height: 32, borderRadius: 16,
    borderWidth: 3, borderColor: revaColors.green500,
    alignItems: 'center', justifyContent: 'center',
  },
  markNode: {
    position: 'absolute', top: -3, width: 7, height: 7, borderRadius: 3.5,
    backgroundColor: revaColors.green600,
  },
  markCore: { width: 7, height: 7, borderRadius: 3.5, backgroundColor: revaColors.green500 },
  brand: { fontWeight: '800', fontSize: 18, color: revaColors.ink1 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 1 },
  statusDot: { width: 7, height: 7, borderRadius: 3.5, backgroundColor: revaColors.green500 },
  statusText: { fontSize: 12, color: revaColors.ink2 },

  scrollContent: { padding: revaSpacing.s4, paddingBottom: revaSpacing.s5 },
  empty: { paddingTop: revaSpacing.s9, paddingHorizontal: revaSpacing.s6 },
  emptyText: { fontSize: 15, lineHeight: 23, color: revaColors.ink3, textAlign: 'center' },

  row: { flexDirection: 'row', marginBottom: 12 },
  bubble: { maxWidth: '82%', paddingVertical: 11, paddingHorizontal: 15, borderRadius: revaRadii.lg },
  bubbleMe: {
    backgroundColor: revaColors.green500,
    borderBottomRightRadius: 5,
  },
  bubbleMeText: { color: revaColors.greenOn, fontSize: 15, lineHeight: 22 },
  bubbleAgent: {
    backgroundColor: revaColors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaColors.line,
    borderBottomLeftRadius: 5,
    ...revaShadows.sm,
  },

  composer: {
    paddingHorizontal: revaSpacing.s3,
    paddingTop: revaSpacing.s2,
    paddingBottom: revaSpacing.s2,
    backgroundColor: revaColors.paper,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: revaColors.line,
  },
  quicks: { gap: 8, paddingBottom: 10, paddingHorizontal: 2 },
  chip: {
    backgroundColor: revaColors.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaColors.green100,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 13,
    paddingVertical: 7,
  },
  chipText: { fontSize: 13, fontWeight: '600', color: revaColors.green600 },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: revaColors.surface,
    borderWidth: 1.5,
    borderColor: revaColors.lineStrong,
    borderRadius: revaRadii.pill,
    paddingLeft: 16,
    paddingRight: 6,
    paddingVertical: 6,
  },
  input: { flex: 1, fontSize: 15, color: revaColors.ink1, paddingVertical: Platform.OS === 'ios' ? 6 : 2 },
  send: {
    width: 38, height: 38, borderRadius: 19,
    backgroundColor: revaColors.green500,
    alignItems: 'center', justifyContent: 'center',
  },
  sendDisabled: { backgroundColor: revaColors.green300 },
});

const mdStyles = {
  body: { color: revaColors.ink1, fontSize: 15, lineHeight: 23 },
  paragraph: { marginTop: 0, marginBottom: 8 },
  heading2: { fontSize: 16, fontWeight: '700' as const, color: revaColors.ink1, marginTop: 6, marginBottom: 4 },
  heading3: { fontSize: 15, fontWeight: '700' as const, color: revaColors.ink1, marginTop: 6, marginBottom: 4 },
  strong: { fontWeight: '700' as const, color: revaColors.ink1 },
  bullet_list: { marginBottom: 4 },
  list_item: { marginBottom: 2 },
  code_inline: { backgroundColor: revaColors.paper2, color: revaColors.ink1, fontFamily: 'IBMPlexMono' },
};
