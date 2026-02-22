'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';

/**
 * 语音快捷记录页面 - 适用于所有设备（华为/安卓/iPhone）
 *
 * 用法：
 *   https://health.executor.life/quick-record?token=YOUR_TOKEN
 *
 * 流程：
 *   打开页面 → 自动开始录音 → 识别为文字 → 发送到健康API → 朗读结果
 */

const API_BASE = 'https://health.executor.life/api';

type Phase = 'idle' | 'recording' | 'transcribing' | 'sending' | 'speaking' | 'done' | 'error';

export default function QuickRecordPage() {
  const searchParams = useSearchParams();
  const tokenFromUrl = searchParams.get('token') || '';

  const [token, setToken] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [transcript, setTranscript] = useState('');
  const [reply, setReply] = useState('');
  const [error, setError] = useState('');
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // 初始化 token：URL 参数 > localStorage
  useEffect(() => {
    if (tokenFromUrl) {
      setToken(tokenFromUrl);
      localStorage.setItem('quick_record_token', tokenFromUrl);
    } else {
      const saved = localStorage.getItem('quick_record_token') || localStorage.getItem('auth_token') || '';
      setToken(saved);
    }
  }, [tokenFromUrl]);

  // token 就绪后自动开始录音
  useEffect(() => {
    if (token && phase === 'idle') {
      startRecording();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
  }, []);

  // 页面卸载时清理
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  const startRecording = async () => {
    setPhase('recording');
    setTranscript('');
    setReply('');
    setError('');
    setRecordingSeconds(0);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 选择兼容的 MIME 类型
      let mimeType = 'audio/webm';
      if (!MediaRecorder.isTypeSupported('audio/webm')) {
        mimeType = 'audio/mp4';
        if (!MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = '';  // 让浏览器自选
        }
      }

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: mediaRecorder.mimeType });
        if (audioBlob.size < 1000) {
          setError('录音太短，请重试');
          setPhase('error');
          return;
        }

        await processAudio(audioBlob, mediaRecorder.mimeType);
      };

      mediaRecorder.start();

      // 录音计时
      timerRef.current = setInterval(() => {
        setRecordingSeconds(s => s + 1);
      }, 1000);

    } catch (err: any) {
      console.error('麦克风访问失败:', err);
      setError('无法访问麦克风，请在浏览器设置中允许麦克风权限');
      setPhase('error');
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
  };

  const processAudio = async (audioBlob: Blob, mimeType: string) => {
    // Step 1: 语音转文字
    setPhase('transcribing');
    try {
      const reader = new FileReader();
      const base64 = await new Promise<string>((resolve, reject) => {
        reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(audioBlob);
      });

      const format = mimeType.includes('mp4') ? 'mp4' : 'webm';
      const transcribeRes = await fetch(`${API_BASE}/chat/transcribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ audio_base64: base64, audio_format: format }),
      });

      if (!transcribeRes.ok) {
        throw new Error(`语音识别失败: ${transcribeRes.status}`);
      }

      const transcribeData = await transcribeRes.json();
      const text = transcribeData.text?.trim();

      if (!text) {
        setError('未识别到语音内容，请重试');
        setPhase('error');
        return;
      }

      setTranscript(text);

      // Step 2: 发送到健康 API
      setPhase('sending');
      const sayRes = await fetch(`${API_BASE}/siri/say`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text }),
      });

      if (!sayRes.ok) {
        throw new Error(`API 请求失败: ${sayRes.status}`);
      }

      const sayData = await sayRes.json();
      const replyText = sayData.text || '已记录';
      setReply(replyText);

      // Step 3: 朗读结果
      setPhase('speaking');
      await speakText(replyText);
      setPhase('done');

    } catch (err: any) {
      console.error('处理失败:', err);
      setError(err.message || '处理失败，请重试');
      setPhase('error');
    }
  };

  const speakText = (text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) {
        resolve();
        return;
      }

      // 截取前200字朗读，避免太长
      const shortText = text.length > 200 ? text.slice(0, 200) + '...' : text;
      const utterance = new SpeechSynthesisUtterance(shortText);
      utterance.lang = 'zh-CN';
      utterance.rate = 1.1;
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve();
      // 5秒超时保底
      const timeout = setTimeout(() => resolve(), 15000);
      utterance.onend = () => {
        clearTimeout(timeout);
        resolve();
      };
      window.speechSynthesis.speak(utterance);
    });
  };

  // 阶段展示配置
  const phaseConfig: Record<Phase, { icon: string; text: string; color: string; bgColor: string }> = {
    idle: { icon: '🎤', text: '准备中...', color: 'text-gray-500', bgColor: 'bg-gray-100' },
    recording: { icon: '🔴', text: `正在听你说... ${recordingSeconds}秒`, color: 'text-red-600', bgColor: 'bg-red-50' },
    transcribing: { icon: '✍️', text: '正在识别语音...', color: 'text-blue-600', bgColor: 'bg-blue-50' },
    sending: { icon: '📡', text: '正在处理...', color: 'text-purple-600', bgColor: 'bg-purple-50' },
    speaking: { icon: '🔊', text: '正在朗读结果...', color: 'text-green-600', bgColor: 'bg-green-50' },
    done: { icon: '✅', text: '完成', color: 'text-green-700', bgColor: 'bg-green-50' },
    error: { icon: '❌', text: '出错了', color: 'text-red-600', bgColor: 'bg-red-50' },
  };

  const current = phaseConfig[phase];

  // 未设置 Token
  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 flex items-center justify-center p-6">
        <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center shadow-xl">
          <div className="text-5xl mb-4">🔑</div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">需要设置 Token</h1>
          <p className="text-sm text-gray-600 mb-6">
            请在健康 App 的「设置」页面复制 Token，然后通过链接参数传入。
          </p>
          <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-500 font-mono break-all">
            https://health.executor.life/quick-record?token=你的Token
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${current.bgColor} flex flex-col items-center justify-center p-6 transition-colors duration-500`}>
      {/* 主按钮区域 */}
      <div className="flex flex-col items-center gap-8 max-w-sm w-full">
        {/* 大圆按钮 */}
        <button
          onClick={() => {
            if (phase === 'recording') {
              stopRecording();
            } else if (phase === 'done' || phase === 'error' || phase === 'idle') {
              startRecording();
            }
          }}
          disabled={phase === 'transcribing' || phase === 'sending' || phase === 'speaking'}
          className={`
            w-40 h-40 rounded-full flex items-center justify-center text-6xl
            shadow-2xl transition-all duration-300 active:scale-95
            ${phase === 'recording'
              ? 'bg-red-500 animate-pulse shadow-red-300'
              : phase === 'transcribing' || phase === 'sending' || phase === 'speaking'
                ? 'bg-gray-300 cursor-not-allowed'
                : 'bg-white hover:bg-gray-50 shadow-gray-300'
            }
          `}
        >
          {phase === 'recording' ? '⏹️' : current.icon}
        </button>

        {/* 状态文字 */}
        <p className={`text-lg font-semibold ${current.color} text-center`}>
          {current.text}
        </p>

        {/* 识别到的文字 */}
        {transcript && (
          <div className="w-full bg-white/80 backdrop-blur rounded-xl p-4 shadow-lg">
            <p className="text-xs text-gray-400 mb-1">你说的：</p>
            <p className="text-gray-900 font-medium">{transcript}</p>
          </div>
        )}

        {/* AI 回复 */}
        {reply && (
          <div className="w-full bg-white/80 backdrop-blur rounded-xl p-4 shadow-lg">
            <p className="text-xs text-gray-400 mb-1">AI 回复：</p>
            <p className="text-gray-800 text-sm whitespace-pre-wrap">{reply}</p>
          </div>
        )}

        {/* 错误信息 */}
        {error && (
          <div className="w-full bg-red-100 rounded-xl p-4 border border-red-200">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}

        {/* 底部操作 */}
        {(phase === 'done' || phase === 'error') && (
          <button
            onClick={startRecording}
            className="bg-white text-gray-800 px-6 py-3 rounded-full font-semibold shadow-lg hover:bg-gray-50 active:scale-95 transition-all"
          >
            🎤 再说一条
          </button>
        )}
      </div>

      {/* 底部说明 */}
      <p className="fixed bottom-6 text-xs text-gray-400 text-center px-4">
        说出要记录的内容，如「吃了两个鸡蛋」「跑步30分钟」「做了50个俯卧撑」
      </p>
    </div>
  );
}
