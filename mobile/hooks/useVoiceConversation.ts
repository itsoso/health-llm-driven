import { useCallback, useEffect, useRef, useState } from 'react';
import { ensureAIConsent } from '../services/aiConsent';
import { aiConsentRevision, subscribeAIConsentInvalidation } from '../services/aiConsentState';
import Voice, {
  type SpeechResultsEvent,
  type SpeechErrorEvent,
} from '@react-native-voice/voice';
import * as Speech from 'expo-speech';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { streamChat, getConversationMessages } from '../services/chat';
import {
  loadVoiceStyle, resolveIosSpeechOptions, getVoiceStyle, type VoiceStyle,
} from '../services/voiceStyle';
import { synthesize as cloudSynthesize, cleanupTmpTts } from '../services/cloudTts';
import { estimateTtsFallbackMs, shouldFinishAudioPlayback } from '../utils/audioPlayback';
import { splitTextForCloudTts } from '../utils/ttsText';
import {
  bindVoiceEventHandlers,
  isVoiceEventHandlerOwner,
  releaseVoiceEventHandlers,
  type VoiceEventHandlers,
  type VoiceEventLease,
} from '../services/voiceEventRouter';

/**
 * 语音连续对话状态机.
 *
 * idle → listening → thinking → speaking → idle
 *
 * TTS provider 双栈:
 *   - ios   : expo-speech AVSpeechSynthesizer (离线, 机械感)
 *   - cloud : 后端 /tts/synthesize 代理阿里云 CosyVoice (真人级, 需联网)
 *
 * 云端失败 (网络 / 后端错误) 自动降级到 ios 档, 保证不哑巴.
 *
 * TTS 用"句尾符号"(。！？.!?\n) 切段, 收到一整句就入队播. 串行播放, 避免并发打架.
 * 打断: startListening 会 stop() + 清队列, 让用户随时插话.
 */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface VoiceTurn {
  role: 'user' | 'assistant';
  text: string;
  at: number;
}

// 只用真标点切句; \n 不算句末 — 段落换行交给标点本身的自然停顿,
// 否则 \n\n 会触发额外的 synth 来回 (网络 500ms+), 听起来"卡顿"
// `.` 前后都是数字 (3.6 / 1.0.2) 不当句末 — 否则 "3.6 公里" 会被切成 "3" + "6 公里"
// 后面的 stripMarkdownForTTS 拿不到完整 decimal 就没法念成"3 点 6"
const SENTENCE_END = /[。！？!?]|(?<!\d)\.(?!\d)/;
// 太短的句子 (< 3 字) 直接合并到下一个, 避免"是。" / "OK!" 这种微音轨抖动
const MIN_SENTENCE_LEN = 3;

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


interface ActivePlayer {
  cancel: () => void;
}

