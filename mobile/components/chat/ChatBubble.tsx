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
import { getCardActionRuntimeGroupKey, getCardActionRuntimeKey, renderCard } from './cards';
import { createMdStylesChat } from '../../constants/markdownStyles';
import type { ColorPalette } from '../../hooks/useTheme';
import type { MedicationDecisionStatus, UIMessage } from '../../hooks/useChatEngine';
import { speakWithUserVoice, type SpeakHandle } from '../../services/speakWithUserVoice';
import { dispatchChatCardAction, type ChatCardActionResult } from '../../services/chatCardActions';
import { rememberVerifiedWriteReceipt } from '../../services/conversationContinuity';
import { formatWriteReceipt } from '../../services/writeReceipt';
import {
  buildCardActionReceiptIdentity,
  loadCardActionCompletion,
  saveCardActionReceipt,
} from '../../services/cardActionReceiptStorage';
import { durationBucket, emitClientEvent } from '../../services/clientEvents';
import type { ChatCardActionDescriptor, ChatCardActionRuntimeState, ServerCardDescriptor } from './cards/types';
import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import { useToast } from '../../hooks/useToast';
import {
  shareImage,
  sharePlainCaption,
  sharePlainText,
} from '../../utils/share';
import { buildAiShareMessage, buildXiaohongshuShareMessage } from '../../utils/aiShareText';
import { buildChatImageSource } from '../../utils/chatImageSource';
import { saveChatImageToLibrary } from '../../services/chatImageSave';
import { containsMarkdownTable, preprocessMarkdownTables } from '../../utils/markdownTables';
import { prepareSafeMarkdown, safeMarkdownIt } from '../../utils/safeMarkdown';
import { extractRevaUiBlocks } from '../../utils/revaUiBlocks';
import { DietShareComposer } from '../diet/DietShareComposer';
import {
  buildChatDietShareInput,
  buildDietSharePresentation,
} from '../diet/dietSharePresentation';
import type { MedicationSafetyAlert } from '../../services/medications';
import InterventionDraftSheet from '../actions/InterventionDraftSheet';
import { createInterventionDraft } from '../../services/actionCards';
import {
  buildInterventionDraft,
  type InterventionDraft,
} from '../../services/interventionDraft';
import { invalidateQueryKeys, queryKeys } from '../../applib/queryKeys';
import { buildAgentTransparency } from '../../utils/chatTransparency';
import MedicalCitations from './MedicalCitations';
import AnswerEvidencePanel from './AnswerEvidencePanel';

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
  onSendSuggestedPrompt?: (prompt: string, extraContext?: string) => void;
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
  const [dietShareComposerOpen, setDietShareComposerOpen] = useState(false);
  const [timeRevealed, setTimeRevealed] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [cardActionStateByKey, setCardActionStateByKey] = useState<Record<string, ChatCardActionRuntimeState>>({});
  const [cardReceiptByKey, setCardReceiptByKey] = useState<Record<string, WriteReceipt[]>>({});
  const [cardSafetyAlertsByKey, setCardSafetyAlertsByKey] = useState<Record<string, MedicationSafetyAlert[]>>({});
  const [cardDataPatchState, setCardDataPatchState] = useState<{
    itemId: string;
    data: Record<string, unknown>;
  }>(() => ({ itemId: item.id, data: {} }));
  const [cardDecisionStatus, setCardDecisionStatus] = useState<MedicationDecisionStatus | undefined>(
    () => readMedicationDecisionStatus(item.decisionStatus ?? item.cardData?.decision_status),
  );
  const [cardReceiptPersistenceWarning, setCardReceiptPersistenceWarning] = useState(false);
  const [todayPlanDraft, setTodayPlanDraft] = useState<InterventionDraft | null>(null);
  const [savingTodayPlan, setSavingTodayPlan] = useState(false);
  const cardActionLocksRef = useRef(new Set<string>());
  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speechActiveRef = useRef(false);
  const speechHandleRef = useRef<SpeakHandle | null>(null);
  const copyResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timeRevealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
  const assistantCompletionActionsEnabled = !item.streaming
    && item.completionStatus !== 'interrupted'
    && item.completionStatus !== 'error';
  const messageExportActionsEnabled = isUser || assistantCompletionActionsEnabled;
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
      completionStatus: item.completionStatus,
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
      item.completionStatus,
      item.perf,
    ],
  );
  const sentTimeShort = formatMessageTimeLabel(item.createdAt);
  const sentTimeFull = formatMessageFullTimeLabel(item.createdAt);
  const timeAccessibilityPrefix = sentTimeFull
    ? `${isUser ? '你发送于' : '小巴回复于'} ${sentTimeFull}. `
    : '';
  const revealMessageTime = useCallback(() => {
    if (!sentTimeShort) return;
    setTimeRevealed(true);
    if (timeRevealTimerRef.current) clearTimeout(timeRevealTimerRef.current);
    timeRevealTimerRef.current = setTimeout(() => {
      setTimeRevealed(false);
      timeRevealTimerRef.current = null;
    }, 2200);
  }, [sentTimeShort]);
  const showMessageTime = !!sentTimeShort && (timeRevealed || showActions || showCardActions);

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
      if (copyResetTimerRef.current) {
        clearTimeout(copyResetTimerRef.current);
        copyResetTimerRef.current = null;
      }
      if (timeRevealTimerRef.current) {
        clearTimeout(timeRevealTimerRef.current);
        timeRevealTimerRef.current = null;
      }
    };
  }, [clearSpeechTimeout]);

  useEffect(() => {
    setCardDecisionStatus(
      readMedicationDecisionStatus(item.decisionStatus ?? item.cardData?.decision_status),
    );
  }, [item.cardData?.decision_status, item.decisionStatus]);

  useEffect(() => {
    const cardType = item.cardType;
    if (!cardType || !item.cardActions?.length) return;
    const actions = item.cardActions;
    let cancelled = false;
    void Promise.all(actions.map(async (action) => {
      const actionKey = getCardActionRuntimeKey(action, { type: cardType });
      const identity = buildCardActionReceiptIdentity(
        action,
        cardType,
        item.sourceTurnId ?? item.sourceMessageId ?? item.id,
      );
      const completion = await loadCardActionCompletion(identity);
      return completion ? { action, actionKey, completion } : undefined;
    })).then((restored) => {
      if (cancelled) return;
      const valid = restored.filter((entry): entry is {
        action: ChatCardActionDescriptor;
        actionKey: string;
        completion: { verified: true; receipt?: WriteReceipt };
      } => !!entry);
      if (valid.length === 0) return;
      const doneActionKeys = new Set<string>();
      valid.forEach((entry) => {
        const groupKey = getCardActionRuntimeGroupKey(entry.action, { type: cardType });
        actions.forEach((sibling) => {
          if (getCardActionRuntimeGroupKey(sibling, { type: cardType }) === groupKey) {
            doneActionKeys.add(getCardActionRuntimeKey(sibling, { type: cardType }));
          }
        });
        cardActionLocksRef.current.add(groupKey);
      });
      setCardActionStateByKey(prev => ({
        ...prev,
        ...Object.fromEntries([...doneActionKeys].map(actionKey => [actionKey, 'done' as const])),
      }));
      const restoredReceipts = valid.filter((entry): entry is {
        action: ChatCardActionDescriptor;
        actionKey: string;
        completion: { verified: true; receipt: WriteReceipt };
      } => !!entry.completion.receipt);
      if (restoredReceipts.length > 0) {
        setCardReceiptByKey(prev => ({
          ...prev,
          ...Object.fromEntries(restoredReceipts.map(entry => [entry.actionKey, [entry.completion.receipt]])),
        }));
      }
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
    const actionGroupKey = getCardActionRuntimeGroupKey(action, descriptor);
    const groupActionKeys = (descriptor.actions?.length ? descriptor.actions : [action])
      .filter((sibling) => getCardActionRuntimeGroupKey(sibling, descriptor) === actionGroupKey)
      .map((sibling) => getCardActionRuntimeKey(sibling, descriptor));
    const groupHasState = (state: ChatCardActionRuntimeState) => (
      groupActionKeys.some(key => cardActionStateByKey[key] === state)
    );
    const setGroupActionState = (state: ChatCardActionRuntimeState) => {
      setCardActionStateByKey(prev => ({
        ...prev,
        ...Object.fromEntries(groupActionKeys.map(key => [key, state])),
      }));
    };
    if (
      cardActionLocksRef.current.has(actionGroupKey)
      || groupHasState('running')
      || groupHasState('done')
    ) {
      return;
    }
    cardActionLocksRef.current.add(actionGroupKey);
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
      setGroupActionState('running');
      try {
        const result = await dispatchChatCardAction(action, receiptIdentity, {
          cardType: descriptor.type,
          cardData: descriptor.data,
        });
        const expiredTerminal = result.status === 'expired'
          && result.decision_status === 'expired';
        const dismissedTerminal = result.status === 'dismissed'
          && result.decision_status === 'dismissed';
        const receiptlessTerminal = expiredTerminal || dismissedTerminal;
        const resultReceipts = result.write_receipts?.length
          ? result.write_receipts
          : result.receipt
            ? [result.receipt]
            : [];
        if (writeAction && !receiptlessTerminal && (
          resultReceipts.length === 0
          || resultReceipts.some(receipt => receipt.verified !== true)
        )) {
          emitWriteTerminal('unverified', false, 'write_receipt_missing_identity');
          throw new Error('write_receipt_missing_identity');
        }
        let receiptPersistenceFailed = false;
        if (resultReceipts.length > 0) {
          const duplicateGuardReceipt = resultReceipts[resultReceipts.length - 1];
          const shouldRememberForContinuity = result.status === 'completed'
            && duplicateGuardReceipt.status === 'verified';
          const persisted = await Promise.allSettled([
            shouldRememberForContinuity
              ? rememberVerifiedWriteReceipt(duplicateGuardReceipt)
              : Promise.resolve(),
            saveCardActionReceipt(receiptIdentity, duplicateGuardReceipt),
          ]);
          const cardDuplicateGuardSaved = persisted[1]?.status === 'fulfilled';
          if (!cardDuplicateGuardSaved) {
            receiptPersistenceFailed = true;
            setCardReceiptPersistenceWarning(true);
            console.warn('[chat] card write receipt persistence failed');
          } else {
            setCardReceiptByKey(prev => ({ ...prev, [actionKey]: resultReceipts }));
          }
        }
        const safetyAlerts = result.safety_alerts;
        if (safetyAlerts?.length) {
          setCardSafetyAlertsByKey(prev => ({ ...prev, [actionKey]: safetyAlerts }));
        }
        if (result.decision_status) {
          setCardDecisionStatus(result.decision_status);
        }
        if (result.patch && Object.keys(result.patch).length > 0) {
          setCardDataPatchState(previous => ({
            itemId: item.id,
            data: {
              ...(previous.itemId === item.id ? previous.data : {}),
              ...result.patch,
            },
          }));
        }
        if (writeAction) {
          if (receiptlessTerminal) {
            emitWriteTerminal(
              'failed',
              false,
              expiredTerminal ? 'write_intent_expired' : 'write_intent_dismissed',
            );
          } else {
            emitWriteTerminal(
              receiptPersistenceFailed ? 'unverified' : 'verified',
              !receiptPersistenceFailed,
              receiptPersistenceFailed ? 'card_receipt_persistence_failed' : undefined,
            );
          }
        }
        const refreshes = [
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
        ];
        if (
          descriptor.type === 'medication_draft'
          || resultReceipts.some(receipt => receipt.resourceType === 'medication_log')
        ) {
          refreshes.push(
            qc.invalidateQueries({ queryKey: queryKeys.medicationsRoot }),
            qc.invalidateQueries({ queryKey: queryKeys.medicationToday }),
          );
        }
        const refreshResults = await Promise.allSettled(refreshes);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        setGroupActionState('done');
        const refreshFailed = refreshResults.some(refresh => refresh.status === 'rejected');
        if (expiredTerminal) {
          toast.show('确认已过期，未写入；请重新发送完整用药记录', 'info');
        } else if (receiptPersistenceFailed) {
          toast.show('已写入，但本机未保存防重复凭证', 'error');
        } else {
          const hasSafetyAdvisory = Boolean(result.safety_alerts?.length);
          toast.show(
            refreshFailed && !hasSafetyAdvisory
              ? '已写入，页面数据稍后刷新'
              : getCardActionSuccessMessage(action, result),
            refreshFailed && !hasSafetyAdvisory
              ? 'info'
              : getCardActionSuccessType(action, result),
          );
        }
        if (result.route) {
          router.push(result.route as any);
        }
      } catch (error) {
        cardActionLocksRef.current.delete(actionGroupKey);
        emitWriteTerminal('failed', false, 'card_action_failed');
        setGroupActionState('error');
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
        toast.show(cardActionErrorMessage(error), 'error');
        if (__DEV__) console.warn('[cards] action failed', descriptor.type, action.action);
      }
    };

    if (action.action !== 'route.open' && action.requires_manual_confirm) {
      const confirmation = action.confirmation;
      const isDismiss = action.action === 'write_intent.dismiss';
      const isMedicationDismiss = isDismiss && descriptor.type === 'medication_draft';
      Alert.alert(
        isMedicationDismiss
          ? '取消这组用药记录？'
          : isDismiss
            ? '取消这项待确认操作？'
            : confirmation?.title || action.label,
        isMedicationDismiss
          ? '确认取消后，这组待确认记录不会写入。'
          : isDismiss
            ? '确认取消后，这项操作不会执行。'
            : confirmation?.detail || '确认后会写入你的健康记录。',
        [
          {
            text: isDismiss ? '再看看' : confirmation?.cancel_label || '取消',
            style: 'cancel',
            onPress: () => { cardActionLocksRef.current.delete(actionGroupKey); },
          },
          {
            text: isDismiss ? '确认取消' : confirmation?.confirm_label || action.label,
            ...(isDismiss ? { style: 'destructive' as const } : {}),
            onPress: execute,
          },
        ],
      );
      return;
    }

    await execute();
  }, [cardActionStateByKey, item.id, item.sourceMessageId, item.sourceTurnId, qc, toast]);

  const isUserVisibleWriteReceipt = (receipt: WriteReceipt) => (
    receipt.resourceType !== 'aigc_media_confirmation'
  );
  const cardReceipts = Object.values(cardReceiptByKey).flat().filter(isUserVisibleWriteReceipt);
  const latestCardReceipt = cardReceipts.length > 0 ? cardReceipts[cardReceipts.length - 1] : null;
  const directWriteReceipts = (item.writeReceipts || []).filter(isUserVisibleWriteReceipt);
  const visibleWriteReceipts = cardReceipts.length > 0
    ? cardReceipts
    : directWriteReceipts;
  const liveCardSafetyAlerts = Object.values(cardSafetyAlertsByKey).flat();
  const cardSafetyAlerts = liveCardSafetyAlerts.length > 0
    ? liveCardSafetyAlerts
    : item.safetyAlerts || [];
  const latestWriteReceipt = latestCardReceipt
    || (directWriteReceipts.length > 0 ? directWriteReceipts[directWriteReceipts.length - 1] : null);
  const effectiveCardData = useMemo(() => {
    const patch = cardDataPatchState.itemId === item.id ? cardDataPatchState.data : {};
    return item.cardData
      && typeof item.cardData === 'object'
      && !Array.isArray(item.cardData)
      && Object.keys(patch).length > 0
      ? { ...item.cardData, ...patch }
      : item.cardData;
  }, [cardDataPatchState, item.cardData, item.id]);
  const cardSharePayload = useMemo(
    () => buildCardSharePayload(item.cardType, effectiveCardData, latestWriteReceipt),
    [effectiveCardData, item.cardType, latestWriteReceipt],
  );
  const handleCardShare = useCallback(async () => {
    if (!cardSharePayload) return;
    try { Haptics.selectionAsync(); } catch {}
    try {
      await sharePlainText(cardSharePayload);
    } catch { /* 用户取消分享也会走这里, 不打扰 */ }
  }, [cardSharePayload]);
  const openCardActions = useCallback(() => {
    if (!cardSharePayload || selectionMode) return;
    try { Haptics.selectionAsync(); } catch {}
    revealMessageTime();
    setShowCardActions(true);
  }, [cardSharePayload, revealMessageTime, selectionMode]);

  const cardDataRecord = effectiveCardData && typeof effectiveCardData === 'object' && !Array.isArray(effectiveCardData)
    ? effectiveCardData as Record<string, unknown>
    : null;
  const isRecordedDietCard = item.cardType === 'diet_draft' && (
    cardDataRecord?.recorded === true
    || latestWriteReceipt?.status === 'verified'
  );
  const chatDietShareInput = item.cardType === 'diet_draft' && cardDataRecord
    ? buildChatDietShareInput(cardDataRecord, latestWriteReceipt)
    : null;
  const chatDietPhotoSource = chatDietShareInput?.available
    ? buildChatImageSource(chatDietShareInput.photoUri, imageAuthToken)
    : undefined;
  const canEditDietShare = Boolean(chatDietShareInput?.available && chatDietPhotoSource);
  const renderedCardData = item.cardType === 'medication_draft' && cardDataRecord
    ? { ...cardDataRecord, ...(cardDecisionStatus ? { decision_status: cardDecisionStatus } : {}) }
    : effectiveCardData;
  const renderedCardActions = cardDecisionStatus && cardDecisionStatus !== 'pending'
    ? []
    : item.cardActions;
  const hasPendingDietDraftEditor = item.cardType === 'diet_draft' && !isRecordedDietCard;
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
  const hasEmbeddedMediaInteraction = item.cardType === 'aigc_media_job'
    || item.cardType === 'aigc_media_confirmation';
  const hasNestedCardInteraction = hasEmbeddedCardEditor
    || hasEmbeddedMediaInteraction
    || Boolean(renderedCardActions?.length)
    || cardSafetyAlerts.length > 0;

  const handleCopy = useCallback(async () => {
    // 先收起长按菜单，避免异步剪贴板写入期间再次长按时仍处于旧菜单状态。
    setShowActions(false);
    setShowShareActions(false);
    if (!messageExportActionsEnabled) {
      toast.show('这条回复没有完整结束，暂不能复制。', 'info');
      return;
    }
    try {
      await Clipboard.setStringAsync(item.content);
      setCopied(true);
      if (copyResetTimerRef.current) clearTimeout(copyResetTimerRef.current);
      copyResetTimerRef.current = setTimeout(() => {
        setCopied(false);
        copyResetTimerRef.current = null;
      }, 1500);
      try { await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); } catch {}
    } catch {
      toast.show('复制失败，请重试', 'error');
    }
  }, [item.content, messageExportActionsEnabled, toast]);

  if (item.cardType && item.cardData) {
    const rendered = renderCard(
      { type: item.cardType, data: renderedCardData, actions: renderedCardActions },
      {
        onAction: handleCardAction,
        onSendSuggestedPrompt,
        healthEvidenceParent: {
          messageRef: item.sourceMessageId,
          turnRef: item.sourceTurnId,
        },
        actionStateByKey: cardActionStateByKey,
      },
    );
    if (rendered) {
      const cardContents = (
        <View testID="assistant-card-content-frame">
          {rendered}
          {visibleWriteReceipts.map(receipt => (
            <WriteReceiptLine key={receipt.operationId} receipt={receipt} />
          ))}
          {cardSafetyAlerts.length > 0 ? <MedicationSafetyAdvisory alerts={cardSafetyAlerts} /> : null}
          {cardReceiptPersistenceWarning ? <WriteReceiptPersistenceWarning /> : null}
        </View>
      );
      return (
        <>
          <View style={[styles.msgRow, styles.msgRowAI]}>
            <View testID="assistant-card-frame" style={styles.cardFrame}>
              {hasNestedCardInteraction ? (
                <View
                  testID={hasEmbeddedCardEditor
                    ? 'assistant-editable-card-interaction-surface'
                    : 'assistant-actionable-card-interaction-surface'}
                  accessibilityRole="summary"
                  accessibilityLabel={hasEmbeddedCardEditor ? '可编辑健康卡片' : '可操作健康卡片'}
                >
                  {cardContents}
                </View>
              ) : (
                <Pressable
                  testID="assistant-card-interaction-surface"
                  onPress={revealMessageTime}
                  onLongPress={openCardActions}
                  delayLongPress={350}
                  accessibilityRole="summary"
                  accessibilityLabel={cardSharePayload ? '长按卡片打开分享操作' : '健康卡片'}
                >
                  {cardContents}
                </Pressable>
              )}
              {showMessageTime ? <MessageTime label={sentTimeShort} isUser={false} /> : null}
              {(showCardActions || isRecordedDietCard) && cardSharePayload && !selectionMode ? (
                <View testID="assistant-card-share-actions" style={styles.cardShareActions}>
                  {isRecordedDietCard ? (
                    <Pressable
                      onPress={() => {
                        if (canEditDietShare) setDietShareComposerOpen(true);
                      }}
                      disabled={!canEditDietShare}
                      hitSlop={6}
                      accessibilityRole="button"
                      accessibilityLabel="编辑分享图"
                      accessibilityHint={!canEditDietShare ? '需要这餐的可用照片才能编辑分享图' : undefined}
                      accessibilityState={{ disabled: !canEditDietShare }}
                      style={({ pressed }) => [
                        styles.cardSaveButton,
                        !canEditDietShare && styles.actionBtnDisabled,
                        pressed && styles.actionBtnPressed,
                      ]}
                    >
                      <Ionicons name="create-outline" size={13} color={C.ink3} />
                      <Text style={txt.cardSaveButton}>编辑分享图</Text>
                    </Pressable>
                  ) : null}
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
                  {!isRecordedDietCard ? (
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
                  ) : null}
                  {isRecordedDietCard && !canEditDietShare ? (
                    <Text style={txt.cardShareUnavailableHint}>没有可用餐食照片，仅支持分享正文</Text>
                  ) : null}
                </View>
              ) : null}
            </View>
          </View>
          {dietShareComposerOpen && chatDietShareInput?.available && chatDietPhotoSource ? (
            <DietShareComposer
              visible
              record={chatDietShareInput.record}
              dateLabel={`今日 · ${buildDietSharePresentation(chatDietShareInput.record).mealLabel}`}
              photoSource={chatDietPhotoSource}
              onClose={() => setDietShareComposerOpen(false)}
              onShareText={handleCardShare}
              onShareFeedback={(feedback) => {
                toast.show(feedback.title, feedback.tone === 'success' ? 'success' : 'error');
              }}
              onShareTerminal={(meta) => {
                void emitClientEvent('diet_share_terminal', meta);
              }}
            />
          ) : null}
        </>
      );
    }
  }

  const hasTable = !isUser && containsMarkdownTable(displayText);

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
    const share = async () => {
      const source = buildChatImageSource(uri, imageAuthToken);
      if (!source) {
        toast.show('图片需要登录后才能分享', 'info');
        return;
      }
      try {
        await shareImage(source.uri, {
          target: 'more',
          cacheKey: item.id,
          headers: source.headers,
        });
      } catch {
        toast.show('分享图片失败，请稍后重试', 'error');
      }
    };
    Alert.alert('图片', undefined, [
      { text: '保存到相册', onPress: () => { void handleSaveImage(uri); } },
      { text: '分享图片', onPress: () => { void share(); } },
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
    revealMessageTime();
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
    if (!assistantCompletionActionsEnabled) {
      toast.show('这条回复没有完整结束，暂不能播报。', 'info');
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
    if (!assistantCompletionActionsEnabled) {
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
    revealMessageTime();
    if (showActions) {
      setShowActions(false);
      setShowShareActions(false);
    }
  };

  const renderMessageActions = () => {
    if (!showActions || selectionMode) return null;
    const canCopy = messageExportActionsEnabled && item.content.trim().length > 0;
    const canSelect = !!onEnterSelection;
    const canShare = canCopy;
    const canSpeak = !isUser && assistantCompletionActionsEnabled && !!assistantTextForActions;
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

  const incompleteAssistantReply = item.completionStatus === 'interrupted'
    || item.completionStatus === 'error';
  const showsAnswerEvidencePanel = !!item.answerEvidence || (
    !item.streaming
    && !!assistantTextForActions
    && (!incompleteAssistantReply || transparency.visible)
  );
  const assistantSurfaceAccessible = !hasInlineEditableCard && !showsAnswerEvidencePanel;

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
            {showMessageTime ? <MessageTime label={sentTimeShort} isUser /> : null}
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
            accessible={assistantSurfaceAccessible}
            accessibilityRole={assistantSurfaceAccessible ? 'text' : undefined}
            accessibilityLabel={assistantSurfaceAccessible ? `${timeAccessibilityPrefix}AI: ${assistantTextForActions || (revaUiContent.cards.length > 0 ? '图表卡片' : item.content)}` : undefined}
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
                  const rendered = renderCard(card, {
                    onAction: handleCardAction,
                    onSendSuggestedPrompt,
                    healthEvidenceParent: {
                      messageRef: item.sourceMessageId,
                      turnRef: item.sourceTurnId,
                    },
                    actionStateByKey: cardActionStateByKey,
                  });
                  return rendered ? <View key={`${card.type}-${index}`}>{rendered}</View> : null;
                })}
              </View>
            ) : null}
            {!item.streaming ? (
              <MedicalCitations citations={item.medicalCitations} />
            ) : null}
            {visibleWriteReceipts.map(receipt => (
              <WriteReceiptLine key={receipt.operationId} receipt={receipt} />
            ))}
            {cardSafetyAlerts.length > 0 ? <MedicationSafetyAdvisory alerts={cardSafetyAlerts} /> : null}
            {cardReceiptPersistenceWarning ? <WriteReceiptPersistenceWarning /> : null}
            {showsAnswerEvidencePanel ? (
              <AnswerEvidencePanel
                profile={transparency}
                answerEvidence={item.answerEvidence}
                sources={item.sourcesUsed}
                thinkingSteps={thinkingSteps}
                completionActionsEnabled={assistantCompletionActionsEnabled}
                incomplete={incompleteAssistantReply}
                onOpenMemory={() => router.push('/memory')}
                onShareWeChat={() => { void handleShare('wechat'); }}
                onShareXiaohongshu={() => { void handleShare('xiaohongshu'); }}
                onCopy={() => { void handleCopy(); }}
                copied={copied}
              />
            ) : null}
            {showMessageTime ? <MessageTime label={sentTimeShort} isUser={false} /> : null}
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
  const label = formatWriteReceipt(receipt);
  return (
    <View
      testID="write-receipt"
      style={styles.writeReceipt}
      accessibilityRole="text"
      accessibilityLabel={label}
    >
      <Ionicons name="checkmark-circle" size={14} color={C.green600} />
      <Text style={styles.writeReceiptText}>{label}</Text>
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

function MedicationSafetyAdvisory({ alerts }: { alerts: MedicationSafetyAlert[] }) {
  const validAlerts = alerts.filter(alert => (
    typeof alert?.title === 'string'
    && alert.title.trim().length > 0
    && typeof alert?.message === 'string'
    && alert.message.trim().length > 0
  ));
  if (validAlerts.length === 0) return null;
  return (
    <View
      testID="medication-safety-advisory"
      style={styles.medicationSafetyAdvisory}
      accessibilityLiveRegion="polite"
    >
      <Ionicons name="shield-checkmark-outline" size={15} color={revaSemantic.caution.fg} />
      <View style={styles.medicationSafetyAdvisoryTextGroup}>
        {validAlerts.map((alert, index) => (
          <View key={`${alert.rule_id}-${index}`}>
            <Text style={styles.medicationSafetyAdvisoryTitle}>{alert.title.trim()}</Text>
            <Text style={styles.medicationSafetyAdvisoryText}>{alert.message.trim()}</Text>
            {typeof alert.action === 'string' && alert.action.trim() ? (
              <Text style={styles.medicationSafetyAdvisoryAction}>{alert.action.trim()}</Text>
            ) : null}
          </View>
        ))}
      </View>
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

function readMedicationDecisionStatus(value: unknown): MedicationDecisionStatus | undefined {
  return value === 'pending' || value === 'executed' || value === 'dismissed' || value === 'expired'
    ? value
    : undefined;
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
  const hasVerifiedReceipt = latestWriteReceipt?.resourceType === 'diet_record'
    && latestWriteReceipt.status === 'verified';
  const isPersistedCard = data.recorded === true && cardNumber(data.record_id) != null;
  if (!hasVerifiedReceipt && !isPersistedCard) return null;
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
  const source = cardText(data.source);
  const rawConfidence = cardNumber(data.ai_confidence ?? data.confidence);
  const confidence = rawConfidence != null && rawConfidence > 1 ? rawConfidence / 100 : rawConfidence;
  const lowConfidence = source !== 'manual'
    && source !== 'user_corrected'
    && confidence != null
    && confidence >= 0
    && confidence < 0.7;

  const lines = ['今日饮食打卡', '今天这餐被小巴认真记下来了', ''];
  lines.push(food ? `${meal} · ${food}` : meal);

  if (lowConfidence) {
    lines.push('', '营养待核对');
  } else {
    const macroParts = [
      calories != null ? `${Math.round(calories)} kcal` : null,
      protein != null ? `蛋白 ${Math.round(protein)}g` : null,
      carbs != null ? `碳水 ${Math.round(carbs)}g` : null,
      fat != null ? `脂肪 ${Math.round(fat)}g` : null,
    ].filter(Boolean);
    if (macroParts.length > 0) lines.push('', '营养概览', macroParts.join(' · '));
    if (suggestions[0]) lines.push('', '今日策略', `下一步：${suggestions[0]}`);
  }
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
    'aigc_media.confirm',
  ].includes(action.action);
}

function cardActionErrorMessage(error: unknown): string {
  const response = (error as { response?: { status?: unknown; data?: unknown } } | undefined)?.response;
  const status = typeof response?.status === 'number' ? response.status : undefined;
  if (status == null || status < 400 || status >= 500) return '操作失败，请稍后重试';
  const data = response?.data;
  const detail = data && typeof data === 'object'
    ? (data as { detail?: unknown }).detail
    : undefined;
  const text = Array.isArray(detail)
    ? detail.map((item) => (
      item && typeof item === 'object' && 'msg' in item
        ? String((item as { msg?: unknown }).msg ?? '')
        : ''
    )).find(Boolean)
    : typeof detail === 'string'
      ? detail
      : undefined;
  const normalized = text?.trim();
  if (!normalized || /(?:token|secret|password|traceback|stack|psycopg2|sqlalchemy|uniqueviolation|object|\{|\})/i.test(normalized)) {
    return '操作失败，请稍后重试';
  }
  return normalized.slice(0, 80);
}

function getCardActionSuccessMessage(
  action: ChatCardActionDescriptor,
  result: ChatCardActionResult,
): string {
  if (result.safety_alerts?.some(alert => alert.rule_id === 'medication.safety_precheck_incomplete')) {
    return '已记录；自动安全筛查暂未完成，不代表当前用药组合安全';
  }
  if (result.safety_alerts?.length) return '已记录；请查看用药安全提示';
  if (result.route || action.action === 'route.open') return '已打开';
  if (action.action === 'diet_record.create') {
    if (result.nutrition_status === 'estimated') return '已记录饮食，营养已估算';
    if (result.nutrition_status === 'estimate_failed') return '已记录饮食，营养估算稍后补充';
    return '已记录饮食';
  }
  if (action.action === 'daily_plan_action.complete') return '已完成今日行动';
  if (result.status === 'dismissed') return '已忽略';
  return '已执行';
}

function getCardActionSuccessType(
  action: ChatCardActionDescriptor,
  result: ChatCardActionResult,
): 'info' | 'error' | 'success' {
  if (result.safety_alerts?.some(alert => alert.rule_id === 'medication.safety_precheck_incomplete')) {
    return 'info';
  }
  if (result.safety_alerts?.some(alert => (
    alert.severity?.label === 'critical' || alert.severity?.label === 'high'
  ))) {
    return 'error';
  }
  if (result.safety_alerts?.length) return 'info';
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
      <Text style={summaryStyles.conclusionLabel}>小巴</Text>
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
    marginBottom: 10,
    gap: 8,
  },
  conclusionLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  conclusionDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: C.green500,
  },
  conclusionLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
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
  cardFrame: { flex: 1, minWidth: 0, maxWidth: '100%', position: 'relative' },
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
  medicationSafetyAdvisory: {
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: revaSemantic.caution.bg,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
    maxWidth: '100%',
  },
  medicationSafetyAdvisoryTextGroup: {
    flex: 1,
    gap: 7,
  },
  medicationSafetyAdvisoryTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: revaSemantic.caution.fg,
    fontWeight: '800',
  } as TextStyle,
  medicationSafetyAdvisoryText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink2,
    fontWeight: '600',
  } as TextStyle,
  medicationSafetyAdvisoryAction: {
    marginTop: 2,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink3,
  } as TextStyle,
  medicationSafetyAdvisoryRemaining: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: revaSemantic.caution.fg,
    fontWeight: '700',
  } as TextStyle,
  medicationSafetyDetailsButton: {
    minHeight: 44,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 2,
  },
  medicationSafetyDetailsText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: revaSemantic.caution.fg,
    fontWeight: '700',
  } as TextStyle,
  bubble: { maxWidth: '82%', borderRadius: 14, paddingHorizontal: 13, paddingVertical: 9, position: 'relative' },
  bubbleUser: { backgroundColor: C.green500, borderBottomRightRadius: 5 },
  messageTime: {
    position: 'absolute',
    bottom: -16,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: revaRadii.pill,
    backgroundColor: 'rgba(252,251,247,0.92)',
    fontFamily: revaFonts.mono,
    fontSize: 10.5,
    lineHeight: 14,
    fontWeight: '600',
    letterSpacing: 0,
    zIndex: 3,
  } as TextStyle,
  messageTimeUser: {
    right: 0,
    color: 'rgba(255,255,255,0.86)',
    backgroundColor: 'rgba(17,92,64,0.78)',
  } as TextStyle,
  messageTimeAI: {
    left: 0,
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
  actionBtnDisabled: { opacity: 0.45 },
  actionBtnPressed: { opacity: 0.82 },
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
  cardShareButton: { fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 15, fontWeight: '900', color: C.green700 } as TextStyle,
  cardSaveButton: { fontFamily: revaFonts.sans, fontSize: 11.5, lineHeight: 15, fontWeight: '900', color: C.ink3 } as TextStyle,
  cardShareUnavailableHint: { width: '100%', fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 15, color: C.ink3 } as TextStyle,
  fallback: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 20, color: C.ink2, fontStyle: 'italic' } as TextStyle,
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
