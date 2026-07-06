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
import { getCardActionRuntimeKey, renderCard } from './cards';
import InterventionDraftSheet from '../actions/InterventionDraftSheet';
import { createMdStylesChat } from '../../constants/markdownStyles';
import type { ColorPalette } from '../../hooks/useTheme';
import type { UIMessage } from '../../hooks/useChatEngine';
import { invalidateQueryKeys, queryKeys } from '../../applib/queryKeys';
import { createInterventionDraft } from '../../services/actionCards';
import { createRecordFromAssistantReply, saveAssistantReplyAsMemory } from '../../services/chatResultActions';
import { buildInterventionDraft, type InterventionDraft } from '../../services/interventionDraft';
import { speakWithUserVoice, type SpeakHandle } from '../../services/speakWithUserVoice';
import { dispatchChatCardAction, type ChatCardActionResult } from '../../services/chatCardActions';
import AttributionChips from './AttributionChips';
import type { ChatCardActionDescriptor, ChatCardActionRuntimeState, ServerCardDescriptor } from './cards/types';
import {
  revaColors as C,
  revaRadii,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import { useToast } from '../../hooks/useToast';
import { sharePlainText } from '../../utils/share';
import { buildAiShareMessage } from '../../utils/aiShareText';
import { containsMarkdownTable, preprocessMarkdownTables } from '../../utils/markdownTables';
import { extractRevaUiBlocks } from '../../utils/revaUiBlocks';
import {
  buildAgentTransparency,
  formatDurationMs,
  type AgentTransparencyBand,
  type AgentTransparencyProfile,
} from '../../utils/chatTransparency';

// 结果操作按钮的装饰性 hue (加入计划绿/保存记忆紫/生成记录青/继续追问蓝) ——
// 「是哪个动作」的色码, 非临床好坏, 保留 Reva 亮色调色板字面量.
const ACTION_PURPLE = '#7C5CBF';
const ACTION_TEAL = '#2F9E8F';

type ResultActionKey = 'plan' | 'memory' | 'record' | 'followup';
type ResultActionDoneLabels = Partial<Record<ResultActionKey, string>>;

// Markdown 样式走共享 factory (constants/markdownStyles, 4 个屏共用, 不动它的 ColorPalette 契约).
// Reva light-first → 用映射到 reva token 的精简调色板算一次, 模块级静态 (无 dark 实例态).
const MD_PALETTE = {
  labelPrimary: C.ink1,
  labelSecondary: C.ink2,
  labelTertiary: C.ink3,
  brand: C.green500,
  fill: C.paper2,
  separator: C.line,
} as unknown as ColorPalette;
const MD_STYLES = createMdStylesChat(MD_PALETTE);

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
  const toast = useToast();
  const isUser = item.role === 'user';
  const [draft, setDraft] = useState<InterventionDraft | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);
  const [showActions, setShowActions] = useState(false);  // 长按显示操作
  const [speaking, setSpeaking] = useState(false);
  const [resultActionBusy, setResultActionBusy] = useState<ResultActionKey | null>(null);
  const [resultActionDoneLabels, setResultActionDoneLabels] = useState<ResultActionDoneLabels>({});
  const [cardActionStateByKey, setCardActionStateByKey] = useState<Record<string, ChatCardActionRuntimeState>>({});
  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speechActiveRef = useRef(false);
  const speechHandleRef = useRef<SpeakHandle | null>(null);
  // 流式期间跳过 sanitizeAiContent + extractRevaUiBlocks 这两条 O(n) 正则:
  // 每个 token 批次都对全量累积文本重跑一遍 → 整轮回复退化为 O(n²), 长回复打满
  // JS 线程 (镜像 113-121 行 "流式期间纯 Text, done 后才 Markdown" 的既有策略).
  // 流式降级路径 (468 行) 用的就是纯文本, 而 reva-ui 块本就只在 done 后可用 →
  // 流式中用原始 item.content 直渲, 终态 (item.streaming 转 false) 才跑全量处理, 行为无损.
  const streamingBubble = !isUser && !!item.streaming;
  const displayText = useMemo(
    () => (streamingBubble ? item.content : sanitizeAiContent(item.content)),
    [streamingBubble, item.content],
  );
  const revaUiContent = useMemo(
    () => (!isUser && !streamingBubble ? extractRevaUiBlocks(displayText) : { text: displayText, cards: [] }),
    [displayText, isUser, streamingBubble],
  );
  const assistantText = revaUiContent.text;
  const structuredSummary = useMemo(
    () => (!isUser && !item.streaming ? parseStructuredHealthSummary(assistantText) : null),
    [assistantText, isUser, item.streaming],
  );
  const visibleMarkdown = useMemo(
    () => (structuredSummary ? stripStructuredHealthSummary(assistantText) : assistantText),
    [assistantText, structuredSummary],
  );
  const thinkingSteps = useMemo(
    () => (!isUser && Array.isArray(item.thinkingSteps)
      ? item.thinkingSteps.map(step => String(step || '').trim()).filter(Boolean).slice(-4)
      : []),
    [isUser, item.thinkingSteps],
  );
  // P0-1 渐进渲染 (刀⑤): 首 token 前显示的"细状态行" —— 单行进度, 非大面板。
  // 只在流式且尚无正文时展示; 首 token 到达后 useChatEngine 清空 currentStatus → 状态行消失,
  // 交给思考完成态 pill。
  const currentStatus = useMemo(
    () => (!isUser && item.streaming ? String(item.currentStatus || '').trim() : ''),
    [isUser, item.streaming, item.currentStatus],
  );
  const visibleAssistantMarkdown = (
    thinkingSteps.length > 0 && visibleMarkdown === '⏳ AI 正在思考中...'
      ? ''
      : visibleMarkdown
  );
  const assistantTextForActions = assistantText.trim();
  // 流式期间故意不跑 preprocessMarkdownTables + <Markdown> 整树渲染:
  // visibleMarkdown 每个 token 批次都变, memo 会失效 → 每秒 10-20 次全量
  // markdown 预处理 + react-native-markdown-display 整树重渲, 长回复打满 JS 线程,
  // 帧率掉/触摸输入迟滞 (mac 端同类病见 #129/#132). 流式中降级为 plain <Text>
  // (保留换行), 流完 (item.streaming 转 false) 才走富 markdown —— 终态结果不变.
  const isStreaming = streamingBubble;
  const renderedMarkdown = useMemo(
    () => (isStreaming ? '' : preprocessMarkdownTables(visibleAssistantMarkdown)),
    [isStreaming, visibleAssistantMarkdown],
  );
  const images = item.imageUris;
  const transparency = useMemo(
    () => buildAgentTransparency({
      elapsedMs: item.elapsedMs,
      llmRounds: item.llmRounds,
      llmRoundsMs: item.llmRoundsMs,
      model: item.model,
      llmUsage: item.llmUsage,
      sourcesUsed: item.sourcesUsed,
      toolsUsed: item.toolsUsed,
      perf: item.perf,
      fallbackReasons: item.fallbackReasons,
    }),
    [
      item.elapsedMs,
      item.llmRounds,
      item.llmRoundsMs,
      item.model,
      item.llmUsage,
      item.sourcesUsed,
      item.toolsUsed,
      item.perf,
      item.fallbackReasons,
    ],
  );

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

  const handleCardAction = useCallback(async (
    action: ChatCardActionDescriptor,
    descriptor: ServerCardDescriptor,
  ) => {
    const actionKey = getCardActionRuntimeKey(action, descriptor);
    if (cardActionStateByKey[actionKey] === 'running' || cardActionStateByKey[actionKey] === 'done') {
      return;
    }
    const execute = async () => {
      setCardActionStateByKey(prev => ({ ...prev, [actionKey]: 'running' }));
      try {
        const result = await dispatchChatCardAction(action);
        await Promise.all([
          qc.invalidateQueries({ queryKey: ['timeline', 'today'] }),
          qc.invalidateQueries({ queryKey: ['agenda', 'today'] }),
          qc.invalidateQueries({ queryKey: ['daily-artifact', 'me'] }),
          qc.invalidateQueries({ queryKey: ['write-intents'] }),
          qc.invalidateQueries({ queryKey: ['diet'] }),
          qc.invalidateQueries({ queryKey: ['dashboard'] }),
          qc.invalidateQueries({ queryKey: ['today-dynamic-view', 'mobile.today'] }),
        ]);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        setCardActionStateByKey(prev => ({ ...prev, [actionKey]: 'done' }));
        toast.show(getCardActionSuccessMessage(action, result), getCardActionSuccessType(action, result));
        if (result.route) {
          router.push(result.route as any);
        }
      } catch {
        setCardActionStateByKey(prev => ({ ...prev, [actionKey]: 'error' }));
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
        toast.show('操作失败，请稍后重试', 'error');
        if (__DEV__) console.warn('[cards] action failed', descriptor.type, action.action);
      }
    };

    if (action.action !== 'route.open' && action.confirmation) {
      Alert.alert(
        action.confirmation.title || action.label,
        action.confirmation.detail || '确认后会写入你的健康记录。',
        [
          {
            text: action.confirmation.cancel_label || '取消',
            style: 'cancel',
          },
          {
            text: action.confirmation.confirm_label || action.label,
            onPress: execute,
          },
        ],
      );
      return;
    }

    await execute();
  }, [cardActionStateByKey, qc, toast]);

  if (item.cardType && item.cardData) {
    const rendered = renderCard(
      { type: item.cardType, data: item.cardData, actions: item.cardActions },
      { onAction: handleCardAction, actionStateByKey: cardActionStateByKey },
    );
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
      title: inferActionTitle(assistantTextForActions),
      advice: assistantTextForActions,
      sourceType: 'chat',
      sourceId: item.id,
    }));
  };

  const markResultActionDone = (key: ResultActionKey, label: string) => {
    setResultActionDoneLabels(prev => ({ ...prev, [key]: label }));
  };

  const handleAddToTodayPlan = async () => {
    if (!assistantTextForActions || resultActionBusy) return;
    setResultActionBusy('plan');
    try {
      const nextDraft = buildInterventionDraft({
        title: inferActionTitle(assistantTextForActions),
        advice: assistantTextForActions,
        sourceType: 'chat',
        sourceId: item.id,
      });
      await createInterventionDraft(nextDraft);
      await invalidateQueryKeys(qc, [
        queryKeys.actionCards,
        queryKeys.todayCoachRoot,
        queryKeys.agentAgendaRoot,
        ['agenda', 'today'],
        ['daily-artifact', 'me'],
        ['today-dynamic-view', 'mobile.today'],
      ]);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      markResultActionDone('plan', '已加入');
      toast.show('已加入今日计划', 'success');
    } catch {
      toast.show('加入今日计划失败，请稍后重试', 'error');
    } finally {
      setResultActionBusy(null);
    }
  };

  const handleSaveMemory = async () => {
    if (!assistantTextForActions || resultActionBusy) return;
    setResultActionBusy('memory');
    try {
      await saveAssistantReplyAsMemory(assistantTextForActions);
      await invalidateQueryKeys(qc, [['memory-facts'], ['memory-stats']]);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      markResultActionDone('memory', '已保存');
      toast.show('已保存到记忆', 'success');
    } catch {
      toast.show('保存记忆失败，请稍后重试', 'error');
    } finally {
      setResultActionBusy(null);
    }
  };

  const handleCreateRecord = async () => {
    if (!assistantTextForActions || resultActionBusy) return;
    setResultActionBusy('record');
    try {
      const result = await createRecordFromAssistantReply(assistantTextForActions);
      await invalidateQueryKeys(qc, [
        queryKeys.dashboard,
        queryKeys.dataHealth,
        queryKeys.todayCoachRoot,
        queryKeys.agentAgendaRoot,
        ['timeline', 'today'],
        ['agenda', 'today'],
        ['daily-artifact', 'me'],
        ['diet'],
        ['today-dynamic-view', 'mobile.today'],
      ]);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      if (result.status === 'created') {
        markResultActionDone('record', '已生成');
        toast.show(result.message || '已生成记录', 'success');
      } else {
        markResultActionDone('record', '去记录页');
        toast.show(result.message, 'info');
        router.push(result.route as any);
      }
    } catch {
      toast.show('生成记录失败，请稍后重试', 'error');
    } finally {
      setResultActionBusy(null);
    }
  };

  const handleContinueFollowUp = () => {
    if (resultActionBusy) return;
    setResultActionBusy('followup');
    const title = inferActionTitle(assistantTextForActions);
    const params = {
      prompt: `请基于「${title}」继续追问，先问我一个最关键的确认问题，再细化成今天能执行的一步。`,
      promptNonce: String(Date.now()),
    };
    try {
      if (typeof (router as any).setParams === 'function') {
        (router as any).setParams(params);
      } else {
        router.push({ pathname: '/(tabs)/chat', params } as any);
      }
    } catch {
      router.push({ pathname: '/(tabs)/chat', params } as any);
    }
    Promise.resolve(Haptics.selectionAsync()).catch(() => {});
    markResultActionDone('followup', '已放入输入框');
    toast.show('已放入输入框', 'info');
    setTimeout(() => setResultActionBusy(null), 250);
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
    const text = stripMarkdownForSpeech(assistantTextForActions);
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
    const message = buildAiShareMessage(assistantTextForActions);
    if (!message) return;
    Haptics.selectionAsync();
    try {
      await sharePlainText({
        title: '小巴 · 建议',
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
            accessibilityLabel={`AI: ${assistantTextForActions || (revaUiContent.cards.length > 0 ? '图表卡片' : item.content)}`}
            accessibilityState={selectionMode ? { selected } : undefined}
          >
            {currentStatus ? (
              <StatusLine label={currentStatus} />
            ) : null}
            {thinkingSteps.length > 0 ? (
              <ThinkingStepsPanel steps={thinkingSteps} streaming={item.streaming} />
            ) : null}
            {structuredSummary ? (
              <StructuredSummaryCard summary={structuredSummary} />
            ) : null}
            {visibleAssistantMarkdown && isStreaming ? (
              // 流式降级: plain text, 保留换行, 不做 markdown 解析/整树渲染
              <Text selectable style={txt.streaming}>{visibleAssistantMarkdown}</Text>
            ) : visibleAssistantMarkdown ? (
              <Markdown style={MD_STYLES}>{renderedMarkdown}</Markdown>
            ) : !item.streaming && !displayText ? (
              <Text style={txt.fallback}>抱歉，这条回复没能送达。你可以重新提问。</Text>
            ) : null}
            {revaUiContent.cards.length > 0 ? (
              <View testID="assistant-reva-ui-cards" style={styles.inlineCardStack}>
                {revaUiContent.cards.map((card, index) => {
                  const rendered = renderCard(card, { onAction: handleCardAction, actionStateByKey: cardActionStateByKey });
                  return rendered ? <View key={`${card.type}-${index}`}>{rendered}</View> : null;
                })}
              </View>
            ) : null}
            {/* P4: 显式归因 chips — 仅当 LLM 在回答里加了"(基于你的 X)" 等 marker 才渲染.
                 markdown 渲染完后, 流式结束才出 (避免提取不全的 marker 闪现) */}
            {assistantTextForActions && !item.streaming ? (
              <AttributionChips text={assistantTextForActions} />
            ) : null}
            {!item.streaming && assistantTextForActions ? (
              <View style={styles.resultActionGrid}>
                <ResultActionButton
                  icon={resultActionDoneLabels.plan ? 'checkmark-circle-outline' : 'add-circle-outline'}
                  label={resultActionDoneLabels.plan || '加入今日计划'}
                  color={C.green500}
                  onPress={handleAddToTodayPlan}
                  loading={resultActionBusy === 'plan'}
                  disabled={!!resultActionBusy}
                />
                <ResultActionButton
                  icon={resultActionDoneLabels.memory ? 'checkmark-circle-outline' : 'bookmark-outline'}
                  label={resultActionDoneLabels.memory || '保存记忆'}
                  color={ACTION_PURPLE}
                  onPress={handleSaveMemory}
                  loading={resultActionBusy === 'memory'}
                  disabled={!!resultActionBusy}
                />
                <ResultActionButton
                  icon={resultActionDoneLabels.record ? 'checkmark-circle-outline' : 'create-outline'}
                  label={resultActionDoneLabels.record || '生成记录'}
                  color={ACTION_TEAL}
                  onPress={handleCreateRecord}
                  loading={resultActionBusy === 'record'}
                  disabled={!!resultActionBusy}
                />
                <ResultActionButton
                  icon={resultActionDoneLabels.followup ? 'checkmark-circle-outline' : 'chatbubble-ellipses-outline'}
                  label={resultActionDoneLabels.followup || '继续追问'}
                  color={C.blue500}
                  onPress={handleContinueFollowUp}
                  loading={resultActionBusy === 'followup'}
                  disabled={!!resultActionBusy}
                />
              </View>
            ) : null}
            {!item.streaming && assistantTextForActions && transparency.visible ? (
              <AgentTransparencyPanel profile={transparency} />
            ) : null}
            {assistantTextForActions && showActions ? (
              <View style={styles.actionsRow}>
                <Pressable
                  style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                  onPress={openDraft}
                  accessibilityRole="button"
                  accessibilityLabel="加入健康行动"
                >
                  <Ionicons name="add-circle-outline" size={14} color={C.green500} />
                  <Text style={txt.actionBtn}>加入行动</Text>
                </Pressable>
                <Pressable
                  style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                  onPress={handleCopy}
                  accessibilityRole="button"
                  accessibilityLabel="复制全文"
                >
                  <Ionicons name="copy-outline" size={14} color={C.green500} />
                  <Text style={txt.actionBtn}>复制</Text>
                </Pressable>
              </View>
            ) : null}
            {item.streaming && thinkingSteps.length === 0 && !currentStatus ? (
              <ActivityIndicator size="small" color={C.green500} style={{ marginTop: 4 }} />
            ) : null}
            {/* 2026-05-13: 耗时 + 模型名 footer + 🔊 播报按钮 (流式结束才显示) */}
            {!item.streaming && assistantTextForActions ? (
              <View style={styles.metaRow}>
                <View style={{ flex: 1 }} />
                {!selectionMode ? (
                  <Pressable
                    onPress={handleShare}
                    hitSlop={6}
                    accessibilityRole="button"
                    accessibilityLabel="分享"
                    style={({ pressed }) => [styles.speakBtn, pressed && styles.actionBtnPressed]}
                  >
                    <Ionicons name="share-outline" size={14} color={C.ink2} />
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
                    color={speaking ? C.green500 : C.ink2}
                  />
                </Pressable>
              </View>
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
  loading,
  disabled,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  color: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        resultActionStyles.button,
        pressed && !disabled && resultActionStyles.pressed,
        disabled && resultActionStyles.disabled,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled, busy: !!loading }}
    >
      {loading ? (
        <ActivityIndicator size="small" color={color} />
      ) : (
        <Ionicons name={icon} size={13} color={color} />
      )}
      <Text style={[resultActionStyles.label, { color }]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

function getCardActionSuccessMessage(
  action: ChatCardActionDescriptor,
  result: ChatCardActionResult,
): string {
  if (result.route || action.action === 'route.open') return '已打开';
  if (action.action === 'diet_record.create') {
    if (result.nutrition_status === 'estimated') return '已记录饮食，营养已估算';
    if (result.nutrition_status === 'estimate_failed') return '已记录饮食，营养估算稍后补充';
    return '已记录饮食';
  }
  if (result.status === 'dismissed' || action.action === 'write_intent.dismiss') return '已忽略';
  return '已执行';
}

function getCardActionSuccessType(
  action: ChatCardActionDescriptor,
  result: ChatCardActionResult,
): 'info' | 'error' | 'success' {
  if (action.action === 'diet_record.create' && result.nutrition_status === 'estimate_failed') {
    return 'info';
  }
  return 'success';
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

// 指标状态 = 真正的「好坏」语义 → Reva 三步临床色 (warning=caution / danger=risk / success=normal),
// 中性回退用灰 (= legacy neutral.solid).
function statusTone(status?: string): string {
  if (!status) return '#8A968F';
  if (/⚠|低|风险|异常|未达标|偏低|偏高|0%/.test(status)) return revaSemantic.caution.fg;
  if (/❌|严重|急|失败/.test(status)) return revaSemantic.risk.fg;
  if (/✅|正常|优秀|良好|充沛/.test(status)) return revaSemantic.normal.fg;
  return '#8A968F';
}

function StructuredSummaryCard({
  summary,
}: {
  summary: StructuredHealthSummary;
}) {
  return (
    <View style={[summaryStyles.card, { backgroundColor: C.paper, borderColor: C.line }]}>
      {summary.metrics.length > 0 ? (
        <>
          <View style={summaryStyles.header}>
            <Ionicons name="analytics-outline" size={14} color={C.green500} />
            <Text style={summaryStyles.title}>指标摘要</Text>
          </View>
          <View style={summaryStyles.metrics}>
            {summary.metrics.map(metric => (
              <View key={`${metric.label}-${metric.value}`} style={summaryStyles.metricRow}>
                <Text style={summaryStyles.metricLabel} numberOfLines={1}>
                  {metric.label}
                </Text>
                <Text style={summaryStyles.metricValue} numberOfLines={1}>
                  {metric.value}
                </Text>
                {metric.status ? (
                  <View style={[summaryStyles.statusDot, { backgroundColor: statusTone(metric.status) }]} />
                ) : null}
              </View>
            ))}
          </View>
        </>
      ) : null}

      {summary.advice.length > 0 ? (
        <View style={[summaryStyles.adviceBlock, summary.metrics.length > 0 && { borderTopColor: C.line, borderTopWidth: StyleSheet.hairlineWidth }]}>
          <View style={summaryStyles.header}>
            <Ionicons name="pin-outline" size={14} color={C.green500} />
            <Text style={summaryStyles.title}>今日建议</Text>
          </View>
          {summary.advice.map((item, index) => (
            <View key={`${index}-${item}`} style={summaryStyles.adviceRow}>
              <Text style={summaryStyles.adviceIndex}>{index + 1}</Text>
              <Text style={summaryStyles.adviceText} numberOfLines={2}>
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
    borderRadius: revaRadii.pill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: C.paper2,
    paddingHorizontal: 9,
  },
  pressed: { opacity: 0.78 },
  disabled: { opacity: 0.58 },
  label: {
    fontFamily: revaFonts.sans,
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
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.ink1,
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
    fontFamily: revaFonts.sans,
    width: 58,
    fontSize: 12,
    fontWeight: '700',
    color: C.ink2,
  } as TextStyle,
  metricValue: {
    fontFamily: revaFonts.mono,
    flex: 1,
    fontSize: 13,
    fontWeight: '800',
    color: C.ink1,
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
    fontFamily: revaFonts.mono,
    width: 18,
    fontSize: 11,
    fontWeight: '900',
    color: C.green500,
    textAlign: 'center',
  } as TextStyle,
  adviceText: {
    fontFamily: revaFonts.sans,
    flex: 1,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
    color: C.ink2,
  } as TextStyle,
});

// Reva 设计语言: 用户气泡 green500, AI 气泡 surface + 软阴影 (light-first). 数字/耗时走 mono.
const styles = StyleSheet.create({
  msgRow: { flexDirection: 'row', marginBottom: 12, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  cardFrame: { flex: 1, minWidth: 0, maxWidth: '100%' },
  inlineCardStack: { marginTop: 10, gap: 8 },
  bubble: { maxWidth: '88%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleUser: { backgroundColor: C.green500, borderBottomRightRadius: 4 },
  bubbleSelected: {
    borderWidth: 2,
    borderColor: C.green500,
    shadowColor: C.green500,
    shadowOpacity: 0.16,
    shadowRadius: 8,
    elevation: 2,
  },
  selectMark: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: C.line,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
    marginBottom: 10,
    backgroundColor: C.paper,
  },
  selectMarkActive: {
    backgroundColor: C.green500,
    borderColor: C.green500,
  },
  siriBadge: {
    position: 'absolute',
    top: -6, right: -6,
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: C.green500,
    borderWidth: 1.5, borderColor: C.paper,
    alignItems: 'center', justifyContent: 'center',
    zIndex: 2,
  },
  bubbleAI: {
    backgroundColor: C.surface, borderBottomLeftRadius: 4,
    ...revaShadows.sm,
  },
  bubbleAIWide: { flex: 1, maxWidth: '94%', flexShrink: 1, alignSelf: 'stretch' },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
  msgImageSingle: { width: 160, height: 120, borderRadius: 10 },
  msgImageGrid: { width: 72, height: 72, borderRadius: 8 },
  // 刀⑤ 细状态行: 单行, 小 spinner + 灰字, 无边框无背景 (低干扰), 首 token 前短暂出现.
  statusLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    marginBottom: 2,
    minHeight: 20,
  },
  thinkingPanel: {
    alignSelf: 'stretch',
    minWidth: 260,
    gap: 8,
    marginBottom: 10,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.paper2,
    paddingHorizontal: 11,
    paddingVertical: 10,
  },
  // 完成态: 低干扰内联状态行, 展开时在下方补步骤列表.
  thinkingPill: {
    alignSelf: 'stretch',
    width: '100%',
    marginBottom: 8,
    paddingBottom: 7,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
    backgroundColor: 'transparent',
  },
  thinkingPillHeader: {
    minHeight: 22,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 0,
    paddingVertical: 0,
  },
  thinkingPillList: {
    gap: 6,
    paddingHorizontal: 0,
    paddingBottom: 0,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  thinkingHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  thinkingHeaderCopy: {
    flex: 1,
    minWidth: 0,
  },
  thinkingSubtitle: {
    marginTop: 1,
  },
  thinkingProgressPill: {
    minWidth: 38,
    minHeight: 22,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  thinkingProgressTrack: {
    height: 3,
    borderRadius: 999,
    backgroundColor: C.line,
    overflow: 'hidden',
  },
  thinkingProgressFill: {
    height: '100%',
    borderRadius: 999,
    backgroundColor: C.green500,
  },
  thinkingList: {
    gap: 6,
  },
  thinkingStepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  thinkingStepIndex: {
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  thinkingStepIndexActive: {
    backgroundColor: C.green600,
    borderColor: C.green600,
  },
  actionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
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
    borderTopColor: C.line,
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
  transparencyPanel: {
    marginTop: 9,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper2,
    overflow: 'hidden',
  },
  transparencyHeader: {
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  transparencyBody: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    paddingHorizontal: 10,
    paddingVertical: 9,
    gap: 8,
  },
  transparencyBar: {
    height: 7,
    borderRadius: 999,
    flexDirection: 'row',
    overflow: 'hidden',
    backgroundColor: C.line,
  },
  transparencyLegend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  transparencyRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  transparencyChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
  },
  transparencyChip: {
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
});

const txt = {
  bubbleUser: { fontFamily: revaFonts.sans, fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  // 与 markdownStyles body (fontSize 15 / lineHeight 23) 对齐, 流式→终态切 markdown 时无跳动
  streaming: { fontFamily: revaFonts.sans, fontSize: 15, lineHeight: 23, color: C.ink1 } as TextStyle,
  statusLine: { flex: 1, minWidth: 0, fontFamily: revaFonts.sans, fontSize: 12.5, lineHeight: 17, fontWeight: '700', color: C.ink3 } as TextStyle,
  thinkingPillLabel: { flex: 1, minWidth: 0, fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 16, fontWeight: '800', color: C.ink3 } as TextStyle,
  thinkingTitle: { fontFamily: revaFonts.sans, fontSize: 12.5, lineHeight: 17, fontWeight: '900', color: C.ink1 } as TextStyle,
  thinkingSubtitle: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, color: C.ink3 } as TextStyle,
  thinkingProgressText: { fontFamily: revaFonts.mono, fontSize: 10.5, lineHeight: 13, fontWeight: '800', color: C.green700 } as TextStyle,
  thinkingStepIndex: { fontFamily: revaFonts.mono, fontSize: 10, lineHeight: 13, fontWeight: '900', color: C.green700 } as TextStyle,
  thinkingStepIndexActive: { color: C.greenOn } as TextStyle,
  thinkingStep: { flex: 1, fontFamily: revaFonts.sans, fontSize: 12.2, lineHeight: 18, color: C.ink2, fontWeight: '600' } as TextStyle,
  actionBtn: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '700', color: C.green500 } as TextStyle,
  fallback: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 20, color: C.ink2, fontStyle: 'italic' } as TextStyle,
  meta: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3 } as TextStyle,
  transparencyTitle: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 16, fontWeight: '800', color: C.ink2 } as TextStyle,
  transparencyLabel: { width: 64, fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 16, color: C.ink3 } as TextStyle,
  transparencyValue: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 16, fontWeight: '700', color: C.ink2 } as TextStyle,
  transparencyMono: { fontFamily: revaFonts.mono, fontSize: 10.5, lineHeight: 15, color: C.ink3 } as TextStyle,
  transparencyChip: { fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 14, color: C.ink2, fontWeight: '700' } as TextStyle,
};

// P0-1 渐进渲染 (刀⑤): 首 token 前的"细状态行" —— 单行进度 + 小 spinner, 低干扰。
// 例: "正在理解…" → "查看步数数据…" → "正在整理回答…"。首 token 到达后由上游清空 → 消失。
function StatusLine({ label }: { label: string }) {
  return (
    <View
      testID="assistant-status-line"
      style={styles.statusLine}
      accessibilityLiveRegion="polite"
      accessibilityLabel={`小巴${label}`}
    >
      <ActivityIndicator size="small" color={C.green500} />
      <Text style={txt.statusLine} numberOfLines={1}>{label}</Text>
    </View>
  );
}

function ThinkingStepsPanel({ steps, streaming }: { steps: string[]; streaming?: boolean }) {
  // 完成态默认折叠成一条 slim pill;流式态保持实时进度展开 (用户要看到它在干活).
  const [expanded, setExpanded] = React.useState(false);
  if (steps.length === 0) return null;

  const latestStep = steps[steps.length - 1];

  // 完成态: slim pill 行 (勾 + 「思考完成 · N 步」+ 折叠箭头), 点击展开/收起步骤列表.
  if (!streaming) {
    const summary = `思考完成 · ${steps.length} 步`;
    return (
      <View testID="assistant-thinking-panel" style={styles.thinkingPill}>
        <Pressable
          onPress={() => setExpanded((prev) => !prev)}
          style={({ pressed }) => [styles.thinkingPillHeader, pressed && styles.actionBtnPressed]}
          accessibilityRole="button"
          accessibilityLabel={expanded ? '收起思考步骤' : '展开思考步骤'}
          accessibilityState={{ expanded }}
        >
          <Ionicons name="checkmark-circle" size={15} color={C.green500} />
          <Text style={txt.thinkingPillLabel} numberOfLines={1}>{summary}</Text>
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={C.ink3} />
        </Pressable>
        {expanded ? (
          <View style={styles.thinkingPillList}>
            {steps.map((step, index) => (
              <View
                key={`${step}-${index}`}
                style={styles.thinkingStepRow}
                accessibilityLabel={`已完成步骤:${step}`}
              >
                <View style={styles.thinkingStepIndex}>
                  <Text style={txt.thinkingStepIndex}>{index + 1}</Text>
                </View>
                <Text style={txt.thinkingStep} numberOfLines={2}>{step}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </View>
    );
  }

  // 流式态: 实时进度面板 (header + 进度条 + 步骤列表), 保持不变.
  const progressText = `${steps.length}/${steps.length}`;
  return (
    <View
      testID="assistant-thinking-panel"
      style={styles.thinkingPanel}
      accessibilityLabel={`小巴正在思考,当前步骤:${latestStep}`}
    >
      <View style={styles.thinkingHeader}>
        <Ionicons name="pulse-outline" size={16} color={C.green500} />
        <View style={styles.thinkingHeaderCopy}>
          <Text style={txt.thinkingTitle}>小巴正在思考</Text>
          <Text style={[txt.thinkingSubtitle, styles.thinkingSubtitle]} numberOfLines={1}>
            整理健康数据和下一步建议
          </Text>
        </View>
        <View style={styles.thinkingProgressPill}>
          <Text style={txt.thinkingProgressText}>{progressText}</Text>
        </View>
      </View>
      <View style={styles.thinkingProgressTrack}>
        <View style={[styles.thinkingProgressFill, { width: '78%' }]} />
      </View>
      <View style={styles.thinkingList}>
        {steps.map((step, index) => {
          const active = index === steps.length - 1;
          return (
            <View
              key={`${step}-${index}`}
              style={styles.thinkingStepRow}
              accessibilityLabel={`${active ? '当前步骤' : '已完成步骤'}:${step}`}
            >
              <View style={[styles.thinkingStepIndex, active && styles.thinkingStepIndexActive]}>
                <Text style={[txt.thinkingStepIndex, active && txt.thinkingStepIndexActive]}>{index + 1}</Text>
              </View>
              <Text style={txt.thinkingStep} numberOfLines={2}>{step}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function bandColor(kind: AgentTransparencyBand['kind']): string {
  switch (kind) {
    case 'prellm': return '#CBD5D1';
    case 'ttft': return '#F5A623';
    case 'gen': return C.green500;
    case 'tool': return C.blue500;
    case 'orch': return revaSemantic.risk.fg;
    case 'total':
    default:
      return C.green300;
  }
}

function AgentTransparencyPanel({ profile }: { profile: AgentTransparencyProfile }) {
  const [open, setOpen] = React.useState(false);
  const rows = [
    ...(profile.stages.length > 0 ? [{ label: '继续阶段', value: profile.stages.map(s => `${s.label} ${s.value}`).join(' · ') }] : []),
    ...(profile.rounds.length > 0 ? [{ label: 'LLM 轮次', value: profile.rounds.map(r => `${r.label} ${r.value}`).join('\n') }] : []),
    ...(profile.tokenLine ? [{ label: 'Token', value: profile.tokenLine }] : []),
    ...(profile.errorLine ? [{ label: '失败', value: profile.errorLine }] : []),
    ...(profile.traceLine ? [{ label: '追踪', value: profile.traceLine }] : []),
  ];
  return (
    <View style={styles.transparencyPanel}>
      <Pressable
        onPress={() => setOpen(o => !o)}
        style={({ pressed }) => [styles.transparencyHeader, pressed && styles.actionBtnPressed]}
        accessibilityRole="button"
        accessibilityLabel={open ? '收起执行透视' : '展开执行透视'}
      >
        <Ionicons name="analytics-outline" size={13} color={C.green500} />
        <Text style={txt.transparencyTitle} numberOfLines={1}>
          透视 · {profile.headline || '本轮执行'}
        </Text>
        <Ionicons
          name={open ? 'chevron-up' : 'chevron-down'}
          size={13}
          color={C.ink3}
        />
      </Pressable>
      {open && (
        <View style={styles.transparencyBody}>
          {profile.bands.length > 0 ? (
            <>
              <View style={styles.transparencyBar}>
                {profile.bands.map((band, index) => (
                  <View
                    key={`${band.kind}-${index}`}
                    style={{
                      flexGrow: band.ratio,
                      flexBasis: 0,
                      backgroundColor: bandColor(band.kind),
                    }}
                  />
                ))}
              </View>
              <View style={styles.transparencyLegend}>
                {profile.bands.map((band, index) => (
                  <Text key={`${band.kind}-legend-${index}`} style={txt.transparencyMono}>
                    {band.label} {formatDurationMs(band.ms)}
                  </Text>
                ))}
              </View>
            </>
          ) : null}
          {rows.map(row => (
            <View key={row.label} style={styles.transparencyRow}>
              <Text style={txt.transparencyLabel}>{row.label}</Text>
              <Text style={txt.transparencyValue}>{row.value}</Text>
            </View>
          ))}
          {profile.sources.length > 0 ? (
            <View style={styles.transparencyRow}>
              <Text style={txt.transparencyLabel}>引用数据</Text>
              <View style={{ flex: 1, gap: 3 }}>
                {profile.sources.slice(0, 8).map(source => (
                  <Text key={source} style={txt.transparencyValue}>· {source}</Text>
                ))}
              </View>
            </View>
          ) : null}
          {profile.routing.length > 0 ? (
            <View style={styles.transparencyRow}>
              <Text style={txt.transparencyLabel}>路由</Text>
              <View style={[styles.transparencyChipRow, { flex: 1 }]}>
                {profile.routing.map(reason => (
                  <View key={reason} style={styles.transparencyChip}>
                    <Text style={txt.transparencyChip}>{reason}</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
          {profile.tools.length > 0 ? (
            <View style={styles.transparencyRow}>
              <Text style={txt.transparencyLabel}>调用 Skill</Text>
              <View style={[styles.transparencyChipRow, { flex: 1 }]}>
                {profile.tools.map(tool => (
                  <View key={tool} style={styles.transparencyChip}>
                    <Text style={txt.transparencyChip}>{tool}</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
        </View>
      )}
    </View>
  );
}
