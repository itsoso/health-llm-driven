import React, { useState, useRef, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import Markdown from 'react-native-markdown-display';
import { streamChat, type ChatMessage } from '@/services/chat';
import { colors, spacing, radii, shadows } from '@/constants/theme';

// Gradient-like colored view (avoids expo-linear-gradient native module issues)
function BrandCircle({ size, children, style }: { size: number; children: React.ReactNode; style?: any }) {
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }, style]}>
      {children}
    </View>
  );
}

interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
}

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }

const SUGGESTIONS = [
  { icon: 'pulse-outline' as const, text: '今天的健康状况如何？' },
  { icon: 'moon-outline' as const, text: '分析我的睡眠质量' },
  { icon: 'fitness-outline' as const, text: '给我运动建议' },
  { icon: 'trending-up-outline' as const, text: 'HRV趋势分析' },
];

export default function ChatScreen() {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const flatListRef = useRef<FlatList>(null);

  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || isStreaming) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    setInput('');
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: msg };
    const assistantId = nextId();
    const assistantMsg: UIMessage = { id: assistantId, role: 'assistant', content: '', streaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      for await (const token of streamChat(msg)) {
        setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: m.content + token } : m));
      }
    } catch (err: any) {
      setMessages(prev => prev.map(m =>
        m.id === assistantId ? { ...m, content: m.content || `[错误] ${err?.message || '请求失败'}` } : m
      ));
    } finally {
      setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, streaming: false } : m));
      setIsStreaming(false);
    }
  }, [input, isStreaming]);

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
        {!isUser && (
          <BrandCircle size={30} style={{ marginRight: 8 }}>
            <Ionicons name="sparkles" size={14} color="#fff" />
          </BrandCircle>
        )}
        {isUser ? (
          <View style={[styles.bubble, styles.bubbleUser, { backgroundColor: colors.brand }]}>
            <Text style={txt.bubbleUser}>{item.content}</Text>
          </View>
        ) : (
          <View style={[styles.bubble, styles.bubbleAI]}>
            <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
            {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 6, alignSelf: 'flex-start' }} />}
          </View>
        )}
      </View>
    );
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Ionicons name="sparkles" size={18} color={colors.brand} />
        <Text style={txt.headerTitle}>AI 健康助理</Text>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={90}>
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
          ListEmptyComponent={
            <View style={styles.welcome}>
              <BrandCircle size={72} style={{ marginBottom: 16 }}>
                <Ionicons name="sparkles" size={32} color="#fff" />
              </BrandCircle>
              <Text style={txt.welcomeTitle}>AI 健康助理</Text>
              <Text style={txt.welcomeSub}>我可以帮你分析数据、解答疑问、提供建议</Text>
              <View style={styles.sugGrid}>
                {SUGGESTIONS.map(s => (
                  <TouchableOpacity key={s.text} style={styles.sugCard} onPress={() => sendMessage(s.text)} activeOpacity={0.7}>
                    <Ionicons name={s.icon} size={18} color={colors.brand} />
                    <Text style={txt.sugText}>{s.text}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          }
        />
        <View style={styles.inputBar}>
          <TextInput
            style={styles.textInput}
            placeholder="输入消息..."
            placeholderTextColor={colors.labelTertiary}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => sendMessage()}
            returnKeyType="send"
            multiline
            maxLength={2000}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!input.trim() || isStreaming) && { opacity: 0.4 }]}
            onPress={() => sendMessage()}
            disabled={!input.trim() || isStreaming}
          >
            <BrandCircle size={34}>
              <Ionicons name="arrow-up" size={18} color="#fff" />
            </BrandCircle>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  messageList: { padding: spacing.lg, paddingBottom: 8 },
  msgRow: { flexDirection: 'row', marginBottom: spacing.md, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  avatar: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  bubble: { maxWidth: '78%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleUser: { borderBottomRightRadius: 4 },
  bubbleAI: { backgroundColor: '#fff', borderBottomLeftRadius: 4, ...shadows.subtle },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderTopWidth: 0.5, borderTopColor: colors.separator,
    backgroundColor: colors.bgPrimary, paddingBottom: 8,
  },
  textInput: {
    flex: 1, backgroundColor: colors.bgCard, borderRadius: 22,
    paddingHorizontal: 16, paddingTop: 10, paddingBottom: 10,
    fontSize: 15, maxHeight: 100, color: colors.labelPrimary,
    borderWidth: 1, borderColor: colors.separator,
  },
  sendBtn: { padding: 2 },
  sendCircle: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  welcome: { alignItems: 'center', paddingTop: 60 },
  welcomeCircle: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  sugGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xxl, paddingHorizontal: spacing.lg },
  sugCard: {
    width: '47%', backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, gap: 6, ...shadows.subtle,
  },
});

const txt = {
  headerTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  bubbleAI: { fontSize: 15, lineHeight: 22, color: colors.labelPrimary } as TextStyle,
  welcomeTitle: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4, textAlign: 'center' } as TextStyle,
  sugText: { fontSize: 13, color: colors.labelPrimary, lineHeight: 18 } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 22, color: colors.labelPrimary },
  heading1: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary, marginTop: 8, marginBottom: 4 },
  heading2: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, marginTop: 6, marginBottom: 4 },
  heading3: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 4, marginBottom: 2 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 4 },
  ordered_list: { marginVertical: 4 },
  list_item: { flexDirection: 'row', marginVertical: 2 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 4, fontFamily: 'Menlo', fontSize: 13, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 8, padding: 10, fontFamily: 'Menlo', fontSize: 13, marginVertical: 6 },
  code_block: { backgroundColor: '#F2F2F7', borderRadius: 8, padding: 10, fontFamily: 'Menlo', fontSize: 13, marginVertical: 6 },
  blockquote: { borderLeftWidth: 3, borderLeftColor: colors.brand, paddingLeft: 10, marginVertical: 4, opacity: 0.8 },
  hr: { backgroundColor: colors.separator, height: 1, marginVertical: 8 },
  paragraph: { marginVertical: 2 },
  link: { color: colors.brand },
  table: { borderWidth: 0.5, borderColor: colors.separator, borderRadius: 6, marginVertical: 6 },
  th: { padding: 6, fontWeight: '600', backgroundColor: '#F2F2F7' },
  td: { padding: 6 },
  tr: { borderBottomWidth: 0.5, borderColor: colors.separator },
});
