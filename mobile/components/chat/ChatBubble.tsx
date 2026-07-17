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
import { captureRef } from 'react-native-view-shot';
import Markdown from 'react-native-markdown-display';
import { getCardActionRuntimeKey, renderCard } from './cards';
import { createMdStylesChat } from '../../constants/markdownStyles';
import type { ColorPalette } from '../../hooks/useTheme';
import type { UIMessage } from '../../hooks/useChatEngine';
import { speakWithUserVoice, type SpeakHandle } from '../../services/speakWithUserVoice';
import { dispatchChatCardAction, type ChatCardActionResult } from '../../services/chatCardActions';
import { rememberVerifiedWriteReceipt } from '../../services/conversationContinuity';
import {
  buildCardActionReceiptIdentity,
  loadCardActionCompletion,
  saveCardActionReceipt,
} from '../../services/cardActionReceiptStorage';
import { durationBucket, emitClientEvent } from '../../services/clientEvents';
import { AttributionDetails, normalizedAttributionCount } from './AttributionChips';
import type { ChatCardActionDescriptor, ChatCardActionRuntimeState, ServerCardDescriptor } from './cards/types';
import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import { SOCIAL_BRAND } from '../../constants/brand';
import { useToast } from '../../hooks/useToast';
import { shareLocalImage, sharePlainCaption, sharePlainText } from '../../utils/share';
import { buildAiShareMessage, buildXiaohongshuShareMessage } from '../../utils/aiShareText';
import { buildChatImageSource } from '../../utils/chatImageSource';
import { containsMarkdownTable, preprocessMarkdownTables } from '../../utils/markdownTables';
import { prepareSafeMarkdown, safeMarkdownIt } from '../../utils/safeMarkdown';
import { extractRevaUiBlocks } from '../../utils/revaUiBlocks';
import { saveChatImageToLibrary } from '../../services/chatImageSave';
import InterventionDraftSheet from '../actions/InterventionDraftSheet';
import { createInterventionDraft } from '../../services/actionCards';
import {
  buildInterventionDraft,
  type InterventionDraft,
} from '../../services/interventionDraft';
import { invalidateQueryKeys, queryKeys } from '../../applib/queryKeys';
import {
  buildAgentTransparency,
  formatDurationMs,
  type AgentTransparencyBand,
  type AgentTransparencyProfile,
} from '../../utils/chatTransparency';

type WriteReceipt = NonNullable<ChatCardActionResult['receipt']>;

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
const THINKING_PLACEHOLDER_TEXT = '⏳ AI 正在思考中...';
const INLINE_EDITABLE_CARD_TYPES = new Set(['diet_draft', 'record_quality', 'save_recipe']);

interface Props {
  item: UIMessage;
  onViewImage?: (uri: string) => void;
  imageAuthToken?: string | null;
  selectionMode?: boolean;
  selected?: boolean;
  onToggleSelected?: (id: string) => void;
  /** 微信式: 长按这条消息进入多选模式 (仅可分享的消息才传). 进入后默认选中该条. */
  onEnterSelection?: (id: string) => void;
  onSendSuggestedPrompt?: (prompt: string) => void;
  onStopStreaming?: () => void;
}

