import React from 'react';
import {
  View, Text, Modal, Pressable, ScrollView, TouchableOpacity,
  StyleSheet, Alert, ActivityIndicator,
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
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={e => e.stopPropagation()}>
          <View style={styles.handle} />
          <Text style={styles.title}>对话历史</Text>
          {conversations.length === 0 ? (
            <View style={styles.loadingWrap}>
              <ActivityIndicator size="small" color={colors.brand} />
              <Text style={styles.loadingText}>加载中...</Text>
            </View>
          ) : (
            <ScrollView style={{ maxHeight: 400 }} showsVerticalScrollIndicator={false}>
              {conversations.slice(0, 20).map((item: any) => (
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
                      {item.created_at?.slice(0, 10) || ''}
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
  sheet: {
    backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingHorizontal: spacing.xl, paddingBottom: 40, paddingTop: 8,
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
