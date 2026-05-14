import React, { useMemo, useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, TextStyle,
  Alert, ActivityIndicator, Pressable,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';
import Markdown from 'react-native-markdown-display';
import BrandCircle from './BrandCircle';
import { renderCard } from './cards';
import InterventionDraftSheet from '../actions/InterventionDraftSheet';
import { createMdStylesChat } from '../../constants/markdownStyles';
import type { UIMessage } from '../../hooks/useChatEngine';
import { invalidateQueryKeys, queryKeys } from '../../applib/queryKeys';
import { createInterventionDraft } from '../../services/actionCards';
import { buildInterventionDraft, type InterventionDraft } from '../../services/interventionDraft';
import AttributionChips from './AttributionChips';
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
  const [showActions, setShowActions] = useState(false);  // 长按显示操作
  const [speaking, setSpeaking] = useState(false);

  // unmount 时停止播报, 避免气泡消失后还在念
  useEffect(() => {
    return () => {
      if (speaking) { try { Speech.stop(); } catch {} }
    };
  }, [speaking]);

  if (item.cardType && item.cardData) {
    const rendered = renderCard({ type: item.cardType, data: item.cardData });
    if (rendered) return <View style={[styles.msgRow, styles.msgRowAI]}><View style={{ width: 36 }} />{rendered}</View>;
  }

  const displayText = useMemo(() => sanitizeAiContent(item.content), [item.content]);
  const images = item.imageUris;
  const hasTable = !isUser && /\n\s*\|.+\|\s*\n\s*\|[\s|:\-]+\|\s*\n\s*\|/.test(displayText);

  const handleCopy = () => {
    Clipboard.setStringAsync(item.content);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    Alert.alert('已复制');
  };

  const handleLongPress = () => {
    Haptics.selectionAsync();
    setShowActions(prev => !prev);
  };

  const openDraft = () => {
    setShowActions(false);
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

  // 播报当前 AI 气泡内容. 同 bubble 再点 = 停; 切其他气泡播报会接管 (Speech 是单例, 自动 stop 旧的).
  const handleSpeak = () => {
    if (speaking) {
      try { Speech.stop(); } catch {}
      setSpeaking(false);
      return;
    }
    const text = stripMarkdownForSpeech(displayText);
    if (!text) return;
    Haptics.selectionAsync();
    setSpeaking(true);
    Speech.speak(text, {
      language: 'zh-CN',
      rate: 1.0,
      pitch: 1.0,
      onDone: () => setSpeaking(false),
      onStopped: () => setSpeaking(false),
      onError: () => setSpeaking(false),
    });
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
            activeOpacity={0.95}
            onLongPress={handleLongPress}
            accessibilityRole="text"
            accessibilityLabel={`AI: ${item.content}`}
          >
            {displayText ? (
              <Markdown style={mdStyles}>{displayText}</Markdown>
            ) : !item.streaming ? (
              <Text style={txt.fallback}>抱歉，这条回复没能送达。你可以重新提问。</Text>
            ) : null}
            {/* P4: 显式归因 chips — 仅当 LLM 在回答里加了"(基于你的 X)" 等 marker 才渲染.
                 markdown 渲染完后, 流式结束才出 (避免提取不全的 marker 闪现) */}
            {displayText && !item.streaming ? (
              <AttributionChips text={displayText} />
            ) : null}
            {displayText && showActions ? (
              <View style={styles.actionsRow}>
                <Pressable
                  style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                  onPress={openDraft}
                  accessibilityRole="button"
                  accessibilityLabel="加入健康行动"
                >
                  <Ionicons name="add-circle-outline" size={14} color={c.brand} />
                  <Text style={txt.actionBtn}>加入行动</Text>
                </Pressable>
                <Pressable
                  style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                  onPress={handleCopy}
                  accessibilityRole="button"
                  accessibilityLabel="复制全文"
                >
                  <Ionicons name="copy-outline" size={14} color={c.brand} />
                  <Text style={txt.actionBtn}>复制</Text>
                </Pressable>
              </View>
            ) : null}
            {item.streaming && <ActivityIndicator size="small" color={c.brand} style={{ marginTop: 4 }} />}
            {/* 2026-05-13: 耗时 + 模型名 footer + 🔊 播报按钮 (流式结束才显示) */}
            {!item.streaming && displayText ? (
              <View style={styles.metaRow}>
                {item.elapsedMs != null ? (
                  <>
                    <Ionicons name="time-outline" size={10} color={c.labelTertiary} />
                    <Text style={txt.meta}>
                      {(item.elapsedMs / 1000).toFixed(1)}s
                      {item.llmRounds && item.llmRounds > 1 ? ` · ${item.llmRounds} 轮` : ''}
                      {item.model ? ` · ${item.model}` : ''}
                    </Text>
                  </>
                ) : null}
                <View style={{ flex: 1 }} />
                <Pressable
                  onPress={handleSpeak}
                  hitSlop={6}
                  accessibilityRole="button"
                  accessibilityLabel={speaking ? '停止播报' : '语音播报'}
                  style={({ pressed }) => [styles.speakBtn, pressed && styles.actionBtnPressed]}
                >
                  <Ionicons
                    name={speaking ? 'stop-circle' : 'volume-high-outline'}
                    size={14}
                    color={speaking ? c.brand : c.labelSecondary}
                  />
                </Pressable>
              </View>
            ) : null}
            {/* 2026-05-14 #4: 可解释性 chip — AI 用了什么数据 (默认折叠) */}
            {!item.streaming && item.sourcesUsed && item.sourcesUsed.length > 0 ? (
              <SourcesChip sources={item.sourcesUsed} c={c} />
            ) : null}
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

/**
 * 清理流式回复的常见破损形态:
 * - 去掉 [附图: xxx] 内部标记
 * - 去掉只有表头和分隔行、没有 body 的残缺 markdown 表格 (后端在 body 之前断流)
 * - 去掉孤零的 ❌ 行 (error payload 为空时残留)
 * - trim
 */
function sanitizeAiContent(raw: string): string {
  let s = raw.replace(/\n?\[附图: [^\]]+\]/g, '');
  // 残缺表格: "| a | b |\n|---|---|" 后面没有数据行 (下一行不以 | 开头或到末尾)
  s = s.replace(/(^|\n)\|[^\n]*\|\n\|[\s|:\-]+\|(?=\n(?!\s*\|)|\n?$)/g, '');
  // 孤零 ❌ 行: "\n❌" 或 "\n❌ " 行尾, 无实际错误信息
  s = s.replace(/\n+❌\s*(?=\n|$)/g, '');
  return s.trim();
}

/** 把 markdown 文本剥成"能给 TTS 念"的纯文本 — 去标题/粗斜/列表标记/链接/表格管道. */
function stripMarkdownForSpeech(s: string): string {
  return s
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/~~([^~]+)~~/g, '$1')
    .replace(/\|/g, ' ')
    .replace(/^[\s|:\-]+$/gm, '')
    .replace(/\n+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

const ChatBubble = React.memo(ChatBubbleInner);
export default ChatBubble;

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    msgRow: { flexDirection: 'row', marginBottom: 12, alignItems: 'flex-end' },
    msgRowUser: { justifyContent: 'flex-end' },
    msgRowAI: { justifyContent: 'flex-start' },
    bubble: { maxWidth: '88%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
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
    bubbleAIWide: { flex: 1, maxWidth: '94%', flexShrink: 1, alignSelf: 'stretch' },
    imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
    msgImageSingle: { width: 160, height: 120, borderRadius: 10 },
    msgImageGrid: { width: 72, height: 72, borderRadius: 8 },
    actionsRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
      marginTop: 10,
      paddingTop: 8,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
    },
    actionBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      borderRadius: radii.full,
      backgroundColor: c.brandLight,
      paddingHorizontal: 10,
      paddingVertical: 6,
    },
    actionBtnPressed: { opacity: 0.82 },
    speakBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 999,
    },
    metaRow: {
      flexDirection: 'row', alignItems: 'center', gap: 3,
      marginTop: 6,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
    actionBtn: { fontSize: 12, fontWeight: '700', color: c.brand } as TextStyle,
    fallback: { fontSize: 14, lineHeight: 20, color: c.labelSecondary, fontStyle: 'italic' } as TextStyle,
    meta: { fontSize: 10, color: c.labelTertiary, fontFamily: 'Courier' } as TextStyle,
  };
}

