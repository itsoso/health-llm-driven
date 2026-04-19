'use client';

import { useCallback, useRef } from 'react';
import { api } from '@/services/api/client';
import { openclawApi, agentApi, ChatMessage, DietSavedData, ActivitySavedData } from '@/services/api/ai';
import { dispatchCard, renderServerCards } from '@/components/assistant/inlineCards';

// ── Types ──

export interface UseChatDeps {
  conversationId: number | undefined;
  setConversationId: (id: number | undefined) => void;
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  setLoading: (v: boolean) => void;
  setDoneMessageIds: React.Dispatch<React.SetStateAction<Set<number>>>;
  setInputText: (v: string) => void;
  setInlineResponse: React.Dispatch<React.SetStateAction<{question: string; answer: string; loading: boolean} | null>>;
  inlineResponseRef: React.RefObject<HTMLDivElement | null>;
  inlineMode: boolean;
  inputText: string;
  pendingImage: {base64: string; type: string} | null;
  pendingFile: {base64: string; name: string} | null;
  clearPendingAttachment: () => void;
  setDietNotification: (v: DietSavedData | null) => void;
  setActivityNotifications: (v: ActivitySavedData[]) => void;
  setPlanCreatedNotification: (v: {message: string; planId?: number} | null) => void;
  dashboardRefreshAfterAction: () => void;
  loadConversations: () => Promise<void>;
  /** 拉取当前对话上下文快照给动态卡片系统用 */
  getCardContextSnapshot?: () => { garmin?: any; score?: any; weather?: any; aqi?: any; profile?: any };
}

// ── Helpers ──

const isPostWorkoutMessage = (msg: string) => {
  const kw = ['跑完了','运动结束','锻炼完了','训练结束','跑步结束','运动完成','刚跑完','刚运动完','刚锻炼完','刚练完','骑完车','游完泳','运动完了','同步Garmin','同步garmin','分析本次训练','分析刚才的运动'];
  return kw.some(k => msg.includes(k));
};

function handleDoneEvent(
  result: any,
  deps: Pick<UseChatDeps, 'setMessages' | 'setDietNotification' | 'setActivityNotifications' | 'setPlanCreatedNotification'>,
) {
  const { setMessages, setDietNotification, setActivityNotifications, setPlanCreatedNotification } = deps;

  if (result.workout_analysis?.content) {
    setMessages(prev => [...prev, { id: result.workout_analysis.message_id, role: 'assistant', content: result.workout_analysis.content, created_at: new Date().toISOString() }]);
  }
  if (result.diet_saved && result.diet_data) {
    setDietNotification(result.diet_data);
    setTimeout(() => setDietNotification(null), 5000);
  }
  if (result.activities_saved && result.activities) {
    const saved = result.activities.filter((a: ActivitySavedData) => a.status !== 'already_exists');
    const planResult = saved.find((a: any) => a.type === 'create_plan') as any;
    if (planResult) {
      setPlanCreatedNotification({ message: planResult.message, planId: planResult.plan_id });
      setTimeout(() => setPlanCreatedNotification(null), 8000);
    }
    const nonPlan = saved.filter((a: any) => a.type !== 'create_plan');
    if (nonPlan.length > 0) {
      setActivityNotifications(nonPlan);
      setTimeout(() => setActivityNotifications([]), 5000);
    }
  }
  if (result.reminder?.reminder_minutes > 0) {
    const { reminder_minutes, reminder_message, activity_name } = result.reminder;
    if ('Notification' in window && Notification.permission === 'granted') {
      setTimeout(() => new Notification(`${activity_name} - 休息提醒`, { body: reminder_message, icon: '/icon-192x192.png' }), reminder_minutes * 60 * 1000);
    }
  }
}

// ── Hook ──

