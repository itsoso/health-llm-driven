/**
 * Reva Agent view. Reusable body used by the standalone route
 * (app/reva-agent.tsx) and the Reva hub's assistant tab (app/reva.tsx).
 * Powered by the real `useChatEngine` streaming. No outer SafeAreaView — the host
 * provides layout/insets.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Markdown from 'react-native-markdown-display';
import { prepareSafeMarkdown, safeMarkdownIt } from '../../utils/safeMarkdown';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import { renderCard } from '../chat/cards';
import { revaColors as C, revaRadii, revaShadows } from '../../constants/revaTheme';
import { RevaMark } from './RevaKit';

const QUICKS = ['今天能跑步吗？', '解读我的血糖', '这周吃得怎么样？'];

function RevaBubble({ message }: { message: UIMessage }) {
  if (message.cardType && message.cardData) {
    const rendered = renderCard({
      type: message.cardType,
      data: message.cardData,
      actions: message.cardActions,
    });
    if (rendered) {
      return (
        <View style={[styles.row, { justifyContent: 'flex-start' }]}>
          <View style={styles.cardFrame}>{rendered}</View>
        </View>
      );
    }
  }
  if (message.role === 'user') {
    return (
      <View style={[styles.row, { justifyContent: 'flex-end' }]}>
        <View style={[styles.bubble, styles.bubbleMe]}><Text style={styles.bubbleMeText}>{message.content}</Text></View>
      </View>
    );
  }
  return (
    <View style={[styles.row, { justifyContent: 'flex-start' }]}>
      <View style={[styles.bubble, styles.bubbleAgent]}>
        {message.content ? <Markdown style={mdStyles} markdownit={safeMarkdownIt}>{prepareSafeMarkdown(message.content)}</Markdown> : <ActivityIndicator size="small" color={C.green500} />}
      </View>
    </View>
  );
}

export function RevaAgentView({ bottomInset = 0 }: { bottomInset?: number }) {
  const { messages, isStreaming, sendMessage } = useChatEngine();
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(t);
  }, [messages]);

  const submit = useCallback((text?: string) => {
    const t = (text ?? draft).trim();
    if (!t || isStreaming) return;
    setDraft('');
    void sendMessage(t);
  }, [draft, isStreaming, sendMessage]);

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <RevaMark size={32} />
        <View style={{ flex: 1 }}>
          <Text style={styles.brand}>小巴</Text>
          <View style={styles.statusRow}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>了解你的全部健康数据</Text>
          </View>
        </View>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={8}>
        <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={styles.scrollContent} keyboardDismissMode="interactive">
          {messages.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>问问小巴 —— 它了解你的体检异常项、手环数据和 90 天计划。</Text>
            </View>
          ) : (
            messages.map(m => <RevaBubble key={m.id} message={m} />)
          )}
        </ScrollView>

        <View style={[styles.composer, { paddingBottom: 10 + bottomInset }]}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.quicks}>
            {QUICKS.map(q => (
              <Pressable key={q} onPress={() => submit(q)} style={styles.chip} disabled={isStreaming}>
                <Text style={styles.chipText}>{q}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <View style={styles.inputBar}>
            <TextInput
              value={draft} onChangeText={setDraft} placeholder="问问小巴…" placeholderTextColor={C.ink3}
              style={styles.input} returnKeyType="send" onSubmitEditing={() => submit()} editable={!isStreaming}
            />
            <Pressable onPress={() => submit()} style={[styles.send, (!draft.trim() || isStreaming) && styles.sendDisabled]} disabled={!draft.trim() || isStreaming}>
              {isStreaming ? <ActivityIndicator size="small" color={C.greenOn} /> : <Ionicons name="arrow-up" size={20} color={C.greenOn} />}
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 11,
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line, backgroundColor: C.paper,
  },
  brand: { fontWeight: '800', fontSize: 18, color: C.ink1 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 1 },
  statusDot: { width: 7, height: 7, borderRadius: 3.5, backgroundColor: C.green500 },
  statusText: { fontSize: 12, color: C.ink2 },
  scrollContent: { padding: 16, paddingBottom: 20 },
  empty: { paddingTop: 48, paddingHorizontal: 24 },
  emptyText: { fontSize: 15, lineHeight: 23, color: C.ink3, textAlign: 'center' },
  row: { flexDirection: 'row', marginBottom: 12 },
  bubble: { maxWidth: '82%', paddingVertical: 11, paddingHorizontal: 15, borderRadius: revaRadii.lg },
  bubbleMe: { backgroundColor: C.green500, borderBottomRightRadius: 5 },
  bubbleMeText: { color: C.greenOn, fontSize: 15, lineHeight: 22 },
  bubbleAgent: { backgroundColor: C.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, borderBottomLeftRadius: 5, ...revaShadows.sm },
  cardFrame: { flex: 1, maxWidth: '100%' },
  composer: { paddingHorizontal: 12, paddingTop: 8, backgroundColor: C.paper, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line },
  quicks: { gap: 8, paddingBottom: 10, paddingHorizontal: 2 },
  chip: { backgroundColor: C.green50, borderWidth: StyleSheet.hairlineWidth, borderColor: C.green100, borderRadius: revaRadii.pill, paddingHorizontal: 13, paddingVertical: 7 },
  chipText: { fontSize: 13, fontWeight: '600', color: C.green600 },
  inputBar: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.surface, borderWidth: 1.5, borderColor: C.lineStrong, borderRadius: revaRadii.pill, paddingLeft: 16, paddingRight: 6, paddingVertical: 6 },
  input: { flex: 1, fontSize: 15, color: C.ink1, paddingVertical: Platform.OS === 'ios' ? 6 : 2 },
  send: { width: 38, height: 38, borderRadius: 19, backgroundColor: C.green500, alignItems: 'center', justifyContent: 'center' },
  sendDisabled: { backgroundColor: C.green300 },
});

const mdStyles = {
  body: { color: C.ink1, fontSize: 15, lineHeight: 23 },
  paragraph: { marginTop: 0, marginBottom: 8 },
  heading2: { fontSize: 16, fontWeight: '700' as const, color: C.ink1, marginTop: 6, marginBottom: 4 },
  heading3: { fontSize: 15, fontWeight: '700' as const, color: C.ink1, marginTop: 6, marginBottom: 4 },
  strong: { fontWeight: '700' as const, color: C.ink1 },
  bullet_list: { marginBottom: 4 },
  list_item: { marginBottom: 2 },
  code_inline: { backgroundColor: C.paper2, color: C.ink1, fontFamily: 'IBMPlexMono' },
};