function ChatBubbleInner({
  item,
  onViewImage,
  imageAuthToken,
  selectionMode = false,
  selected = false,
  onToggleSelected,
  onEnterSelection,
  onSendSuggestedPrompt,
  onStopStreaming,
}: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  const isUser = item.role === 'user';
  const [showActions, setShowActions] = useState(false);  // 长按显示操作
  const [showShareActions, setShowShareActions] = useState(false);
  const [showCardActions, setShowCardActions] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [cardActionStateByKey, setCardActionStateByKey] = useState<Record<string, ChatCardActionRuntimeState>>({});
  const [cardReceiptByKey, setCardReceiptByKey] = useState<Record<string, WriteReceipt>>({});
  const [cardReceiptPersistenceWarning, setCardReceiptPersistenceWarning] = useState(false);
  const [todayPlanDraft, setTodayPlanDraft] = useState<InterventionDraft | null>(null);
  const [savingTodayPlan, setSavingTodayPlan] = useState(false);
  const cardActionLocksRef = useRef(new Set<string>());
  const cardFrameRef = useRef<View | null>(null);
  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speechActiveRef = useRef(false);
  const speechHandleRef = useRef<SpeakHandle | null>(null);
  // 流式期间跳过 sanitizeAiContent + extractRevaUiBlocks 这两条 O(n) 正则:
  // 每个 token 批次都对全量累积文本重跑一遍 → 整轮回复退化为 O(n²), 长回复打满
  // JS 线程。正文仍走 Markdown 渲染, 但 reva-ui 块本就只在 done 后可用。
  // 流式中用原始 item.content 作为正文源, 终态 (item.streaming 转 false) 才跑全量处理。
  const streamingBubble = !isUser && !!item.streaming;
  const displayText = useMemo(
    () => (streamingBubble ? item.content : sanitizeAiContent(item.content)),
    [streamingBubble, item.content],
  );
  const revaUiContent = useMemo(
    () => (!isUser && !streamingBubble ? extractRevaUiBlocks(displayText) : { text: displayText, cards: [] }),
    [displayText, isUser, streamingBubble],
  );
  const hasInlineEditableCard = useMemo(
    () => revaUiContent.cards.some(card => INLINE_EDITABLE_CARD_TYPES.has(card.type)),
    [revaUiContent.cards],
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
  const advisorPresentation = useMemo(
    () => (
      !isUser
      && !item.streaming
      && item.completionStatus !== 'interrupted'
      && item.completionStatus !== 'error'
        ? parseAdvisorPresentation(visibleMarkdown)
        : null
    ),
    [isUser, item.completionStatus, item.streaming, visibleMarkdown],
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
  const placeholderOnly = visibleMarkdown === THINKING_PLACEHOLDER_TEXT;
  const processingStatusLabel = currentStatus
    || (item.streaming && (placeholderOnly || !visibleMarkdown.trim()) ? '正在理解你的问题…' : '');
  const showProcessingPanel = !isUser && (
    thinkingSteps.length > 0
    || !!processingStatusLabel
  );
  const rawVisibleAssistantMarkdown = (
    showProcessingPanel && placeholderOnly
      ? ''
      : visibleMarkdown
  );
  const visibleAssistantMarkdown = item.streaming
    ? rawVisibleAssistantMarkdown
    : advisorPresentation?.details ?? rawVisibleAssistantMarkdown;
  const assistantTextForActions = assistantText.trim();
  const renderedMarkdown = useMemo(
    () => preprocessMarkdownTables(visibleAssistantMarkdown),
    [visibleAssistantMarkdown],
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
    ],
  );
  const sentTimeShort = formatMessageTimeLabel(item.createdAt);
  const sentTimeFull = formatMessageFullTimeLabel(item.createdAt);
  const timeAccessibilityPrefix = sentTimeFull
    ? `${isUser ? '你发送于' : '小巴回复于'} ${sentTimeFull}. `
    : '';

  const openTodayPlanDraft = useCallback((advice: string) => {
    const cleanAdvice = advice.trim();
    if (!cleanAdvice) return;
    try { Haptics.selectionAsync(); } catch {}
    setTodayPlanDraft(buildInterventionDraft({
      title: cleanAdvice.length > 28 ? `${cleanAdvice.slice(0, 28)}...` : cleanAdvice,
      advice: cleanAdvice,
      sourceType: 'chat',
      sourceId: item.id,
      verificationDays: 1,
    }));
  }, [item.id]);

  const submitTodayPlanDraft = useCallback(async (draft: InterventionDraft) => {
    if (savingTodayPlan) return;
    setSavingTodayPlan(true);
    try {
      await createInterventionDraft(draft);
      await invalidateQueryKeys(qc, [
        queryKeys.actionCards,
        queryKeys.todayCoachRoot,
        queryKeys.agentAgendaRoot,
        ['agenda', 'today'],
        ['daily-artifact', 'me'],
        ['today-dynamic-view', 'mobile.today'],
      ]);
      setTodayPlanDraft(null);
      try { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); } catch {}
      toast.show('已加入今天，完成后可直接打卡', 'success');
    } catch (error) {
      try { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error); } catch {}
      toast.show('加入失败，请稍后重试', 'error');
      if (__DEV__) console.warn('[chat] add today plan failed', error);
    } finally {
      setSavingTodayPlan(false);
    }
  }, [qc, savingTodayPlan, toast]);

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

  useEffect(() => {
    const cardType = item.cardType;
    if (!cardType || !item.cardActions?.length) return;
    let cancelled = false;
    void Promise.all(item.cardActions.map(async (action) => {
      const actionKey = getCardActionRuntimeKey(action, { type: cardType });
      const identity = buildCardActionReceiptIdentity(
        action,
        cardType,
        item.sourceTurnId ?? item.sourceMessageId ?? item.id,
      );
      const completion = await loadCardActionCompletion(identity);
      return completion ? { actionKey, completion } : undefined;
    })).then((restored) => {
      if (cancelled) return;
      const valid = restored.filter((entry): entry is {
        actionKey: string;
        completion: { verified: true; receipt?: WriteReceipt };
      } => !!entry);
      if (valid.length === 0) return;
      setCardActionStateByKey(prev => ({
        ...prev,
        ...Object.fromEntries(valid.map(entry => [entry.actionKey, 'done' as const])),
      }));
      const restoredReceipts = valid.filter((entry): entry is {
        actionKey: string;
        completion: { verified: true; receipt: WriteReceipt };
      } => !!entry.completion.receipt);
      if (restoredReceipts.length > 0) {
        setCardReceiptByKey(prev => ({
          ...prev,
          ...Object.fromEntries(restoredReceipts.map(entry => [entry.actionKey, entry.completion.receipt])),
        }));
      }
      valid.forEach(entry => cardActionLocksRef.current.add(entry.actionKey));
    }).catch(() => {
      if (__DEV__) console.warn('[chat] card receipt restore failed');
    });
    return () => { cancelled = true; };
  }, [item.cardActions, item.cardType, item.id, item.sourceMessageId, item.sourceTurnId]);

  const handleCardAction = useCallback(async (
    action: ChatCardActionDescriptor,
    descriptor: ServerCardDescriptor,
  ) => {
    const actionKey = getCardActionRuntimeKey(action, descriptor);
    if (
      cardActionLocksRef.current.has(actionKey)
      || cardActionStateByKey[actionKey] === 'running'
      || cardActionStateByKey[actionKey] === 'done'
    ) {
      return;
    }
    cardActionLocksRef.current.add(actionKey);
    const receiptIdentity = buildCardActionReceiptIdentity(
      action,
      descriptor.type,
      item.sourceTurnId ?? item.sourceMessageId ?? item.id,
    );
    const execute = async () => {
      const actionStartedAt = Date.now();
      const writeAction = isWriteCardAction(action);
      let writeTerminalSent = false;
      const emitWriteTerminal = (
        phase: 'verified' | 'unverified' | 'failed',
        verified: boolean,
        errorCode?: string,
      ) => {
        if (!writeAction || writeTerminalSent) return;
        writeTerminalSent = true;
        void emitClientEvent('write_receipt_terminal', {
          phase,
          duration_bucket: durationBucket(actionStartedAt),
          action_type: action.action,
          verified,
          ...(errorCode ? { error_code: errorCode } : {}),
        });
      };
      setCardActionStateByKey(prev => ({ ...prev, [actionKey]: 'running' }));
      try {
        const result = await dispatchChatCardAction(action, receiptIdentity);
        if (writeAction && result.receipt?.verified !== true) {
          emitWriteTerminal('unverified', false, 'write_receipt_missing_identity');
          throw new Error('write_receipt_missing_identity');
        }
        let receiptPersistenceFailed = false;
        if (result.receipt) {
          const persisted = await Promise.allSettled([
            rememberVerifiedWriteReceipt(result.receipt),
            saveCardActionReceipt(receiptIdentity, result.receipt),
          ]);
          const cardDuplicateGuardSaved = persisted[1]?.status === 'fulfilled';
          if (!cardDuplicateGuardSaved) {
            receiptPersistenceFailed = true;
            setCardReceiptPersistenceWarning(true);
            console.warn('[chat] card write receipt persistence failed');
          } else {
            setCardReceiptByKey(prev => ({ ...prev, [actionKey]: result.receipt as WriteReceipt }));
          }
        }
        if (writeAction) {
          emitWriteTerminal(
            receiptPersistenceFailed ? 'unverified' : 'verified',
            !receiptPersistenceFailed,
            receiptPersistenceFailed ? 'card_receipt_persistence_failed' : undefined,
          );
        }
        const refreshResults = await Promise.allSettled([
          qc.invalidateQueries({ queryKey: queryKeys.actionCards }),
          qc.invalidateQueries({ queryKey: queryKeys.todayCoachRoot }),
          qc.invalidateQueries({ queryKey: queryKeys.agentAgendaRoot }),
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
        const refreshFailed = refreshResults.some(refresh => refresh.status === 'rejected');
        if (receiptPersistenceFailed) {
          toast.show('已写入，但本机未保存防重复凭证', 'error');
        } else {
          toast.show(
            refreshFailed ? '已写入，页面数据稍后刷新' : getCardActionSuccessMessage(action, result),
            refreshFailed ? 'info' : getCardActionSuccessType(action, result),
          );
        }
        if (result.route) {
          router.push(result.route as any);
        }
      } catch {
        cardActionLocksRef.current.delete(actionKey);
        emitWriteTerminal('failed', false, 'card_action_failed');
        setCardActionStateByKey(prev => ({ ...prev, [actionKey]: 'error' }));
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
        toast.show('操作失败，请稍后重试', 'error');
        if (__DEV__) console.warn('[cards] action failed', descriptor.type, action.action);
      }
    };

    if (action.action !== 'route.open' && action.requires_manual_confirm) {
      const confirmation = action.confirmation;
      Alert.alert(
        confirmation?.title || action.label,
        confirmation?.detail || '确认后会写入你的健康记录。',
        [
          {
            text: confirmation?.cancel_label || '取消',
            style: 'cancel',
            onPress: () => { cardActionLocksRef.current.delete(actionKey); },
          },
          {
            text: confirmation?.confirm_label || action.label,
            onPress: execute,
          },
        ],
      );
      return;
    }

    await execute();
  }, [cardActionStateByKey, item.id, item.sourceMessageId, item.sourceTurnId, qc, toast]);

  const cardReceipts = Object.values(cardReceiptByKey);
  const latestCardReceipt = cardReceipts.length > 0 ? cardReceipts[cardReceipts.length - 1] : null;
  const directWriteReceipts = item.writeReceipts || [];
  const latestWriteReceipt = latestCardReceipt
    || (directWriteReceipts.length > 0 ? directWriteReceipts[directWriteReceipts.length - 1] : null);
  const cardSharePayload = useMemo(
    () => buildCardSharePayload(item.cardType, item.cardData, latestWriteReceipt),
    [item.cardData, item.cardType, latestWriteReceipt],
  );
  const handleCardShare = useCallback(async () => {
    if (!cardSharePayload) return;
    try { Haptics.selectionAsync(); } catch {}
    try {
      await sharePlainText(cardSharePayload);
    } catch { /* 用户取消分享也会走这里, 不打扰 */ }
  }, [cardSharePayload]);
  const captureCardScreenshot = useCallback(async () => {
    if (!cardFrameRef.current) return;
    return captureRef(cardFrameRef.current, {
      format: 'png',
      quality: 1,
      result: 'tmpfile',
    });
  }, []);
  const handleSaveCardScreenshot = useCallback(async () => {
    try { Haptics.selectionAsync(); } catch {}
    try {
      const uri = await captureCardScreenshot();
      if (!uri) return;
      await saveChatImageToLibrary({ uri });
      toast.show('已保存到照片', 'success');
    } catch {
      toast.show('保存截图失败，请稍后重试', 'error');
    }
  }, [captureCardScreenshot, toast]);
  const handleShareCardImage = useCallback(async (target: 'wechat' | 'xiaohongshu' | 'more' = 'more') => {
    try { Haptics.selectionAsync(); } catch {}
    try {
      const uri = await captureCardScreenshot();
      if (!uri) return;
      await shareLocalImage(uri);
    } catch {
      const targetName = target === 'wechat' ? '微信' : target === 'xiaohongshu' ? '小红书' : '图片';
      toast.show(`分享${targetName}失败，请稍后重试`, 'error');
    }
  }, [captureCardScreenshot, toast]);
  const openCardActions = useCallback(() => {
    if (!cardSharePayload || selectionMode) return;
    try { Haptics.selectionAsync(); } catch {}
    setShowCardActions(true);
  }, [cardSharePayload, selectionMode]);

  const cardDataRecord = item.cardData && typeof item.cardData === 'object' && !Array.isArray(item.cardData)
    ? item.cardData as Record<string, unknown>
    : null;
  const hasPendingDietDraftEditor = item.cardType === 'diet_draft'
    && latestWriteReceipt?.status !== 'verified';
  const hasRecordAdjustEditor = item.cardType === 'record_quality' && Boolean(
    cardDataRecord?.adjust_record
    || (Array.isArray(cardDataRecord?.expanded_sections)
      && cardDataRecord.expanded_sections.includes('adjust_record'))
    || item.cardActions?.some((action) => (
      action.action === 'ui.inline.expand'
      && action.payload?.target === 'adjust_record'
    )),
  );
  const hasEmbeddedCardEditor = hasPendingDietDraftEditor || hasRecordAdjustEditor;

  if (item.cardType && item.cardData) {
    const rendered = renderCard(
      { type: item.cardType, data: item.cardData, actions: item.cardActions },
      { onAction: handleCardAction, actionStateByKey: cardActionStateByKey },
    );
    if (rendered) {
      const cardContents = (
        <View ref={cardFrameRef} testID="assistant-card-capture-frame" collapsable={false}>
          {rendered}
          {latestWriteReceipt ? <WriteReceiptLine receipt={latestWriteReceipt} /> : null}
          {cardReceiptPersistenceWarning ? <WriteReceiptPersistenceWarning /> : null}
          <MessageTime label={sentTimeShort} isUser={false} />
        </View>
      );
      return (
        <View style={[styles.msgRow, styles.msgRowAI]}>
          <View testID="assistant-card-frame" style={styles.cardFrame}>
            {hasEmbeddedCardEditor ? (
              <View
                testID="assistant-editable-card-interaction-surface"
                accessibilityRole="summary"
                accessibilityLabel="可编辑健康卡片"
              >
                {cardContents}
              </View>
            ) : (
              <Pressable
                testID="assistant-card-interaction-surface"
                onLongPress={openCardActions}
                delayLongPress={350}
                accessibilityRole="summary"
                accessibilityLabel={cardSharePayload ? '长按卡片打开分享操作' : '健康卡片'}
              >
                {cardContents}
              </Pressable>
            )}
            {showCardActions && cardSharePayload && !selectionMode ? (
              <View testID="assistant-card-share-actions" style={styles.cardShareActions}>
                <Pressable
                  onPress={handleSaveCardScreenshot}
                  hitSlop={6}
                  accessibilityRole="button"
                  accessibilityLabel="保存卡片图片"
                  style={({ pressed }) => [styles.cardSaveButton, pressed && styles.actionBtnPressed]}
                >
                  <Ionicons name="image-outline" size={13} color={C.ink3} />
                  <Text style={txt.cardSaveButton}>保存图片</Text>
                </Pressable>
                <Pressable
                  onPress={() => handleShareCardImage('more')}
                  hitSlop={6}
                  accessibilityRole="button"
                  accessibilityLabel="分享卡片图片"
                  style={({ pressed }) => [styles.cardShareButton, pressed && styles.actionBtnPressed]}
                >
                  <Ionicons name="share-social-outline" size={13} color={C.green700} />
                  <Text style={txt.cardShareButton}>分享图片</Text>
                </Pressable>
                <Pressable
                  onPress={handleCardShare}
                  hitSlop={6}
                  accessibilityRole="button"
                  accessibilityLabel="分享卡片正文"
                  style={({ pressed }) => [styles.cardShareButton, pressed && styles.actionBtnPressed]}
                >
                  <Ionicons name="document-text-outline" size={13} color={C.green700} />
                  <Text style={txt.cardShareButton}>分享正文</Text>
                </Pressable>
                <Pressable
                  onPress={() => setShowCardActions(false)}
                  hitSlop={6}
                  accessibilityRole="button"
                  accessibilityLabel="收起卡片操作"
                  style={({ pressed }) => [styles.cardSaveButton, pressed && styles.actionBtnPressed]}
                >
                  <Ionicons name="close" size={13} color={C.ink3} />
                  <Text style={txt.cardSaveButton}>收起</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </View>
      );
    }
  }

  const hasTable = !isUser && containsMarkdownTable(displayText);

  const handleCopy = () => {
    Clipboard.setStringAsync(item.content);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setShowActions(false);
    setShowShareActions(false);
    toast.show('已复制', 'success');
  };

  const handleSaveImage = async (uri: string) => {
    const source = buildChatImageSource(uri, imageAuthToken);
    if (!source) {
      toast.show('图片需要登录后才能保存', 'info');
      return;
    }
    try {
      await saveChatImageToLibrary(source);
      try { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); } catch {}
      toast.show('已保存到相册', 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || '');
      if (message === 'photo_permission_denied') {
        Alert.alert('需要照片权限', '请在 iPhone 设置中允许小巴添加照片。');
        return;
      }
      toast.show('保存失败，请稍后重试', 'error');
      if (__DEV__) console.warn('[chat] save image failed', error);
    }
  };

  const handleImageLongPress = (uri: string) => {
    if (selectionMode) {
      onToggleSelected?.(item.id);
      return;
    }
    try { Haptics.selectionAsync(); } catch {}
    Alert.alert('图片', undefined, [
      { text: '保存到相册', onPress: () => { void handleSaveImage(uri); } },
      { text: '取消', style: 'cancel' },
    ]);
  };

  const renderMessageImages = () => {
    if (!images || images.length === 0) return null;
    return (
      <View style={styles.imageGrid}>
        {images.map((uri, i) => {
          const source = buildChatImageSource(uri, imageAuthToken);
          if (!source) return null;
          return (
            <TouchableOpacity
              key={`${uri}-${i}`}
              onPress={() => onViewImage?.(uri)}
              onLongPress={() => handleImageLongPress(uri)}
              activeOpacity={0.85}
              accessibilityRole="imagebutton"
              accessibilityLabel={`打开图片 ${i + 1}`}
            >
              <Image
                source={source}
                style={images.length === 1 ? styles.msgImageSingle : styles.msgImageGrid}
                contentFit="cover"
              />
            </TouchableOpacity>
          );
        })}
      </View>
    );
  };

  const openMessageActions = () => {
    if (selectionMode) {
      onToggleSelected?.(item.id);
      return;
    }
    Haptics.selectionAsync();
    setShowShareActions(false);
    setShowActions(prev => !prev);
  };

  const handleSelectMessage = () => {
    if (!onEnterSelection) return;
    setShowActions(false);
    setShowShareActions(false);
    try {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch {}
    onEnterSelection(item.id);
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
  const handleShare = async (target: 'wechat' | 'xiaohongshu' | 'more' = 'more') => {
    if (item.completionStatus === 'interrupted' || item.completionStatus === 'error') {
      toast.show('这条回复没有完整结束，暂不能分享。', 'info');
      return;
    }
    const message = target === 'xiaohongshu'
      ? buildXiaohongshuShareMessage(assistantTextForActions)
      : buildAiShareMessage(assistantTextForActions);
    if (!message) return;
    Haptics.selectionAsync();
    try {
      if (target === 'xiaohongshu') {
        await sharePlainCaption({
          title: '小巴 · 小红书文案',
          message,
        });
        toast.show('小红书文案已复制', 'success');
        return;
      }
      await sharePlainText({ title: '小巴 · 建议', message });
    } catch { /* 用户取消分享也会走这里, 不打扰 */ }
  };

  const handleMessageShare = async (target: 'xiaohongshu' | 'more' = 'more') => {
    setShowActions(false);
    setShowShareActions(false);
    if (isUser) {
      try {
        await sharePlainText({ title: '小巴 · 对话', message: item.content.trim() });
      } catch { /* 用户取消分享不打扰 */ }
      return;
    }
    await handleShare(target);
  };

  const handleSpeakFromMenu = () => {
    setShowActions(false);
    setShowShareActions(false);
    void handleSpeak();
  };

  const handleBubblePress = () => {
    if (selectionMode) {
      onToggleSelected?.(item.id);
      return;
    }
    if (showActions) {
      setShowActions(false);
      setShowShareActions(false);
    }
  };

  const renderMessageActions = () => {
    if (!showActions || selectionMode) return null;
    const canCopy = item.content.trim().length > 0;
    const canSelect = !!onEnterSelection;
    const canShare = canCopy && (
      isUser
      || (item.completionStatus !== 'interrupted' && item.completionStatus !== 'error')
    );
    const canSpeak = !isUser && !!assistantTextForActions;
    if (!canCopy && !canSelect && !canShare && !canSpeak) return null;

    if (showShareActions && !isUser) {
      return (
        <View style={styles.actionsRow}>
          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
            onPress={() => { void handleMessageShare('more'); }}
            accessibilityRole="button"
            accessibilityLabel="系统分享"
          >
            <Ionicons name="share-social-outline" size={14} color={C.green500} />
            <Text style={txt.actionBtn}>系统分享</Text>
          </Pressable>
          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
            onPress={() => { void handleMessageShare('xiaohongshu'); }}
            accessibilityRole="button"
            accessibilityLabel="小红书文案"
          >
            <Ionicons name="book-outline" size={14} color={C.green500} />
            <Text style={txt.actionBtn}>小红书文案</Text>
          </Pressable>
          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
            onPress={() => setShowShareActions(false)}
            accessibilityRole="button"
            accessibilityLabel="返回消息操作"
          >
            <Ionicons name="arrow-back" size={14} color={C.green500} />
            <Text style={txt.actionBtn}>返回</Text>
          </Pressable>
        </View>
      );
    }

    return (
      <View style={[styles.actionsRow, isUser && styles.actionsRowUser]}>
        {canCopy ? (
          <Pressable
            style={({ pressed }) => [styles.actionBtn, isUser && styles.actionBtnOnUser, pressed && styles.actionBtnPressed]}
            onPress={handleCopy}
            accessibilityRole="button"
            accessibilityLabel="复制全文"
          >
            <Ionicons name="copy-outline" size={14} color={isUser ? C.green700 : C.green500} />
            <Text style={[txt.actionBtn, isUser && txt.actionBtnOnUser]}>复制</Text>
          </Pressable>
        ) : null}
        {canSelect ? (
          <Pressable
            style={({ pressed }) => [styles.actionBtn, isUser && styles.actionBtnOnUser, pressed && styles.actionBtnPressed]}
            onPress={handleSelectMessage}
            accessibilityRole="button"
            accessibilityLabel="选择这条消息"
          >
            <Ionicons name="checkbox-outline" size={14} color={isUser ? C.green700 : C.green500} />
            <Text style={[txt.actionBtn, isUser && txt.actionBtnOnUser]}>选择</Text>
          </Pressable>
        ) : null}
        {canShare ? (
          <Pressable
            style={({ pressed }) => [styles.actionBtn, isUser && styles.actionBtnOnUser, pressed && styles.actionBtnPressed]}
            onPress={() => {
              if (isUser) {
                void handleMessageShare('more');
              } else {
                setShowShareActions(true);
              }
            }}
            accessibilityRole="button"
            accessibilityLabel={isUser ? '分享这条消息' : '分享这条回复'}
          >
            <Ionicons name="share-social-outline" size={14} color={isUser ? C.green700 : C.green500} />
            <Text style={[txt.actionBtn, isUser && txt.actionBtnOnUser]}>分享</Text>
          </Pressable>
        ) : null}
        {canSpeak ? (
          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
            onPress={handleSpeakFromMenu}
            accessibilityRole="button"
            accessibilityLabel={speaking ? '停止播报' : '语音播报'}
          >
            <Ionicons
              name={speaking ? 'stop-circle' : 'volume-high-outline'}
              size={14}
              color={C.green500}
            />
            <Text style={txt.actionBtn}>{speaking ? '停止' : '朗读'}</Text>
          </Pressable>
        ) : null}
      </View>
    );
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
        {isUser ? (
          <TouchableOpacity
            style={[styles.bubble, styles.bubbleUser, selected && styles.bubbleSelected]}
            activeOpacity={0.8}
            onPress={handleBubblePress}
            onLongPress={selectionMode ? undefined : openMessageActions}
            accessibilityRole="text"
            accessibilityLabel={`${timeAccessibilityPrefix}你: ${item.content}${item.fromSiri ? ' (来自 Siri)' : ''}`}
            accessibilityState={selectionMode ? { selected } : undefined}
          >
            {item.fromSiri && (
              <View style={styles.siriBadge} accessibilityLabel="来自 Siri">
                <Ionicons name="sparkles" size={11} color="#fff" />
              </View>
            )}
            {renderMessageImages()}
            {displayText ? <Text style={txt.bubbleUser}>{displayText}</Text> : null}
            <MessageTime label={sentTimeShort} isUser />
            {renderMessageActions()}
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            testID="assistant-message-surface"
            style={[styles.bubble, styles.bubbleAI, hasTable && styles.bubbleAIWide, selected && styles.bubbleSelected]}
            activeOpacity={hasInlineEditableCard ? 1 : 0.95}
            disabled={hasInlineEditableCard}
            onPress={hasInlineEditableCard ? undefined : handleBubblePress}
            onLongPress={hasInlineEditableCard ? undefined : openMessageActions}
            accessibilityRole={hasInlineEditableCard ? undefined : 'text'}
            accessibilityLabel={hasInlineEditableCard ? undefined : `${timeAccessibilityPrefix}AI: ${assistantTextForActions || (revaUiContent.cards.length > 0 ? '图表卡片' : item.content)}`}
            accessibilityState={selectionMode ? { selected } : undefined}
          >
            {renderMessageImages()}
            {item.streaming && showProcessingPanel ? (
              <ThinkingStepsPanel
                steps={thinkingSteps}
                streaming={item.streaming}
                statusLabel={processingStatusLabel}
                onStop={onStopStreaming}
              />
            ) : null}
            {advisorPresentation?.conclusion ? (
              <AssistantConclusion text={advisorPresentation.conclusion} />
            ) : null}
            {structuredSummary ? (
              <StructuredSummaryCard
                summary={structuredSummary}
                showEyebrow={!advisorPresentation?.conclusion}
                onAddToTodayPlan={openTodayPlanDraft}
                onSendSuggestedPrompt={onSendSuggestedPrompt}
              />
            ) : null}
            {visibleAssistantMarkdown ? (
              <SafeMarkdown content={renderedMarkdown} fallbackText={visibleAssistantMarkdown} />
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
            {latestWriteReceipt ? <WriteReceiptLine receipt={latestWriteReceipt} /> : null}
            {cardReceiptPersistenceWarning ? <WriteReceiptPersistenceWarning /> : null}
            {!item.streaming
              && item.completionStatus !== 'interrupted'
              && item.completionStatus !== 'error'
              && assistantTextForActions ? (
              <AssistantUtilityPanel
                profile={transparency}
                sources={item.sourcesUsed}
                thinkingSteps={thinkingSteps}
                onOpenMemory={() => router.push('/memory')}
                onShareWeChat={() => { void handleShare('wechat'); }}
                onShareXiaohongshu={() => { void handleShare('xiaohongshu'); }}
              />
            ) : null}
            {!item.streaming
              && item.completionStatus !== 'interrupted'
              && item.completionStatus !== 'error'
              && assistantTextForActions ? (
              <View style={styles.conclusionCopyRow}>
                <Pressable
                  style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
                  onPress={handleCopy}
                  accessibilityRole="button"
                  accessibilityLabel="复制回答"
                  hitSlop={6}
                >
                  <Ionicons name="copy-outline" size={14} color={C.green500} />
                  <Text style={txt.actionBtn}>复制</Text>
                </Pressable>
              </View>
            ) : null}
            <MessageTime label={sentTimeShort} isUser={false} />
            {renderMessageActions()}
          </TouchableOpacity>
        )}
      </View>
      <InterventionDraftSheet
        visible={!!todayPlanDraft}
        draft={todayPlanDraft}
        isSaving={savingTodayPlan}
        onClose={() => setTodayPlanDraft(null)}
        onSubmit={submitTodayPlanDraft}
      />
    </>
  );
}

function parseMessageDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatMessageTimeLabel(value?: string | null): string {
  const date = parseMessageDate(value);
  if (!date) return '';
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function formatMessageFullTimeLabel(value?: string | null): string {
  const date = parseMessageDate(value);
  if (!date) return '';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function MessageTime({ label, isUser }: { label: string; isUser: boolean }) {
  if (!label) return null;
  return (
    <Text
      testID="message-time"
      style={[styles.messageTime, isUser ? styles.messageTimeUser : styles.messageTimeAI]}
    >
      {label}
    </Text>
  );
}

function WriteReceiptLine({ receipt }: { receipt: WriteReceipt }) {
  return (
    <View
      testID="write-receipt"
      style={styles.writeReceipt}
      accessibilityRole="text"
      accessibilityLabel={formatWriteReceipt(receipt)}
    >
      <Ionicons name="checkmark-circle" size={14} color={C.green600} />
      <Text style={styles.writeReceiptText}>{formatWriteReceipt(receipt)}</Text>
    </View>
  );
}

function WriteReceiptPersistenceWarning() {
  return (
    <View
      testID="write-receipt-warning"
      style={styles.writeReceiptWarning}
      accessibilityRole="alert"
    >
      <Ionicons name="warning-outline" size={14} color={revaSemantic.caution.fg} />
      <Text style={styles.writeReceiptWarningText}>
        已写入，但本机未保存防重复凭证
      </Text>
    </View>
  );
}

function cardText(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (Array.isArray(value)) {
    const joined = value.map(cardText).filter(Boolean).join(' + ');
    return joined || undefined;
  }
  return undefined;
}

function cardNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function cardMealLabel(value: unknown): string {
  const raw = cardText(value);
  if (raw === 'breakfast' || raw === '早餐') return '早餐';
  if (raw === 'lunch' || raw === '午餐') return '午餐';
  if (raw === 'dinner' || raw === '晚餐') return '晚餐';
  if (raw === 'snack' || raw === '加餐' || raw === '夜宵') return '加餐';
  return '这餐';
}

function buildCardSharePayload(
  cardType?: string,
  cardData?: unknown,
  latestWriteReceipt?: WriteReceipt | null,
): { title: string; message: string } | null {
  if (!cardData || typeof cardData !== 'object' || Array.isArray(cardData)) {
    return null;
  }
  const data = cardData as Record<string, unknown>;
  if (cardType === 'record_quality') return buildDietQualitySharePayload(data);
  if (cardType !== 'diet_draft') return null;
  if (latestWriteReceipt?.resourceType !== 'diet_record' || latestWriteReceipt.status !== 'verified') return null;
  return buildDietDraftSharePayload(data);
}

function buildDietDraftSharePayload(data: Record<string, unknown>): { title: string; message: string } {
  const meal = cardMealLabel(data.meal_type);
  const food = cardText(data.food_items);
  const calories = cardNumber(data.calories);
  const protein = cardNumber(data.protein);
  const carbs = cardNumber(data.carbs);
  const fat = cardNumber(data.fat);
  const suggestions = Array.isArray(data.suggestions)
    ? data.suggestions.map(cardText).filter((item): item is string => Boolean(item))
    : [];

  const lines = ['今日饮食打卡', '今天这餐被小巴认真记下来了', ''];
  lines.push(food ? `${meal} · ${food}` : meal);

  const macroParts = [
    calories != null ? `${Math.round(calories)} kcal` : null,
    protein != null ? `蛋白 ${Math.round(protein)}g` : null,
    carbs != null ? `碳水 ${Math.round(carbs)}g` : null,
    fat != null ? `脂肪 ${Math.round(fat)}g` : null,
  ].filter(Boolean);
  if (macroParts.length > 0) lines.push('', '营养概览', macroParts.join(' · '));
  if (suggestions[0]) lines.push('', '今日策略', `下一步：${suggestions[0]}`);
  lines.push('', '#小红书饮食日记 #朋友圈打卡 #小巴', '', '— 小巴');

  return {
    title: '小巴 · 饮食记录',
    message: lines.join('\n'),
  };
}

function buildDietQualitySharePayload(data: Record<string, unknown>): { title: string; message: string } | null {
  if (cardText(data.domain) !== 'diet') return null;
  const progress = data.progress && typeof data.progress === 'object' && !Array.isArray(data.progress)
    ? data.progress as Record<string, unknown>
    : {};
  const title = cardText(data.title);
  const summary = cardText(data.summary);
  const caloriesTotal = cardNumber(progress.calories_total);
  const mealsCount = cardNumber(progress.meals_count);
  const proteinTotal = cardNumber(progress.protein_total_g);
  const proteinTarget = cardNumber(progress.protein_target_g);
  const remainingProtein = cardNumber(progress.remaining_protein_g);
  const nextAction = cardText(data.next_action);

  const lines = ['今日饮食打卡', '今天这餐被小巴认真记下来了', ''];
  if (title) lines.push(title);
  if (summary) lines.push(summary);
  if (caloriesTotal != null) {
    lines.push('', '营养概览', `今日摄入 ${Math.round(caloriesTotal)} kcal${mealsCount != null ? ` · ${Math.round(mealsCount)} 餐` : ''}`);
  }
  if (proteinTotal != null && proteinTarget != null) {
    const remaining = remainingProtein != null ? ` · 还差约 ${Math.round(remainingProtein)}g` : '';
    lines.push(`蛋白进度 ${Math.round(proteinTotal)}/${Math.round(proteinTarget)}g${remaining}`);
  }
  if (nextAction) lines.push('', '今日策略', `下一步：${nextAction}`);
  lines.push('', '#小红书饮食日记 #朋友圈打卡 #小巴', '', '— 小巴');

  return {
    title: '小巴 · 饮食记录',
    message: lines.join('\n'),
  };
}

function isWriteCardAction(action: ChatCardActionDescriptor): boolean {
  return [
    'agenda.complete',
    'daily_plan_action.complete',
    'diet_record.create',
    'write_intent.confirm',
    'write_intent.dismiss',
  ].includes(action.action);
}

function formatWriteReceipt(receipt: WriteReceipt): string {
  if (receipt.resourceType === 'diet_record') {
    return receipt.status === 'dismissed'
      ? `已忽略 · 饮食记录 #${receipt.resourceId}`
      : `已保存到今日饮食 · 记录 #${receipt.resourceId}`;
  }
  const resourceLabels: Record<string, string> = {
    agenda_event: '今日行动',
    intervention_event: '今日行动',
    diet_record: '饮食记录',
    write_intent: '待确认项',
    smart_reminder: '提醒',
    health_record: '健康记录',
  };
  const verb = receipt.status === 'dismissed' ? '已忽略' : '已写入';
  const resourceLabel = resourceLabels[receipt.resourceType] || '健康数据';
  return `${verb} · ${resourceLabel} #${receipt.resourceId}`;
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
  if (action.action === 'daily_plan_action.complete') return '已完成今日行动';
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

interface ParsedTodayAdvice {
  items: string[];
  consumedLineIndexes: Set<number>;
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

  const advice = parseTodayAdvice(lines).items;

  if (metrics.length === 0 && advice.length === 0) return null;
  return { metrics, advice };
}

function isMeaningfulAdvice(value: string): boolean {
  const normalized = value
    .replace(/[\s\-—–_.。·]/g, '')
    .replace(/[✅⚠️❌]/g, '')
    .trim();
  if (!normalized) return false;
  return !/^(?:无|暂无|暂无建议|无建议|待补充|待生成|na|n\/a)$/i.test(normalized);
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

function normalizeAdviceHeader(line: string): string {
  return line
    .trim()
    .replace(/^#{1,6}\s*/, '')
    .replace(/^>\s*/, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/^[📌💡✅🌿✨]\uFE0F?\s*/u, '')
    .replace(/[：:]\s*$/, '')
    .trim();
}

function isTodayAdviceHeader(line: string): boolean {
  return /^(?:今日|今天)(?:建议|行动)$/.test(normalizeAdviceHeader(line));
}

function isSectionTitleAdvice(rawLine: string, cleaned: string): boolean {
  const normalized = cleaned
    .replace(/^[^\u3400-\u9FFFA-Za-z0-9]*/u, '')
    .trim();
  if (/^#{1,6}\s*/.test(rawLine.trim())) return true;
  if (/^[一二三四五六七八九十]+[、.．)]/.test(normalized)) return true;
  if (normalized.length <= 28 && /(?:状态|概况|清单|总结|分析|说明|注意事项|方案|安排|原则|策略|重点)$/.test(normalized)) {
    return true;
  }
  return false;
}

function isMedicationAdvice(value: string): boolean {
  const medicationTerm = /药|服用|处方|剂量|加量|减量|胶囊|注射|胰岛素|喷剂|滴剂|补剂|补充剂|保健品|维生素|益生菌|鱼油|叶酸/i;
  const medicationDose = /\d+(?:\.\d+)?\s*(?:mg|毫克|iu|单位)/i;
  return medicationTerm.test(value) || medicationDose.test(value);
}

function isBounded(value: string | undefined, min: number, max: number): boolean {
  if (!value) return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min && parsed <= max;
}

function isSafeHydrationAction(value: string): boolean {
  const match = value.match(
    /^(?:饮水未达标[，,]\s*)?(?:(?:今天|今日|今晚|上午|下午|早上|中午|睡前|起床后|饭后|餐后)\s*)?(?:先|优先|记得|请)?(?:补充|补水|喝水|饮水)\s*(?:约\s*)?(\d{2,4})\s*(?:ml|毫升)$/i,
  );
  return isBounded(match?.[1], 100, 500);
}

function isSafeMovementAction(value: string): boolean {
  const match = value.match(
    /^(?:(?:今天|今日|今晚|上午|下午|饭后|餐后)\s*)?(?:先|优先|只做|安排)?\s*(?:轻松|低强度)?(?:步行|散步|走路|拉伸|轻活动|恢复活动)\s*(?:约\s*)?(\d+)\s*(分钟|步)$/,
  );
  if (!match) return false;
  return match[2] === '分钟'
    ? isBounded(match[1], 5, 60)
    : isBounded(match[1], 100, 5000);
}

function isSafeSleepAction(value: string): boolean {
  const match = value.match(
    /^(?:今天|今日|今晚)\s*(?:提前\s*)?(\d{1,2})(?::(\d{2})|点(半)?)\s*(?:前)?(?:上床|睡觉|休息)$/,
  );
  if (!match) return false;
  const hour = Number(match[1]);
  const minute = match[2] ? Number(match[2]) : match[3] ? 30 : 0;
  return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
}

function isSafeScreenCutoffAction(value: string): boolean {
  const match = value.match(
    /^(?:睡前|今晚睡前)\s*(\d+)\s*分钟(?:停止|暂停)(?:看|使用)?(?:手机|屏幕|电子设备)$/,
  );
  return isBounded(match?.[1], 10, 180);
}

function isSafeMeasurementAction(value: string): boolean {
  return /^(?:今天|今日|今晚|明早|起床后)\s*(?:记录|测量|监测)\s*(?:体重|腰围|血压|血糖|症状|饮水|睡眠)(?:\s*(?:一次|1次))?$/.test(value)
    || /^(?:记录|测量|监测)\s*(?:体重|腰围|血压|血糖|症状|饮水|睡眠)\s*(?:一次|1次)$/.test(value);
}

function isSafeCareContactAction(value: string): boolean {
  return /^(?:今天|今日|本周)\s*(?:预约|联系|咨询)\s*(?:医生|门诊|科室|体检|复查)$/.test(value);
}

function isExecutableTodayAdvice(value: string): boolean {
  if (value.length > 96 || /[：:]\s*$/.test(value) || isMedicationAdvice(value)) return false;
  const normalized = value.replace(/^[✅⚠️❌🌿✨]\uFE0F?\s*/u, '').trim();
  return isSafeHydrationAction(normalized)
    || isSafeMovementAction(normalized)
    || /^(?:今天|今日|今晚)\s*(?:先|优先)?\s*(?:暂停|停止)高强度(?:训练|运动)[，,]\s*(?:优先)?(?:睡眠|休息|轻活动|恢复活动)(?:与(?:睡眠|休息|轻活动|恢复活动))*$/.test(normalized)
    || isSafeSleepAction(normalized)
    || isSafeScreenCutoffAction(normalized)
    || isSafeMeasurementAction(normalized)
    || isSafeCareContactAction(normalized);
}

function parseTodayAdvice(lines: string[]): ParsedTodayAdvice {
  const headerIndex = lines.findIndex(isTodayAdviceHeader);
  if (headerIndex < 0) return { items: [], consumedLineIndexes: new Set() };

  const items: string[] = [];
  const consumedLineIndexes = new Set<number>([headerIndex]);
  for (let index = headerIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^\s*\|/.test(line)) continue;
    const cleaned = cleanAdviceMarkdown(line);
    if (!cleaned) {
      continue;
    }
    if (isSectionTitleAdvice(line, cleaned)) {
      return { items: [], consumedLineIndexes: new Set() };
    }
    if (!isMeaningfulAdvice(cleaned) || !isExecutableTodayAdvice(cleaned)) {
      return { items: [], consumedLineIndexes: new Set() };
    }
    if (items.length >= 3) return { items: [], consumedLineIndexes: new Set() };
    items.push(cleaned);
    consumedLineIndexes.add(index);
  }

  if (items.length === 0) return { items: [], consumedLineIndexes: new Set() };
  return { items, consumedLineIndexes };
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
  const adviceLineIndexes = parseTodayAdvice(lines).consumedLineIndexes;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();

    if (adviceLineIndexes.has(i)) continue;

    if (isMetricTableStart(lines, i)) {
      skipTable = true;
      i += 1;
      continue;
    }
    if (skipTable) {
      if (trimmed.startsWith('|')) continue;
      skipTable = false;
    }

    kept.push(line);
  }

  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

interface AdvisorPresentation {
  conclusion: string;
  details: string;
}

function cleanConclusionText(value: string): string {
  return value
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^>\s*/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s*\n\s*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function parseAdvisorPresentation(text: string): AdvisorPresentation | null {
  const trimmed = text.trim();
  if (!trimmed || /^\s*(?:\||```|[-*+]\s|\d+[.)、]\s)/.test(trimmed)) return null;
  if (/^(?:✅\s*)?(?:已记录|已删除|已更新|已修改|已保存|已撤销|已取消|记录成功|删除成功)/.test(
    cleanConclusionText(trimmed),
  )) return null;

  const blocks = trimmed.split(/\n\s*\n/).filter(Boolean);
  if (blocks.length === 0) return null;
  let firstBlock = blocks[0];
  let remainingBlocks = blocks.slice(1);

  if (firstBlock.length > 150) {
    const relativeSentenceEnd = firstBlock.slice(30, 130).search(/[。！？!?]/);
    if (relativeSentenceEnd >= 0) {
      const splitAt = relativeSentenceEnd + 31;
      const rest = firstBlock.slice(splitAt).trim();
      firstBlock = firstBlock.slice(0, splitAt).trim();
      if (rest) remainingBlocks = [rest, ...remainingBlocks];
    }
  }

  const conclusion = cleanConclusionText(firstBlock);
  if (!conclusion) return null;
  return { conclusion, details: remainingBlocks.join('\n\n').trim() };
}

class MarkdownRenderBoundary extends React.Component<
  { resetKey: string; fallbackText: string; children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(prevProps: { resetKey: string }) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.failed) {
      this.setState({ failed: false });
    }
  }

  componentDidCatch(error: unknown) {
    if (__DEV__) console.warn('[chat] markdown render failed; showing plain-text fallback', error);
  }

  render() {
    if (this.state.failed) {
      return <Text style={txt.streaming}>{this.props.fallbackText}</Text>;
    }
    return this.props.children;
  }
}

function SafeMarkdown({ content, fallbackText }: { content: string; fallbackText: string }) {
  const safeContent = prepareSafeMarkdown(content);
  return (
    <MarkdownRenderBoundary resetKey={content} fallbackText={fallbackText}>
      <Markdown style={MD_STYLES} markdownit={safeMarkdownIt}>{safeContent}</Markdown>
    </MarkdownRenderBoundary>
  );
}

function AssistantConclusionLabel() {
  return (
    <View style={summaryStyles.conclusionLabelRow}>
      <View testID="assistant-conclusion-dot" style={summaryStyles.conclusionDot} />
      <Text style={summaryStyles.conclusionLabel}>小巴结论</Text>
    </View>
  );
}

function AssistantConclusion({ text }: { text: string }) {
  return (
    <View testID="assistant-conclusion" style={summaryStyles.conclusion}>
      <AssistantConclusionLabel />
      <Text style={summaryStyles.conclusionText}>{text}</Text>
    </View>
  );
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
  showEyebrow,
  onAddToTodayPlan,
  onSendSuggestedPrompt,
}: {
  summary: StructuredHealthSummary;
  showEyebrow: boolean;
  onAddToTodayPlan?: (advice: string) => void;
  onSendSuggestedPrompt?: (prompt: string) => void;
}) {
  const primaryAdvice = summary.advice[0];
  const secondaryAdvice = summary.advice.slice(1);
  return (
    <View style={summaryStyles.card}>
      {showEyebrow ? (
        <AssistantConclusionLabel />
      ) : null}
      {summary.metrics.length > 0 ? (
          <View testID="assistant-metric-grid" style={summaryStyles.metrics}>
            {summary.metrics.map((metric, index) => (
              <View
                key={`${metric.label}-${metric.value}`}
                testID={`assistant-metric-cell-${index}`}
                style={summaryStyles.metricCell}
              >
                <Text style={summaryStyles.metricLabel} numberOfLines={1}>
                  {metric.label}
                </Text>
                <Text style={summaryStyles.metricValue} numberOfLines={2}>
                  {metric.value}
                </Text>
                {metric.status ? (
                  <Text style={[summaryStyles.metricStatus, { color: statusTone(metric.status) }]} numberOfLines={1}>
                    {metric.status}
                  </Text>
                ) : null}
              </View>
            ))}
          </View>
      ) : null}

      {primaryAdvice ? (
        <View testID="assistant-action-card" style={summaryStyles.actionCard}>
          <Text style={summaryStyles.actionEyebrow}>今天只做</Text>
          <Text style={summaryStyles.actionTitle}>{primaryAdvice}</Text>
          {secondaryAdvice.length > 0 ? (
            <View style={summaryStyles.actionSecondaryList}>
              {secondaryAdvice.map(item => (
                <View key={item} style={summaryStyles.actionSecondaryRow}>
                  <View style={summaryStyles.actionSecondaryDot} />
                  <Text style={summaryStyles.actionSecondary}>{item}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {onAddToTodayPlan || onSendSuggestedPrompt ? (
            <View style={summaryStyles.actionButtons}>
              {onAddToTodayPlan ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="把建议加入今天计划"
                  onPress={() => onAddToTodayPlan(primaryAdvice)}
                  style={({ pressed }) => [summaryStyles.actionPrimary, pressed && styles.actionBtnPressed]}
                >
                  <Text style={summaryStyles.actionPrimaryText}>加入今天</Text>
                </Pressable>
              ) : null}
              {onSendSuggestedPrompt ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="解释这条建议的依据"
                  onPress={() => onSendSuggestedPrompt(`解释为什么建议我：${primaryAdvice}`)}
                  style={({ pressed }) => [summaryStyles.actionSecondaryButton, pressed && styles.actionBtnPressed]}
                >
                  <Text style={summaryStyles.actionSecondaryButtonText}>为什么</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const ChatBubble = React.memo(ChatBubbleInner);
export default ChatBubble;

const summaryStyles = StyleSheet.create({
  conclusion: {
    marginBottom: 12,
    gap: 5,
  },
  conclusionLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  conclusionDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: C.green500,
  },
  conclusionLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
    letterSpacing: 0,
    color: C.green600,
  } as TextStyle,
  conclusionText: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 23,
    fontWeight: '400',
    letterSpacing: 0,
    color: C.ink1,
  } as TextStyle,
  card: {
    marginBottom: 12,
    gap: 10,
  },
  metrics: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    overflow: 'hidden',
  },
  metricCell: {
    minWidth: '33.333%',
    flexGrow: 1,
    flexBasis: 0,
    minHeight: 74,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: C.line,
  },
  metricLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 15,
    fontWeight: '700',
    color: C.ink3,
  } as TextStyle,
  metricValue: {
    marginTop: 3,
    fontFamily: revaFonts.mono,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '900',
    color: C.ink1,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  metricStatus: {
    marginTop: 3,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    lineHeight: 14,
    fontWeight: '800',
  } as TextStyle,
  actionCard: {
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    borderLeftWidth: 3,
    borderLeftColor: C.green300,
    backgroundColor: C.surface2,
    paddingHorizontal: 14,
    paddingVertical: 13,
    gap: 6,
  },
  actionEyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 15,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  actionTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 15.5,
    lineHeight: 22,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  actionSecondaryList: { gap: 2 },
  actionSecondaryRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  actionSecondaryDot: { width: 3, height: 3, borderRadius: 2, marginTop: 7, backgroundColor: C.green300 },
  actionSecondary: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 17,
    color: C.ink2,
  } as TextStyle,
  actionButtons: {
    marginTop: 5,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  actionPrimary: {
    minHeight: 38,
    flex: 1,
    borderRadius: 8,
    backgroundColor: C.green500,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  actionPrimaryText: {
    fontFamily: revaFonts.sans,
    fontSize: 12.5,
    fontWeight: '900',
    color: C.greenOn,
  } as TextStyle,
  actionSecondaryButton: {
    minHeight: 38,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
    paddingHorizontal: 12,
  },
  actionSecondaryButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 12.5,
    fontWeight: '800',
    color: C.ink2,
  } as TextStyle,
});

// Reva 设计语言: 用户气泡 green500, AI 正文无框,结构化对象使用独立卡片. 数字/耗时走 mono.
const styles = StyleSheet.create({
  msgRow: { flexDirection: 'row', marginBottom: 14, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  cardFrame: { flex: 1, minWidth: 0, maxWidth: '100%' },
  cardShareActions: {
    marginTop: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
  },
  cardShareButton: {
    minHeight: 30,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.green50,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  cardSaveButton: {
    minHeight: 30,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  inlineCardStack: { marginTop: 10, gap: 8 },
  writeReceipt: {
    minHeight: 28,
    marginTop: 8,
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.green50,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    alignSelf: 'flex-start',
    maxWidth: '100%',
  },
  writeReceiptText: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.green700,
    fontWeight: '600',
  } as TextStyle,
  writeReceiptWarning: {
    minHeight: 28,
    marginTop: 8,
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: revaSemantic.caution.bg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    alignSelf: 'flex-start',
    maxWidth: '100%',
  },
  writeReceiptWarningText: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: revaSemantic.caution.fg,
    fontWeight: '600',
  } as TextStyle,
  bubble: { maxWidth: '82%', borderRadius: 14, paddingHorizontal: 13, paddingVertical: 9 },
  bubbleUser: { backgroundColor: C.green500, borderBottomRightRadius: 5 },
  messageTime: {
    marginTop: 6,
    fontFamily: revaFonts.mono,
    fontSize: 10.5,
    lineHeight: 14,
    fontWeight: '600',
    letterSpacing: 0,
  } as TextStyle,
  messageTimeUser: {
    alignSelf: 'flex-end',
    color: 'rgba(255,255,255,0.72)',
  } as TextStyle,
  messageTimeAI: {
    alignSelf: 'flex-start',
    color: C.ink3,
  } as TextStyle,
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
    flex: 1,
    maxWidth: '100%',
    alignSelf: 'stretch',
    borderRadius: 0,
    paddingHorizontal: 0,
    paddingVertical: 2,
    backgroundColor: 'transparent',
    shadowOpacity: 0,
    elevation: 0,
  },
  bubbleAIWide: { flex: 1, maxWidth: '94%', flexShrink: 1, alignSelf: 'stretch' },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
  msgImageSingle: { width: 160, height: 120, borderRadius: 10 },
  msgImageGrid: { width: 72, height: 72, borderRadius: 8 },
  thinkingPanel: {
    alignSelf: 'stretch',
    width: '100%',
    maxWidth: '100%',
    gap: 8,
    marginBottom: 10,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  thinkingAnalysisCard: {
    alignSelf: 'stretch',
    width: '100%',
    marginBottom: 12,
    borderRadius: revaRadii.xs,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderLeftWidth: 3,
    borderLeftColor: C.green300,
    backgroundColor: C.surface2,
    overflow: 'hidden',
  },
  thinkingAnalysisHeader: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  thinkingIndicatorWrap: {
    width: 26,
    height: 26,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  thinkingAnalysisCopy: { flex: 1, minWidth: 0, gap: 2 },
  thinkingStopButton: { minHeight: 32, justifyContent: 'center', paddingHorizontal: 4 },
  thinkingAnalysisSteps: {
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  thinkingAnalysisStepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  thinkingAnalysisStepIcon: {
    width: 18,
    height: 18,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green500,
  },
  thinkingAnalysisStepIconActive: {
    backgroundColor: C.paper,
    borderWidth: 1.5,
    borderColor: C.green500,
  },
  thinkingSkeleton: {
    gap: 7,
    paddingHorizontal: 12,
    paddingTop: 3,
    paddingBottom: 11,
  },
  thinkingSkeletonLine: {
    height: 8,
    borderRadius: 4,
    backgroundColor: C.paper2,
  },
  // 完成态: 低干扰内联状态行, 展开时在下方补步骤列表.
  thinkingPill: {
    alignSelf: 'flex-start',
    minWidth: 132,
    maxWidth: '100%',
    marginBottom: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    overflow: 'hidden',
  },
  thinkingPillStreaming: {
    minWidth: 220,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.paper2,
  },
  thinkingPillExpanded: {
    alignSelf: 'stretch',
    width: '100%',
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.paper2,
  },
  thinkingPillHeader: {
    minHeight: 22,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  thinkingPillCopy: {
    flex: 1,
    minWidth: 0,
  },
  thinkingDoneCopy: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  thinkingPillList: {
    gap: 6,
    minWidth: 240,
    paddingHorizontal: 9,
    paddingBottom: 8,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.green100,
  },
  thinkingPillListExpanded: {
    minWidth: 0,
    width: '100%',
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
    alignItems: 'flex-start',
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
  actionsRowUser: {
    borderTopColor: 'rgba(255,255,255,0.24)',
    justifyContent: 'flex-end',
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
  actionBtnOnUser: {
    backgroundColor: 'rgba(255,255,255,0.92)',
  },
  actionBtnPressed: { opacity: 0.82 },
  conclusionCopyRow: {
    flexDirection: 'row',
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  assistantUtilityPanel: {
    alignSelf: 'stretch',
    width: '100%',
    marginTop: 12,
  },
  assistantUtilityRail: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 10,
    backgroundColor: C.paper2,
    paddingHorizontal: 4,
  },
  assistantUtilityEvidence: {
    minHeight: 38,
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 8,
  },
  assistantUtilitySpacer: { flex: 1 },
  assistantUtilityDivider: {
    width: StyleSheet.hairlineWidth,
    height: 18,
    backgroundColor: C.line,
  },
  assistantUtilityShare: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
  },
  // 分享入口品牌 badge:白色 glyph 落在平台品牌色圆角块上(微信绿 / 小红书红),
  // 品牌色由 SOCIAL_BRAND(constants/brand.ts)提供,组件不裸写 hex(过 design 闸)。
  shareBadgeWeChat: {
    width: 18, height: 18, borderRadius: 5,
    backgroundColor: SOCIAL_BRAND.wechat,
    alignItems: 'center', justifyContent: 'center',
  },
  shareBadgeXhs: {
    width: 18, height: 18, borderRadius: 5,
    backgroundColor: SOCIAL_BRAND.xiaohongshu,
    alignItems: 'center', justifyContent: 'center',
  },
  assistantUtilityDetails: {
    marginTop: 7,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    paddingHorizontal: 11,
    paddingVertical: 10,
    gap: 12,
  },
  assistantUtilitySection: { gap: 7 },
  assistantUtilityThoughts: { gap: 6 },
  assistantUtilityThoughtRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  transparencyPanel: {
    marginTop: 9,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper2,
    overflow: 'hidden',
  },
  transparencyPanelCollapsed: {
    alignSelf: 'flex-start',
    maxWidth: '100%',
    borderRadius: revaRadii.pill,
  },
  transparencyPanelOpen: {
    alignSelf: 'stretch',
    borderRadius: 14,
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
  thinkingAnalysisEyebrow: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, fontWeight: '900', color: C.green600 } as TextStyle,
  thinkingAnalysisTitle: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 20, fontWeight: '800', color: C.ink1 } as TextStyle,
  thinkingStop: { fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 16, fontWeight: '800', color: C.ink3 } as TextStyle,
  thinkingAnalysisStep: { flex: 1, fontFamily: revaFonts.sans, fontSize: 12.5, lineHeight: 18, fontWeight: '700', color: C.ink3 } as TextStyle,
  thinkingAnalysisStepActive: { color: C.ink1, fontWeight: '900' } as TextStyle,
  thinkingAnalysisStepNumber: { fontFamily: revaFonts.mono, fontSize: 10, lineHeight: 13, fontWeight: '900', color: C.green600 } as TextStyle,
  thinkingPillLabel: { flex: 1, minWidth: 0, fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 16, fontWeight: '800', color: C.ink3 } as TextStyle,
  thinkingDoneLabel: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 16, fontWeight: '900', color: C.green700 } as TextStyle,
  thinkingDoneMeta: { fontFamily: revaFonts.sans, fontSize: 11.2, lineHeight: 16, fontWeight: '800', color: C.ink3 } as TextStyle,
  thinkingLatestStep: { fontFamily: revaFonts.sans, fontSize: 12.2, lineHeight: 17, fontWeight: '800', color: C.ink1 } as TextStyle,
  thinkingTitle: { fontFamily: revaFonts.sans, fontSize: 12.5, lineHeight: 17, fontWeight: '900', color: C.ink1 } as TextStyle,
  thinkingSubtitle: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, color: C.ink3 } as TextStyle,
  thinkingProgressText: { fontFamily: revaFonts.mono, fontSize: 10.5, lineHeight: 13, fontWeight: '800', color: C.green700 } as TextStyle,
  thinkingStepIndex: { fontFamily: revaFonts.mono, fontSize: 10, lineHeight: 13, fontWeight: '900', color: C.green700 } as TextStyle,
  thinkingStepIndexActive: { color: C.greenOn } as TextStyle,
  thinkingStep: { flex: 1, fontFamily: revaFonts.sans, fontSize: 12.2, lineHeight: 18, color: C.ink2, fontWeight: '600' } as TextStyle,
  actionBtn: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '700', color: C.green500 } as TextStyle,
  actionBtnOnUser: { color: C.green700 } as TextStyle,
  assistantUtilityEvidence: { flex: 1, minWidth: 0, fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 16, fontWeight: '800', color: C.ink2 } as TextStyle,
  assistantUtilityShare: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, fontWeight: '700', color: C.ink2 } as TextStyle,
  assistantUtilitySectionTitle: { fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 14, fontWeight: '900', color: C.ink3 } as TextStyle,
  assistantUtilityThought: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 17, fontWeight: '700', color: C.ink2 } as TextStyle,
  cardShareButton: { fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 15, fontWeight: '900', color: C.green700 } as TextStyle,
  cardSaveButton: { fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 15, fontWeight: '900', color: C.ink3 } as TextStyle,
  fallback: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 20, color: C.ink2, fontStyle: 'italic' } as TextStyle,
  transparencyTitle: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 16, fontWeight: '800', color: C.ink2 } as TextStyle,
  transparencyLabel: { width: 64, fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 16, color: C.ink3 } as TextStyle,
  transparencyValue: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 16, fontWeight: '700', color: C.ink2 } as TextStyle,
  transparencyMono: { fontFamily: revaFonts.mono, fontSize: 10.5, lineHeight: 15, color: C.ink3 } as TextStyle,
  transparencyChip: { fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 14, color: C.ink2, fontWeight: '700' } as TextStyle,
};

function ThinkingStepsPanel({
  steps,
  streaming,
  statusLabel,
  onStop,
}: {
  steps: string[];
  streaming?: boolean;
  statusLabel?: string;
  onStop?: () => void;
}) {
  // 完成态默认折叠成一条 slim pill;流式态保持实时进度展开 (用户要看到它在干活).
  const [expanded, setExpanded] = React.useState(false);
  const cleanStatusLabel = String(statusLabel || '').trim();
  if (steps.length === 0 && !cleanStatusLabel) return null;

  const latestStep = steps[steps.length - 1];

  if (streaming) {
    const visibleStep = cleanStatusLabel || latestStep || '正在理解你的问题…';
    return (
      <View
        testID="assistant-thinking-panel"
        style={styles.thinkingAnalysisCard}
        accessibilityLabel={`小巴正在分析,当前步骤:${visibleStep}`}
      >
        <View style={styles.thinkingAnalysisHeader}>
          <View style={styles.thinkingIndicatorWrap}>
            <ActivityIndicator testID="assistant-thinking-indicator" size="small" color={C.green500} />
          </View>
          <View style={styles.thinkingAnalysisCopy}>
            <Text style={txt.thinkingAnalysisEyebrow}>正在分析</Text>
            <Text style={txt.thinkingAnalysisTitle} numberOfLines={2}>{visibleStep}</Text>
          </View>
          {onStop ? (
            <Pressable
              onPress={onStop}
              accessibilityRole="button"
              accessibilityLabel="停止本轮分析"
              hitSlop={8}
              style={({ pressed }) => [styles.thinkingStopButton, pressed && styles.actionBtnPressed]}
            >
              <Text style={txt.thinkingStop}>停止</Text>
            </Pressable>
          ) : null}
        </View>
        {steps.filter(step => step !== visibleStep).length > 0 ? (
          <View style={styles.thinkingAnalysisSteps}>
          {steps.filter(step => step !== visibleStep).slice(-3).map((step, index) => {
            return (
              <View key={`${step}-${index}`} style={styles.thinkingAnalysisStepRow}>
                <View style={styles.thinkingAnalysisStepIcon}>
                  <Ionicons name="checkmark" size={12} color="#fff" />
                </View>
                <Text style={txt.thinkingAnalysisStep} numberOfLines={2}>
                  {step}
                </Text>
              </View>
            );
          })}
          </View>
        ) : null}
        {steps.length === 0 ? (
          <View testID="assistant-thinking-skeleton" style={styles.thinkingSkeleton}>
            <View style={[styles.thinkingSkeletonLine, { width: '88%' }]} />
            <View style={[styles.thinkingSkeletonLine, { width: '66%' }]} />
            <View style={[styles.thinkingSkeletonLine, { width: '78%' }]} />
          </View>
        ) : null}
      </View>
    );
  }

  // 完成态: slim pill 行 (勾 + 「思考完成 · N 步」+ 折叠箭头), 点击展开/收起步骤列表.
  if (!streaming) {
    return (
      <View testID="assistant-thinking-panel" style={[styles.thinkingPill, expanded && styles.thinkingPillExpanded]}>
        <Pressable
          onPress={() => setExpanded((prev) => !prev)}
          style={({ pressed }) => [styles.thinkingPillHeader, pressed && styles.actionBtnPressed]}
          accessibilityRole="button"
          accessibilityLabel={expanded ? '收起思考步骤' : '展开思考步骤'}
          accessibilityState={{ expanded }}
        >
          <Ionicons name="checkmark-circle" size={15} color={C.green500} />
          <View style={styles.thinkingDoneCopy}>
            <Text style={txt.thinkingDoneLabel} numberOfLines={1}>思考完成</Text>
            <Text style={txt.thinkingDoneMeta} numberOfLines={1}> · {steps.length} 步</Text>
          </View>
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={C.ink3} />
        </Pressable>
        {expanded ? (
          <View style={[styles.thinkingPillList, styles.thinkingPillListExpanded]}>
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

function AssistantUtilityPanel({
  profile,
  sources,
  thinkingSteps,
  onOpenMemory,
  onShareWeChat,
  onShareXiaohongshu,
}: {
  profile: AgentTransparencyProfile;
  sources?: readonly string[];
  thinkingSteps: readonly string[];
  onOpenMemory: () => void;
  onShareWeChat: () => void;
  onShareXiaohongshu: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const sourceCount = normalizedAttributionCount(sources);
  const rows = [
    ...(profile.stages.length > 0 ? [{ label: '继续阶段', value: profile.stages.map(s => `${s.label} ${s.value}`).join(' · ') }] : []),
    ...(profile.rounds.length > 0 ? [{ label: 'LLM 轮次', value: profile.rounds.map(r => `${r.label} ${r.value}`).join('\n') }] : []),
    ...(profile.costLine ? [{ label: '成本', value: profile.costLine }] : []),
    ...(profile.tokenLine ? [{ label: 'Token', value: profile.tokenLine }] : []),
    ...(profile.errorLine ? [{ label: '失败', value: profile.errorLine }] : []),
    ...(profile.traceLine ? [{ label: '追踪', value: profile.traceLine }] : []),
  ];
  const hasExecutionDetails = profile.bands.length > 0
    || rows.length > 0
    || profile.tools.length > 0
    || (sourceCount === 0 && profile.sources.length > 0);
  const hasDetails = sourceCount > 0 || hasExecutionDetails || thinkingSteps.length > 0;
  return (
    <View
      testID="assistant-utility-panel"
      style={styles.assistantUtilityPanel}
    >
      <View style={styles.assistantUtilityRail}>
        {hasDetails ? (
          <Pressable
            onPress={() => setOpen(o => !o)}
            style={({ pressed }) => [styles.assistantUtilityEvidence, pressed && styles.actionBtnPressed]}
            accessibilityRole="button"
            accessibilityLabel={open ? '收起依据与过程' : '展开依据与过程'}
            accessibilityState={{ expanded: open }}
          >
            <Ionicons name="layers-outline" size={13} color={C.ink3} />
            {/* 第一部分只留干净入口"依据与过程 · N";耗时/轮次/模型名(profile.headline)
                太技术,收进展开面(下方 执行过程 顶部),不在常显行透出。 */}
            <Text style={txt.assistantUtilityEvidence} numberOfLines={1}>
              {`依据与过程${sourceCount > 0 ? ` · ${sourceCount}` : ''}`}
            </Text>
            <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={13} color={C.ink3} />
          </Pressable>
        ) : <View style={styles.assistantUtilitySpacer} />}
        <View style={styles.assistantUtilityDivider} />
        <Pressable
          onPress={onShareWeChat}
          accessibilityRole="button"
          accessibilityLabel="微信分享这条回复"
          style={({ pressed }) => [styles.assistantUtilityShare, pressed && styles.actionBtnPressed]}
        >
          <View style={styles.shareBadgeWeChat}>
            <Ionicons name="logo-wechat" size={12} color={C.greenOn} />
          </View>
          <Text style={txt.assistantUtilityShare}>微信</Text>
        </Pressable>
        <Pressable
          onPress={onShareXiaohongshu}
          accessibilityRole="button"
          accessibilityLabel="小红书分享这条回复"
          style={({ pressed }) => [styles.assistantUtilityShare, pressed && styles.actionBtnPressed]}
        >
          <View style={styles.shareBadgeXhs}>
            <Ionicons name="book" size={11} color={C.greenOn} />
          </View>
          <Text style={txt.assistantUtilityShare}>小红书</Text>
        </Pressable>
      </View>
      {open && hasDetails ? (
        <View style={styles.assistantUtilityDetails}>
          {/* 耗时/轮次/模型名从常显行下放到这里(展开才见):透明化不丢,只是不喧闹。 */}
          {profile.headline ? (
            <Text style={txt.transparencyMono} numberOfLines={1}>{profile.headline}</Text>
          ) : null}
          {sourceCount > 0 ? (
            <View style={styles.assistantUtilitySection}>
              <Text style={txt.assistantUtilitySectionTitle}>使用数据</Text>
              <AttributionDetails sources={sources} onOpenMemory={onOpenMemory} />
            </View>
          ) : null}
          {thinkingSteps.length > 0 ? (
            <View style={styles.assistantUtilitySection}>
              <Text style={txt.assistantUtilitySectionTitle}>思考过程</Text>
              <View style={styles.assistantUtilityThoughts}>
                {thinkingSteps.map((step, index) => (
                  <View key={`${step}-${index}`} style={styles.assistantUtilityThoughtRow}>
                    <Ionicons name="checkmark-circle" size={13} color={C.green500} />
                    <Text style={txt.assistantUtilityThought}>{step}</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
          {hasExecutionDetails ? (
            <View style={styles.assistantUtilitySection}>
              <Text style={txt.assistantUtilitySectionTitle}>执行过程</Text>
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
            sourceCount === 0 ? (
              <View style={styles.transparencyRow}>
                <Text style={txt.transparencyLabel}>引用数据</Text>
                <View style={{ flex: 1, gap: 3 }}>
                  {profile.sources.slice(0, 8).map(source => (
                    <Text key={source} style={txt.transparencyValue}>· {source}</Text>
                  ))}
                </View>
              </View>
            ) : null
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
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
