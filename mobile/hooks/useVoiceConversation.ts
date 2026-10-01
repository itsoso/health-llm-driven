import { useCallback, useEffect, useRef, useState } from 'react';
import { ensureAIConsent } from '../services/aiConsent';
import { aiConsentRevision, subscribeAIConsentInvalidation } from '../services/aiConsentState';
import * as Speech from 'expo-speech';
import { setAudioModeAsync } from 'expo-audio';
import {
  cancelAgentRun,
  getAgentTurnStatus,
  getConversationMessages,
  streamChat,
} from '../services/chat';
import {
  createCloudRealtimeAsrSession,
  type RealtimeAsrSession,
} from '../services/cloudRealtimeAsr';
import {
  createCloudStreamingTtsSession,
  type StreamingTtsSession,
} from '../services/cloudStreamingTts';
import {
  loadVoiceStyle, resolveIosSpeechOptions, getVoiceStyle, type VoiceStyle,
} from '../services/voiceStyle';
import { splitTextForCloudTts } from '../utils/ttsText';

/**
 * 语音连续对话状态机.
 *
 * idle → listening → thinking → speaking → idle
 *
 * ASR 使用 authenticated cloud realtime session：partial 只展示，stop 后的
 * authoritative final 才进入 Agent。每轮携带 client_turn_id，插话会同时
 * abort 本地传输并请求取消 owner-scoped Agent Run。
 *
 * TTS provider 双栈:
 *   - ios   : expo-speech AVSpeechSynthesizer (离线, 机械感)
 *   - cloud : 后端 /tts/stream 代理阿里云 CosyVoice, 原生内存 PCM 播放
 *
 * 云端会话在首个分片开始前失败时降级到 iOS；流中失败不重播已发送文本，
 * 避免健康建议重复。TTS 按自然短语边界增量送入同一会话。
 * 打断: startListening 会停止播放、清队列并取消服务端运行，让用户随时插话.
 */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface VoiceTurn {
  role: 'user' | 'assistant';
  text: string;
  at: number;
}

let voiceTurnCounter = 0;
function nextVoiceTurnId(): string {
  return `voice-turn-${++voiceTurnCounter}-${Date.now()}`;
}

// 只用真标点切句; \n 不算句末 — 段落换行交给标点本身的自然停顿,
// 否则 \n\n 会触发额外的 synth 来回 (网络 500ms+), 听起来"卡顿"
// `.` 前后都是数字 (3.6 / 1.0.2) 不当句末 — 否则 "3.6 公里" 会被切成 "3" + "6 公里"
// 后面的 stripMarkdownForTTS 拿不到完整 decimal 就没法念成"3 点 6"
const SPEAKABLE_BOUNDARY = /[。！？!?，,；;：:]|(?<!\d)\.(?!\d)/;
// 太短的句子 (< 3 字) 直接合并到下一个, 避免"是。" / "OK!" 这种微音轨抖动
const MIN_SENTENCE_LEN = 3;
const MAX_STREAM_FRAGMENT_LEN = 48;