export function useVoiceConversation() {
  const [state, setState] = useState<VoiceState>('idle');
  // 给 Voice listener 用的 stateRef — 避免 useEffect 依赖 state
  // (依赖 state 会让 Voice 监听器每次状态切换都重挂, 在 iOS 上覆盖前一份导致 partial events 丢失)
  const stateRef = useRef<VoiceState>('idle');
  useEffect(() => { stateRef.current = state; }, [state]);
  const [transcript, setTranscript] = useState('');
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const latestPartialRef = useRef('');
  const conversationIdRef = useRef<number | undefined>(undefined);

  // 静默自动提交 — onSpeechPartialResults 收到新文字就重置 timer,
  // 持续 1.2s 没新内容 → 自动 stop + submit, 不用用户主动点停止.
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 防双发: silence timer 触发 submit 后置 true, onSpeechResults/End 看到就跳过.
  // Voice.stop() 会触发 onSpeechResults 带 final 文本 + onSpeechEnd, 不防就发两遍.
  const justSubmittedRef = useRef(false);
  const SILENCE_AUTO_SUBMIT_MS = 1200;

  const pendingTextRef = useRef('');
  const assistantTextRef = useRef('');
  const ttsQueueRef = useRef<string[]>([]);
  const isSpeakingRef = useRef(false);
  // prefetch: 当前句在播时, 提前合成队列下一句的音频, 消除句间 network gap
  const preSynthRef = useRef<{ text: string; promise: Promise<string> } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const voiceEventLeaseRef = useRef<VoiceEventLease | null>(null);
  const voiceHandlersRef = useRef<VoiceEventHandlers>({});
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

  // 云端播放中的 player, stop 时用于打断
  const activePlayerRef = useRef<ActivePlayer | null>(null);

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

  const setRecordingMode = useCallback(async () => {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording: true,  // → .playAndRecord category
      });
    } catch (e) {
      if (__DEV__) console.warn('[voice] setRecordingMode failed:', e);
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

  const stopCurrentSpeech = useCallback(() => {
    try { Speech.stop(); } catch {}
    activePlayerRef.current?.cancel();
    activePlayerRef.current = null;
    isSpeakingRef.current = false;
  }, []);

  const speakViaIos = useCallback((text: string, onDone: () => void) => {
    Speech.speak(text, {
      ...iosOptsRef.current,
      onDone: () => { isSpeakingRef.current = false; onDone(); },
      onStopped: () => { isSpeakingRef.current = false; },
      onError: () => { isSpeakingRef.current = false; onDone(); },
    });
  }, []);

  const speakViaCloud = useCallback(async (text: string, onDone: () => void) => {
    const opt = getVoiceStyle(voiceStyleRef.current);
    const voiceKey = opt.cloudVoiceKey ?? 'cloned_private_female';
    try {
      // 优先复用 prefetch 好的 audio (另一句在播时合成的)
      let localUri: string;
      const pre = preSynthRef.current;
      if (pre && pre.text === text) {
        preSynthRef.current = null;
        localUri = await pre.promise;
      } else {
        const synth = await cloudSynthesize({ text, voiceKey });
        localUri = synth.localUri;
      }

      // 立即为队列下一句预合成, 跟本句播放并行, 消除句间 network gap
      const nextText = ttsQueueRef.current[0];
      if (nextText && !preSynthRef.current) {
        const p = cloudSynthesize({ text: nextText, voiceKey }).then(r => r.localUri).catch(() => '');
        preSynthRef.current = { text: nextText, promise: p };
      }
      // 新 player 每句一个, 简化生命周期 (非高频场景, 代价可接受)
      const player = createAudioPlayer({ uri: localUri });
      let finished = false;
      let fallbackTimer: ReturnType<typeof setTimeout> | null = null;
      const finish = () => {
        if (finished) return;
        finished = true;
        if (fallbackTimer) {
          clearTimeout(fallbackTimer);
          fallbackTimer = null;
        }
        try { player.remove(); } catch {}
        activePlayerRef.current = null;
        isSpeakingRef.current = false;
        onDone();
      };
      activePlayerRef.current = {
        cancel: () => {
          try { player.pause(); } catch {}
          finish();
        },
      };
      // 监听播放完成; expo-audio 的 status 回调通过 addListener
      const sub = player.addListener('playbackStatusUpdate', (status: any) => {
        if (shouldFinishAudioPlayback(status)) {
          sub?.remove?.();
          finish();
        }
      });
      // 兜底: player 若永不触发 finish (比如 mp3 损坏), 硬超时后 finish.
      // CosyVoice 实测约每字 200-250ms (中文), 取 280ms + 8s 安全余量,
      // 必须比真实播放时长长, 否则兜底先触发 finish → 下一句重叠播.
      // 80 字 → ~22s + 8s = 30s. 最大 60s.
      const estMs = estimateTtsFallbackMs(text, (player as any).duration);
      fallbackTimer = setTimeout(() => { if (!finished) { try { sub?.remove?.(); } catch {}; finish(); } }, estMs);
      player.play();
    } catch (e) {
      // 云端失败 → 降级 iOS
      if (__DEV__) console.warn('[TTS] cloud failed, fallback to iOS:', e);
      // 首次失败时也刷新一次 iOS voice opts 保证有得用
      if (!iosOptsRef.current.voice) {
        iosOptsRef.current = { language: 'zh-CN', rate: 1.0, pitch: 1.0 };
      }
      speakViaIos(text, onDone);
    }
  }, [speakViaIos]);

  const flushTTS = useCallback(() => {
    if (isSpeakingRef.current) return;
    const next = ttsQueueRef.current.shift();
    if (!next) return;
    isSpeakingRef.current = true;
    const provider = getVoiceStyle(voiceStyleRef.current).provider;
    const onDone = () => { isSpeakingRef.current = false; flushTTS(); };
    if (provider === 'cloud') {
      void speakViaCloud(next, onDone);
    } else {
      speakViaIos(next, onDone);
    }
  }, [speakViaCloud, speakViaIos]);

  const enqueueTtsText = useCallback((text: string) => {
    ttsQueueRef.current.push(...splitTextForCloudTts(text));
  }, []);

  const enqueueSentences = useCallback((chunk: string) => {
    pendingTextRef.current += chunk;
    while (true) {
      const m = pendingTextRef.current.match(SENTENCE_END);
      if (!m || m.index === undefined) break;
      const cut = m.index + 1;
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

  const submit = useCallback(async (userText: string) => {
    setState('thinking');
    setTurns((prev) => [...prev, { role: 'user', text: userText, at: Date.now() }]);

    await refreshVoiceStyle();

    pendingTextRef.current = '';
    assistantTextRef.current = '';
    ttsQueueRef.current = [];

    const ac = new AbortController();
    abortRef.current = ac;

    let replyStarted = false;

    try {
      let lastFailedTool = '';  // 同一 tool 连续失败只提示一次
      // channel='voice':语音转写可能失真(1.2s 静默即自动提交,用户未必复核),
      // 症状类记录在后端保留确认前置。
      for await (const evt of streamChat(userText, conversationIdRef.current, undefined, ac.signal, undefined, 'voice')) {
        if (evt.type === 'token' || evt.type === 'tool') {
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
      await waitTTSDrain();
      if (mountedRef.current) setState('idle');
    } catch (e: any) {
      const msg = e?.message || '请求失败';
      if (msg === 'aborted') {
        if (mountedRef.current) setState('idle');
        return;
      }
      if (!mountedRef.current) return;
      setError(msg);
      setTurns((prev) => [...prev, { role: 'assistant', text: `[错误] ${msg}`, at: Date.now() }]);
      setState('error');
    } finally {
      abortRef.current = null;
    }
  }, [refreshVoiceStyle, enqueueSentences, flushTail, waitTTSDrain]);

  // submit 用 ref 暴露给 Voice listener, 让 useEffect 只挂一次, 避免每次 state 变化重挂导致 partial events 丢失
  const submitRef = useRef(submit);
  useEffect(() => { submitRef.current = submit; }, [submit]);

  useEffect(() => {
    mountedRef.current = true;
    // 收到 partial 时重置 silence timer; 1.2s 内没新内容 → 自动 stop + submit.
    // 这比 iOS 系统的 onSpeechEnd (2-3s 才触发) 快得多, 体验上"说完即送".
    //
    // 注意: 此 effect 永不重挂 (deps=[]). Voice listener 只在 mount 时挂一次,
    // 在 unmount 时清理. submit/setPlaybackMode/stopCurrentSpeech 都通过 ref / closure
    // 访问最新值, 否则 state 变化会让 effect 重挂, iOS 上 Voice 监听器互相覆盖
    // 导致 partial events 直接丢失 → 用户看不到识别中文字.
    const armSilenceTimer = () => {
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = setTimeout(() => {
        const text = (latestPartialRef.current || '').trim();
        if (text) {
          // 防双发: 标记已提交, 后续 Voice.stop() 触发的 onSpeechResults/End
          // 看到 justSubmittedRef=true 就跳过, 不再 submit.
          justSubmittedRef.current = true;
          latestPartialRef.current = '';
          releaseVoiceEventHandlers(voiceEventLeaseRef.current);
          voiceEventLeaseRef.current = null;
          Voice.stop().catch(() => {});
          setPlaybackMode();
          submitRef.current(text);
        }
      }, SILENCE_AUTO_SUBMIT_MS);
    };

    voiceHandlersRef.current = {
      onSpeechPartialResults: (e: SpeechResultsEvent) => {
        // silence timer 已触发 submit → 接下来的 partial 全部忽略, 直到下次 startListening 重置
        if (justSubmittedRef.current) return;
        const val = e.value?.[0] || '';
        if (val && val !== latestPartialRef.current) {
          latestPartialRef.current = val;
          setTranscript(val);
          armSilenceTimer();
        }
      },
      onSpeechResults: (e: SpeechResultsEvent) => {
        if (justSubmittedRef.current) return;
        const val = e.value?.[0] || latestPartialRef.current;
        latestPartialRef.current = val;
        setTranscript(val);
        armSilenceTimer();
      },
      onSpeechEnd: () => {
        // silence timer 可能已经先触发提交了 → 跳过, 不重发
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
        }
        if (justSubmittedRef.current) {
          // 自然说完: 切回 playback 让后续 LLM reply TTS 走外放. 不 submit.
          releaseVoiceEventHandlers(voiceEventLeaseRef.current);
          voiceEventLeaseRef.current = null;
          setPlaybackMode();
          return;
        }
        const text = (latestPartialRef.current || '').trim();
        releaseVoiceEventHandlers(voiceEventLeaseRef.current);
        voiceEventLeaseRef.current = null;
        setPlaybackMode();
        if (text) submitRef.current(text);
        else if (stateRef.current !== 'thinking' && stateRef.current !== 'speaking') setState('idle');
      },
      onSpeechError: (e: SpeechErrorEvent) => {
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
        }
        const msg = e.error?.message || '语音识别失败';
        releaseVoiceEventHandlers(voiceEventLeaseRef.current);
        voiceEventLeaseRef.current = null;
        setError(msg);
        setState('error');
        setPlaybackMode();
      },
    };
    return () => {
      mountedRef.current = false;
      listeningStartSeqRef.current += 1;
      if (resumeListeningTimerRef.current) {
        clearTimeout(resumeListeningTimerRef.current);
        resumeListeningTimerRef.current = null;
      }
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      const ownsNativeSession = isVoiceEventHandlerOwner(voiceEventLeaseRef.current);
      releaseVoiceEventHandlers(voiceEventLeaseRef.current);
      voiceEventLeaseRef.current = null;
      if (ownsNativeSession) Voice.destroy().catch(() => undefined);
      // 清队列必须早于 cancel；cancel 会同步触发 onDone -> flushTTS。
      ttsQueueRef.current = [];
      pendingTextRef.current = '';
      preSynthRef.current = null;
      stopCurrentSpeech();
      abortRef.current?.abort();
      cleanupTmpTts().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startListening = useCallback(async () => {
    const startSeq = ++listeningStartSeqRef.current;
    if (!await ensureAIConsent() || !mountedRef.current || startSeq !== listeningStartSeqRef.current) return;
    const consentRevision = aiConsentRevision();
    const isCurrentStart = () => mountedRef.current && startSeq === listeningStartSeqRef.current
      && consentRevision === aiConsentRevision();
    try {
      // 顺序很重要: 先清队列 + preSynth, 再 stopCurrentSpeech.
      // stopCurrentSpeech 会同步触发 finish → onDone → flushTTS, 若此时队列未清
      // 就会继续播下一句, 打断失败.
      ttsQueueRef.current = [];
      pendingTextRef.current = '';
      preSynthRef.current = null;
      abortRef.current?.abort();
      stopCurrentSpeech();
      setError(null);
      setTranscript('');
      latestPartialRef.current = '';
      justSubmittedRef.current = false;  // 新一轮开始, 解锁 listener
      // 先切到 .playAndRecord, 再启动 Voice — 顺序很重要, Voice.start 依赖 session 已经就绪
      await setRecordingMode();
      if (!isCurrentStart()) return;
      releaseVoiceEventHandlers(voiceEventLeaseRef.current);
      voiceEventLeaseRef.current = bindVoiceEventHandlers(voiceHandlersRef.current);
      setState('listening');
      await Voice.start('zh-CN');
      if (!isCurrentStart()) {
        await Voice.cancel();
        await Voice.stop();
      }
    } catch (e: any) {
      if (!isCurrentStart()) return;
      releaseVoiceEventHandlers(voiceEventLeaseRef.current);
      voiceEventLeaseRef.current = null;
      setError(String(e?.message || e));
      setState('error');
      // 失败也切回 playback, 免得下次 TTS 又走听筒
      setPlaybackMode();
    }
  }, [stopCurrentSpeech, setRecordingMode, setPlaybackMode]);

  const stopListening = useCallback(async () => {
    listeningStartSeqRef.current += 1;
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    try { await Voice.stop(); } catch {}
    // 录音结束切回 .playback, 后续 TTS 走外放
    await setPlaybackMode();
  }, [setPlaybackMode]);

  const reset = useCallback(() => {
    listeningStartSeqRef.current += 1;
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    justSubmittedRef.current = false;
    if (resumeListeningTimerRef.current) {
      clearTimeout(resumeListeningTimerRef.current);
      resumeListeningTimerRef.current = null;
    }
    // 和 startListening/unmount 使用同一顺序，避免 cancel 回调继续播下一段。
    ttsQueueRef.current = [];
    pendingTextRef.current = '';
    assistantTextRef.current = '';
    preSynthRef.current = null;
    stopCurrentSpeech();
    recordedItemsRef.current = [];
    abortRef.current?.abort();
    releaseVoiceEventHandlers(voiceEventLeaseRef.current);
    voiceEventLeaseRef.current = null;
    Voice.stop().catch(() => {});
    Voice.cancel?.().catch(() => {});
    setPlaybackMode();
    setState('idle');
    setTranscript('');
    setError(null);
  }, [stopCurrentSpeech, setPlaybackMode]);

  useEffect(() => subscribeAIConsentInvalidation(reset), [reset]);

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
      preSynthRef.current = null;
      stopCurrentSpeech();

      setState('speaking');
      setTurns((prev) => [...prev, { role: 'assistant', text, at: Date.now() }]);

      // 整段入队 (不流式, 已经是完整一段)
      pendingTextRef.current = text;
      flushTail();

      await waitTTSDrain();
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
    [refreshVoiceStyle, stopCurrentSpeech, flushTail, startListening, waitTTSDrain],
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
