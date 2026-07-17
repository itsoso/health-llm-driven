/**
 * ConversationShareImage —— 「选一段对话成图」的离屏渲染层。
 *
 * 把用户选中的消息渲染成一张干净的品牌长图(头部 + 气泡 + 页脚水印),供 captureRef
 * 截成 PNG 分享/存图。**不是**原始截屏 —— 是重排的分享图(类似微信/ChatGPT 对话分享)。
 * 在 chat.tsx 里以离屏方式挂载(绝对定位 + opacity 0),width 固定、height 随内容,
 * captureRef 能拿到完整高度(超屏也行)。
 */
import React, { forwardRef } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import MarkdownText from '../shared/MarkdownText';
import { revaColors as R } from '../../constants/revaTheme';

export type ShareImageMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  imageUris?: string[];
};

const CARD_WIDTH = 360;

interface Props {
  messages: ShareImageMessage[];
  dateLabel?: string;
}

/** 离屏截图层 —— 固定宽度、内容自适应高度。ref 转发给外层容器供 captureRef。 */
const ConversationShareImage = forwardRef<View, Props>(({ messages, dateLabel }, ref) => {
  return (
    <View ref={ref} collapsable={false} style={styles.canvas}>
      {/* 头部 */}
      <View style={styles.header}>
        <View style={styles.brandDot}>
          <Ionicons name="pulse" size={16} color={R.greenOn} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.brandName}>小巴 · 健康对话</Text>
          {!!dateLabel && <Text style={styles.brandDate}>{dateLabel}</Text>}
        </View>
      </View>

      {/* 气泡 */}
      <View style={styles.body}>
        {messages.map((m) => {
          const isUser = m.role === 'user';
          const imgCount = (m.imageUris || []).filter((u) => !!String(u || '').trim()).length;
          return (
            <View
              key={m.id}
              style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}
            >
              {!isUser && <Text style={styles.speaker}>小巴</Text>}
              <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
                {isUser ? (
                  <Text style={styles.userText}>{m.content.trim()}</Text>
                ) : (
                  <MarkdownText variant="chat">{m.content.trim()}</MarkdownText>
                )}
                {imgCount > 0 && (
                  <Text style={[styles.imgNote, isUser && styles.imgNoteUser]}>
                    🖼 含 {imgCount} 张图片
                  </Text>
                )}
              </View>
            </View>
          );
        })}
      </View>

      {/* 页脚水印 */}
      <View style={styles.footer}>
        <Ionicons name="pulse" size={12} color={R.green500} />
        <Text style={styles.footerText}>小巴 · 你忠实的健康参谋</Text>
      </View>
    </View>
  );
});

ConversationShareImage.displayName = 'ConversationShareImage';

const styles = StyleSheet.create({
  canvas: {
    width: CARD_WIDTH,
    backgroundColor: R.surface2,
    paddingBottom: 14,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 14,
  },
  brandDot: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: R.green500,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandName: { fontSize: 15, fontWeight: '700', color: R.ink1 },
  brandDate: { fontSize: 11, color: R.ink3, marginTop: 1 },
  body: { paddingHorizontal: 14, gap: 12 },
  row: { maxWidth: '100%' },
  rowUser: { alignItems: 'flex-end' },
  rowAssistant: { alignItems: 'flex-start' },
  speaker: { fontSize: 11, color: R.ink3, marginBottom: 3, marginLeft: 4 },
  bubble: {
    maxWidth: '88%',
    borderRadius: 16,
    paddingHorizontal: 13,
    paddingVertical: 10,
  },
  bubbleUser: { backgroundColor: R.green500, borderTopRightRadius: 5 },
  bubbleAssistant: {
    backgroundColor: R.surface,
    borderTopLeftRadius: 5,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: R.green100,
  },
  userText: { fontSize: 15, lineHeight: 22, color: R.greenOn },
  imgNote: { fontSize: 12, color: R.ink3, marginTop: 6 },
  imgNoteUser: { color: 'rgba(255,255,255,0.85)' },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: R.green100,
  },
  footerText: { fontSize: 11, color: R.ink3, letterSpacing: 0.3 },
});

export default ConversationShareImage;
