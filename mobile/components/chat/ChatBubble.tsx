import React, { useMemo, useState } from 'react';
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
import InterventionDraftSheet from '../actions/InterventionDraftSheet';
import { createMdStylesChat } from '../../constants/markdownStyles';
import type { UIMessage } from '../../hooks/useChatEngine';
import { invalidateQueryKeys, queryKeys } from '../../applib/queryKeys';
import { createInterventionDraft } from '../../services/actionCards';
import { buildInterventionDraft, type InterventionDraft } from '../../services/interventionDraft';
import { radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  item: UIMessage;
  onViewImage?: (uri: string) => void;
}

function ChatBubbleInner({ item, onViewImage }: Props) {
  const qc = useQueryClient();
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const mdStyles = useMemo(() => createMdStylesChat(c), [c]);
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
            accessibilityLabel={`你: ${item.content}${item.fromSiri ? ' (来自 Siri)' : ''}`}
          >
            {item.fromSiri && (
              <View style={styles.siriBadge} accessibilityLabel="来自 Siri">
                <Ionicons name="sparkles" size={11} color="#fff" />
              </View>
            )}
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
                <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
              </ScrollView>
            ) : (
              <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
            )}
            {displayText ? (
              <Pressable
                style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                onPress={openDraft}
                accessibilityRole="button"
                accessibilityLabel="加入健康行动"
              >
                <Ionicons name="add-circle-outline" size={14} color={c.brand} />
                <Text style={txt.actionBtn}>加入行动</Text>
              </Pressable>
            ) : null}
            {item.streaming && <ActivityIndicator size="small" color={c.brand} style={{ marginTop: 4 }} />}
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

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    msgRow: { flexDirection: 'row', marginBottom: 10, alignItems: 'flex-end' },
    msgRowUser: { justifyContent: 'flex-end' },
    msgRowAI: { justifyContent: 'flex-start' },
    bubble: { maxWidth: '80%', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8 },
    bubbleUser: { backgroundColor: c.brand, borderBottomRightRadius: 4 },
    siriBadge: {
      position: 'absolute',
      top: -6, right: -6,
      width: 18, height: 18, borderRadius: 9,
      backgroundColor: c.brand,
      borderWidth: 1.5, borderColor: c.bgPrimary,
      alignItems: 'center', justifyContent: 'center',
      zIndex: 2,
    },
    bubbleAI: {
      backgroundColor: c.bgCard, borderBottomLeftRadius: 4,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
          }),
    },
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
      backgroundColor: c.brandLight,
      paddingHorizontal: 10,
      paddingVertical: 6,
    },
    actionBtnPressed: { opacity: 0.82 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
    actionBtn: { fontSize: 12, fontWeight: '700', color: c.brand } as TextStyle,
  };
}
