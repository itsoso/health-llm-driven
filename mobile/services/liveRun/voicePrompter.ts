/**
 * Live Run 离线语音提示 (P2).
 *
 * 职责:
 * - 维护规则触发时间戳, 90s 内同规则不重复
 * - 调用 expo-speech, 离线合成 (不用网络)
 * - 队列 pending 提示, 正在播放时新事件入队
 *
 * 设计:
 * - 规则文本要短 (<15 字), 动词开头
 * - 避免 TTS 朗读问题: 处理 "3.6" 小数点 → "3点6"
 * - 不打断用户: 正在播放时等待结束再播下一个
 */
import * as Speech from 'expo-speech';

const COOLDOWN_MS = 90_000;

interface QueuedSpeak {
  ruleId: string;
  message: string;
  addedAt: number;
}

const queue: QueuedSpeak[] = [];
const lastTriggeredAt = new Map<string, number>();
let speaking = false;

function normalizeForTTS(text: string): string {
  return text.replace(/(\d)\.(\d)/g, '$1点$2');
}

function pump(): void {
  if (speaking) return;
  const next = queue.shift();
  if (!next) return;
  speaking = true;
  try {
    Speech.speak(normalizeForTTS(next.message), {
      language: 'zh-CN',
      onDone: () => {
        speaking = false;
        if (queue.length > 0) setTimeout(pump, 200);
      },
      onStopped: () => {
        speaking = false;
      },
      onError: (e) => {
        console.warn('[VoicePrompter] speak error:', e);
        speaking = false;
        if (queue.length > 0) setTimeout(pump, 200);
      },
    });
  } catch (e) {
    console.warn('[VoicePrompter] speak threw:', e);
    speaking = false;
  }
}

export function triggerRule(
  ruleId: string,
  message: string,
  _metricSnapshot?: Record<string, any>,
): boolean {
  const now = Date.now();
  const last = lastTriggeredAt.get(ruleId);
  if (last != null && now - last < COOLDOWN_MS) {
    return false;
  }
  lastTriggeredAt.set(ruleId, now);
  queue.push({ ruleId, message, addedAt: now });
  pump();
  return true;
}

export function clearQueue(): void {
  queue.length = 0;
  lastTriggeredAt.clear();
  try {
    Speech.stop();
  } catch {
    // ignore
  }
  speaking = false;
}

export function speakNow(message: string): void {
  queue.push({ ruleId: 'manual', message, addedAt: Date.now() });
  pump();
}
