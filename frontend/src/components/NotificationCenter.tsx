'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Bell, X, AlertTriangle, Heart, Sparkles, Clock, CheckCircle, Info } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { notificationApi } from '@/services/api';

interface NotificationLog {
  id: number;
  notification_type: string;
  channel: string;
  title: string;
  content: string;
  status: string;
  sent_at: string | null;
  created_at: string | null;
}

const TYPE_CONFIG: Record<string, { icon: React.ReactNode; color: string }> = {
  health_alert: { icon: <AlertTriangle className="w-4 h-4" />, color: 'text-red-400' },
  anomaly_alert: { icon: <AlertTriangle className="w-4 h-4" />, color: 'text-orange-400' },
  morning_briefing: { icon: <Sparkles className="w-4 h-4" />, color: 'text-yellow-400' },
  daily_insight: { icon: <Sparkles className="w-4 h-4" />, color: 'text-blue-400' },
  reminder: { icon: <Clock className="w-4 h-4" />, color: 'text-purple-400' },
  plan_reminder: { icon: <Clock className="w-4 h-4" />, color: 'text-purple-400' },
  achievement: { icon: <CheckCircle className="w-4 h-4" />, color: 'text-green-400' },
  test: { icon: <Info className="w-4 h-4" />, color: 'text-gray-400' },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type] || { icon: <Heart className="w-4 h-4" />, color: 'text-gray-400' };
}

function formatTime(dateStr: string | null) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}天前`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export default function NotificationCenter() {
  const { isAuthenticated } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [logs, setLogs] = useState<NotificationLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasNew, setHasNew] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const lastSeenRef = useRef<number>(0);

  // 从 localStorage 获取上次查看时间
  useEffect(() => {
    const saved = localStorage.getItem('notification_last_seen');
    if (saved) lastSeenRef.current = parseInt(saved, 10);
  }, []);

  const fetchLogs = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try {
      const res = await notificationApi.getLogs(30);
      const items = res.data.logs || [];
      setLogs(items);
      // 检查是否有新通知
      if (items.length > 0) {
        const latestTime = new Date(items[0].created_at || items[0].sent_at || 0).getTime();
        if (latestTime > lastSeenRef.current) {
          setHasNew(true);
        }
      }
    } catch {
      // 静默失败
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  // 打开时加载 + 标记已读
  useEffect(() => {
    if (isOpen) {
      fetchLogs();
      setHasNew(false);
      const now = Date.now();
      lastSeenRef.current = now;
      localStorage.setItem('notification_last_seen', now.toString());
    }
  }, [isOpen, fetchLogs]);

  // 定期检查新通知（每 5 分钟）
  useEffect(() => {
    if (!isAuthenticated) return;
    fetchLogs(); // 初次加载
    const timer = setInterval(fetchLogs, 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, [isAuthenticated, fetchLogs]);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [isOpen]);

  if (!isAuthenticated) return null;

  return (
    <div className="relative" ref={panelRef}>
      {/* 铃铛按钮 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-full text-gray-300 hover:bg-white/5 hover:text-white transition-all"
        title="通知中心"
      >
        <Bell className="w-5 h-5" />
        {hasNew && (
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-[#1a1625] animate-pulse" />
        )}
      </button>

      {/* 通知面板 */}
      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-80 sm:w-96 max-h-[70vh] bg-[#252033] rounded-xl shadow-2xl border border-purple-900/40 z-50 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
          {/* 头部 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-purple-900/30">
            <h3 className="text-sm font-semibold text-white">通知中心</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* 通知列表 */}
          <div className="flex-1 overflow-y-auto">
            {loading && logs.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
                加载中...
              </div>
            ) : logs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                <Bell className="w-8 h-8 mb-2 opacity-50" />
                <p className="text-sm">暂无通知</p>
              </div>
            ) : (
              <div className="divide-y divide-purple-900/20">
                {logs.map((log) => {
                  const cfg = getTypeConfig(log.notification_type);
                  const isNewItem = new Date(log.created_at || log.sent_at || 0).getTime() > lastSeenRef.current;
                  return (
                    <div
                      key={log.id}
                      className={`px-4 py-3 hover:bg-white/5 transition-all ${isNewItem ? 'bg-purple-600/5' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <span className={`mt-0.5 flex-shrink-0 ${cfg.color}`}>
                          {cfg.icon}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-200 leading-tight">
                            {log.title}
                          </p>
                          {log.content && (
                            <p className="text-xs text-gray-400 mt-1 line-clamp-2 leading-relaxed">
                              {log.content}
                            </p>
                          )}
                          <p className="text-xs text-gray-500 mt-1.5">
                            {formatTime(log.sent_at || log.created_at)}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
