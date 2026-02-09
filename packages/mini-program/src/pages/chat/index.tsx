/**
 * 健康问答对话页面 - OpenClaw 集成
 */
import { View, Text, Input, ScrollView } from '@tarojs/components';
import { useState, useEffect, useRef, useCallback } from 'react';
import Taro from '@tarojs/taro';
import { chatSend, getChatConversations, getChatMessages, deleteChatConversation } from '../../services/api';
import './index.scss';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

interface Conversation {
  id: number;
  title: string;
  updated_at: string;
  last_message?: string;
}

const QUICK_QUESTIONS = [
  { label: '分析打卡', text: '请分析一下我今天的打卡完成情况，给出建议' },
  { label: '运动建议', text: '根据我的身体数据，今天适合做什么运动？' },
  { label: '睡眠分析', text: '帮我分析一下最近的睡眠质量，有什么改善建议？' },
  { label: '饮食建议', text: '根据我的健康目标，今天的饮食应该注意什么？' },
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const scrollId = useRef('msg-bottom');

  // 加载对话列表
  const loadConversations = useCallback(async () => {
    try {
      const list = await getChatConversations();
      setConversations(list || []);
    } catch (e) {
      console.error('加载对话列表失败:', e);
    }
  }, []);

  // 加载指定对话的消息
  const loadConversation = useCallback(async (convId: number) => {
    try {
      const detail = await getChatMessages(convId);
      setMessages(detail.messages || []);
      setConversationId(convId);
      setShowHistory(false);
    } catch (e) {
      console.error('加载对话失败:', e);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // 发送消息
  const handleSend = async (text?: string) => {
    const msg = (text || inputText).trim();
    if (!msg || loading) return;

    setInputText('');

    // 乐观更新：先显示用户消息
    const tempUserMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: msg,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const result = await chatSend(msg, conversationId);

      // 更新会话 ID
      if (!conversationId && result.conversation_id) {
        setConversationId(result.conversation_id);
      }

      // 添加 AI 回复
      const aiMsg: Message = {
        id: result.message_id,
        role: 'assistant',
        content: result.reply,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (e: any) {
      const errorMsg: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '抱歉，请求失败了，请稍后再试。',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  // 新建对话
  const handleNewChat = () => {
    setMessages([]);
    setConversationId(undefined);
    setShowHistory(false);
  };

  // 删除对话
  const handleDeleteConversation = async (convId: number) => {
    try {
      await deleteChatConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (conversationId === convId) {
        handleNewChat();
      }
      Taro.showToast({ title: '已删除', icon: 'success' });
    } catch (e) {
      Taro.showToast({ title: '删除失败', icon: 'none' });
    }
  };

  // 历史面板
  const toggleHistory = () => {
    if (!showHistory) {
      loadConversations();
    }
    setShowHistory(!showHistory);
  };

  // 渲染消息内容（简单的 markdown 支持）
  const renderContent = (content: string) => {
    // 按段落分割
    return content.split('\n').map((line, i) => {
      const trimmed = line.trim();
      if (!trimmed) return <View key={i} className="msg-line-empty" />;

      // 加粗 **text**
      const boldRegex = /\*\*(.*?)\*\*/g;
      let parts: (string | { bold: string })[] = [];
      let lastIndex = 0;
      let match;
      while ((match = boldRegex.exec(trimmed)) !== null) {
        if (match.index > lastIndex) {
          parts.push(trimmed.slice(lastIndex, match.index));
        }
        parts.push({ bold: match[1] });
        lastIndex = match.index + match[0].length;
      }
      if (lastIndex < trimmed.length) {
        parts.push(trimmed.slice(lastIndex));
      }

      return (
        <View key={i} className="msg-line">
          {parts.map((p, j) =>
            typeof p === 'string' ? (
              <Text key={j}>{p}</Text>
            ) : (
              <Text key={j} className="msg-bold">{p.bold}</Text>
            )
          )}
        </View>
      );
    });
  };

  return (
    <View className="chat-page">
      {/* 顶部栏 */}
      <View className="chat-header">
        <View className="header-left" onClick={toggleHistory}>
          <Text className="header-icon">{showHistory ? '✕' : '☰'}</Text>
        </View>
        <Text className="header-title">健康顾问</Text>
        <View className="header-right" onClick={handleNewChat}>
          <Text className="header-icon">+</Text>
        </View>
      </View>

      {/* 历史对话侧栏 */}
      {showHistory && (
        <View className="history-panel">
          <View className="history-header">
            <Text className="history-title">对话记录</Text>
          </View>
          <ScrollView scrollY className="history-list">
            {conversations.length === 0 ? (
              <View className="history-empty">
                <Text>暂无对话记录</Text>
              </View>
            ) : (
              conversations.map(conv => (
                <View
                  key={conv.id}
                  className={`history-item ${conv.id === conversationId ? 'active' : ''}`}
                  onClick={() => loadConversation(conv.id)}
                >
                  <View className="history-item-content">
                    <Text className="history-item-title">{conv.title}</Text>
                    {conv.last_message && (
                      <Text className="history-item-preview">{conv.last_message}</Text>
                    )}
                  </View>
                  <View
                    className="history-item-delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteConversation(conv.id);
                    }}
                  >
                    <Text>×</Text>
                  </View>
                </View>
              ))
            )}
          </ScrollView>
        </View>
      )}

      {/* 消息列表 */}
      <ScrollView
        scrollY
        className="chat-messages"
        scrollIntoView={scrollId.current}
        scrollWithAnimation
      >
        {messages.length === 0 && !loading && (
          <View className="welcome-area">
            <View className="welcome-icon-wrap">
              <Text className="welcome-icon">💬</Text>
            </View>
            <Text className="welcome-title">你好，我是你的健康顾问</Text>
            <Text className="welcome-desc">
              我了解你的健康数据，可以为你提供个性化的健康建议
            </Text>
            <View className="quick-questions">
              {QUICK_QUESTIONS.map((q, idx) => (
                <View
                  key={idx}
                  className="quick-btn"
                  onClick={() => handleSend(q.text)}
                >
                  <Text>{q.label}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {messages.map(msg => (
          <View key={msg.id} className={`msg-row ${msg.role}`}>
            {msg.role === 'assistant' && (
              <View className="msg-avatar ai">
                <Text>💬</Text>
              </View>
            )}
            <View className={`msg-bubble ${msg.role}`}>
              {renderContent(msg.content)}
            </View>
          </View>
        ))}

        {loading && (
          <View className="msg-row assistant">
            <View className="msg-avatar ai">
              <Text>💬</Text>
            </View>
            <View className="msg-bubble assistant typing">
              <View className="typing-dots">
                <View className="dot" />
                <View className="dot" />
                <View className="dot" />
              </View>
            </View>
          </View>
        )}

        <View id="msg-bottom" />
      </ScrollView>

      {/* 快捷提问（对话进行中也显示） */}
      {messages.length > 0 && !loading && (
        <View className="quick-bar">
          <ScrollView scrollX className="quick-scroll">
            {QUICK_QUESTIONS.map((q, idx) => (
              <View
                key={idx}
                className="quick-chip"
                onClick={() => handleSend(q.text)}
              >
                <Text>{q.label}</Text>
              </View>
            ))}
          </ScrollView>
        </View>
      )}

      {/* 输入区域 */}
      <View className="chat-input-area">
        <Input
          className="chat-input"
          placeholder="输入健康相关问题..."
          value={inputText}
          onInput={(e) => setInputText(e.detail.value)}
          onConfirm={() => handleSend()}
          confirmType="send"
          adjustPosition
        />
        <View
          className={`send-btn ${inputText.trim() && !loading ? 'active' : ''}`}
          onClick={() => handleSend()}
        >
          <Text className="send-icon">↑</Text>
        </View>
      </View>
    </View>
  );
}
