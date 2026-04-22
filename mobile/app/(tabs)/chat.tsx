import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, TextStyle, Image,
  Alert, Keyboard, Modal, Pressable, Dimensions,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import Markdown from 'react-native-markdown-display';
import { deleteConversation } from '@/services/chat';
import { useChatEngine, type UIMessage } from '@/hooks/useChatEngine';
import ChatInputBar from '@/components/chat/ChatInputBar';
import { renderCard } from '@/components/chat/cards';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function BrandCircle({ size, children, style }: { size: number; children: React.ReactNode; style?: any }) {
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }, style]}>
      {children}
    </View>
  );
}

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

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const isUser = item.role === 'user';
    if (item.cardType && item.cardData) {
      const rendered = renderCard({ type: item.cardType, data: item.cardData });
      if (rendered) return <View style={[styles.msgRow, styles.msgRowAI]}><View style={{ width: 36 }} />{rendered}</View>;
    }
    const displayText = item.content.replace(/\n?\[附图: [^\]]+\]/g, '').trim();
    const images = item.imageUris;
    return (
      <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
        {!isUser && <BrandCircle size={30} style={{ marginRight: 8 }}><Ionicons name="sparkles" size={14} color="#fff" /></BrandCircle>}
        {isUser ? (
          <TouchableOpacity style={[styles.bubble, styles.bubbleUser]} activeOpacity={0.8}
            onLongPress={() => { Clipboard.setStringAsync(item.content); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('已复制'); }}>
            {images && images.length > 0 && (
              <View style={styles.imageGrid}>
                {images.map((uri, i) => (
                  <TouchableOpacity key={i} onPress={() => setViewingImage(uri)} activeOpacity={0.85}>
                    <Image source={{ uri }} style={images.length === 1 ? styles.msgImageSingle : styles.msgImageGrid} resizeMode="cover" />
                  </TouchableOpacity>
                ))}
              </View>
            )}
            {displayText ? <Text selectable style={txt.bubbleUser}>{displayText}</Text> : null}
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[styles.bubble, styles.bubbleAI]} activeOpacity={0.8}
            onLongPress={() => { Clipboard.setStringAsync(item.content); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('已复制'); }}>
            <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
            {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 6, alignSelf: 'flex-start' }} />}
          </TouchableOpacity>
        )}
      </View>
    );
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Ionicons name="sparkles" size={18} color={colors.brand} />
        <Text style={txt.headerTitle}>AI 健康助理</Text>
        <View style={{ flex: 1 }} />
        <TouchableOpacity onPress={chat.newChat} hitSlop={8}>
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
          }} hitSlop={8} style={{ marginLeft: 12 }}>
            <Ionicons name="trash-outline" size={18} color={colors.red} />
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={90}>
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

        <ChatInputBar onSend={handleSend} isStreaming={chat.isStreaming} />
        {!keyboardVisible && <View style={{ height: 83 }} />}
      </KeyboardAvoidingView>

      <Modal visible={!!viewingImage} transparent animationType="fade" onRequestClose={() => setViewingImage(null)}>
        <Pressable style={styles.imageViewerOverlay} onPress={() => setViewingImage(null)}>
          {viewingImage && (
            <Image source={{ uri: viewingImage }} style={styles.imageViewerImage} resizeMode="contain" />
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
  msgRow: { flexDirection: 'row', marginBottom: spacing.md, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '80%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleUser: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  bubbleAI: { backgroundColor: '#fff', borderBottomLeftRadius: 4, ...shadows.subtle },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
  msgImageSingle: { width: 160, height: 120, borderRadius: 10 },
  msgImageGrid: { width: 72, height: 72, borderRadius: 8 },
  imageViewerOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center', alignItems: 'center',
  },
  imageViewerImage: {
    width: Dimensions.get('window').width - 32,
    height: Dimensions.get('window').height * 0.7,
  },
  imageViewerClose: { position: 'absolute', top: 60, right: 20 },
  welcome: { alignItems: 'center', paddingTop: 60 },
  sugGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xxl, paddingHorizontal: spacing.lg },
  sugCard: {
    width: '47%', backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, gap: 6, ...shadows.subtle,
  },
});

const txt = {
  headerTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  welcomeTitle: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4, textAlign: 'center' } as TextStyle,
  sugText: { fontSize: 13, color: colors.labelPrimary, lineHeight: 18 } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 22, color: colors.labelPrimary },
  heading2: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, marginTop: 6, marginBottom: 4 },
  heading3: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 4, marginBottom: 2 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 4 },
  list_item: { flexDirection: 'row', marginVertical: 2 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 4, fontFamily: 'Menlo', fontSize: 13, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 8, padding: 10, fontFamily: 'Menlo', fontSize: 13, marginVertical: 6 },
  paragraph: { marginVertical: 2 },
  link: { color: colors.brand },
});
