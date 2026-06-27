import React, { useState } from 'react';
import {
  View, Text, Modal, Pressable, ScrollView, TouchableOpacity,
  StyleSheet, Alert, ActivityIndicator, useWindowDimensions,
  TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

interface Props {
  visible: boolean;
  onClose: () => void;
  conversations: any[];
  setConversations: React.Dispatch<React.SetStateAction<any[]>>;
  currentConversationId?: number;
  onSelectConversation: (id: number) => void;
  onDeleteConversation: (id: number) => void;
  onRenameConversation?: (id: number, title: string) => Promise<void> | void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export default function ConversationSheet({
  visible, onClose, conversations, setConversations,
  currentConversationId, onSelectConversation, onDeleteConversation,
  onRenameConversation, loading, error, onRetry,
}: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [savingId, setSavingId] = useState<number | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
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

  const startRename = (item: any) => {
    setEditingId(item.id);
    setDraftTitle(item.title || '');
    setRenameError(null);
  };

  const cancelRename = () => {
    setEditingId(null);
    setDraftTitle('');
    setRenameError(null);
  };

  const saveRename = async (item: any) => {
    const title = draftTitle.trim();
    if (!title || savingId) return;
    setSavingId(item.id);
    setRenameError(null);
    try {
      await onRenameConversation?.(item.id, title);
      cancelRename();
    } catch {
      setRenameError('重命名失败，请稍后重试');
    } finally {
      setSavingId(null);
    }
  };

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
          {loading ? (
            <View style={styles.loadingWrap}>
              <ActivityIndicator size="small" color={C.green500} />
              <Text style={styles.loadingText}>加载中...</Text>
            </View>
          ) : error ? (
            <View style={styles.loadingWrap}>
              <Ionicons name="alert-circle-outline" size={28} color={revaSemantic.risk.fg} />
              <Text style={[styles.loadingText, { color: revaSemantic.risk.fg }]}>{error}</Text>
              {onRetry && (
                <TouchableOpacity onPress={onRetry} style={styles.retryBtn} activeOpacity={0.7}>
                  <Text style={styles.retryBtnText}>重试</Text>
                </TouchableOpacity>
              )}
            </View>
          ) : conversations.length === 0 ? (
            <View style={styles.loadingWrap}>
              <Ionicons name="chatbubbles-outline" size={28} color={C.ink3} />
              <Text style={styles.loadingText}>还没有历史对话</Text>
            </View>
          ) : (
            <ScrollView style={{ maxHeight: listMaxHeight }} showsVerticalScrollIndicator={false}>
              {sortedConversations.slice(0, 20).map((item: any) => {
                const isEditing = editingId === item.id;
                return (
                  <View key={item.id} style={[styles.row, currentConversationId === item.id && styles.rowActive]}>
                    {isEditing ? (
                      <View style={styles.editWrap}>
                        <TextInput
                          accessibilityLabel="对话标题"
                          value={draftTitle}
                          onChangeText={setDraftTitle}
                          autoFocus
                          editable={savingId !== item.id}
                          placeholder="输入标题"
                          placeholderTextColor={C.ink3}
                          returnKeyType="done"
                          onSubmitEditing={() => saveRename(item)}
                          style={styles.titleInput}
                        />
                        <TouchableOpacity
                          onPress={() => saveRename(item)}
                          disabled={!draftTitle.trim() || savingId === item.id}
                          hitSlop={8}
                          style={[styles.iconBtn, (!draftTitle.trim() || savingId === item.id) && styles.iconBtnDisabled]}
                          accessibilityRole="button"
                          accessibilityLabel="保存标题"
                        >
                          <Ionicons name="checkmark" size={18} color={C.green500} />
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={cancelRename}
                          hitSlop={8}
                          style={styles.iconBtn}
                          accessibilityRole="button"
                          accessibilityLabel="取消重命名"
                        >
                          <Ionicons name="close" size={18} color={C.ink2} />
                        </TouchableOpacity>
                        {!!renameError && <Text style={styles.renameError}>{renameError}</Text>}
                      </View>
                    ) : (
                      <>
                        <TouchableOpacity
                          style={styles.rowMain}
                          onPress={() => { onClose(); onSelectConversation(item.id); }}
                          activeOpacity={0.6}
                          accessibilityRole="button"
                          accessibilityLabel={`对话: ${item.title || `对话 #${item.id}`}`}
                        >
                          <Text style={styles.rowTitle} numberOfLines={1}>
                            {item.title || `对话 #${item.id}`}
                          </Text>
                          <Text style={styles.rowDate}>
                            {(item.updated_at || item.created_at)?.slice(0, 10) || ''}
                          </Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => startRename(item)}
                          hitSlop={8}
                          style={styles.iconBtn}
                          accessibilityRole="button"
                          accessibilityLabel="重命名对话"
                        >
                          <Ionicons name="pencil-outline" size={16} color={C.ink2} />
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => {
                            Alert.alert('删除对话', `确定删除「${item.title || '对话'}」？`, [
                              { text: '取消', style: 'cancel' },
                              { text: '删除', style: 'destructive', onPress: () => onDeleteConversation(item.id) },
                            ]);
                          }}
                          hitSlop={8} style={styles.iconBtn}
                          accessibilityRole="button"
                          accessibilityLabel="删除对话"
                        >
                          <Ionicons name="trash-outline" size={16} color={revaSemantic.risk.fg} />
                        </TouchableOpacity>
                      </>
                    )}
                  </View>
                );
              })}
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
    backgroundColor: C.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingHorizontal: revaSpacing.s5, paddingBottom: 40, paddingTop: 8,
  },
  sheetTablet: {
    borderRadius: 20, paddingBottom: revaSpacing.s5,
  },
  handle: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: C.ink4,
    alignSelf: 'center', marginBottom: revaSpacing.s4,
  },
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, marginBottom: 12 },
  loadingWrap: { alignItems: 'center', paddingVertical: 20, gap: 8 },
  loadingText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3 },
  row: {
    paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line, flexDirection: 'row', alignItems: 'center',
  },
  rowActive: { backgroundColor: C.green50 },
  rowMain: { flex: 1, minWidth: 0 },
  rowTitle: { fontFamily: revaFonts.sans, fontSize: 15, color: C.ink1 },
  rowDate: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3, marginTop: 2 },
  iconBtn: { padding: 8 },
  iconBtnDisabled: { opacity: 0.4 },
  editWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4, flexWrap: 'wrap' },
  titleInput: {
    flex: 1, minWidth: 140, minHeight: 36, paddingHorizontal: 10,
    paddingVertical: 6, borderRadius: revaRadii.sm, borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line, color: C.ink1, backgroundColor: C.paper,
    fontFamily: revaFonts.sans, fontSize: 15,
  },
  renameError: { fontFamily: revaFonts.sans, width: '100%', color: revaSemantic.risk.fg, fontSize: 12, marginTop: 2 },
  retryBtn: {
    marginTop: 8, paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: revaRadii.md, backgroundColor: C.green500,
  },
  retryBtnText: { fontFamily: revaFonts.sans, fontSize: 14, color: '#fff', fontWeight: '500' },
});