function stripMarkdownForTTS(s: string): string {
  return s
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\|/g, ' ')
    .replace(/^[\s|:\-]+$/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
    .replace(/~~([^~]+)~~/g, '$1')
    // "7.7 小时" → "7 小时 42 分钟" (TTS 默认读"七点七小时", 不自然)
    // 只规范时间类 decimal, 其他 decimal (7.7 公里 / 百分比) 保留原样
    .replace(/(\d+)\.(\d+)\s*小时/g, (_, h, frac) => {
      const hInt = parseInt(h, 10);
      const mins = Math.round(parseFloat(`0.${frac}`) * 60);
      if (mins === 0) return `${hInt} 小时`;
      if (mins === 60) return `${hInt + 1} 小时`;
      return `${hInt} 小时 ${mins} 分`;
    })
    // 段落换行变成单空格, 让标点自己定停顿,不让 TTS 把段落空行当 "全部停"
    .replace(/\n+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    // 兜底: 数字间的英文 "." 替换成中文 "点" — iOS Speech / 部分 TTS 会把
    // "3.6 公里" 读成 "三 六公里" (吞掉 .). 这条放最后, "小时" 已经在前面消化掉了.
    .replace(/(\d)\.(\d)/g, '$1点$2');
}

/**
 * 从 health_record 的 args.data 抽一个 60 字以内的人类可读摘要.
 * 供 voice-chat 关闭时的 summary 卡显示 "本次记了什么".
 * 返回空字符串时调用方应跳过 (data 格式未知 / 不认识的 record_type).
 */
function formatRecordLabel(recordType: string, d: Record<string, any>): string {
  if (!d) return '';
  switch (recordType) {
    case 'water': {
      const amt = d.amount ?? 250;
      return `饮水 ${amt}ml`;
    }
    case 'weight': {
      if (d.weight != null) return `体重 ${d.weight}kg`;
      return '体重记录';
    }
    case 'blood_pressure':
      return `血压 ${d.systolic}/${d.diastolic}`;
    case 'diet': {
      const meal = {
        breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐',
      }[d.meal_type as string] || d.meal_type || '饮食';
      const food = d.food_items || d.description || '';
      return `${meal}: ${String(food).slice(0, 40)}`;
    }
    case 'supplement':
      return `补剂: ${d.supplement_name || '未指定'}`;
    case 'supplement_group': {
      const t = { morning: '早上', noon: '中午', evening: '晚上', bedtime: '睡前' }[d.timing as string] || d.timing;
      return `补剂组: ${t}`;
    }
    case 'exercise': {
      const ex = d.exercise_type || '运动';
      if (d.reps) return `${ex} ${d.reps}${d.sets ? ' x ' + d.sets + '组' : '次'}`;
      if (d.duration) return `${ex} ${d.duration}分钟`;
      return `${ex}`;
    }
    case 'medication':
      return `服药: ${d.medication_name || '未指定'}${d.taken_time ? ' @' + d.taken_time : ''}`;
    case 'illness':
      return `生病: ${d.illness_name || '症状'}`;
    case 'rhinitis': {
      const parts = [];
      if (d.sneezing != null) parts.push(`喷嚏 ${d.sneezing}`);
      if (d.congestion != null) parts.push(`鼻塞 ${d.congestion}`);
      if (d.runny_nose != null) parts.push(`流涕 ${d.runny_nose}`);
      return `鼻炎: ${parts.join('/') || '症状'}`;
    }
    case 'mood':
      return `心情 ${d.score ?? '-'}${d.notes ? ' - ' + String(d.notes).slice(0, 20) : ''}`;
    case 'symptom': {
      // 新 schema (2026-05-08): body_part + description + optional severity
      if (d.body_part || d.description) {
        const partLabels: Record<string, string> = {
          eye: '眼', respiratory: '呼吸道', skin: '皮肤', digestive: '消化',
          musculoskeletal: '肌肉骨', head: '头', general: '全身', other: '其他',
        };
        const part = partLabels[d.body_part] || d.body_part || '症状';
        const desc = d.description || '';
        const sev = d.severity ? ` (严重度 ${d.severity}/10)` : '';
        return `${part}: ${desc}${sev}`;
      }
      // 旧 schema fallback (disease_tracking.SymptomLog, 迁移期)
      const sym = Array.isArray(d.symptoms) ? d.symptoms.map((s: any) => s.name).join('/') : '';
      return `症状: ${sym || '记录'}`;
    }
    case 'reminder':
      return `提醒: ${d.title || '未命名'}`;
    case 'garmin_sync':
      return '触发 Garmin 同步';
    default:
      return `${recordType} 记录`;
  }
}


export function useVoiceConversation() {
  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const latestPartialRef = useRef('');
  const conversationIdRef = useRef<number | undefined>(undefined);

  // 静默自动提交 — realtime ASR partial 更新时重置 timer；超时后先向
  // ASR 请求 authoritative final，再提交，绝不直接提交 partial。
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const SILENCE_AUTO_SUBMIT_MS = 1200;

  const pendingTextRef = useRef('');
  const assistantTextRef = useRef('');
  const ttsQueueRef = useRef<string[]>([]);
  const isSpeakingRef = useRef(false);
  const streamingTtsRef = useRef<StreamingTtsSession | null>(null);
  const ttsPumpPromiseRef = useRef<Promise<void> | null>(null);
  const ttsGenerationRef = useRef(0);
  const forceIosTtsRef = useRef(false);
  const ttsErrorRef = useRef<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const realtimeAsrRef = useRef<RealtimeAsrSession | null>(null);
  const finalizingAsrRef = useRef<RealtimeAsrSession | null>(null);
  const finalizeListeningRef = useRef<Promise<void> | null>(null);
  const activeAgentTurnRef = useRef<{ clientTurnId: string; runId?: string } | null>(null);
  const mountedRef = useRef(true);
  const listeningStartSeqRef = useRef(0);
  const resumeListeningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // I Phase 2: 本次会话内成功 health_record 的录入摘要 (关闭 voice-chat 时弹 summary 卡用)
  // 记 record_type + 简短描述 + 原始 record_data (撤销用)
  const recordedItemsRef = useRef<{
    type: string;
    label: string;
    data: Record<string, any>;
    at: number;
  }[]>([]);

  // 当前 voice style (读 AsyncStorage, 每轮开播前刷新)
  const voiceStyleRef = useRef<VoiceStyle>('cloud_cloned_private_female');
  const iosOptsRef = useRef<Speech.SpeechOptions>({ language: 'zh-CN', rate: 1.0, pitch: 1.0 });

  /**
   * iOS AVAudioSession 模式动态切换 (修复音量变小问题):
   *
   *   播放模式 (.playback category):        默认外放, 音量正常
   *   录音模式 (.playAndRecord category):   需要录音; 默认会路由到 receiver (听筒)
   *                                         导致 TTS 回放音量小
   *
   * 策略:
   *   - 初始默认 playback (allowsRecording=false) → 外放
   *   - startListening 前切到 playAndRecord (allowsRecording=true)
   *   - stopListening 后切回 playback
   *
   * 注: expo-audio 当前 API 不支持 .defaultToSpeaker / proximity 监听,
   *   要做到"贴耳自动听筒"需要原生代码, 先实现 80% 场景的音量问题.
   */
  const setPlaybackMode = useCallback(async () => {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording: false,  // → .playback category, 外放
      });
    } catch (e) {
      if (__DEV__) console.warn('[voice] setPlaybackMode failed:', e);
    }
  }, []);

  useEffect(() => {
    // 进入页面默认外放
    setPlaybackMode();
  }, [setPlaybackMode]);

  const refreshVoiceStyle = useCallback(async () => {
    try {
      const style = await loadVoiceStyle();
      voiceStyleRef.current = style;
      const opt = getVoiceStyle(style);
      if (opt.provider === 'ios') {
        iosOptsRef.current = await resolveIosSpeechOptions(style);
      }
    } catch (e) {
      if (__DEV__) console.warn('[voice] refreshVoiceStyle failed:', e);
    }
  }, []);

  useEffect(() => {
    refreshVoiceStyle();
  }, [refreshVoiceStyle]);

  const stopCurrentSpeech = useCallback(async () => {
    ttsGenerationRef.current += 1;
    try { Speech.stop(); } catch {}
    const session = streamingTtsRef.current;
    streamingTtsRef.current = null;
    await session?.cancel().catch(() => undefined);
    ttsPumpPromiseRef.current = null;
    isSpeakingRef.current = false;
    forceIosTtsRef.current = false;
    ttsErrorRef.current = null;
  }, []);

  const speakViaIos = useCallback((text: string, onDone: () => void) => {
    Speech.speak(text, {
      ...iosOptsRef.current,
      onDone: () => { isSpeakingRef.current = false; onDone(); },
      onStopped: () => { isSpeakingRef.current = false; },
      onError: () => { isSpeakingRef.current = false; onDone(); },
    });
  }, []);

  const flushIosTTS = useCallback(() => {
    if (isSpeakingRef.current) return;
    const next = ttsQueueRef.current.shift();
    if (!next) return;
    isSpeakingRef.current = true;
    const onDone = () => { isSpeakingRef.current = false; flushIosTTS(); };
    speakViaIos(next, onDone);
  }, [speakViaIos]);

  const flushTTS = useCallback(() => {
    const provider = getVoiceStyle(voiceStyleRef.current).provider;
    if (provider !== 'cloud' || forceIosTtsRef.current) {
      flushIosTTS();
      return;
    }
    if (ttsPumpPromiseRef.current || ttsQueueRef.current.length === 0) return;

    const generation = ttsGenerationRef.current;
    const task = (async () => {
      let session = streamingTtsRef.current;
      let sessionReady = Boolean(session);
      try {
        if (!session) {
          const opt = getVoiceStyle(voiceStyleRef.current);
          session = createCloudStreamingTtsSession({
            voiceKey: opt.cloudVoiceKey ?? 'cloned_private_female',
          });
          streamingTtsRef.current = session;
          isSpeakingRef.current = true;
          const started = await session.start();
          if (!started || generation !== ttsGenerationRef.current) return;
          sessionReady = true;
        }
        while (generation === ttsGenerationRef.current && ttsQueueRef.current.length > 0) {
          const next = ttsQueueRef.current[0];
          await session.append(next);
          if (generation !== ttsGenerationRef.current) return;
          ttsQueueRef.current.shift();
        }
      } catch (error: any) {
        if (generation !== ttsGenerationRef.current) return;
        streamingTtsRef.current = null;
        await session?.cancel().catch(() => undefined);
        isSpeakingRef.current = false;
        if (!sessionReady) {
          // No text reached the provider, so local fallback cannot duplicate speech.
          forceIosTtsRef.current = true;
          if (!iosOptsRef.current.voice) {
            iosOptsRef.current = { language: 'zh-CN', rate: 1.0, pitch: 1.0 };
          }
          flushIosTTS();
        } else {
          ttsQueueRef.current = [];
          ttsErrorRef.current = new Error(error?.message || '流式语音播放失败');
        }
      }
    })();
    ttsPumpPromiseRef.current = task;
    void task.finally(() => {
      if (ttsPumpPromiseRef.current === task) ttsPumpPromiseRef.current = null;
    });
  }, [flushIosTTS]);

  const enqueueTtsText = useCallback((text: string) => {
    ttsQueueRef.current.push(...splitTextForCloudTts(text));
  }, []);

  const enqueueSentences = useCallback((chunk: string) => {
    pendingTextRef.current += chunk;
    while (true) {
      const m = pendingTextRef.current.match(SPEAKABLE_BOUNDARY);
      if ((!m || m.index === undefined) && pendingTextRef.current.length < MAX_STREAM_FRAGMENT_LEN) break;
      const cut = m && m.index !== undefined ? m.index + 1 : MAX_STREAM_FRAGMENT_LEN;
      const sentence = pendingTextRef.current.slice(0, cut).trim();
      pendingTextRef.current = pendingTextRef.current.slice(cut);
      if (sentence) {
        const clean = stripMarkdownForTTS(sentence).trim();
        // 太短的微句 (< MIN_SENTENCE_LEN) 退回 pending, 攒到下一句一起 synth, 避免段落首句"是。"独立成轨
        if (clean.length >= MIN_SENTENCE_LEN) {
          enqueueTtsText(clean);
        } else if (clean) {
          pendingTextRef.current = clean + (pendingTextRef.current.startsWith(' ') ? '' : ' ') + pendingTextRef.current;
        }
      }
    }
    flushTTS();
  }, [enqueueTtsText, flushTTS]);

  const flushTail = useCallback(() => {
    const tail = pendingTextRef.current.trim();
    pendingTextRef.current = '';
    if (tail) {
      const clean = stripMarkdownForTTS(tail).trim();
      if (clean) {
        enqueueTtsText(clean);
        flushTTS();
      }
    }
  }, [enqueueTtsText, flushTTS]);

  const waitTTSDrain = useCallback(async () => {
    while (
      mountedRef.current
      && (ttsQueueRef.current.length > 0 || isSpeakingRef.current)
    ) {
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
    }
  }, []);

  const finishTTS = useCallback(async () => {
    flushTTS();
    while (ttsPumpPromiseRef.current) {
      await ttsPumpPromiseRef.current;
    }
    if (ttsErrorRef.current) {
      const error = ttsErrorRef.current;
      ttsErrorRef.current = null;
      throw error;
    }
    if (forceIosTtsRef.current || getVoiceStyle(voiceStyleRef.current).provider !== 'cloud') {
      await waitTTSDrain();
      return;
    }
    const session = streamingTtsRef.current;
    if (!session) return;
    await session.finish();
    if (streamingTtsRef.current === session) streamingTtsRef.current = null;
    isSpeakingRef.current = false;
  }, [flushTTS, waitTTSDrain]);

  const submit = useCallback(async (userText: string) => {
    const clientTurnId = nextVoiceTurnId();
    setState('thinking');
    setTurns((prev) => [...prev, { role: 'user', text: userText, at: Date.now() }]);
    pendingTextRef.current = '';
    assistantTextRef.current = '';
    ttsQueueRef.current = [];
    forceIosTtsRef.current = false;
    ttsErrorRef.current = null;

    const ac = new AbortController();
    abortRef.current = ac;
    activeAgentTurnRef.current = { clientTurnId };

    let replyStarted = false;
    let reachedTerminalEvent = false;

    try {
      await refreshVoiceStyle();
      if (ac.signal.aborted) throw new Error('aborted');
      let lastFailedTool = '';  // 同一 tool 连续失败只提示一次
      // channel='voice':语音转写可能失真(1.2s 静默即自动提交,用户未必复核),
      // 症状类记录在后端保留确认前置。
      for await (const evt of streamChat(
        userText,
        conversationIdRef.current,
        undefined,
        ac.signal,
        undefined,
        'voice',
        clientTurnId,
      )) {
        if (evt.type === 'persisted') {
          if (evt.conversationId && !conversationIdRef.current) {
            conversationIdRef.current = evt.conversationId;
          }
          if (activeAgentTurnRef.current?.clientTurnId === clientTurnId && evt.runId) {
            activeAgentTurnRef.current.runId = evt.runId;
          }
        } else if (evt.type === 'token' || evt.type === 'tool') {
          const chunk = evt.content || '';
          if (!chunk) continue;

          // tool 失败的可见提示文本不进 TTS 队列 — 用户听到 LLM 重试时连说 5 遍'操作未成功'噪音大
          // 同一个 tool 连续失败也只显示一次
          const isToolFailure = evt.type === 'tool' && chunk.includes('⚠️ 操作未成功');
          if (isToolFailure) {
            const toolName = evt.toolName || '';
            if (toolName && toolName === lastFailedTool) continue;  // 同 tool 重复, 跳过
            lastFailedTool = toolName;
          } else if (evt.type === 'tool') {
            lastFailedTool = '';  // 非失败事件重置去重锁

            // I Phase 2: sniff 成功的 health_record → 推到 recordedItemsRef
            // 关闭 voice-chat 时给用户看 summary 卡: '本次记了 X 项: ...'
            if (evt.toolName === 'health_record' && evt.toolSuccess && evt.recordType && evt.recordData) {
              const label = formatRecordLabel(evt.recordType, evt.recordData);
              if (label) {
                recordedItemsRef.current.push({
                  type: evt.recordType,
                  label,
                  data: evt.recordData,
                  at: Date.now(),
                });
              }
            }
          }

          if (!replyStarted) {
            replyStarted = true;
            setState('speaking');
            setTurns((prev) => [...prev, { role: 'assistant', text: '', at: Date.now() }]);
          }
          assistantTextRef.current += chunk;
          setTurns((prev) => {
            const copy = prev.slice();
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') {
              copy[copy.length - 1] = { ...last, text: assistantTextRef.current };
            }
            return copy;
          });
          // 失败提示不入 TTS, 用户看文字就够了
          if (!isToolFailure) {
            enqueueSentences(chunk);
          }
        } else if (evt.type === 'done') {
          reachedTerminalEvent = true;
          if (activeAgentTurnRef.current?.clientTurnId === clientTurnId) {
            activeAgentTurnRef.current = null;
          }
          if (evt.conversationId && !conversationIdRef.current) {
            conversationIdRef.current = evt.conversationId;
          }
          flushTail();
        } else if (evt.type === 'error') {
          throw new Error(evt.content || '请求出错');
        }
      }
      if (!replyStarted) {
        setState('idle');
        return;
      }
      flushTail();
      await finishTTS();
      if (mountedRef.current) setState('idle');
    } catch (e: any) {
      const msg = e?.message || '请求失败';
      if (msg === 'aborted') {
        return;
      }
      if (!mountedRef.current) return;
      setError(msg);
      setTurns((prev) => [...prev, { role: 'assistant', text: `[错误] ${msg}`, at: Date.now() }]);
      setState('error');
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
      if (
        reachedTerminalEvent
        && activeAgentTurnRef.current?.clientTurnId === clientTurnId
      ) {
        activeAgentTurnRef.current = null;
      }
    }
  }, [refreshVoiceStyle, enqueueSentences, flushTail, finishTTS]);

  const cancelActiveAgentTurn = useCallback(async () => {
    const active = activeAgentTurnRef.current;
    abortRef.current?.abort();
    if (!active) return;

    let runId = active.runId;
    if (!runId) {
      let status = null;
      for (let attempt = 0; attempt < 3 && !runId; attempt += 1) {
        status = await getAgentTurnStatus(active.clientTurnId);
        runId = status?.runId;
        if (!runId && attempt < 2) {
          await new Promise<void>(resolve => setTimeout(resolve, 80));
        }
      }
      if (!runId) {
        if (activeAgentTurnRef.current?.clientTurnId === active.clientTurnId) {
          activeAgentTurnRef.current = null;
        }
        return;
      }
      if (['succeeded', 'failed', 'cancelled', 'interrupted', 'reconciliation_required'].includes(
        status?.status || '',
      )) {
        if (activeAgentTurnRef.current?.clientTurnId === active.clientTurnId) {
          activeAgentTurnRef.current = null;
        }
        return;
      }
    }
    try {
      await cancelAgentRun(runId);
    } catch {
      throw new Error('上一轮对话未能安全停止，请稍后重试');
    }
    if (activeAgentTurnRef.current?.clientTurnId === active.clientTurnId) {
      activeAgentTurnRef.current = null;
    }
  }, []);

  const finalizeListening = useCallback(async () => {
    if (finalizeListeningRef.current) return finalizeListeningRef.current;
    const session = realtimeAsrRef.current;
    if (!session) return;
    realtimeAsrRef.current = null;
    finalizingAsrRef.current = session;
    const finalizeSeq = listeningStartSeqRef.current;
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    const task = (async () => {
      try {
        const result = await session.stop();
        await setPlaybackMode();
        if (!mountedRef.current || finalizeSeq !== listeningStartSeqRef.current) return;
        const finalText = result.text.trim();
        latestPartialRef.current = finalText;
        setTranscript(finalText);
        if (finalText) await submit(finalText);
        else setState('idle');
      } catch (e: any) {
        await session.cancel().catch(() => undefined);
        await setPlaybackMode();
        if (!mountedRef.current) return;
        setError(String(e?.message || '云端实时语音识别失败'));
        setState('error');
      } finally {
        if (finalizingAsrRef.current === session) finalizingAsrRef.current = null;
        finalizeListeningRef.current = null;
      }
    })();
    finalizeListeningRef.current = task;
    return task;
  }, [setPlaybackMode, submit]);

  const startListening = useCallback(async () => {
    const startSeq = ++listeningStartSeqRef.current;
    if (!await ensureAIConsent() || !mountedRef.current || startSeq !== listeningStartSeqRef.current) return;
    const consentRevision = aiConsentRevision();
    const isCurrentStart = () => mountedRef.current && startSeq === listeningStartSeqRef.current
      && consentRevision === aiConsentRevision();
    try {
      // 顺序很重要: 先清队列，再取消 TTS / Agent，最后才打开麦克风。
      ttsQueueRef.current = [];
      pendingTextRef.current = '';
      await stopCurrentSpeech();
      if (realtimeAsrRef.current) {
        const previousSession = realtimeAsrRef.current;
        realtimeAsrRef.current = null;
        await previousSession.cancel();
      }
      await cancelActiveAgentTurn();
      if (!isCurrentStart()) return;
      setError(null);
      setTranscript('');
      latestPartialRef.current = '';
      let session!: RealtimeAsrSession;
      session = createCloudRealtimeAsrSession({
        onTranscript: (text) => {
          if (!mountedRef.current || realtimeAsrRef.current !== session) return;
          const normalized = text.trim();
          if (!normalized || normalized === latestPartialRef.current) return;
          latestPartialRef.current = normalized;
          setTranscript(normalized);
          if (finalizeListeningRef.current) return;
          if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = setTimeout(() => {
            silenceTimerRef.current = null;
            void finalizeListening();
          }, SILENCE_AUTO_SUBMIT_MS);
        },
      });
      realtimeAsrRef.current = session;
      setState('listening');
      const started = await session.start();
      if (!started || !isCurrentStart()) {
        if (realtimeAsrRef.current === session) realtimeAsrRef.current = null;
        await session.cancel();
        if (isCurrentStart()) setState('idle');
      }
    } catch (e: any) {
      if (!isCurrentStart()) return;
      const session = realtimeAsrRef.current;
      realtimeAsrRef.current = null;
      await session?.cancel().catch(() => undefined);
      setError(String(e?.message || e));
      setState('error');
      await setPlaybackMode();
    }
  }, [cancelActiveAgentTurn, finalizeListening, setPlaybackMode, stopCurrentSpeech]);

  const stopListening = useCallback(async () => {
    listeningStartSeqRef.current += 1;
    await finalizeListening();
  }, [finalizeListening]);

  const reset = useCallback(() => {
    listeningStartSeqRef.current += 1;
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (resumeListeningTimerRef.current) {
      clearTimeout(resumeListeningTimerRef.current);
      resumeListeningTimerRef.current = null;
    }
    // 和 startListening/unmount 使用同一顺序，避免 cancel 回调继续播下一段。
    ttsQueueRef.current = [];
    pendingTextRef.current = '';
    assistantTextRef.current = '';
    void stopCurrentSpeech();
    recordedItemsRef.current = [];
    const session = realtimeAsrRef.current;
    realtimeAsrRef.current = null;
    void session?.cancel();
    const finalizingSession = finalizingAsrRef.current;
    finalizingAsrRef.current = null;
    void finalizingSession?.cancel();
    void cancelActiveAgentTurn().catch(() => undefined);
    void setPlaybackMode();
    setState('idle');
    setTranscript('');
    setError(null);
  }, [cancelActiveAgentTurn, stopCurrentSpeech, setPlaybackMode]);

  useEffect(() => subscribeAIConsentInvalidation(reset), [reset]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      listeningStartSeqRef.current += 1;
      if (resumeListeningTimerRef.current) {
        clearTimeout(resumeListeningTimerRef.current);
        resumeListeningTimerRef.current = null;
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      ttsQueueRef.current = [];
      pendingTextRef.current = '';
      void stopCurrentSpeech();
      const session = realtimeAsrRef.current;
      realtimeAsrRef.current = null;
      void session?.cancel();
      const finalizingSession = finalizingAsrRef.current;
      finalizingAsrRef.current = null;
      void finalizingSession?.cancel();
      void cancelActiveAgentTurn().catch(() => undefined);
    };
  }, [cancelActiveAgentTurn, stopCurrentSpeech]);

  /**
   * 直接喂一段文本走 TTS 播 (不走 LLM, 用于晨间简报 / 系统播报场景).
   *
   * 行为:
   *   - 把 text 作为 assistant turn 加到 turns
   *   - 按句切段入 TTS 队列, 串行播完
   *   - opts.thenListen=true: 播完自动进 listening, 接用户接话 (Agent Native 闭环)
   */
  const speakDirect = useCallback(
    async (text: string, opts?: { thenListen?: boolean }) => {
      if (!text || !text.trim()) return;
      await refreshVoiceStyle();
      if (!mountedRef.current) return;
      // 清当前播放队列, 防止冲撞
      ttsQueueRef.current = [];
      pendingTextRef.current = '';
      forceIosTtsRef.current = false;
      ttsErrorRef.current = null;
      await stopCurrentSpeech();

      setState('speaking');
      setTurns((prev) => [...prev, { role: 'assistant', text, at: Date.now() }]);

      // 整段入队 (不流式, 已经是完整一段)
      pendingTextRef.current = text;
      flushTail();

      await finishTTS();
      if (!mountedRef.current) return;

      if (opts?.thenListen) {
        setState('idle');
        // 等 200ms 让用户感知"该我说了"
        resumeListeningTimerRef.current = setTimeout(() => {
          resumeListeningTimerRef.current = null;
          if (mountedRef.current) void startListening();
        }, 200);
      } else {
        setState('idle');
      }
    },
    [refreshVoiceStyle, stopCurrentSpeech, flushTail, finishTTS, startListening],
  );

  return {
    state,
    transcript,
    turns,
    error,
    startListening,
    stopListening,
    reset,
    speakDirect,
    loadConversation: useCallback(async (conversationId: number) => {
      // 加载历史对话 → 填 turns 展示 (不触发 TTS 回放, 只是历史气泡 review).
      // 用户可以接着说, 新消息会 append 到同一 conversation_id.
      try {
        const { messages } = await getConversationMessages(conversationId);
        conversationIdRef.current = conversationId;
        const mapped: VoiceTurn[] = messages
          .filter(m => m.role === 'user' || m.role === 'assistant')
          .map(m => ({
            role: m.role as 'user' | 'assistant',
            text: (m.content || '').toString(),
            at: Date.parse((m as any).created_at || '') || Date.now(),
          }));
        setTurns(mapped);
      } catch {
        // 静默失败, 保留空 turns
      }
    }, []),
    isActive: state !== 'idle' && state !== 'error',
    // I Phase 2: 本次会话内成功 health_record 摘要 (调用方读 .current 即可, 不需要 React state)
    recordedItemsRef,
  };
}
