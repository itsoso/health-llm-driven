/**
 * ConversationShareImage —— 「选一段对话成图」的离屏渲染层。
 *
 * 把用户选中的消息渲染成一张干净的品牌长图(头部 + 气泡 + 页脚水印),供 captureRef
 * 截成 PNG 分享/存图。**不是**原始截屏 —— 是重排的分享图(类似微信/ChatGPT 对话分享)。
 * 用户附图与助手回答里的 markdown 图片会作为真实图片块进入长图;截图必须等所有
 * 图片 onLoad/onError 落定(或超时占位)后才触发 onReady,避免导出空白图块。
 * 在 chat.tsx 里以离屏方式挂载(绝对定位 + opacity 0),width 固定、height 随内容,
 * captureRef 能拿到完整高度(超屏也行)。
 */
import React, { forwardRef, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, type LayoutChangeEvent } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';

import MarkdownText from '../shared/MarkdownText';
import { buildChatImageSource, type ChatImageSource } from '../../utils/chatImageSource';
import { revaColors as R } from '../../constants/revaTheme';
import { colors as lightPalette } from '../../constants/theme';
import { APP_DISPLAY_NAME } from '../../constants/brand';

export type ShareImageMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  imageUris?: string[];
};

const CARD_WIDTH = 360;

/** 离屏导出图等待远程图片落定的上限;超时后以可见占位继续导出,不静默丢图。 */
export const SHARE_IMAGE_LOAD_TIMEOUT_MS = 8_000;

const MARKDOWN_IMAGE_RE = /!\[[^\]]*]\(\s*([^)\s]+)\s*\)/g;

function markdownImageUris(content: string): string[] {
  const uris: string[] = [];
  for (const match of String(content || '').matchAll(MARKDOWN_IMAGE_RE)) {
    const uri = String(match[1] || '').trim();
    if (uri) uris.push(uri);
  }
  return uris;
}

type ShareImageTile = { key: string; uri: string };

interface Props {
  messages: ShareImageMessage[];
  dateLabel?: string;
  imageAuthToken?: string | null;
  onReady?: () => void;
}

/** 离屏截图层 —— 固定宽度、内容自适应高度。ref 转发给外层容器供 captureRef。 */
const ConversationShareImage = forwardRef<View, Props>(
  ({ messages, dateLabel, imageAuthToken = null, onReady }, ref) => {
  const tileGroups = useMemo(
    () =>
      messages.map((message) => ({
        id: message.id,
        tiles: (message.role === 'user'
          ? (message.imageUris || [])
          : markdownImageUris(message.content))
          .map((uri, index): ShareImageTile => ({ key: `${message.id}-${index}`, uri: String(uri || '').trim() }))
          .filter((tile) => tile.uri.length > 0),
      })),
    [messages],
  );
  const tiles = useMemo(() => tileGroups.flatMap((group) => group.tiles), [tileGroups]);
  const sources = useMemo(() => {
    const map = new Map<string, ChatImageSource | undefined>();
    for (const tile of tiles) map.set(tile.key, buildChatImageSource(tile.uri, imageAuthToken));
    return map;
  }, [tiles, imageAuthToken]);

  const [layoutReady, setLayoutReady] = useState(false);
  const [failedTiles, setFailedTiles] = useState<Record<string, true>>({});
  const [settledCount, setSettledCount] = useState(0);
  const settledRef = useRef<Set<string>>(new Set());
  const readyFiredRef = useRef(false);

  const settleTile = useCallback((key: string, loaded: boolean) => {
    if (settledRef.current.has(key)) return;
    settledRef.current.add(key);
    if (!loaded) setFailedTiles((prev) => ({ ...prev, [key]: true }));
    setSettledCount(settledRef.current.size);
  }, []);

  // 受保护图片缺少 token 时不能挂住导出;直接以可见占位落定。
  useEffect(() => {
    for (const tile of tiles) {
      if (!sources.get(tile.key)) settleTile(tile.key, false);
    }
  }, [tiles, sources, settleTile]);

  useEffect(() => {
    if (!layoutReady || tiles.length === 0 || settledCount >= tiles.length) return undefined;
    const timeout = setTimeout(() => {
      for (const tile of tiles) settleTile(tile.key, false);
    }, SHARE_IMAGE_LOAD_TIMEOUT_MS);
    return () => clearTimeout(timeout);
  }, [layoutReady, tiles, settledCount, settleTile]);

  useEffect(() => {
    if (readyFiredRef.current || !layoutReady || settledCount < tiles.length) return;
    readyFiredRef.current = true;
    onReady?.();
  }, [layoutReady, settledCount, tiles.length, onReady]);

  const handleLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    if (width > 0 && height > 0) setLayoutReady(true);
  };

  return (
    <View
      ref={ref}
      collapsable={false}
      onLayout={handleLayout}
      style={styles.canvas}
      testID="conversation-share-image"
    >
      <View style={styles.topRule} />

      {/* 头部 */}
      <View style={styles.header}>
        <View style={styles.brandRow}>
          <View style={styles.brandDot}>
            <Ionicons name="pulse" size={17} color={R.focusBg} />
          </View>
          <Text style={styles.brandEyebrow}>REVA HEALTH NOTE</Text>
        </View>
        <Text style={styles.brandName}>{APP_DISPLAY_NAME} · 对话摘录</Text>
        <View style={styles.headerMeta}>
          <Text style={styles.brandDate}>
            {[dateLabel, `${messages.length} 条已选对话`].filter(Boolean).join('  ·  ')}
          </Text>
          <View style={styles.selectedBadge}>
            <Text style={styles.selectedBadgeText}>已精选</Text>
          </View>
        </View>
      </View>

      {/* 气泡 */}
      <View style={styles.body}>
        {messages.map((m) => {
          const isUser = m.role === 'user';
          const messageTiles = (tileGroups.find((group) => group.id === m.id)?.tiles) || [];
          return (
            <View
              key={m.id}
              style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}
            >
              <View style={isUser ? styles.userSpeakerRow : styles.assistantSpeakerRow}>
                {!isUser && (
                  <View style={styles.assistantAvatar}>
                    <Ionicons name="pulse" size={11} color={R.greenOn} />
                  </View>
                )}
                <Text style={[styles.speaker, isUser && styles.speakerUser]}>
                  {isUser ? '你' : APP_DISPLAY_NAME}
                </Text>
                {!isUser && <Text style={styles.speakerRole}>健康参谋</Text>}
              </View>
              <View
                testID={`share-bubble-${m.id}`}
                style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}
              >
                {isUser ? (
                  <Text style={styles.userText}>{m.content.trim()}</Text>
                ) : (
                  <MarkdownText variant="chat" palette={lightPalette} omitImages>
                    {m.content.trim()}
                  </MarkdownText>
                )}
                {messageTiles.length > 0 && (
                  <View style={styles.imageStack} testID={`share-images-${m.id}`}>
                    {messageTiles.map((tile) => {
                      const source = sources.get(tile.key);
                      if (!source || failedTiles[tile.key]) {
                        return (
                          <View
                            key={tile.key}
                            testID={`share-image-failed-${tile.key}`}
                            style={[styles.imageTile, styles.imageTileFailed]}
                          >
                            <Ionicons name="image-outline" size={20} color={R.ink3} />
                            <Text style={styles.imageFailText}>图片加载失败</Text>
                          </View>
                        );
                      }
                      return (
                        <Image
                          key={tile.key}
                          testID={`share-image-${tile.key}`}
                          source={source}
                          style={styles.imageTile}
                          contentFit="contain"
                          cachePolicy="memory-disk"
                          priority="high"
                          onLoad={() => settleTile(tile.key, true)}
                          onError={() => settleTile(tile.key, false)}
                        />
                      );
                    })}
                  </View>
                )}
              </View>
            </View>
          );
        })}
      </View>

      {/* 页脚水印 */}
      <View style={styles.footer}>
        <View style={styles.footerBrand}>
          <Ionicons name="pulse" size={12} color={R.green500} />
          <Text style={styles.footerText}>{APP_DISPLAY_NAME} · 你忠实的健康参谋</Text>
        </View>
        <Text style={styles.footerNote}>内容仅作健康管理参考</Text>
      </View>
    </View>
  );
  });

