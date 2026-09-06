/**
 * 云端 TTS 客户端 — 走后端 /tts/synthesize 代理 (阿里云 CosyVoice).
 *
 * 为什么要后端代理:
 *   1. DashScope API key 不能泄露到客户端
 *   2. 句级缓存 — 同一段文本多用户共享 mp3, 省钱
 *   3. Provider 切换 (未来上 VoxCPM 自部署) 不用发 mobile 版本
 *
 * 客户端用 expo-file-system 写 mp3 到临时文件, expo-audio useAudioPlayer 播放.
 * (不能用 Speech.speak — 那是 iOS 系统合成; 云端 mp3 必须走音频播放器.)
 */
import * as FileSystem from 'expo-file-system/legacy';
import api from './api';
import { requireAIConsent } from './aiConsent';

export type CloudVoiceKey =
  | 'cloned_private_female'
  | 'soft_hk_female'
  | 'warm_female'
  | 'gentle_cs_female'
  | 'knowing_female'
  | 'casual_female'
  | 'calm_male';

export interface SynthesizeOpts {
  text: string;
  voiceKey: CloudVoiceKey;
  speed?: number;   // 0.5 - 2.0
}

export interface SynthesizedAudio {
  localUri: string;   // file:// path to mp3
  bytes: number;
}

/**
 * 合成一段文本, 返回本地 mp3 file uri. 客户端侧不做缓存
 * (后端已做内容级缓存, 本地再缓存只是 double-cache 无必要).
 */
export async function synthesize(opts: SynthesizeOpts): Promise<SynthesizedAudio> {
  const text = opts.text.trim();
  if (!text) throw new Error('text empty');
  await requireAIConsent();

  // axios 拿 arraybuffer 再写入文件. fetch + FileSystem.writeAsStringAsync(base64)
  // 也能做到, 但 axios 统一了超时和拦截器.
  const resp = await api.post(
    '/tts/synthesize',
    { text, voice_style: opts.voiceKey, speed: opts.speed ?? 1.0 },
    {
      responseType: 'arraybuffer',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'audio/mpeg',
      },
    },
  );

  if (resp.status !== 200) {
    throw new Error(`TTS HTTP ${resp.status}`);
  }

  // arraybuffer → base64 → 写 mp3
  const bytes = resp.data as ArrayBuffer;
  const base64 = arrayBufferToBase64(bytes);
  const cacheDir = FileSystem.cacheDirectory;
  if (!cacheDir) throw new Error('no cache dir');
  const filename = `tts_${Date.now()}_${Math.random().toString(36).slice(2, 8)}.mp3`;
  const localUri = `${cacheDir}${filename}`;
  await FileSystem.writeAsStringAsync(localUri, base64, {
    encoding: FileSystem.EncodingType.Base64,
  });
  return { localUri, bytes: bytes.byteLength };
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(
      null,
      bytes.subarray(i, Math.min(i + chunk, bytes.length)) as unknown as number[],
    );
  }
  // React Native btoa available via global polyfill; fallback to Buffer if not
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const g = globalThis as any;
  if (typeof g.btoa === 'function') return g.btoa(binary);
  return Buffer.from(binary, 'binary').toString('base64');
}

/**
 * 清理缓存目录里的临时 TTS mp3 (conversation 退出时调用).
 */
export async function cleanupTmpTts(): Promise<void> {
  try {
    const dir = FileSystem.cacheDirectory;
    if (!dir) return;
    const entries = await FileSystem.readDirectoryAsync(dir);
    await Promise.all(
      entries
        .filter((n) => n.startsWith('tts_') && n.endsWith('.mp3'))
        .map((n) => FileSystem.deleteAsync(dir + n, { idempotent: true })),
    );
  } catch {
    // 旁路: 缓存清理 fire-and-forget, 失败下次启动再清.
  }
}
