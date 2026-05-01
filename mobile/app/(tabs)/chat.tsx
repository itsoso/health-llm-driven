import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, TextStyle,
  Alert, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router } from 'expo-router';
import { deleteConversation } from '../../services/chat';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import ChatInputBar from '../../components/chat/ChatInputBar';
import BrandCircle from '../../components/chat/BrandCircle';
import ChatBubble from '../../components/chat/ChatBubble';
import { colors, spacing, radii, shadows } from '../../constants/theme';

const SUGGESTIONS = [
  { icon: 'pulse-outline' as const, text: '今天的健康状况如何？' },
  { icon: 'moon-outline' as const, text: '分析我的睡眠质量' },
  { icon: 'fitness-outline' as const, text: '给我运动建议' },
  { icon: 'trending-up-outline' as const, text: 'HRV趋势分析' },
];

export default function ChatScreen() {
  const chat = useChatEngine();
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [viewingImage, setViewingImage] = useState<string | null>(null);

  // Context from alert / push deep-link. Read ONCE on first mount, then cleared so
  // subsequent navigations to this tab don't keep re-prefilling the input.
  const params = useLocalSearchParams<{ prompt?: string; badge?: string }>();
  const [contextBadge, setContextBadge] = useState<string | null>(null);
  const [initialInput, setInitialInput] = useState<string | undefined>(undefined);
  const contextConsumed = useRef(false);

  useEffect(() => {
    if (contextConsumed.current) return;
    if (params.prompt || params.badge) {
      contextConsumed.current = true;
      if (params.prompt) setInitialInput(params.prompt);
      if (params.badge) setContextBadge(params.badge);
      // Clear the URL params so refresh / re-focus don't repopulate
      try { router.setParams({ prompt: undefined, badge: undefined } as any); } catch {}
    }
  }, [params.prompt, params.badge]);

  useEffect(() => { chat.loadLatestConversation(); }, []);

  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => {
      setKeyboardVisible(true);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  const handleSend = useCallback((text: string, images?: any) => {
    chat.sendMessage(text, images);
  }, [chat.sendMessage]);

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => (
    <ChatBubble item={item} onViewImage={setViewingImage} />
  ), []);

  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const kbOffset = Platform.OS === 'ios' ? 49 + insets.bottom : 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Ionicons name="sparkles" size={18} color={colors.brand} />
        <Text style={txt.headerTitle}>AI 健康助理</Text>
        <View style={{ flex: 1 }} />
        <TouchableOpacity onPress={chat.newChat} hitSlop={8} accessibilityLabel="新建对话" accessibilityRole="button">
          <Ionicons name="create-outline" size={20} color={colors.labelSecondary} />
        </TouchableOpacity>
        {chat.conversationId && chat.messages.length > 0 && (
          <TouchableOpacity onPress={() => {
            Alert.alert('删除对话', '确定删除当前对话？', [
              { text: '取消', style: 'cancel' },
              { text: '删除', style: 'destructive', onPress: async () => {
                await deleteConversation(chat.conversationId!);
                chat.newChat();
              }},
            ]);
          }} hitSlop={8} style={{ marginLeft: 12 }} accessibilityLabel="删除当前对话" accessibilityRole="button">
            <Ionicons name="trash-outline" size={18} color={colors.red} />
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={kbOffset}>
        <FlatList
          ref={flatListRef}
          data={chat.messages}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => { if (isNearBottom.current) flatListRef.current?.scrollToEnd({ animated: true }); }}
          onScroll={(e) => { const { layoutMeasurement, contentOffset, contentSize } = e.nativeEvent; isNearBottom.current = contentSize.height - contentOffset.y - layoutMeasurement.height < 120; }}
          scrollEventThrottle={100}
          ListEmptyComponent={
            <View style={styles.welcome}>
              <BrandCircle size={72} style={{ marginBottom: 16 }}>
                <Ionicons name="sparkles" size={32} color="#fff" />
              </BrandCircle>
              <Text style={txt.welcomeTitle}>AI 健康助理</Text>
              <Text style={txt.welcomeSub}>我可以帮你分析数据、解答疑问、提供建议</Text>
              <View style={styles.sugGrid}>
                {SUGGESTIONS.map(s => (
                  <TouchableOpacity key={s.text} style={styles.sugCard} onPress={() => handleSend(s.text, null)} activeOpacity={0.7}>
                    <Ionicons name={s.icon} size={18} color={colors.brand} />
                    <Text style={txt.sugText}>{s.text}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          }
        />

        {contextBadge && (
          <View style={styles.contextBanner}>
            <Ionicons name="link-outline" size={13} color={colors.brand} />
            <Text style={txt.contextBanner} numberOfLines={1}>
              基于 {contextBadge}
            </Text>
            <TouchableOpacity onPress={() => setContextBadge(null)} hitSlop={8}>
              <Ionicons name="close" size={14} color={colors.labelTertiary} />
            </TouchableOpacity>
          </View>
        )}

        <ChatInputBar onSend={handleSend} isStreaming={chat.isStreaming} initialText={initialInput} />
        {!keyboardVisible && <View style={{ height: 83 }} />}
      </KeyboardAvoidingView>

      <Modal visible={!!viewingImage} transparent animationType="fade" onRequestClose={() => setViewingImage(null)}>
        <Pressable style={styles.imageViewerOverlay} onPress={() => setViewingImage(null)}>
          {viewingImage && (
            <Image source={{ uri: viewingImage }} style={{ width: windowWidth - 32, height: windowHeight * 0.7 }} contentFit="contain" />
          )}
          <TouchableOpacity style={styles.imageViewerClose} onPress={() => setViewingImage(null)}>
            <Ionicons name="close-circle" size={32} color="#fff" />
          </TouchableOpacity>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  messageList: { padding: spacing.lg, paddingBottom: 8 },
  imageViewerOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center', alignItems: 'center',
  },
  imageViewerClose: { position: 'absolute', top: 60, right: 20 },
  welcome: { alignItems: 'center', paddingTop: 60 },
  sugGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xxl, paddingHorizontal: spacing.lg },
  sugCard: {
    width: '47%', backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, gap: 6, ...shadows.subtle,
  },
  contextBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginHorizontal: spacing.lg, marginBottom: 4,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    backgroundColor: colors.brandLight, borderRadius: radii.md,
  },
});

const txt = {
  headerTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  welcomeTitle: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4, textAlign: 'center' } as TextStyle,
  sugText: { fontSize: 13, color: colors.labelPrimary, lineHeight: 18 } as TextStyle,
  contextBanner: { fontSize: 12, color: colors.brand, flex: 1, fontWeight: '500' } as TextStyle,
};
