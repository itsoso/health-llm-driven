import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, TextStyle,
  Alert, ActivityIndicator, ScrollView, Pressable,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import Markdown from 'react-native-markdown-display';
import BrandCircle from './BrandCircle';
import { renderCard } from './cards';
import InterventionDraftSheet from '@/components/actions/InterventionDraftSheet';
import { mdStylesChat } from '@/constants/markdownStyles';
import type { UIMessage } from '@/hooks/useChatEngine';
import { invalidateQueryKeys, queryKeys } from '@/lib/queryKeys';
import { createInterventionDraft } from '@/services/actionCards';
import { buildInterventionDraft, type InterventionDraft } from '@/services/interventionDraft';
import { colors, radii, shadows } from '@/constants/theme';

interface Props {
  item: UIMessage;
  onViewImage?: (uri: string) => void;
}

function ChatBubbleInner({ item, onViewImage }: Props) {
  const qc = useQueryClient();
  const isUser = item.role === 'user';
  const [draft, setDraft] = useState<InterventionDraft | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);

  if (item.cardType && item.cardData) {
    const rendered = renderCard({ type: item.cardType, data: item.cardData });
    if (rendered) return <View style={[styles.msgRow, styles.msgRowAI]}><View style={{ width: 36 }} />{rendered}</View>;
  }

  const displayText = item.content.replace(/\n?\[附图: [^\]]+\]/g, '').trim();
  const images = item.imageUris;
  const hasTable = !isUser && /\n\s*\|.+\|\s*\n\s*\|[\s|:\-]+\|/.test(displayText);

  const handleCopy = () => {
    Clipboard.setStringAsync(item.content);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    Alert.alert('已复制');
  };

  const openDraft = () => {
    setDraft(buildInterventionDraft({
      title: inferActionTitle(displayText),
      advice: displayText,
      sourceType: 'chat',
      sourceId: item.id,
    }));
  };

  const submitDraft = async (nextDraft: InterventionDraft) => {
    setSavingDraft(true);
    try {
      await createInterventionDraft(nextDraft);
      await invalidateQueryKeys(qc, [
        queryKeys.actionCards,
        queryKeys.todayCoachRoot,
        queryKeys.agentAgendaRoot,
      ]);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setDraft(null);
      Alert.alert('已加入行动', '可以在行动页继续跟踪和复盘。');
    } catch {
      Alert.alert('保存失败', '健康行动保存失败，请稍后重试。');
    } finally {
      setSavingDraft(false);
    }
  };

  return (
    <>
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
                      contentFit="cover"
                    />
                  </TouchableOpacity>
                ))}
              </View>
            )}
            {displayText ? <Text selectable style={txt.bubbleUser}>{displayText}</Text> : null}
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={[styles.bubble, styles.bubbleAI, hasTable && styles.bubbleAIWide]}
            activeOpacity={0.8}
            onLongPress={handleCopy}
            accessibilityRole="text"
            accessibilityLabel={`AI: ${item.content}`}
          >
            {hasTable ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ minWidth: '100%' }}>
                <Markdown style={mdStylesChat}>{item.content || ' '}</Markdown>
              </ScrollView>
            ) : (
              <Markdown style={mdStylesChat}>{item.content || ' '}</Markdown>
            )}
            {displayText ? (
              <Pressable
                style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                onPress={openDraft}
                accessibilityRole="button"
                accessibilityLabel="加入健康行动"
              >
                <Ionicons name="add-circle-outline" size={14} color={colors.brand} />
                <Text style={txt.actionBtn}>加入行动</Text>
              </Pressable>
            ) : null}
            {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 4 }} />}
          </TouchableOpacity>
        )}
      </View>
      <InterventionDraftSheet
        visible={!!draft}
        draft={draft}
        isSaving={savingDraft}
        onClose={() => setDraft(null)}
        onSubmit={submitDraft}
      />
    </>
  );
}

function inferActionTitle(text: string): string {
  const firstLine = text
    .split('\n')
    .map(line => line.replace(/^#+\s*/, '').replace(/^[-*]\s*/, '').trim())
    .find(Boolean);
  if (!firstLine) return '健康行动';
  return firstLine.length > 18 ? firstLine.slice(0, 18) : firstLine;
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
  bubbleAIWide: { maxWidth: '94%', flexShrink: 1, alignSelf: 'stretch' },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
  msgImageSingle: { width: 160, height: 120, borderRadius: 10 },
  msgImageGrid: { width: 72, height: 72, borderRadius: 8 },
  actionBtn: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 8,
    borderRadius: radii.full,
    backgroundColor: colors.brandLight,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  actionBtnPressed: { opacity: 0.82 },
});

const txt = {
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  actionBtn: { fontSize: 12, fontWeight: '700', color: colors.brand } as TextStyle,
};