export function useChat(deps: UseChatDeps) {
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const handleInlineSend = useCallback(async (text?: string) => {
    const d = depsRef.current;
    const msg = (text || d.inputText).trim();
    if (!msg) return;
    d.setInputText('');
    d.setInlineResponse({ question: msg, answer: '', loading: true });
    setTimeout(() => d.inlineResponseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    try {
      let fullText = '';
      for await (const event of agentApi.streamMessage(msg, d.conversationId)) {
        if (event.event === 'agent_start') {
          // Agent started, silent
        } else if (event.event === 'tool_call') {
          const toolName = event.data?.tool || '';
          const round = event.data?.round || '';
          fullText += `🔧 调用工具: \`${toolName}\` (第${round}轮)\n`;
          d.setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        } else if (event.event === 'tool_result') {
          const toolName = event.data?.tool || '';
          const success = event.data?.success;
          fullText += `${success ? '✅' : '❌'} ${toolName} ${success ? '完成' : '失败'}\n\n`;
          d.setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        } else if (event.event === 'token') {
          fullText += event.data?.content || '';
          d.setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        } else if (event.event === 'error') {
          const errMsg = event.data?.message || '请求失败';
          fullText += `\n❌ ${errMsg}`;
          d.setInlineResponse(prev => prev ? { ...prev, answer: fullText, loading: false } : null);
          return;
        } else if (event.event === 'done') {
          if (event.data?.conversation_id && !d.conversationId) d.setConversationId(event.data.conversation_id);
          d.dashboardRefreshAfterAction();
        }
      }
      d.setInlineResponse(prev => prev ? { ...prev, loading: false } : null);
    } catch {
      d.setInlineResponse(prev => prev ? { ...prev, answer: prev?.answer || '请求失败，请重试', loading: false } : null);
    }
  }, []);

  const handleSend = useCallback(async (text?: string, imageBase64?: string, imageType?: string) => {
    const d = depsRef.current;
    const msg = (text || d.inputText).trim();
    const hasAttachment = d.pendingImage || d.pendingFile;
    if (!msg && !hasAttachment) return;
    if (d.inlineMode && !hasAttachment) { handleInlineSend(text); return; }

    const finalImageBase64 = imageBase64 || d.pendingImage?.base64;
    const finalImageType = imageType || d.pendingImage?.type;
    const finalFileBase64 = d.pendingFile?.base64;
    const finalFileName = d.pendingFile?.name;
    const finalMsg = msg || (finalImageBase64 ? '请看这张图片，帮我分析一下' : (finalFileBase64 ? `请分析这个文件：${finalFileName}` : ''));
    if (!finalMsg) return;

    d.setInputText('');
    d.clearPendingAttachment();

    const tempUserMsg: ChatMessage = { id: Date.now(), role: 'user', content: finalMsg, created_at: new Date().toISOString(), image_preview: finalImageBase64 ? `data:image/${finalImageType || 'jpeg'};base64,${finalImageBase64}` : undefined, file_name: finalFileName };
    d.setMessages(prev => [...prev, tempUserMsg]);
    d.setLoading(true);

    const isWorkoutDone = isPostWorkoutMessage(finalMsg);
    let workoutAnalysisPromise: Promise<any> | null = isWorkoutDone ? api.post('/workout/post-run-analyze?format=full').catch(() => null) : null;

    const aiMsgId = Date.now() + 1;
    let waitTimer: NodeJS.Timeout | undefined;
    let waitTimer2: NodeJS.Timeout | undefined;
    const buf = { content: '', timer: null as NodeJS.Timeout | null };
    const toolsUsed = new Set<string>();
    try {
      d.setMessages(prev => [...prev, { id: aiMsgId, role: 'assistant', content: '', created_at: new Date().toISOString() }]);
      let gotDone = false, firstToken = true;
      waitTimer = setTimeout(() => { if (firstToken) d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '⏳ AI 正在思考中，复杂分析可能需要 1-2 分钟...' } : m)); }, 8000);
      waitTimer2 = setTimeout(() => { if (firstToken) d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '⏳ 正在调用多个 AI 模型进行深度分析，请耐心等待...' } : m)); }, 30000);

      const hasMedia = !!(finalImageBase64 || finalFileBase64);
      // 统一走 Agent — 消除双脑架构
      // 保留环境变量 fallback: NEXT_PUBLIC_USE_LEGACY_ROUTING=true 时恢复旧路由
      const useLegacy = process.env.NEXT_PUBLIC_USE_LEGACY_ROUTING === 'true';
      const needsSkillLegacy = useLegacy && /记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|早餐|午餐|晚餐|加餐|固化到|钉到首页|保存到首页|加到计划/.test(finalMsg);
      const streamSource = (useLegacy && (hasMedia || needsSkillLegacy))
        ? openclawApi.streamMessage(finalMsg, d.conversationId, finalImageBase64, finalImageType, finalFileBase64, finalFileName)
        : agentApi.streamMessage(finalMsg, d.conversationId, finalImageBase64, finalImageType, finalFileBase64, finalFileName);

      for await (const event of streamSource) {
        if (event.event === 'agent_start') {
          clearTimeout(waitTimer); clearTimeout(waitTimer2);
        } else if (event.event === 'tool_call') {
          if (firstToken) { firstToken = false; d.setLoading(false); }
          const toolName = event.data?.tool || '';
          const round = event.data?.round || '';
          if (toolName) toolsUsed.add(toolName);
          buf.content += `🔧 调用工具: \`${toolName}\` (第${round}轮)\n`;
          if (!buf.timer) {
            buf.timer = setTimeout(() => { const b = buf.content; buf.content = ''; buf.timer = null; d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }, 50);
          }
        } else if (event.event === 'tool_result') {
          const toolName = event.data?.tool || '';
          const success = event.data?.success;
          buf.content += `${success ? '✅' : '❌'} ${toolName} ${success ? '完成' : '失败'}\n\n`;
          if (!buf.timer) {
            buf.timer = setTimeout(() => { const b = buf.content; buf.content = ''; buf.timer = null; d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }, 50);
          }
        } else if (event.event === 'token') {
          if (firstToken) { firstToken = false; clearTimeout(waitTimer); clearTimeout(waitTimer2); d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '' } : m)); d.setLoading(false); }
          buf.content += event.data.content;
          if (!buf.timer) {
            buf.timer = setTimeout(() => { const b = buf.content; buf.content = ''; buf.timer = null; d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }, 50);
          }
        } else if (event.event === 'done') {
          gotDone = true;
          if (buf.content) { if (buf.timer) { clearTimeout(buf.timer); buf.timer = null; } const b = buf.content; buf.content = ''; d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }
          if (!d.conversationId && event.data.conversation_id) d.setConversationId(event.data.conversation_id);
          if (event.data.message_id) { d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, id: event.data.message_id } : m)); d.setDoneMessageIds(prev => new Set(prev).add(event.data.message_id)); }
          handleDoneEvent(event.data, d);
          d.dashboardRefreshAfterAction();

          // ── 动态卡片: 后端 cards 字段优先, 本地 registry 兜底 ──
          try {
            const serverCards = renderServerCards((event.data as any)?.cards);
            if (serverCards.length > 0) {
              const now = new Date().toISOString();
              // ≥2 张卡合并为 cards_group 消息, iPad 上自动双列
              const msg = serverCards.length >= 2
                ? { id: Date.now() + 100, role: 'assistant' as const, content: '', created_at: now,
                    card_type: 'cards_group', card_data: { cards: serverCards } }
                : { id: Date.now() + 100, role: 'assistant' as const, content: '', created_at: now,
                    card_type: serverCards[0].type, card_data: serverCards[0].data };
              d.setMessages(prev => [...prev, msg]);
            } else {
              const snap = d.getCardContextSnapshot?.() || {};
              const card = await dispatchCard({
                query: finalMsg,
                query_lower: finalMsg.toLowerCase(),
                toolsUsed,
                data: snap,
                api,
              });
              if (card) {
                d.setMessages(prev => [...prev, {
                  id: Date.now() + 100,
                  role: 'assistant',
                  content: '',
                  created_at: new Date().toISOString(),
                  card_type: card.type,
                  card_data: card.data,
                }]);
              }
            }
          } catch (e) {
            if (process.env.NODE_ENV !== 'production') console.warn('[cards] dispatch failed', e);
          }
        } else if (event.event === 'error') {
          clearTimeout(waitTimer); clearTimeout(waitTimer2);
          const errText = event.data.message || '';
          const friendlyMsg = errText.includes('timeout') || errText.includes('Timeout') ? '⏱ 分析超时了，可能是数据量较大。请稍后重试，或换一个更具体的问题。'
            : errText.includes('Gateway') || errText.includes('502') || errText.includes('503') ? '🔧 AI 服务暂时繁忙，请稍后再试。'
            : errText || '抱歉，出了点问题，请重试。';
          d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: friendlyMsg } : m));
        }
      }
      clearTimeout(waitTimer); clearTimeout(waitTimer2);
      if (!gotDone) d.setMessages(prev => { const ai = prev.find(m => m.id === aiMsgId); if (ai && (!ai.content || ai.content.startsWith('⏳'))) return prev.map(m => m.id === aiMsgId ? { ...m, content: '抱歉，OpenClaw 暂时无法响应，请稍后再试。' } : m); return prev; });
      if (buf.content) { if (buf.timer) { clearTimeout(buf.timer); buf.timer = null; } const remaining = buf.content; buf.content = ''; d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + remaining } : m)); }

      // Post-workout analysis fallback
      if (workoutAnalysisPromise && gotDone) {
        d.setLoading(false);
        const loadingMsgId = Date.now() + 2;
        d.setMessages(prev => [...prev, { id: loadingMsgId, role: 'assistant', content: '正在同步 Garmin 数据并进行多模型分析，请稍等约 30-60 秒...', created_at: new Date().toISOString() }]);
        const analysisResp = await workoutAnalysisPromise;
        if (analysisResp?.data?.success) {
          const { workout = {}, multi_model_analysis: analysis = {} } = analysisResp.data;
          const parts = [workout.name, workout.distance_km && `${workout.distance_km}km`, workout.duration_min && `${workout.duration_min}分钟`, workout.pace && `配速${workout.pace}`].filter(Boolean);
          let content = `**运动分析完成：${parts.join(' | ')}**\n\n`;
          if (analysis.aggregation) content += `**综合分析：**\n${analysis.aggregation}\n\n`;
          if (analysis.model_results?.length > 0) { content += '**各模型视角：**\n\n'; for (const mr of analysis.model_results) { const name = (mr.site || '').replace('lb-', '').replace(/-/g, ' '); if (mr.content) content += `**${name}**:\n${mr.content.slice(0, 400)}${mr.content.length > 400 ? '...' : ''}\n\n---\n\n`; } }
          d.setMessages(prev => prev.map(m => m.id === loadingMsgId ? { ...m, content } : m));
        } else {
          d.setMessages(prev => prev.map(m => m.id === loadingMsgId ? { ...m, content: analysisResp?.data?.message || '运动分析未完成，请稍后再试。' } : m));
        }
      }
      d.loadConversations();
    } catch {
      d.setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '抱歉，请求失败了，请稍后再试。' } : m));
    } finally {
      d.setLoading(false);
      clearTimeout(waitTimer); clearTimeout(waitTimer2);
      if (buf.timer) { clearTimeout(buf.timer); buf.timer = null; }
    }
  }, [handleInlineSend]);

  return { handleSend, handleInlineSend };
}
