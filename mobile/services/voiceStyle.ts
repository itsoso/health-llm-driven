import * as Speech from 'expo-speech';
import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * 语音风格档位 — 用户可在 Settings → 语音风格 切换.
 *
 * 注意: 不做明星 IP (林志玲 / 某艺人), 只做"风格". 民法典 1023 条声音权 +
 * App Store 5.2.1 IP 审核都会咬明星名.
 */
export type VoiceStyle = 'gentle_tw' | 'standard_cn' | 'system';

const STORAGE_KEY = 'tts_voice_style';
export const DEFAULT_VOICE_STYLE: VoiceStyle = 'gentle_tw';

export interface VoiceStyleOption {
  key: VoiceStyle;
  label: string;
  description: string;
  // expo-speech SpeechOptions (voice / language / rate / pitch). voice 可能不存在 → fallback 走 system.
  speechOptions: Pick<Speech.SpeechOptions, 'voice' | 'language' | 'rate' | 'pitch'>;
}

export const VOICE_STYLES: VoiceStyleOption[] = [
  {
    key: 'gentle_tw',
    label: '温柔台腔女声',
    description: '台湾普通话, 语速略慢, 有亲和力',
    speechOptions: {
      voice: 'com.apple.ttsbundle.Mei-Jia-compact',
      language: 'zh-TW',
      rate: 0.95,
      pitch: 1.05,
    },
  },
  {
    key: 'standard_cn',
    label: '标准普通话',
    description: '大陆普通话, 正常语速, 清晰',
    speechOptions: {
      voice: 'com.apple.ttsbundle.Tingting-compact',
      language: 'zh-CN',
      rate: 1.0,
      pitch: 1.0,
    },
  },
  {
    key: 'system',
    label: '系统默认',
    description: '跟随 iOS 系统设置',
    speechOptions: {
      language: 'zh-CN',
      rate: 1.0,
      pitch: 1.0,
    },
  },
];

export async function loadVoiceStyle(): Promise<VoiceStyle> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (raw && VOICE_STYLES.some(v => v.key === raw)) return raw as VoiceStyle;
  } catch {}
  return DEFAULT_VOICE_STYLE;
}

export async function saveVoiceStyle(style: VoiceStyle): Promise<void> {
  try { await AsyncStorage.setItem(STORAGE_KEY, style); } catch {}
}

/**
 * 取当前 voice style 对应的 SpeechOptions. 若 voice identifier 在本机不存在,
 * 自动降级到 system (只用 language/rate/pitch).
 * getAvailableVoicesAsync 首次调用稍慢, 调用方自己 cache.
 */
export async function resolveSpeechOptions(style: VoiceStyle): Promise<Speech.SpeechOptions> {
  const opt = VOICE_STYLES.find(v => v.key === style) ?? VOICE_STYLES[0];
  const speech = opt.speechOptions;
  if (!speech.voice) return { ...speech };
  try {
    const voices = await Speech.getAvailableVoicesAsync();
    if (voices.some(v => v.identifier === speech.voice)) return { ...speech };
    // voice 不存在, 剥掉 voice 字段让系统按 language 走默认
    const { voice: _voice, ...fallback } = speech;
    return fallback;
  } catch {
    const { voice: _voice, ...fallback } = speech;
    return fallback;
  }
}
