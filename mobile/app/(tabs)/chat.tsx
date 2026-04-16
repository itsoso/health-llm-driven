import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { streamChat, type ChatMessage } from '@/services/chat';

interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
}

let msgCounter = 0;
function nextId(): string {
  return `msg-${++msgCounter}-${Date.now()}`;
}

export default function ChatScreen() {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const flatListRef = useRef<FlatList>(null);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput('');
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: text };
    const assistantId = nextId();
    const assistantMsg: UIMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      streaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      for await (const token of streamChat(text)) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: m.content + token }
              : m,
          ),
        );
      }
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: m.content || `[错误] ${err?.message || '请求失败'}` }
            : m,
        ),
      );
    } finally {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, streaming: false } : m,
        ),
      );
      setIsStreaming(false);
    }
  }, [input, isStreaming]);

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const isUser = item.role === 'user';
    return (
      <View
        style={[
          styles.msgRow,
          isUser ? styles.msgRowUser : styles.msgRowAssistant,
        ]}
      >
        {!isUser && (
          <View style={styles.avatar}>
            <Ionicons name="sparkles" size={16} color="#007AFF" />
          </View>
        )}
        <View
          style={[
            styles.bubble,
            isUser ? styles.bubbleUser : styles.bubbleAssistant,
          ]}
        >
          <Text
            style={[
              styles.bubbleText,
              isUser ? styles.bubbleTextUser : styles.bubbleTextAssistant,
            ]}
          >
            {item.content}
            {item.streaming && !item.content ? '' : ''}
          </Text>
          {item.streaming && (
            <ActivityIndicator
              size="small"
              color="#007AFF"
              style={styles.streamingDot}
            />
          )}
        </View>
      </View>
    );
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={90}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          inverted={false}
          onContentSizeChange={() =>
            flatListRef.current?.scrollToEnd({ animated: true })
          }
          ListEmptyComponent={
            <View style={styles.emptyChat}>
              <View style={styles.emptyChatCircle}>
                <Ionicons name="chatbubble-ellipses" size={40} color="#007AFF" />
              </View>
              <Text style={styles.emptyChatTitle}>AI 健康助理</Text>
              <Text style={styles.emptyChatSubtitle}>
                问我任何健康相关的问题
              </Text>
              <View style={styles.suggestions}>
                {SUGGESTIONS.map((s) => (
                  <TouchableOpacity
                    key={s}
                    style={styles.suggestionChip}
                    onPress={() => {
                      setInput(s);
                    }}
                  >
                    <Text style={styles.suggestionText}>{s}</Text>
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
            placeholderTextColor="#C7C7CC"
            value={input}
            onChangeText={setInput}
            onSubmitEditing={sendMessage}
            returnKeyType="send"
            multiline
            maxLength={2000}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!input.trim() || isStreaming) && styles.sendBtnDisabled]}
            onPress={sendMessage}
            disabled={!input.trim() || isStreaming}
          >
            <Ionicons
              name="arrow-up-circle"
              size={32}
              color={input.trim() && !isStreaming ? '#007AFF' : '#C7C7CC'}
            />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const SUGGESTIONS = [
  '今天的健康状况如何？',
  '我的睡眠质量怎么样？',
  '给我一些运动建议',
  '分析我最近的HRV趋势',
];

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FDFBF7' },
  container: { flex: 1 },
  messageList: { padding: 16, paddingBottom: 8 },
  msgRow: { flexDirection: 'row', marginBottom: 12, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAssistant: { justifyContent: 'flex-start' },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#E8F0FE',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  bubble: {
    maxWidth: '78%',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  bubbleUser: {
    backgroundColor: '#007AFF',
    borderBottomRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: '#fff',
    borderBottomLeftRadius: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  bubbleText: { fontSize: 15, lineHeight: 22 },
  bubbleTextUser: { color: '#fff' },
  bubbleTextAssistant: { color: '#1C1C1E' },
  streamingDot: { marginTop: 4, alignSelf: 'flex-start' },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: 0.5,
    borderTopColor: '#E5E5EA',
    backgroundColor: '#FDFBF7',
    gap: 8,
  },
  textInput: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 10,
    fontSize: 15,
    maxHeight: 100,
    borderWidth: 1,
    borderColor: '#E5E5EA',
    color: '#1C1C1E',
  },
  sendBtn: { padding: 2 },
  sendBtnDisabled: { opacity: 0.5 },
  emptyChat: { alignItems: 'center', paddingTop: 80 },
  emptyChatCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#E8F0FE',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  emptyChatTitle: { fontSize: 20, fontWeight: '700', color: '#1C1C1E' },
  emptyChatSubtitle: { fontSize: 14, color: '#8E8E93', marginTop: 4 },
  suggestions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 8,
    marginTop: 24,
    paddingHorizontal: 16,
  },
  suggestionChip: {
    backgroundColor: '#fff',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#E5E5EA',
  },
  suggestionText: { fontSize: 13, color: '#007AFF', fontWeight: '500' },
});
