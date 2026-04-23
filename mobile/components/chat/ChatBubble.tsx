import React from 'react';
import {
  View, Text, TouchableOpacity, Image, StyleSheet, TextStyle,
  Alert, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import Markdown from 'react-native-markdown-display';
import BrandCircle from './BrandCircle';
import { renderCard } from './cards';
import { mdStylesChat } from '@/constants/markdownStyles';
import type { UIMessage } from '@/hooks/useChatEngine';
import { colors, shadows } from '@/constants/theme';

interface Props {
  item: UIMessage;
  onViewImage?: (uri: string) => void;
}

function ChatBubbleInner({ item, onViewImage }: Props) {
  const isUser = item.role === 'user';

  if (item.cardType && item.cardData) {
    const rendered = renderCard({ type: item.cardType, data: item.cardData });
    if (rendered) return <View style={[styles.msgRow, styles.msgRowAI]}><View style={{ width: 36 }} />{rendered}</View>;
  }

  const displayText = item.content.replace(/\n?\[附图: [^\]]+\]/g, '').trim();
  const images = item.imageUris;

  const handleCopy = () => {
    Clipboard.setStringAsync(item.content);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    Alert.alert('已复制');
  };

  return (
    <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
      {!isUser && (
        <BrandCircle size={28} style={{ marginRight: 8 }}>
          <Ionicons name="sparkles" size={12} color="#fff" />
        </BrandCircle>
      )}
      {isUser ? (
        <TouchableOpacity
          style={[styles.bubble, styles.bubbleUser]}
          activeOpacity={0.8}
          onLongPress={handleCopy}
          accessibilityRole="text"
          accessibilityLabel={`你: ${item.content}`}
        >
          {images && images.length > 0 && (
            <View style={styles.imageGrid}>
              {images.map((uri, i) => (
                <TouchableOpacity key={i} onPress={() => onViewImage?.(uri)} activeOpacity={0.85}>
                  <Image
                    source={{ uri }}
                    style={images.length === 1 ? styles.msgImageSingle : styles.msgImageGrid}
                    resizeMode="cover"
                  />
                </TouchableOpacity>
              ))}
            </View>
          )}
          {displayText ? <Text selectable style={txt.bubbleUser}>{displayText}</Text> : null}
        </TouchableOpacity>
      ) : (
        <TouchableOpacity
          style={[styles.bubble, styles.bubbleAI]}
          activeOpacity={0.8}
          onLongPress={handleCopy}
          accessibilityRole="text"
          accessibilityLabel={`AI: ${item.content}`}
        >
          <Markdown style={mdStylesChat}>{item.content || ' '}</Markdown>
          {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 4 }} />}
        </TouchableOpacity>
      )}
    </View>
  );
}

const ChatBubble = React.memo(ChatBubbleInner);
export default ChatBubble;

const styles = StyleSheet.create({
  msgRow: { flexDirection: 'row', marginBottom: 10, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '80%', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8 },
  bubbleUser: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  bubbleAI: { backgroundColor: '#fff', borderBottomLeftRadius: 4, ...shadows.subtle },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
  msgImageSingle: { width: 160, height: 120, borderRadius: 10 },
  msgImageGrid: { width: 72, height: 72, borderRadius: 8 },
});

const txt = {
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
};
