import * as Speech from 'expo-speech';
import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * 语音风格 provider 抽象.
 *
 * 当前 provider:
 *   - ios   : expo-speech 调 AVSpeechSynthesizer (本机 iOS 内置 voices)
 *   - cloud : 后端 /tts/synthesize 代理阿里云 DashScope CosyVoice (真人级)
 *
 * 未来 provider:
 *   - voxcpm: 自部署 VoxCPM 开源模型 + 自有 IP 音色 (合法 voice cloning, v2)
 *
 * 设计原则:
 *   - 不在 UI/代码里用明星本名 (民法典 1023 声音权; App Store 5.2.1)
 *   - 每个 style 带 provider + params, 调用方只关心 "选哪个 key"
 *   - cloud 不可用时自动降级到 ios
 */

export type VoiceProvider = 'ios' | 'cloud' | 'voxcpm';

export type VoiceStyle =
  // iOS 本地 (无网络即可用)
  | 'ios_gentle_tw'
  | 'ios_standard_cn'
  | 'ios_system'
  // 阿里云 CosyVoice 云端
  | 'cloud_cloned_private_female' // v3.5-plus 声音复刻 — 专属授权样本
  | 'cloud_soft_hk_female'    // longjiayi_v2 — 港普女声, 柔软感
  | 'cloud_warm_female'       // longwan_v2
  | 'cloud_gentle_cs_female'  // longyue_v2
  | 'cloud_knowing_female'    // longxiaochun_v2
  | 'cloud_casual_female'     // longxiaobai_v2
  | 'cloud_calm_male';        // longcheng_v2

const STORAGE_KEY = 'tts_voice_style_v3';

// 默认走云端"私享女声" — 用户专属声音复刻
export const DEFAULT_VOICE_STYLE: VoiceStyle = 'cloud_cloned_private_female';

export interface VoiceStyleOption {
  key: VoiceStyle;
  provider: VoiceProvider;
  label: string;
  description: string;
  badge?: string;
  // iOS provider 用的 SpeechOptions; cloud provider 用 cloudVoiceKey (backend 理解的 voice_style)
  speechOptions?: Pick<Speech.SpeechOptions, 'voice' | 'language' | 'rate' | 'pitch'>;
  cloudVoiceKey?:
    | 'cloned_private_female'
    | 'soft_hk_female'
    | 'warm_female'
    | 'gentle_cs_female'
    | 'knowing_female'
    | 'casual_female'
    | 'calm_male';
}

export const VOICE_STYLES: VoiceStyleOption[] = [
  {
    key: 'cloud_cloned_private_female',
    provider: 'cloud',
    label: '私享女声',
    description: '专属声音复刻, 真人级 (需联网)',
    badge: '推荐',
    cloudVoiceKey: 'cloned_private_female',
  },
  {
    key: 'cloud_soft_hk_female',
    provider: 'cloud',
    label: '柔软女声',
    description: '带港普口音, 温柔有亲和力 (需联网)',
    cloudVoiceKey: 'soft_hk_female',
  },
  {
    key: 'cloud_warm_female',
    provider: 'cloud',
    label: '温暖女声',
    description: '温暖自然, 日常播报',
    cloudVoiceKey: 'warm_female',
  },
  {
    key: 'cloud_gentle_cs_female',
    provider: 'cloud',
    label: '温柔女声',
    description: '标准普通话, 柔和',
    cloudVoiceKey: 'gentle_cs_female',
  },
  {
    key: 'cloud_knowing_female',
    provider: 'cloud',
    label: '知性女声',
    description: '清晰知性, 沉稳',
    cloudVoiceKey: 'knowing_female',
  },
  {
    key: 'cloud_casual_female',
    provider: 'cloud',
    label: '休闲女声',
    description: '自然轻松, 真人感',
    cloudVoiceKey: 'casual_female',
  },
  {
    key: 'cloud_calm_male',
    provider: 'cloud',
    label: '沉稳男声',
    description: '低频稳重, 专业感',
    cloudVoiceKey: 'calm_male',
  },
  {
    key: 'ios_gentle_tw',
    provider: 'ios',
    label: '台腔女声 (离线)',
    description: 'iOS 内置, 无网络可用',
    speechOptions: {
      voice: 'com.apple.ttsbundle.Mei-Jia-compact',
      language: 'zh-TW',
      rate: 0.95,
      pitch: 1.05,
    },
  },
  {
    key: 'ios_standard_cn',
    provider: 'ios',
    label: '普通话 (离线)',
    description: 'iOS 内置, 大陆普通话',
    speechOptions: {
      voice: 'com.apple.ttsbundle.Tingting-compact',
      language: 'zh-CN',
      rate: 1.0,
      pitch: 1.0,
    },
  },
  {
    key: 'ios_system',
    provider: 'ios',
    label: '系统默认 (离线)',
    description: '跟随 iOS 系统设置',
    speechOptions: { language: 'zh-CN', rate: 1.0, pitch: 1.0 },
  },
];

