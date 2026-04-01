'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';

interface CheckinTemplate {
  id: number;
  name: string;
  icon: string;
  default_target: number;
  unit: string;
}

export default function QuickActionButton() {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [showCheckinModal, setShowCheckinModal] = useState(false);
  const [templates, setTemplates] = useState<CheckinTemplate[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // 在登录、注册、引导页不显示
  const hiddenPaths = ['/login', '/register', '/onboarding', '/overview'];
  const shouldHide = !isAuthenticated || hiddenPaths.some(p => pathname?.startsWith(p));

  // 点击外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  if (shouldHide) return null;

  const showFeedback = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 2000);
  };

  const quickWater = async () => {
    try {
      await api.post('/water/records/me/quick?amount=250');
      showFeedback('已记录 250ml 饮水');
      setIsOpen(false);
    } catch {
      showFeedback('记录失败，请重试');
    }
  };

  const openCheckinModal = async () => {
    try {
      const res = await api.get('/checkin/templates');
      const data = res.data;
      setTemplates(Array.isArray(data) ? data : data.templates || []);
      setShowCheckinModal(true);
      setIsOpen(false);
    } catch {
      showFeedback('加载打卡模板失败');
    }
  };

  const quickCheckin = async (templateId: number, templateName: string) => {
    try {
      await api.post('/checkin/records/quick', { template_id: templateId });
      showFeedback(`${templateName} 已打卡`);
      setShowCheckinModal(false);
    } catch {
      showFeedback('打卡失败，请重试');
    }
  };

  const actions = [
    { icon: '💧', label: '喝水 +250ml', onClick: quickWater },
    { icon: '✅', label: '打卡', onClick: openCheckinModal },
    { icon: '🍽️', label: '记饮食', onClick: () => { setIsOpen(false); router.push('/diet'); } },
    { icon: '🤖', label: 'AI助手', onClick: () => { setIsOpen(false); router.push('/ai-assistant'); } },
  ];

  return (
    <>
      {/* 反馈 toast */}
      {feedback && (
        <div className="fixed bottom-24 right-6 z-[60] bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg animate-bounce text-sm">
          {feedback}
        </div>
      )}

      {/* 打卡模板选择 modal */}
      {showCheckinModal && (
        <div className="fixed inset-0 z-[55] bg-black/50 flex items-end justify-center"
          onClick={() => setShowCheckinModal(false)}>
          <div className="bg-white rounded-t-2xl w-full max-w-md p-6 max-h-[60vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold mb-4">选择打卡项目</h3>
            {templates.length === 0 ? (
              <p className="text-gray-500 text-center py-4">暂无打卡模板，请先创建</p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {templates.map(t => (
                  <button
                    key={t.id}
                    onClick={() => quickCheckin(t.id, t.name)}
                    className="flex items-center gap-2 p-3 rounded-xl border border-gray-200 hover:bg-indigo-50 hover:border-indigo-300 transition"
                  >
                    <span className="text-2xl">{t.icon}</span>
                    <span className="text-sm font-medium">{t.name}</span>
                  </button>
                ))}
              </div>
            )}
            <button
              onClick={() => setShowCheckinModal(false)}
              className="mt-4 w-full py-2 text-gray-500 text-sm"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* FAB 悬浮按钮 */}
      <div ref={menuRef} className="fixed bottom-20 right-4 z-50">
        {/* 展开的操作列表 */}
        {isOpen && (
          <div className="mb-3 flex flex-col gap-2">
            {actions.map((action, i) => (
              <button
                key={i}
                onClick={action.onClick}
                className="flex items-center gap-2 bg-white shadow-lg rounded-full px-4 py-2.5 text-sm font-medium hover:bg-gray-50 transition whitespace-nowrap"
                style={{
                  animation: `slideIn 0.2s ease-out ${i * 0.05}s both`,
                }}
              >
                <span className="text-xl">{action.icon}</span>
                {action.label}
              </button>
            ))}
          </div>
        )}

        {/* 主按钮 */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`w-14 h-14 rounded-full shadow-lg flex items-center justify-center text-white text-2xl transition-all duration-300 ${
            isOpen ? 'bg-red-500 rotate-45' : 'bg-indigo-600 hover:bg-indigo-700'
          }`}
        >
          +
        </button>
      </div>

      <style jsx>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </>
  );
}
