import React from 'react';
import {
  View, Text, Modal, Pressable, ScrollView, TouchableOpacity,
  StyleSheet, Alert, ActivityIndicator, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getConversations, deleteConversation } from '@/services/chat';
import { colors, spacing, radii } from '@/constants/theme';

interface Props {
  visible: boolean;
  onClose: () => void;
  conversations: any[];
  setConversations: React.Dispatch<React.SetStateAction<any[]>>;
  currentConversationId?: number;
  onSelectConversation: (id: number) => void;
  onDeleteConversation: (id: number) => void;
}

export default function ConversationSheet({
  visible, onClose, conversations, setConversations,
  currentConversationId, onSelectConversation, onDeleteConversation,
}: Props) {
  const { height: screenH, width: screenW } = useWindowDimensions();
  const isTablet = screenW >= 768;
  // iPhone: 列表占屏幕 70%; iPad: 占 75% 但封顶 800
  const listMaxHeight = isTablet
    ? Math.min(screenH * 0.75, 800)
    : screenH * 0.7;
  // 单列宽度: iPad 居中并限宽, 让列表别撑满 13 寸屏
  const sheetMaxWidth = isTablet ? 560 : undefined;
  const titleOf = (c: any) => (c?.title || '').trim();
  const isBriefing = (t: string) => t === '每日健康简报' || t.startsWith('每日健康简报 ');
  const isWeekly = (t: string) => t === '每周健康周报' || t.startsWith('每周健康周报 ');
  const isPinned = (t: string) => isBriefing(t) || isWeekly(t);
  const byNewest = (a: any, b: any) =>
    ((b.updated_at || b.created_at || '') as string).localeCompare(
      (a.updated_at || a.created_at || '') as string,
    );
  const sortedConversations = [
    ...conversations.filter((c: any) => isBriefing(titleOf(c))).sort(byNewest),
    ...conversations.filter((c: any) => isWeekly(titleOf(c))).sort(byNewest),
    ...conversations.filter((c: any) => !isPinned(titleOf(c))),
  ];
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.overlay, isTablet && styles.overlayTablet]} onPress={onClose}>
        <Pressable
          style={[
            styles.sheet,
            isTablet && styles.sheetTablet,
            sheetMaxWidth ? { maxWidth: sheetMaxWidth, width: '100%' } : null,
          ]}
          onPress={e => e.stopPropagation()}
        >
          <View style={styles.handle} />
          <Text style={styles.title}>对话历史</Text>
          {conversations.length === 0 ? (
            <View style={styles.loadingWrap}>
              <ActivityIndicator size="small" color={colors.brand} />
              <Text style={styles.loadingText}>加载中...</Text>
            </View>
          ) : (
            <ScrollView style={{ maxHeight: listMaxHeight }} showsVerticalScrollIndicator={false}>
              {sortedConversations.slice(0, 20).map((item: any) => (
                <TouchableOpacity
                  key={item.id}
                  style={styles.row}
                  onPress={() => { onClose(); onSelectConversation(item.id); }}
                  activeOpacity={0.6}
                  accessibilityRole="button"
                  accessibilityLabel={`对话: ${item.title || `对话 #${item.id}`}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle} numberOfLines={1}>
                      {item.title || `对话 #${item.id}`}
                    </Text>
                    <Text style={styles.rowDate}>
                      {(item.updated_at || item.created_at)?.slice(0, 10) || ''}
                    </Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => {
                      Alert.alert('删除对话', `确定删除「${item.title || '对话'}」？`, [
                        { text: '取消', style: 'cancel' },
                        { text: '删除', style: 'destructive', onPress: () => onDeleteConversation(item.id) },
                      ]);
                    }}
                    hitSlop={8} style={{ padding: 8 }}
                    accessibilityRole="button"
                    accessibilityLabel="删除对话"
                  >
                    <Ionicons name="trash-outline" size={16} color={colors.red} />
                  </TouchableOpacity>
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'flex-end' },
  overlayTablet: { justifyContent: 'center', alignItems: 'center' },
  sheet: {
    backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingHorizontal: spacing.xl, paddingBottom: 40, paddingTop: 8,
  },
  sheetTablet: {
    borderRadius: 20, paddingBottom: spacing.xl,
  },
  handle: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: colors.labelQuaternary,
    alignSelf: 'center', marginBottom: spacing.lg,
  },
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, marginBottom: 12 },
  loadingWrap: { alignItems: 'center', paddingVertical: 20, gap: 8 },
  loadingText: { fontSize: 14, color: colors.labelTertiary },
  row: {
    paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator, flexDirection: 'row', alignItems: 'center',
  },
  rowTitle: { fontSize: 15, color: colors.labelPrimary },
  rowDate: { fontSize: 12, color: colors.labelTertiary, marginTop: 2 },
});