/** 2026-05-14 #4: 默认折叠 "AI 用了 N 项数据", 点开列出来. */
function SourcesChip({ sources, c }: { sources: string[]; c: ColorPalette }) {
  const [open, setOpen] = React.useState(false);
  return (
    <View style={{ marginTop: 6 }}>
      <TouchableOpacity
        onPress={() => setOpen(o => !o)}
        style={{
          flexDirection: 'row', alignItems: 'center', gap: 4,
          alignSelf: 'flex-start',
          paddingHorizontal: 8, paddingVertical: 3,
          borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
          backgroundColor: c.fill,
        }}
      >
        <Ionicons name="search-outline" size={11} color={c.labelTertiary} />
        <Text style={{ fontSize: 11, color: c.labelTertiary }}>
          AI 用了 {sources.length} 项数据
        </Text>
        <Ionicons
          name={open ? 'chevron-up' : 'chevron-down'}
          size={11}
          color={c.labelTertiary}
        />
      </TouchableOpacity>
      {open && (
        <View style={{ marginTop: 4, marginLeft: 4, gap: 2 }}>
          {sources.map((s, i) => (
            <View key={i} style={{ flexDirection: 'row', gap: 4 }}>
              <Text style={{ fontSize: 11, color: c.brand, opacity: 0.6 }}>·</Text>
              <Text style={{ fontSize: 11, color: c.labelTertiary, flex: 1 }}>{s}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
