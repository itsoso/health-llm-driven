import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, TextStyle,
  Alert, ActivityIndicator, Pressable,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';
import { setAudioModeAsync } from 'expo-audio';
import Markdown from 'react-native-markdown-display';
import BrandCircle from './BrandCircle';
import { renderCard } from './cards';
import InterventionDraftSheet from '../actions/InterventionDraftSheet';
import { createMdStylesChat } from '../../constants/markdownStyles';
import type { UIMessage } from '../../hooks/useChatEngine';
import { invalidateQueryKeys, queryKeys } from '../../applib/queryKeys';
import { createInterventionDraft } from '../../services/actionCards';
import { saveAssistantReplyAsMemory } from '../../services/chatResultActions';
import { buildInterventionDraft, type InterventionDraft } from '../../services/interventionDraft';
import { speakWithUserVoice, type SpeakHandle } from '../../services/speakWithUserVoice';
import AttributionChips from './AttributionChips';
import { radii } from '../../constants/theme';
import { ColorPalette, useTheme, type SemanticPalette } from '../../hooks/useTheme';
import { useToast } from '../../hooks/useToast';
import { sharePlainText } from '../../utils/share';
import { buildAiShareMessage } from '../../utils/aiShareText';
import { containsMarkdownTable, preprocessMarkdownTables } from '../../utils/markdownTables';

interface Props {
  item: UIMessage;
  onViewImage?: (uri: string) => void;
  selectionMode?: boolean;
  selected?: boolean;
  onToggleSelected?: (id: string) => void;
  /** 微信式: 长按这条消息进入多选模式 (仅可分享的消息才传). 进入后默认选中该条. */
  onEnterSelection?: (id: string) => void;
}

