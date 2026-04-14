'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';

interface Template {
  id: number;
  name: string;
  icon: string;
  unit: string;
  default_target: number;
  category: string;
}

interface TodayRecord {
  template_id: number;
  value: number;
  target: number;
  completion_rate: number;
}

export default function KidsCheckinPage() {
  const { user } = useAuth();
  const { addPoints } = useKidsTheme();
  const userId = user?.id || 'guest';
  const today = new Date().toISOString().split('T')[0];
  const checkinPtsKey = `kids_checkin_pts_${userId}_${today}`;

  const [templates, setTemplates] = useState<Template[]>([]);
  const [todayRecords, setTodayRecords] = useState<Record<number, TodayRecord>>({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [showInput, setShowInput] = useState<number | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [showSuccess, setShowSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      // 先尝试初始化默认模板（如果没有的话）
      await api.post('/checkin/templates/init-defaults').catch(() => {});

      const [tplRes, todayRes] = await Promise.all([
        api.get('/checkin/templates'),
        api.get('/checkin/records/today'),
      ]);

      setTemplates(tplRes.data?.templates || []);

      // 将今日记录转为 map
      const records: Record<number, TodayRecord> = {};
      (todayRes.data?.records || []).forEach((r: any) => {
        records[r.template_id] = r;
      });
      setTodayRecords(records);
    } catch {
      // 忽略
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCheckin = async (template: Template, value?: number) => {
    setSavingId(template.id);
    try {
      const checkinValue = value ?? template.default_target;
      const today = new Date().toISOString().split('T')[0];
      await api.post('/checkin/records', {
        template_id: template.id,
        checkin_date: today,
        value: checkinValue,
        target: template.default_target,
      });

      // 更新本地记录
      const prevRecord = todayRecords[template.id];
      const newValue = (prevRecord?.value || 0) + checkinValue;
      const newRate = newValue / template.default_target * 100;
      const wasNotDone = !prevRecord || prevRecord.completion_rate < 100;
      const isNowDone = newRate >= 100;

      setTodayRecords(prev => ({
        ...prev,
        [template.id]: {
          template_id: template.id,
          value: newValue,
          target: template.default_target,
          completion_rate: newRate,
        },
      }));

      // 首次完成该模板打卡，奖励1积分
      if (wasNotDone && isNowDone) {
        const awardedIds: number[] = JSON.parse(localStorage.getItem(checkinPtsKey) || '[]');
        if (!awardedIds.includes(template.id)) {
          addPoints(1);
          localStorage.setItem(checkinPtsKey, JSON.stringify([...awardedIds, template.id]));
          setShowSuccess(`${template.icon} ${template.name} 打卡完成！🎉 +1积分`);
          setTimeout(() => setShowSuccess(null), 2500);
          setSavingId(null);
          return;
        }
      }

      setShowSuccess(`${template.icon} ${template.name} 已打卡！`);
      setTimeout(() => setShowSuccess(null), 2000);
      setShowInput(null);
      setInputValue('');
    } catch {
      // 忽略
    } finally {
      setSavingId(null);
    }
  };

  const handleCardClick = (template: Template) => {
    // 如果有单位且不是简单的"次"，显示数值输入
    if (template.unit && template.default_target > 1 && !['次', '个'].includes(template.unit)) {
      setShowInput(template.id);
      setInputValue(String(template.default_target));
    } else {
      handleCheckin(template);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-full">
        <div className="text-center">
          <div className="text-6xl mb-4">✅</div>
          <p className="text-xl text-purple-500 font-bold">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-6 py-8">
      <h1 className="text-3xl font-bold text-purple-600 text-center mb-2">✅ 每日打卡</h1>
      <p className="text-lg text-gray-500 text-center mb-8">点击卡片完成今日打卡吧~</p>

      {/* 成功提示 */}
      {showSuccess && (
        <div className="fixed top-8 left-1/2 -translate-x-1/2 z-50 px-6 py-3 bg-green-100 border-2 border-green-300 rounded-2xl shadow-lg">
          <span className="text-lg font-bold text-green-600">{showSuccess}</span>
        </div>
      )}

      {/* 打卡卡片网格 */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-5 max-w-3xl mx-auto">
        {templates.map(tpl => {
          const record = todayRecords[tpl.id];
          const isDone = record && record.completion_rate >= 100;

          return (
            <button
              key={tpl.id}
              onClick={() => !isDone && handleCardClick(tpl)}
              disabled={savingId === tpl.id}
              className={`relative flex flex-col items-center gap-3 p-6 rounded-3xl border-2 shadow-lg transition-all ${
                isDone
                  ? 'bg-green-50 border-green-300 cursor-default'
                  : 'bg-white border-pink-100 hover:border-pink-300 hover:shadow-xl active:scale-95'
              } ${savingId === tpl.id ? 'opacity-50' : ''}`}
            >
              {/* 完成标记 */}
              {isDone && (
                <div className="absolute top-3 right-3 w-8 h-8 bg-green-400 rounded-full flex items-center justify-center shadow">
                  <span className="text-white text-lg">✓</span>
                </div>
              )}

              <span className="text-5xl">{tpl.icon || '📌'}</span>
              <span className="text-lg font-bold text-gray-700">{tpl.name}</span>

              {record ? (
                <span className="text-base text-green-600 font-medium">
                  {record.value}{tpl.unit} / {tpl.default_target}{tpl.unit}
                </span>
              ) : (
                <span className="text-base text-gray-400">
                  目标: {tpl.default_target}{tpl.unit}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 数值输入弹窗 */}
      {showInput !== null && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-3xl p-8 shadow-2xl w-80">
            <h3 className="text-2xl font-bold text-purple-600 text-center mb-6">
              {templates.find(t => t.id === showInput)?.icon}{' '}
              {templates.find(t => t.id === showInput)?.name}
            </h3>
            <div className="flex items-center gap-3 mb-6">
              <input
                type="number"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="flex-1 text-center text-2xl font-bold px-4 py-3 border-2 border-pink-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-purple-300"
                autoFocus
              />
              <span className="text-xl text-gray-500 font-medium">
                {templates.find(t => t.id === showInput)?.unit}
              </span>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => { setShowInput(null); setInputValue(''); }}
                className="flex-1 py-3 rounded-2xl border-2 border-gray-200 text-lg font-bold text-gray-500 hover:bg-gray-50 active:scale-95"
              >
                取消
              </button>
              <button
                onClick={() => {
                  const tpl = templates.find(t => t.id === showInput);
                  if (tpl && inputValue) {
                    handleCheckin(tpl, Number(inputValue));
                  }
                }}
                className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-pink-400 to-purple-400 text-lg font-bold text-white shadow-md hover:shadow-lg active:scale-95"
              >
                打卡
              </button>
            </div>
          </div>
        </div>
      )}

      {templates.length === 0 && (
        <div className="text-center mt-12">
          <div className="text-6xl mb-4">📋</div>
          <p className="text-xl text-gray-400">还没有打卡模板哦~</p>
          <p className="text-lg text-gray-400">请让爸爸妈妈帮你创建吧</p>
        </div>
      )}
    </div>
  );
}
