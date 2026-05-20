'use client';

import { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api/family';

interface Message {
  id: number;
  role: 'user' | 'bot';
  type: 'text' | 'image' | 'parsed';
  content: string;
  parsed?: any;
  timestamp: string;
}

export default function BotTestPage() {
  return <ProtectedRoute><BotTestContent /></ProtectedRoute>;
}

function BotTestContent() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  let msgId = useRef(0);

  const addMessage = (role: 'user' | 'bot', content: string, type: 'text' | 'image' | 'parsed' = 'text', parsed?: any) => {
    const msg: Message = {
      id: ++msgId.current,
      role, type, content, parsed,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages(prev => [...prev, msg]);
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }), 100);
    return msg;
  };

  // 发送文字
  const sendText = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput('');
    addMessage('user', text);
    setSending(true);

    try {
      // 先测试解析
      const parseRes = await familyApi.parseMedicalText(text);
      if (parseRes.data && parseRes.data.type !== 'unknown') {
        addMessage('bot', `🔍 解析结果`, 'parsed', parseRes.data);
      }

      // 发送到 bot 处理
      const botRes = await familyApi.sendBotMessage('text', text);
      if (botRes.data.reply) {
        addMessage('bot', botRes.data.reply);
      } else if (botRes.data.action?.type === 'forward_to_openclaw') {
        addMessage('bot', '💬 这条消息会转发给 AI 助手处理（实际微信场景下由 OpenClaw 回复）');
      }
    } catch (e: any) {
      addMessage('bot', `❌ 错误: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSending(false);
    }
  };

  // 发送图片
  const sendImage = async (file: File) => {
    setSending(true);
    addMessage('user', `📷 [图片] ${file.name}`, 'image');

    try {
      const base64 = await fileToBase64(file);
      const botRes = await familyApi.sendBotMessage('image', base64);
      addMessage('bot', botRes.data.reply || '处理完成');
      if (botRes.data.action) {
        addMessage('bot', `📋 动作: ${JSON.stringify(botRes.data.action)}`, 'parsed', botRes.data.action);
      }
    } catch (e: any) {
      addMessage('bot', `❌ 图片处理失败: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSending(false);
    }
  };

  // 快捷按钮
  const quickSend = (text: string) => {
    setInput(text);
    setTimeout(() => {
      const fakeEvent = { preventDefault: () => {} } as any;
      sendText();
    }, 100);
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* 头部 */}
      <div className="bg-white border-b px-4 py-3 flex items-center gap-3 flex-shrink-0">
        <button onClick={() => router.push('/family')} className="text-gray-500">←</button>
        <div>
          <h1 className="font-bold text-lg">🤖 微信 Bot 模拟测试</h1>
          <p className="text-xs text-gray-400">模拟父母通过微信发消息的场景</p>
        </div>
      </div>

      {/* 快捷操作 */}
      <div className="bg-white border-b px-4 py-2 flex gap-2 overflow-x-auto flex-shrink-0">
        {[
          { label: '血压', text: '血压135/85' },
          { label: '体重', text: '体重68.5公斤' },
          { label: '喝水', text: '喝了一杯水' },
          { label: '吃药', text: '今天吃药了' },
          { label: '血糖', text: '血糖6.1' },
          { label: '体温', text: '发烧38.2度' },
          { label: '心率', text: '心率78' },
          { label: '症状', text: '今天头有点晕' },
        ].map(q => (
          <button
            key={q.label}
            onClick={() => { setInput(q.text); }}
            className="text-xs bg-blue-50 text-blue-600 px-3 py-1.5 rounded-full whitespace-nowrap flex-shrink-0 hover:bg-blue-100"
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* 消息区 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 py-12">
            <div className="text-4xl mb-3">👨‍👩‍👧‍👦</div>
            <p className="text-sm">模拟微信 Bot 交互</p>
            <p className="text-xs mt-1">试试发送"血压135/85"或上传体检报告图片</p>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 ${
              msg.role === 'user'
                ? 'bg-green-500 text-white rounded-br-sm'
                : 'bg-white border shadow-sm rounded-bl-sm'
            }`}>
              {msg.type === 'parsed' && msg.parsed ? (
                <div className="text-sm">
                  <div className="font-medium mb-1">{msg.content}</div>
                  <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto text-gray-600 whitespace-pre-wrap">
                    {JSON.stringify(msg.parsed, null, 2)}
                  </pre>
                </div>
              ) : (
                <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
              )}
              <div className={`text-[10px] mt-1 ${msg.role === 'user' ? 'text-green-200' : 'text-gray-300'}`}>
                {msg.timestamp}
              </div>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-white border shadow-sm rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="bg-white border-t px-4 py-3 flex gap-2 flex-shrink-0">
        <button
          onClick={() => fileRef.current?.click()}
          className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center text-gray-500 hover:bg-gray-200 flex-shrink-0"
        >
          📷
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={e => { if (e.target.files?.[0]) sendImage(e.target.files[0]); e.target.value = ''; }}
        />
        <input
          className="flex-1 border rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          placeholder="输入消息（如：血压150/95）"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.nativeEvent.isComposing || e.keyCode === 229) return;
            if (e.key === 'Enter') sendText();
          }}
          disabled={sending}
        />
        <button
          onClick={sendText}
          disabled={!input.trim() || sending}
          className="w-10 h-10 bg-green-500 text-white rounded-full flex items-center justify-center disabled:opacity-50 flex-shrink-0"
        >
          ➤
        </button>
      </div>
    </div>
  );
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
