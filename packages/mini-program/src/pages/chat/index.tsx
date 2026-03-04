/**
 * 健康问答对话页面 - OpenClaw 集成
 */
import { View, Text, Input, ScrollView } from '@tarojs/components';
import { useState, useEffect, useRef, useCallback } from 'react';
import Taro from '@tarojs/taro';
import { chatSend, getChatConversations, getChatMessages, deleteChatConversation, chatTranscribe, recognizeFood } from '../../services/api';
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
  mode?: string;
}

const QUICK_QUESTIONS = [
  { label: '分析打卡', text: '请分析一下我今天的打卡完成情况，给出建议' },
  { label: '运动建议', text: '根据我的身体数据，今天适合做什么运动？' },
  { label: '睡眠分析', text: '帮我分析一下最近的睡眠质量，有什么改善建议？' },
  { label: '饮食建议', text: '根据我的健康目标，今天的饮食应该注意什么？' },
];

const PROXY_QUICK_QUESTIONS = [
  { label: '你好', text: '你好，你能做什么？' },
  { label: '今日健康', text: '查一下我今天的健康数据' },
  { label: '记录饮水', text: '记录喝水250ml' },
  { label: '健康分析', text: '分析我最近的健康趋势' },
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [isRecording, setIsRecording] = useState(false);
  const [imageUploading, setImageUploading] = useState(false);
  const [chatMode, setChatMode] = useState<'health' | 'proxy'>('health');
  const itemsPerPage = 10;
  const [scrollTarget, setScrollTarget] = useState('msg-bottom');
  const scrollFlip = useRef(false);
  const recorderManager = useRef<Taro.RecorderManager | null>(null);

  // 滚动到底部（通过切换scrollIntoView的值触发）
  const scrollToBottom = useCallback(() => {
    scrollFlip.current = !scrollFlip.current;
    setScrollTarget(scrollFlip.current ? 'msg-bottom-alt' : 'msg-bottom');
  }, []);

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
  const loadConversation = useCallback(async (convId: number, convMode?: string) => {
    try {
      const detail = await getChatMessages(convId);
      setMessages(detail.messages || []);
      setConversationId(convId);
      // 恢复对话的模式
      setChatMode(convMode === 'proxy' ? 'proxy' : detail.mode === 'proxy' ? 'proxy' : 'health');
      setShowHistory(false);
      // 延迟滚动到底部，等待消息渲染完成
      setTimeout(() => scrollToBottom(), 100);
    } catch (e) {
      console.error('加载对话失败:', e);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    }
  }, [scrollToBottom]);

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
    setTimeout(() => scrollToBottom(), 50);

    try {
      const result = await chatSend(msg, conversationId, chatMode === 'proxy' ? 'proxy' : undefined);

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
      setTimeout(() => scrollToBottom(), 50);

      // 健康助理模式下显示活动/饮食通知
      if (chatMode === 'health') {
        if (result.activities_saved && result.activities?.length > 0) {
          const msgs = result.activities
            .filter((a: any) => a.status !== 'already_exists')
            .map((a: any) => a.message);
          if (msgs.length > 0) {
            Taro.showToast({ title: msgs.join('、'), icon: 'none', duration: 3000 });
          }
        }
        if (result.diet_saved) {
          Taro.showToast({ title: '饮食已自动记录', icon: 'success', duration: 2000 });
        }
      }
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

  // 切换模式时新建对话
  const handleModeSwitch = (mode: 'health' | 'proxy') => {
    if (mode === chatMode) return;
    setChatMode(mode);
    setMessages([]);
    setConversationId(undefined);
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
      setSearchQuery('');
      setCurrentPage(1);
    }
    setShowHistory(!showHistory);
  };

  // 语音录制
  const handleVoiceToggle = () => {
    if (isRecording) {
      // 停止录音
      recorderManager.current?.stop();
      return;
    }

    if (!recorderManager.current) {
      recorderManager.current = Taro.getRecorderManager();

      recorderManager.current.onStop(async (res) => {
        setIsRecording(false);
        if (!res.tempFilePath) return;

        Taro.showLoading({ title: '识别中...' });
        try {
          const fs = Taro.getFileSystemManager();
          const base64 = fs.readFileSync(res.tempFilePath, 'base64') as string;
          const result = await chatTranscribe(base64, 'mp3');
          const text = result.text?.trim();
          if (text) {
            setInputText(prev => prev + text);
          } else {
            Taro.showToast({ title: '未识别到语音', icon: 'none' });
          }
        } catch (err) {
          console.error('语音转文字失败:', err);
          Taro.showToast({ title: '语音识别失败', icon: 'none' });
        } finally {
          Taro.hideLoading();
        }
      });

      recorderManager.current.onError((err) => {
        console.error('录音错误:', err);
        setIsRecording(false);
        Taro.showToast({ title: '录音失败', icon: 'none' });
      });
    }

    recorderManager.current.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 64000,
      format: 'mp3',
    });
    setIsRecording(true);
  };

  // 图片识别食物
  const handleImageChoose = () => {
    Taro.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: async (res) => {
        const tempFilePath = res.tempFilePaths[0];
        setImageUploading(true);
        Taro.showLoading({ title: '识别中...' });

        try {
          const fs = Taro.getFileSystemManager();
          const base64 = fs.readFileSync(tempFilePath, 'base64') as string;
          const result = await recognizeFood(base64, 'image/jpeg');

          if (result.success && result.meal_description) {
            const foodText = `我刚吃了：${result.meal_description}，请帮我计算热量并记录`;
            handleSend(foodText);
          } else {
            Taro.showToast({ title: '未识别到食物', icon: 'none' });
          }
        } catch (err) {
          console.error('食物识别失败:', err);
          Taro.showToast({ title: '识别失败，请重试', icon: 'none' });
        } finally {
          setImageUploading(false);
          Taro.hideLoading();
        }
      },
    });
  };

  // 过滤和分页对话列表
  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (conv.last_message && conv.last_message.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const totalPages = Math.ceil(filteredConversations.length / itemsPerPage);
  const paginatedConversations = filteredConversations.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // 渲染行内样式（加粗）
  const renderInline = (text: string) => {
    const boldRegex = /\*\*(.*?)\*\*/g;
    const parts: (string | { bold: string })[] = [];
    let lastIndex = 0;
    let match;
    while ((match = boldRegex.exec(text)) !== null) {
      if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
      parts.push({ bold: match[1] });
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < text.length) parts.push(text.slice(lastIndex));
    return parts.map((p, j) =>
      typeof p === 'string' ? <Text key={j} userSelect>{p}</Text> : <Text key={j} className="msg-bold" userSelect>{p.bold}</Text>
    );
  };

  // 渲染消息内容（markdown 支持：标题、列表、表格、加粗）
  const renderContent = (content: string) => {
    const lines = content.split('\n');
    const elements: any[] = [];
    let i = 0;

    while (i < lines.length) {
      const trimmed = lines[i].trim();

      // 空行
      if (!trimmed) { elements.push(<View key={i} className="msg-line-empty" />); i++; continue; }

      // 表格
      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        const tableRows: string[][] = [];
        while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
          const row = lines[i].trim();
          if (/^\|[\s\-:|]+\|$/.test(row)) { i++; continue; }
          const cells = row.split('|').filter((_, idx, arr) => idx > 0 && idx < arr.length - 1).map(c => c.trim());
          tableRows.push(cells);
          i++;
        }
        if (tableRows.length > 0) {
          elements.push(
            <View key={`t${i}`} className="md-table">
              {tableRows.map((row, ri) => (
                <View key={ri} className={`md-table-row ${ri === 0 ? 'header' : ''}`}>
                  {row.map((cell, ci) => (
                    <View key={ci} className="md-table-cell"><Text userSelect>{cell}</Text></View>
                  ))}
                </View>
              ))}
            </View>
          );
        }
        continue;
      }

      // 标题
      const hMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
      if (hMatch) {
        elements.push(<View key={i} className={`md-h${hMatch[1].length}`}>{renderInline(hMatch[2])}</View>);
        i++; continue;
      }

      // 无序列表
      if (/^[-•]\s+/.test(trimmed)) {
        const items: string[] = [];
        while (i < lines.length && /^[-•]\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^[-•]\s+/, ''));
          i++;
        }
        elements.push(
          <View key={`ul${i}`} className="md-list">
            {items.map((item, li) => (
              <View key={li} className="md-list-item">
                <Text className="md-list-dot">·</Text>
                <View className="md-list-text">{renderInline(item)}</View>
              </View>
            ))}
          </View>
        );
        continue;
      }

      // 有序列表
      if (/^\d+[.)]\s+/.test(trimmed)) {
        const items: string[] = [];
        while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^\d+[.)]\s+/, ''));
          i++;
        }
        elements.push(
          <View key={`ol${i}`} className="md-list">
            {items.map((item, li) => (
              <View key={li} className="md-list-item">
                <Text className="md-list-num">{li + 1}.</Text>
                <View className="md-list-text">{renderInline(item)}</View>
              </View>
            ))}
          </View>
        );
        continue;
      }

      // 普通段落
      elements.push(<View key={i} className="msg-line">{renderInline(trimmed)}</View>);
      i++;
    }

    return elements;
  };

  return (
    <View className="chat-page">
      {/* 顶部栏 */}
      <View className="chat-header">
        <View className="header-left" onClick={toggleHistory}>
          <Text className="header-icon">{showHistory ? '✕' : '☰'}</Text>
        </View>
        <View className="header-center">
          <View className="mode-tabs">
            <View
              className={`mode-tab ${chatMode === 'health' ? 'active' : ''}`}
              onClick={() => handleModeSwitch('health')}
            >
              <Text>健康助理</Text>
            </View>
            <View
              className={`mode-tab ${chatMode === 'proxy' ? 'active' : ''}`}
              onClick={() => handleModeSwitch('proxy')}
            >
              <Text>OpenClaw</Text>
            </View>
          </View>
        </View>
        <View className="header-right" onClick={handleNewChat}>
          <Text className="header-icon">+</Text>
        </View>
      </View>

      {/* 历史对话侧栏 */}
      {showHistory && (
        <View className="history-panel">
          <View className="history-header">
            <Text className="history-title">对话记录</Text>
            {/* 搜索框 */}
            <View className="history-search">
              <Input
                className="history-search-input"
                placeholder="搜索对话..."
                value={searchQuery}
                onInput={(e) => {
                  setSearchQuery(e.detail.value);
                  setCurrentPage(1);
                }}
              />
              <Text className="history-search-icon">🔍</Text>
            </View>
          </View>
          <ScrollView scrollY className="history-list">
            {conversations.length === 0 ? (
              <View className="history-empty">
                <Text>暂无对话记录</Text>
              </View>
            ) : paginatedConversations.length === 0 ? (
              <View className="history-empty">
                <Text className="history-empty-icon">🔍</Text>
                <Text>未找到匹配的对话</Text>
              </View>
            ) : (
              paginatedConversations.map(conv => (
                <View
                  key={conv.id}
                  className={`history-item ${conv.id === conversationId ? 'active' : ''}`}
                  onClick={() => loadConversation(conv.id, conv.mode)}
                >
                  <View className="history-item-content">
                    <Text className="history-item-title">
                      {conv.mode === 'proxy' ? '⚡ ' : ''}{conv.title}
                    </Text>
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

          {/* 分页控件 */}
          {filteredConversations.length > itemsPerPage && (
            <View className="history-pagination">
              <View
                className={`pagination-btn ${currentPage === 1 ? 'disabled' : ''}`}
                onClick={() => currentPage > 1 && setCurrentPage(p => p - 1)}
              >
                <Text>← 上一页</Text>
              </View>
              <Text className="pagination-info">
                {currentPage} / {totalPages}
              </Text>
              <View
                className={`pagination-btn ${currentPage === totalPages ? 'disabled' : ''}`}
                onClick={() => currentPage < totalPages && setCurrentPage(p => p + 1)}
              >
                <Text>下一页 →</Text>
              </View>
            </View>
          )}
        </View>
      )}

      {/* 消息列表 */}
      <ScrollView
        scrollY
        className="chat-messages"
        scrollIntoView={scrollTarget}
        scrollWithAnimation
      >
        {messages.length === 0 && !loading && (
          <View className="welcome-area">
            <View className="welcome-icon-wrap">
              <Text className="welcome-icon">{chatMode === 'proxy' ? '⚡' : '💬'}</Text>
            </View>
            <Text className="welcome-title">
              {chatMode === 'proxy' ? 'OpenClaw 对话模式' : '你好，我是你的智能助理'}
            </Text>
            <Text className="welcome-desc">
              {chatMode === 'proxy'
                ? 'OpenClaw 通过 Skills 自主访问健康数据，提供智能服务'
                : '我了解你的健康数据，可以为你提供个性化的健康建议'}
            </Text>
            <View className="quick-questions">
              {(chatMode === 'proxy' ? PROXY_QUICK_QUESTIONS : QUICK_QUESTIONS).map((q, idx) => (
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
            <View
              className={`msg-bubble ${msg.role}`}
              onLongPress={() => {
                Taro.setClipboardData({
                  data: msg.content,
                  success: () => Taro.showToast({ title: '已复制', icon: 'success', duration: 1500 }),
                });
              }}
            >
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
        <View id="msg-bottom-alt" />
      </ScrollView>

      {/* 快捷提问（对话进行中也显示） */}
      {messages.length > 0 && !loading && (
        <View className="quick-bar">
          <ScrollView scrollX className="quick-scroll">
            {(chatMode === 'proxy' ? PROXY_QUICK_QUESTIONS : QUICK_QUESTIONS).map((q, idx) => (
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
        {chatMode === 'health' && (
          <View
            className={`tool-btn ${imageUploading ? 'uploading' : ''}`}
            onClick={handleImageChoose}
          >
            <Text className="tool-icon">📷</Text>
          </View>
        )}
        <View
          className={`tool-btn ${isRecording ? 'recording' : ''}`}
          onClick={handleVoiceToggle}
        >
          <Text className="tool-icon">{isRecording ? '⏹' : '🎤'}</Text>
        </View>
        <Input
          className="chat-input"
          placeholder={isRecording ? '正在录音...' : '有什么可以帮你的...'}
          value={inputText}
          onInput={(e) => setInputText(e.detail.value)}
          onConfirm={() => handleSend()}
          confirmType="send"
          adjustPosition
          disabled={isRecording}
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
