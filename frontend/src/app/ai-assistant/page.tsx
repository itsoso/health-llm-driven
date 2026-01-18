'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api';

interface BriefingSection {
  title: string;
  status: string;
  items: string[];
}

interface Briefing {
  date: string;
  greeting: string;
  sections: BriefingSection[];
}

interface Recommendation {
  timestamp: string;
  primary: {
    icon: string;
    title: string;
    message: string;
  } | null;
  secondary: string[];
  status: Record<string, any>;
}

interface Reminder {
  type: string;
  title: string;
  message: string;
  scheduled_time: string;
  priority: number;
}

interface ScheduleItem {
  time: string;
  activity: string;
  category: string;
  duration_minutes: number;
  tasks: string[];
}

export default function AIAssistantPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [testResult, setTestResult] = useState<{
    name: string;
    path: string;
    data: any;
    error: string | null;
    loading: boolean;
    duration: number;
  } | null>(null);

  // 更新当前时间
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // 获取数据
  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      router.push('/login');
      return;
    }

    fetchAllData();
  }, []);

  const testApi = async (path: string, name: string) => {
    setTestResult({ name, path, data: null, error: null, loading: true, duration: 0 });
    const startTime = Date.now();
    
    try {
      const response = await api.get(path);
      const duration = Date.now() - startTime;
      setTestResult({ name, path, data: response.data, error: null, loading: false, duration });
    } catch (err: any) {
      const duration = Date.now() - startTime;
      setTestResult({ 
        name, 
        path, 
        data: null, 
        error: err.response?.data?.detail || err.message || '请求失败', 
        loading: false, 
        duration 
      });
    }
  };

  const fetchAllData = async () => {
    setLoading(true);
    setError(null);

    try {
      // 添加时间戳参数防止缓存
      const timestamp = Date.now();
      const [briefingRes, recommendationRes, remindersRes, scheduleRes] = await Promise.allSettled([
        api.get(`/ai-scheduler/morning-briefing?_t=${timestamp}`),
        api.get(`/ai-scheduler/recommendation?_t=${timestamp}`),
        api.get(`/ai-scheduler/reminders?_t=${timestamp}`),
        api.get(`/ai-scheduler/daily-schedule?_t=${timestamp}`),
      ]);

      if (briefingRes.status === 'fulfilled') {
        setBriefing(briefingRes.value.data);
      }
      if (recommendationRes.status === 'fulfilled') {
        setRecommendation(recommendationRes.value.data);
      }
      if (remindersRes.status === 'fulfilled') {
        setReminders(remindersRes.value.data.reminders || []);
      }
      if (scheduleRes.status === 'fulfilled') {
        setSchedule(scheduleRes.value.data.schedule || []);
      }
    } catch (err: any) {
      console.error('获取数据失败:', err);
      setError(err.message || '获取数据失败');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'good': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'warning': return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'poor': return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      default: return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    }
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      routine: 'bg-slate-600',
      meal: 'bg-orange-600',
      work: 'bg-blue-600',
      exercise: 'bg-green-600',
      rest: 'bg-purple-600',
      leisure: 'bg-pink-600',
      sleep: 'bg-indigo-600',
    };
    return colors[category] || 'bg-gray-600';
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('zh-CN', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit',
      hour12: false 
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-purple-500 mx-auto mb-4"></div>
          <p className="text-purple-300 text-lg">加载 AI 助手...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white pt-4">
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* 页面标题 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-3xl">🤖</span>
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
                AI 健康助手
              </h1>
              <p className="text-sm text-slate-400">executor.life · 智能健康分析</p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xl font-mono text-purple-300">{formatTime(currentTime)}</div>
            <div className="text-xs text-slate-500">北京时间</div>
          </div>
        </div>

        {error && (
          <div className="bg-rose-500/20 border border-rose-500/30 rounded-xl p-4 text-rose-300">
            ⚠️ {error}
          </div>
        )}

        {/* 实时建议 - 最重要，放最上面 */}
        {recommendation && (
          <section className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 rounded-2xl p-6 border border-purple-500/20 shadow-xl">
            <div className="flex items-start gap-4">
              <span className="text-5xl">{recommendation.primary?.icon || '💡'}</span>
              <div className="flex-1">
                <h2 className="text-2xl font-bold mb-2">{recommendation.primary?.title || '健康建议'}</h2>
                <p className="text-lg text-purple-200 mb-4">{recommendation.primary?.message}</p>
                
                {recommendation.secondary.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {recommendation.secondary.map((item, idx) => (
                      <span key={idx} className="px-3 py-1 bg-white/10 rounded-full text-sm">
                        {item}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        {/* 当前提醒 - 只在有提醒时显示 */}
        {reminders.length > 0 && (
          <section className="bg-slate-800/50 rounded-2xl p-6 border border-amber-500/20">
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
              <span>🔔</span> 当前提醒
              <span className="text-sm font-normal text-slate-400">
                (±15分钟内)
              </span>
            </h2>
            <div className="grid gap-3">
              {reminders.map((reminder, idx) => (
                <div key={idx} className="flex items-center gap-4 p-4 bg-amber-500/10 rounded-xl border border-amber-500/20">
                  <div className="text-3xl">{reminder.title.split(' ')[0]}</div>
                  <div className="flex-1">
                    <div className="font-semibold">{reminder.title.replace(/^[^\s]+\s/, '')}</div>
                    <div className="text-sm text-slate-400">{reminder.message}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-mono text-amber-400">{reminder.scheduled_time}</div>
                    <div className="text-xs text-slate-500">优先级 {reminder.priority}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          {/* 早间简报 */}
          {briefing && (
            <section className="bg-slate-800/50 rounded-2xl p-6 border border-white/10">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <span>📋</span> 健康简报
                </h2>
                <span className="text-sm text-slate-400">{briefing.date}</span>
              </div>
              
              <p className="text-lg text-purple-300 mb-4">{briefing.greeting}</p>
              
              <div className="space-y-4">
                {briefing.sections.map((section, idx) => (
                  <div key={idx} className={`p-4 rounded-xl border ${getStatusColor(section.status)}`}>
                    <h3 className="font-semibold mb-2">{section.title}</h3>
                    <ul className="space-y-1">
                      {section.items.map((item, itemIdx) => (
                        <li key={itemIdx} className="text-sm opacity-90">• {item}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 今日日程 */}
          <section className="bg-slate-800/50 rounded-2xl p-6 border border-white/10">
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
              <span>📅</span> 今日日程
            </h2>
            
            <div className="space-y-2 max-h-[calc(100vh-320px)] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-800">
              {schedule.map((item, idx) => {
                const isCurrentTime = (() => {
                  const [h, m] = item.time.split(':').map(Number);
                  const itemMinutes = h * 60 + m;
                  const currentMinutes = currentTime.getHours() * 60 + currentTime.getMinutes();
                  return Math.abs(itemMinutes - currentMinutes) < item.duration_minutes;
                })();

                return (
                  <div 
                    key={idx} 
                    className={`flex items-start gap-3 p-3 rounded-xl transition-all ${
                      isCurrentTime 
                        ? 'bg-purple-500/20 border border-purple-500/40 scale-[1.02]' 
                        : 'bg-slate-700/30 hover:bg-slate-700/50'
                    }`}
                  >
                    <div className="text-center min-w-[50px]">
                      <div className={`font-mono text-sm ${isCurrentTime ? 'text-purple-300' : 'text-slate-400'}`}>
                        {item.time}
                      </div>
                      <div className={`text-xs px-2 py-0.5 rounded mt-1 ${getCategoryColor(item.category)}`}>
                        {item.duration_minutes}分钟
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className={`font-medium ${isCurrentTime ? 'text-purple-200' : ''}`}>
                        {item.activity}
                        {isCurrentTime && <span className="ml-2 text-xs text-purple-400">← 当前</span>}
                      </div>
                      <div className="text-xs text-slate-500 mt-1">
                        {item.tasks.join(' · ')}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </div>

        {/* 刷新按钮 */}
        <div className="text-center pt-4">
          <button
            onClick={fetchAllData}
            className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl font-semibold hover:from-purple-500 hover:to-pink-500 transition-all shadow-lg hover:shadow-purple-500/25"
          >
            🔄 刷新数据
          </button>
        </div>

        {/* API 测试区域 */}
        <section className="bg-slate-800/30 rounded-2xl p-6 border border-slate-700/50">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <span>🧪</span> API 测试端点
            <span className="text-sm font-normal text-slate-400">（点击卡片测试）</span>
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {[
              { name: '早间简报', path: '/ai-scheduler/morning-briefing', icon: '📋' },
              { name: '实时建议', path: '/ai-scheduler/recommendation', icon: '💡' },
              { name: '当前提醒', path: '/ai-scheduler/reminders', icon: '🔔' },
              { name: '今日日程', path: '/ai-scheduler/daily-schedule', icon: '📅' },
              { name: '综合摘要', path: '/ai-scheduler/summary', icon: '📊' },
            ].map((apiItem) => (
              <button
                key={apiItem.path}
                onClick={() => testApi(apiItem.path, apiItem.name)}
                className="p-3 bg-slate-700/30 rounded-lg hover:bg-slate-600/50 transition-all text-left group"
              >
                <div className="font-medium text-sm flex items-center gap-2">
                  <span>{apiItem.icon}</span>
                  {apiItem.name}
                  <span className="text-xs text-slate-500 group-hover:text-purple-400">→ 点击测试</span>
                </div>
                <code className="text-xs text-purple-400 break-all">/api/v1{apiItem.path}</code>
              </button>
            ))}
          </div>
          
          {/* API 测试结果弹窗 */}
          {testResult && (
            <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setTestResult(null)}>
              <div className="bg-slate-800 rounded-2xl max-w-3xl w-full max-h-[80vh] overflow-hidden" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between p-4 border-b border-slate-700">
                  <h3 className="text-lg font-bold">{testResult.name} - API 响应</h3>
                  <button onClick={() => setTestResult(null)} className="text-slate-400 hover:text-white text-2xl">×</button>
                </div>
                <div className="p-4 overflow-auto max-h-[60vh]">
                  {testResult.loading ? (
                    <div className="text-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-purple-500 mx-auto"></div>
                      <p className="text-slate-400 mt-2">加载中...</p>
                    </div>
                  ) : testResult.error ? (
                    <div className="bg-rose-500/20 border border-rose-500/30 rounded-lg p-4 text-rose-300">
                      <p className="font-bold">❌ 请求失败</p>
                      <p className="text-sm mt-1">{testResult.error}</p>
                    </div>
                  ) : (
                    <div>
                      <div className="flex items-center gap-2 mb-3">
                        <span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded text-xs">200 OK</span>
                        <span className="text-xs text-slate-500">{testResult.duration}ms</span>
                      </div>
                      <pre className="bg-slate-900 rounded-lg p-4 overflow-auto text-sm text-slate-300 font-mono">
                        {JSON.stringify(testResult.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
                <div className="p-4 border-t border-slate-700 flex justify-end gap-2">
                  <button 
                    onClick={() => testResult.path && testApi(testResult.path, testResult.name)}
                    className="px-4 py-2 bg-purple-600 rounded-lg hover:bg-purple-500 text-sm"
                  >
                    🔄 重新请求
                  </button>
                  <button 
                    onClick={() => {
                      navigator.clipboard.writeText(JSON.stringify(testResult.data, null, 2));
                      alert('已复制到剪贴板');
                    }}
                    className="px-4 py-2 bg-slate-600 rounded-lg hover:bg-slate-500 text-sm"
                  >
                    📋 复制 JSON
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="text-center py-6 text-slate-500 text-sm">
        executor.life · AI 健康助手 · Phase 2 测试页面
      </footer>
    </div>
  );
}
