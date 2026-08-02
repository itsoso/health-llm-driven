import React, { useState } from 'react';
import {
  View, Text, Modal, Pressable, FlatList, TouchableOpacity,
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
  /** 无限下拉分页 */
  hasMore?: boolean;
  loadingMore?: boolean;
  loadMoreError?: boolean;
  onLoadMore?: () => void;
  /** 后端返回的总条数 (决定是否显示 "没有更多了" footer) */
  total?: number;
  /** 受控搜索框(按标题+内容);父层拿到值后 debounce 重拉。 */
  searchValue?: string;
  onSearchChange?: (value: string) => void;
}

export default function ConversationSheet({
  visible, onClose, conversations, setConversations,
  currentConversationId, onSelectConversation, onDeleteConversation,
  onRenameConversation, loading, error, onRetry,
  hasMore, loadingMore, loadMoreError, onLoadMore, total,
  searchValue, onSearchChange,
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
          {onSearchChange && (
            <View style={styles.searchWrap}>
              <Ionicons name="search-outline" size={16} color={C.ink3} style={styles.searchIcon} />
              <TextInput
                accessibilityLabel="搜索对话"
                value={searchValue ?? ''}
                onChangeText={onSearchChange}
                style={styles.searchInput}
                placeholder="搜索标题或内容"
                placeholderTextColor={C.ink3}
                returnKeyType="search"
                autoCorrect={false}
              />
              {!!searchValue && (
                <TouchableOpacity
                  onPress={() => onSearchChange('')}
                  hitSlop={8}
                  accessibilityLabel="清除搜索"
                  style={styles.searchClear}
                >
                  <Ionicons name="close-circle" size={18} color={C.ink3} />
                </TouchableOpacity>
              )}
            </View>
          )}
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
              <Ionicons name={searchValue ? 'search-outline' : 'chatbubbles-outline'} size={28} color={C.ink3} />
              <Text style={styles.loadingText}>{searchValue ? '未找到匹配的对话' : '还没有历史对话'}</Text>
            </View>
          ) : (
            <FlatList
              style={{ maxHeight: listMaxHeight }}
              data={conversations}
              keyExtractor={(item: any) => String(item.id)}
              showsVerticalScrollIndicator={false}
              keyboardShouldPersistTaps="handled"
              onEndReachedThreshold={0.3}
              onEndReached={() => {
                // 还有更多 + 不在加载中 → 拉下一页。上层用 id 去重、按 total 收口。
                if (hasMore && !loadingMore && !loadMoreError) onLoadMore?.();
              }}
              renderItem={({ item }: { item: any }) => {
                const isEditing = editingId === item.id;
                return (
                  <View style={[styles.row, currentConversationId === item.id && styles.rowActive]}>
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
              }}
              ListFooterComponent={
                <ListFooter
                  loadingMore={loadingMore}
                  loadMoreError={loadMoreError}
                  hasMore={hasMore}
                  total={total}
                  onLoadMore={onLoadMore}
                />
              }
            />
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// 一页条数 (与 chat.tsx 的 HISTORY_PAGE_SIZE 对齐) — 仅用于决定
// "没有更多了" 是否值得显示 (总数超过一页才有翻页语义)。
const PAGE_SIZE_FOR_END_HINT = 20;

function ListFooter({
  loadingMore, loadMoreError, hasMore, total, onLoadMore,
}: {
  loadingMore?: boolean;
  loadMoreError?: boolean;
  hasMore?: boolean;
  total?: number;
  onLoadMore?: () => void;
}) {
  if (loadMoreError) {
    return (
      <TouchableOpacity
        onPress={onLoadMore}
        style={styles.footer}
        activeOpacity={0.7}
        accessibilityRole="button"
        accessibilityLabel="加载失败，点击重试"
      >
        <Ionicons name="reload-outline" size={16} color={revaSemantic.risk.fg} />
        <Text style={[styles.footerText, { color: revaSemantic.risk.fg }]}>加载失败，点击重试</Text>
      </TouchableOpacity>
    );
  }
  if (loadingMore) {
    return (
      <View style={styles.footer} accessibilityLabel="加载更多中">
        <ActivityIndicator size="small" color={C.green500} />
      </View>
    );
  }
  // 全部加载完 & 总数超过一页 → 提示到底
  if (!hasMore && (total ?? 0) > PAGE_SIZE_FOR_END_HINT) {
    return (
      <View style={styles.footer}>
        <Text style={styles.footerText}>没有更多了</Text>
      </View>
    );
  }
  return null;
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
  searchWrap: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.paper2, borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.line,
    paddingHorizontal: 10, marginBottom: 12, height: 40,
  },
  searchIcon: { marginRight: 6 },
  searchInput: { flex: 1, fontFamily: revaFonts.sans, fontSize: 15, color: C.ink1, paddingVertical: 0 },
  searchClear: { marginLeft: 6 },
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
  footer: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 16,
  },
  footerText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink3 },
});