function ChatBubbleInner({ item, onViewImage, selectionMode = false, selected = false, onToggleSelected, onEnterSelection }: Props) {
  const qc = useQueryClient();
  const { c, isDark, s } = useTheme();
  const toast = useToast();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const mdStyles = useMemo(() => createMdStylesChat(c), [c]);
  const isUser = item.role === 'user';
  const [draft, setDraft] = useState<InterventionDraft | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);
  const [showActions, setShowActions] = useState(false);  // 长按显示操作
  const [speaking, setSpeaking] = useState(false);
  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speechActiveRef = useRef(false);
  const speechHandleRef = useRef<SpeakHandle | null>(null);
  const displayText = useMemo(() => sanitizeAiContent(item.content), [item.content]);
  const structuredSummary = useMemo(
    () => (!isUser && !item.streaming ? parseStructuredHealthSummary(displayText) : null),
    [displayText, isUser, item.streaming],
  );
  const visibleMarkdown = useMemo(
    () => (structuredSummary ? stripStructuredHealthSummary(displayText) : displayText),
    [displayText, structuredSummary],
  );
  // 流式期间故意不跑 preprocessMarkdownTables + <Markdown> 整树渲染:
  // visibleMarkdown 每个 token 批次都变, memo 会失效 → 每秒 10-20 次全量
  // markdown 预处理 + react-native-markdown-display 整树重渲, 长回复打满 JS 线程,
  // 帧率掉/触摸输入迟滞 (mac 端同类病见 #129/#132). 流式中降级为 plain <Text>
  // (保留换行), 流完 (item.streaming 转 false) 才走富 markdown —— 终态结果不变.
  const isStreaming = !isUser && !!item.streaming;
  const renderedMarkdown = useMemo(
    () => (isStreaming ? '' : preprocessMarkdownTables(visibleMarkdown)),
    [isStreaming, visibleMarkdown],
  );
  const images = item.imageUris;

  const clearSpeechTimeout = useCallback(() => {
    if (speechTimeoutRef.current) {
      clearTimeout(speechTimeoutRef.current);
      speechTimeoutRef.current = null;
    }
  }, []);

  const setSpeechActive = useCallback((active: boolean) => {
    speechActiveRef.current = active;
    setSpeaking(active);
  }, []);

  const finishSpeech = useCallback(() => {
    clearSpeechTimeout();
    speechHandleRef.current = null;
    setSpeechActive(false);
  }, [clearSpeechTimeout, setSpeechActive]);

  // unmount 时停止播报, 避免气泡消失后还在念
  useEffect(() => {
    return () => {
      clearSpeechTimeout();
      if (speechActiveRef.current) {
        try { speechHandleRef.current?.cancel(); } catch {}
        try { Speech.stop(); } catch {}
      }
    };
  }, [clearSpeechTimeout]);

  if (item.cardType && item.cardData) {
    const rendered = renderCard({ type: item.cardType, data: item.cardData });
    if (rendered) {
      return (
        <View style={[styles.msgRow, styles.msgRowAI]}>
          <View style={{ width: 36 }} />
          <View testID="assistant-card-frame" style={styles.cardFrame}>
            {rendered}
          </View>
        </View>
      );
    }
  }

  const hasTable = !isUser && containsMarkdownTable(displayText);

  const handleCopy = () => {
    Clipboard.setStringAsync(item.content);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    Alert.alert('已复制');
  };

  const handleLongPress = () => {
    if (selectionMode) {
      onToggleSelected?.(item.id);
      return;
    }
    // 微信式: 长按可分享的消息直接进入多选模式并选中该条.
    if (onEnterSelection) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      onEnterSelection(item.id);
      return;
    }
    Haptics.selectionAsync();
    setShowActions(prev => !prev);
  };

  // 用户气泡长按: 可进多选则进多选 (微信式), 否则保留复制.
  const handleUserLongPress = () => {
    if (onEnterSelection) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      onEnterSelection(item.id);
      return;
    }
    handleCopy();
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

  const handleSaveMemory = async () => {
    try {
      await saveAssistantReplyAsMemory(displayText);
      await invalidateQueryKeys(qc, [['memory-facts'], ['memory-stats']]);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.show('已保存到记忆', 'success');
    } catch {
      toast.show('保存记忆失败，请稍后重试', 'error');
    }
  };

  const handleCreateRecord = () => {
    router.push('/(tabs)/record' as any);
  };

  const handleContinueFollowUp = () => {
    router.push({
      pathname: '/(tabs)/chat',
      params: {
        prompt: '请基于上一条建议，继续细化成今天能执行的步骤。',
      },
    } as any);
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
  // 走 speakWithUserVoice → 按用户在"语音风格"页选的档位 (cloud / iOS) 播报,
  // 而不是直接 Speech.speak 走 iOS 默认嗓音.
  const handleSpeak = async () => {
    if (speaking) {
      try { speechHandleRef.current?.cancel(); } catch {}
      try { Speech.stop(); } catch {}
      finishSpeech();
      return;
    }
    const text = stripMarkdownForSpeech(displayText);
    if (!text) return;
    try { Haptics.selectionAsync(); } catch {}
    setSpeechActive(true);
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording: false,
      }).catch(() => {});
      try { speechHandleRef.current?.cancel(); } catch {}
      try { Speech.stop(); } catch {}
      // 长回复会在 speakWithUserVoice 内按句切成多段云端 TTS 串行播放。
      // 这里只做按钮状态兜底, 上限放宽到 4 分钟, 避免 60s 后 UI 提前显示为未播放。
      const estMs = Math.max(8000, Math.min(240000, text.length * 260 + 8000));
      speechTimeoutRef.current = setTimeout(finishSpeech, estMs);
      speechHandleRef.current = await speakWithUserVoice(text, {
        onDone: finishSpeech,
        onStopped: finishSpeech,
        onError: finishSpeech,
        onFallback: (kind) => {
          if (kind === 'cloud_to_ios') {
            toast.show('云端语音暂不可用,临时用系统嗓音', 'info');
          }
        },
      });
    } catch (e) {
      finishSpeech();
      if (__DEV__) console.warn('[ChatBubble] speech start failed:', e);
    }
  };

  // 分享当前 AI 气泡 — 系统分享菜单, 微信/群/朋友圈/短信都走这里.
  // 不引 native WeChat SDK (破坏 OTA 反馈环), 复用 RN Share 已够用.
  const handleShare = async () => {
    if (item.completionStatus === 'interrupted' || item.completionStatus === 'error') {
      toast.show('这条回复没有完整结束，暂不能分享。', 'info');
      return;
    }
    const message = buildAiShareMessage(displayText);
    if (!message) return;
    Haptics.selectionAsync();
    try {
      await sharePlainText({
        title: '健康 Agent · 建议',
        message,
      });
    } catch { /* 用户取消分享也会走这里, 不打扰 */ }
  };

  const handleBubblePress = () => {
    if (selectionMode) onToggleSelected?.(item.id);
  };

  return (
    <>
      <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
        {selectionMode && (
          <Pressable
            onPress={() => onToggleSelected?.(item.id)}
            hitSlop={8}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: selected }}
            accessibilityLabel={selected ? '取消选择这条消息' : '选择这条消息'}
            style={[styles.selectMark, selected && styles.selectMarkActive]}
          >
            {selected ? <Ionicons name="checkmark" size={13} color="#fff" /> : null}
          </Pressable>
        )}
        {!isUser && (
          <BrandCircle size={28} style={{ marginRight: 8 }}>
            <Ionicons name="sparkles" size={12} color="#fff" />
          </BrandCircle>
        )}
        {isUser ? (
          <TouchableOpacity
            style={[styles.bubble, styles.bubbleUser, selected && styles.bubbleSelected]}
            activeOpacity={0.8}
            onPress={handleBubblePress}
            onLongPress={selectionMode ? undefined : handleUserLongPress}
            accessibilityRole="text"
            accessibilityLabel={`你: ${item.content}${item.fromSiri ? ' (来自 Siri)' : ''}`}
            accessibilityState={selectionMode ? { selected } : undefined}
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
            style={[styles.bubble, styles.bubbleAI, hasTable && styles.bubbleAIWide, selected && styles.bubbleSelected]}
            activeOpacity={0.95}
            onPress={handleBubblePress}
            onLongPress={handleLongPress}
            accessibilityRole="text"
            accessibilityLabel={`AI: ${item.content}`}
            accessibilityState={selectionMode ? { selected } : undefined}
          >
            {structuredSummary ? (
              <StructuredSummaryCard summary={structuredSummary} c={c} s={s} />
            ) : null}
            {visibleMarkdown && isStreaming ? (
              // 流式降级: plain text, 保留换行, 不做 markdown 解析/整树渲染
              <Text selectable style={txt.streaming}>{visibleMarkdown}</Text>
            ) : visibleMarkdown ? (
              <Markdown style={mdStyles}>{renderedMarkdown}</Markdown>
            ) : !item.streaming && !displayText ? (
              <Text style={txt.fallback}>抱歉，这条回复没能送达。你可以重新提问。</Text>
            ) : null}
            {/* P4: 显式归因 chips — 仅当 LLM 在回答里加了"(基于你的 X)" 等 marker 才渲染.
                 markdown 渲染完后, 流式结束才出 (避免提取不全的 marker 闪现) */}
            {displayText && !item.streaming ? (
              <AttributionChips text={displayText} />
            ) : null}
            {!item.streaming && displayText ? (
              <View style={styles.resultActionGrid}>
                <ResultActionButton
                  icon="add-circle-outline"
                  label="加入今日计划"
                  color={c.brand}
                  onPress={openDraft}
                />
                <ResultActionButton
                  icon="bookmark-outline"
                  label="保存记忆"
                  color={c.purple}
                  onPress={handleSaveMemory}
                />
                <ResultActionButton
                  icon="create-outline"
                  label="生成记录"
                  color={c.teal}
                  onPress={handleCreateRecord}
                />
                <ResultActionButton
                  icon="chatbubble-ellipses-outline"
                  label="继续追问"
                  color={c.blue}
                  onPress={handleContinueFollowUp}
                />
              </View>
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
                {!selectionMode ? (
                  <Pressable
                    onPress={handleShare}
                    hitSlop={6}
                    accessibilityRole="button"
                    accessibilityLabel="分享"
                    style={({ pressed }) => [styles.speakBtn, pressed && styles.actionBtnPressed]}
                  >
                    <Ionicons name="share-outline" size={14} color={c.labelSecondary} />
                  </Pressable>
                ) : null}
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
            {/* 2026-06-12: 调用 Skill chips — 本轮用了哪些 Skill/工具 (对齐 mac/web) */}
            {!item.streaming && item.toolsUsed && item.toolsUsed.length > 0 ? (
              <ToolsChips tools={item.toolsUsed} c={c} />
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

function ResultActionButton({
  icon,
  label,
  color,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  color: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [resultActionStyles.button, pressed && resultActionStyles.pressed]}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={13} color={color} />
      <Text style={[resultActionStyles.label, { color }]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
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
  // LLM 主动输出的 fenced ```menu_share/```card_xxx JSON 块 — 后端会解析成结构化卡片,
  // 文本里要剥掉, 不然用户看到一坨 JSON 源码
  s = s.replace(/```(?:menu_share|card_[a-z_]+)\s*\n[\s\S]*?\n```\s*/g, '');
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

interface StructuredMetricRow {
  label: string;
  value: string;
  status?: string;
}

interface StructuredHealthSummary {
  metrics: StructuredMetricRow[];
  advice: string[];
}

function splitMarkdownTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim())
    .filter(Boolean);
}

function parseStructuredHealthSummary(text: string): StructuredHealthSummary | null {
  const lines = text.split('\n');
  const metrics: StructuredMetricRow[] = [];

  for (let i = 0; i < lines.length - 2; i += 1) {
    const header = splitMarkdownTableRow(lines[i]);
    const divider = lines[i + 1]?.trim() ?? '';
    const looksLikeMetricTable = header.includes('指标')
      && header.includes('数值')
      && /\|?\s*:?-{3,}:?\s*\|/.test(divider);
    if (!looksLikeMetricTable) continue;

    for (let j = i + 2; j < lines.length; j += 1) {
      if (!lines[j].trim().startsWith('|')) break;
      const cells = splitMarkdownTableRow(lines[j]);
      if (cells.length < 2) continue;
      metrics.push({
        label: cells[0],
        value: cells[1],
        status: cells[2],
      });
      if (metrics.length >= 4) break;
    }
    break;
  }

  const advice: string[] = [];
  const adviceStart = lines.findIndex(line => /今日建议|建议/.test(line));
  if (adviceStart >= 0) {
    for (const line of lines.slice(adviceStart + 1)) {
      if (/^\s*\|/.test(line)) continue;        // 跳过表格行
      const cleaned = cleanAdviceMarkdown(line);
      if (!cleaned) {
        if (advice.length > 0) break;
        continue;
      }
      advice.push(cleaned);
      if (advice.length >= 3) break;
    }
  }

  if (metrics.length === 0 && advice.length === 0) return null;
  return { metrics, advice };
}

/**
 * 清掉建议行里的 markdown 标记 (列表 / 标题 ### / 引用 / 粗体 ** / 行内代码),
 * 让"今日建议"摘要卡显示纯净文本。修复 bug: 形如 "1. ### ✅ 你已有的(继续保持)"
 * 的行被原样渲染成字面量 ###。行首标记可能叠加(列表+标题), 故循环剥离。
 */
function cleanAdviceMarkdown(line: string): string {
  let t = line.trim();
  let prev: string;
  do {
    prev = t;
    t = t
      .replace(/^\d+[.)、]\s*/, '')           // 数字列表 1.
      .replace(/^[-*+]\s+/, '')               // 符号列表 (要求空格, 否则会吃掉 **粗体**)
      .replace(/^#{1,6}\s*/, '')              // 标题 ###
      .replace(/^>\s*/, '')                   // 引用 >
      .trim();
  } while (t !== prev);
  return t
    .replace(/\*\*(.+?)\*\*/g, '$1')         // 粗体
    .replace(/__(.+?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')             // 行内代码
    .trim();
}

function isMetricTableStart(lines: string[], index: number): boolean {
  const header = splitMarkdownTableRow(lines[index]);
  const divider = lines[index + 1]?.trim() ?? '';
  return header.includes('指标')
    && header.includes('数值')
    && /\|?\s*:?-{3,}:?\s*\|/.test(divider);
}

function stripStructuredHealthSummary(text: string): string {
  const lines = text.split('\n');
  const kept: string[] = [];
  let skipTable = false;
  let skipAdvice = false;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();

    if (isMetricTableStart(lines, i)) {
      skipTable = true;
      i += 1;
      continue;
    }
    if (skipTable) {
      if (trimmed.startsWith('|')) continue;
      skipTable = false;
    }

    if (/今日建议|建议/.test(trimmed)) {
      skipAdvice = true;
      continue;
    }
    if (skipAdvice) {
      if (!trimmed) {
        skipAdvice = false;
        continue;
      }
      if (/^(?:[-*]|\d+[.)、])\s*/.test(trimmed)) continue;
      skipAdvice = false;
    }

    kept.push(line);
  }

  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function statusTone(s: SemanticPalette, status?: string): string {
  if (!status) return s.neutral.solid;
  if (/⚠|低|风险|异常|未达标|偏低|偏高|0%/.test(status)) return s.warning.solid;
  if (/❌|严重|急|失败/.test(status)) return s.danger.solid;
  if (/✅|正常|优秀|良好|充沛/.test(status)) return s.success.solid;
  return s.neutral.solid;
}

function StructuredSummaryCard({
  summary,
  c,
  s,
}: {
  summary: StructuredHealthSummary;
  c: ColorPalette;
  s: SemanticPalette;
}) {
  return (
    <View style={[summaryStyles.card, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
      {summary.metrics.length > 0 ? (
        <>
          <View style={summaryStyles.header}>
            <Ionicons name="analytics-outline" size={14} color={c.brand} />
            <Text style={[summaryStyles.title, { color: c.labelPrimary }]}>指标摘要</Text>
          </View>
          <View style={summaryStyles.metrics}>
            {summary.metrics.map(metric => (
              <View key={`${metric.label}-${metric.value}`} style={summaryStyles.metricRow}>
                <Text style={[summaryStyles.metricLabel, { color: c.labelSecondary }]} numberOfLines={1}>
                  {metric.label}
                </Text>
                <Text style={[summaryStyles.metricValue, { color: c.labelPrimary }]} numberOfLines={1}>
                  {metric.value}
                </Text>
                {metric.status ? (
                  <View style={[summaryStyles.statusDot, { backgroundColor: statusTone(s, metric.status) }]} />
                ) : null}
              </View>
            ))}
          </View>
        </>
      ) : null}

      {summary.advice.length > 0 ? (
        <View style={[summaryStyles.adviceBlock, summary.metrics.length > 0 && { borderTopColor: c.separator, borderTopWidth: StyleSheet.hairlineWidth }]}>
          <View style={summaryStyles.header}>
            <Ionicons name="pin-outline" size={14} color={c.brand} />
            <Text style={[summaryStyles.title, { color: c.labelPrimary }]}>今日建议</Text>
          </View>
          {summary.advice.map((item, index) => (
            <View key={`${index}-${item}`} style={summaryStyles.adviceRow}>
              <Text style={[summaryStyles.adviceIndex, { color: c.brand }]}>{index + 1}</Text>
              <Text style={[summaryStyles.adviceText, { color: c.labelSecondary }]} numberOfLines={2}>
                {item}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const ChatBubble = React.memo(ChatBubbleInner);
export default ChatBubble;

const resultActionStyles = StyleSheet.create({
  button: {
    width: '48%',
    minHeight: 32,
    borderRadius: radii.full,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: 'rgba(120, 120, 128, 0.12)',
    paddingHorizontal: 9,
  },
  pressed: { opacity: 0.78 },
  label: {
    fontSize: 11,
    fontWeight: '800',
  } as TextStyle,
});

const summaryStyles = StyleSheet.create({
  card: {
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 10,
    marginBottom: 10,
    gap: 8,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 6,
  },
  title: {
    fontSize: 12,
    fontWeight: '800',
  } as TextStyle,
  metrics: {
    gap: 6,
  },
  metricRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  metricLabel: {
    width: 58,
    fontSize: 12,
    fontWeight: '700',
  } as TextStyle,
  metricValue: {
    flex: 1,
    fontSize: 13,
    fontWeight: '800',
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  adviceBlock: {
    paddingTop: 8,
  },
  adviceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
    marginTop: 5,
  },
  adviceIndex: {
    width: 18,
    fontSize: 11,
    fontWeight: '900',
    textAlign: 'center',
  } as TextStyle,
  adviceText: {
    flex: 1,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
  } as TextStyle,
});

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    msgRow: { flexDirection: 'row', marginBottom: 12, alignItems: 'flex-end' },
    msgRowUser: { justifyContent: 'flex-end' },
    msgRowAI: { justifyContent: 'flex-start' },
    cardFrame: { flex: 1, minWidth: 0, maxWidth: '100%' },
    bubble: { maxWidth: '88%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
    bubbleUser: { backgroundColor: c.brand, borderBottomRightRadius: 4 },
    bubbleSelected: {
      borderWidth: 2,
      borderColor: c.brand,
      shadowColor: c.brand,
      shadowOpacity: 0.16,
      shadowRadius: 8,
      elevation: 2,
    },
    selectMark: {
      width: 22,
      height: 22,
      borderRadius: 11,
      borderWidth: 1,
      borderColor: c.separator,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: 8,
      marginBottom: 10,
      backgroundColor: c.bgPrimary,
    },
    selectMarkActive: {
      backgroundColor: c.brand,
      borderColor: c.brand,
    },
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
    resultActionGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 7,
      marginTop: 10,
      paddingTop: 8,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
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
    // 与 markdownStyles body (fontSize 15 / lineHeight 23) 对齐, 流式→终态切 markdown 时无跳动
    streaming: { fontSize: 15, lineHeight: 23, color: c.labelPrimary } as TextStyle,
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

/** 2026-06-12: "调用 Skill" — 本轮调用的 Skill/工具名, 横排 chip (对齐 mac/web).
 * 始终展开 (通常 1-3 个), 灰、小、低调, 不抢内容。 */
function ToolsChips({ tools, c }: { tools: string[]; c: ColorPalette }) {
  const list = tools.filter(t => t && t.trim());
  if (list.length === 0) return null;
  return (
    <View
      style={{
        flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 4,
        marginTop: 6,
      }}
    >
      <Ionicons name="construct-outline" size={11} color={c.labelTertiary} />
      <Text style={{ fontSize: 11, color: c.labelTertiary }}>调用 Skill</Text>
      {list.map((t, i) => (
        <View
          key={i}
          style={{
            paddingHorizontal: 7, paddingVertical: 2,
            borderRadius: 10, borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
            backgroundColor: c.fill,
          }}
        >
          <Text style={{ fontSize: 11, color: c.labelSecondary }}>{t}</Text>
        </View>
      ))}
    </View>
  );
}