export function getVoiceStyle(key: VoiceStyle): VoiceStyleOption {
  return VOICE_STYLES.find(v => v.key === key) ?? VOICE_STYLES[0];
}

export async function loadVoiceStyle(): Promise<VoiceStyle> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (raw && VOICE_STYLES.some(v => v.key === raw)) return raw as VoiceStyle;
    // 迁移: v2 中已重命名的 cloud_* key
    const cloudRename: Record<string, VoiceStyle> = {
      cloud_gentle_female: 'cloud_knowing_female',  // 老"温柔知性" → 新"知性女声"
      cloud_bright_female: 'cloud_gentle_cs_female', // 老"明亮" → 新"温柔"
    };
    if (raw && cloudRename[raw]) return cloudRename[raw];
    // v2 → v3: 老用户档自动迁到新默认 (私享女声), 但保留他们手动选过的非默认档
    const v2 = await AsyncStorage.getItem('tts_voice_style_v2');
    if (v2 && VOICE_STYLES.some(v => v.key === v2)) {
      // 老默认 cloud_soft_hk_female 视为"未手动改" → 升级到新默认
      if (v2 === 'cloud_soft_hk_female') return DEFAULT_VOICE_STYLE;
      return v2 as VoiceStyle;
    }
    if (v2 && cloudRename[v2]) return cloudRename[v2];
    // 兼容 v1 (iOS-only 档)
    const old = await AsyncStorage.getItem('tts_voice_style');
    if (old === 'gentle_tw') return 'ios_gentle_tw';
    if (old === 'standard_cn') return 'ios_standard_cn';
    if (old === 'system') return 'ios_system';
  } catch {
    // 旁路: AsyncStorage 读失败 → 用默认档.
  }
  return DEFAULT_VOICE_STYLE;
}

export async function saveVoiceStyle(style: VoiceStyle): Promise<void> {
  try { await AsyncStorage.setItem(STORAGE_KEY, style); } catch (e) {
    if (__DEV__) console.warn('[voiceStyle] save failed:', e);
  }
}

/**
 * 取 iOS provider 下对应的 SpeechOptions (voice 不存在自动剥掉).
 * cloud provider 调用方不应使用这个, 改用 cloudTts.synthesize.
 */
export async function resolveIosSpeechOptions(style: VoiceStyle): Promise<Speech.SpeechOptions> {
  const opt = getVoiceStyle(style);
  const speech = opt.speechOptions ?? { language: 'zh-CN', rate: 1.0, pitch: 1.0 };
  if (!speech.voice) return { ...speech };
  try {
    const voices = await Speech.getAvailableVoicesAsync();
    if (voices.some(v => v.identifier === speech.voice)) return { ...speech };
    const { voice: _v, ...fallback } = speech;
    return fallback;
  } catch {
    const { voice: _v, ...fallback } = speech;
    return fallback;
  }
}