ConversationShareImage.displayName = 'ConversationShareImage';

const styles = StyleSheet.create({
  canvas: {
    width: CARD_WIDTH,
    backgroundColor: R.paper,
    paddingBottom: 20,
  },
  topRule: {
    height: 6,
    backgroundColor: R.greenBright,
  },
  header: {
    backgroundColor: R.focusBg,
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 20,
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  brandDot: {
    width: 28,
    height: 28,
    borderRadius: 9,
    backgroundColor: R.greenBright,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandEyebrow: {
    fontSize: 10,
    fontWeight: '700',
    color: R.focusInk2,
    letterSpacing: 1.4,
  },
  brandName: {
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '800',
    color: R.focusInk1,
    letterSpacing: -0.4,
    marginTop: 15,
  },
  headerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  brandDate: { fontSize: 11, color: R.focusInk2 },
  selectedBadge: {
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: R.focusBg2,
    borderWidth: 1,
    borderColor: R.focusLine,
  },
  selectedBadgeText: { fontSize: 10, fontWeight: '700', color: R.greenBright },
  body: { paddingHorizontal: 18, paddingTop: 20, gap: 16 },
  row: { maxWidth: '100%' },
  rowUser: { alignItems: 'flex-end' },
  rowAssistant: { alignItems: 'stretch' },
  userSpeakerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginRight: 4,
    marginBottom: 5,
  },
  assistantSpeakerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 4,
    marginBottom: 7,
  },
  assistantAvatar: {
    width: 21,
    height: 21,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: R.green500,
    marginRight: 6,
  },
  speaker: { fontSize: 11, fontWeight: '700', color: R.ink2 },
  speakerUser: { color: R.ink3 },
  speakerRole: { fontSize: 10, color: R.ink3, marginLeft: 6 },
  bubble: {
    borderRadius: 18,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  bubbleUser: {
    maxWidth: '82%',
    backgroundColor: R.green600,
    borderTopRightRadius: 6,
  },
  imageStack: { marginTop: 10, gap: 8 },
  imageTile: {
    width: '100%',
    aspectRatio: 4 / 3,
    borderRadius: 12,
    backgroundColor: R.focusBg2,
    overflow: 'hidden',
  },
  imageTileFailed: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1,
    borderColor: R.focusLine,
    borderStyle: 'dashed',
  },
  imageFailText: {
    fontSize: 11,
    color: R.ink3,
  },
  bubbleAssistant: {
    alignSelf: 'stretch',
    maxWidth: '100%',
    backgroundColor: R.surface,
    borderTopLeftRadius: 6,
    borderWidth: 1,
    borderColor: R.line,
    borderLeftWidth: 3,
    borderLeftColor: R.green500,
  },
  userText: { fontSize: 14, lineHeight: 21, fontWeight: '500', color: R.greenOn },
  footer: {
    marginHorizontal: 18,
    marginTop: 20,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: R.line,
  },
  footerBrand: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  footerText: { fontSize: 11, fontWeight: '600', color: R.ink2, letterSpacing: 0.3 },
  footerNote: { fontSize: 9, color: R.ink3, textAlign: 'center', marginTop: 5 },
});

export default ConversationShareImage;
