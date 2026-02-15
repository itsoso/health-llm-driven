'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api';

const DAILY_TARGET = 1200; // 9岁儿童每日饮水目标(ml)
const MAX_AMOUNT = 2000; // 每日最高上限(ml)

const WATER_AMOUNTS = [
  { amount: 150, label: '小杯水', icon: '🥛' },
  { amount: 250, label: '大杯水', icon: '🥤' },
  { amount: 350, label: '水壶', icon: '🧴' },
];

interface WaterRecord {
  id: number;
  amount: number;
  drink_time: string;
}

export default function KidsWaterPage() {
  const [todayTotal, setTodayTotal] = useState(0);
  const [records, setRecords] = useState<WaterRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [lastAdded, setLastAdded] = useState(0);
  const [showMessage, setShowMessage] = useState('');

  const today = new Date().toISOString().split('T')[0];

  const loadTodayData = useCallback(async () => {
    try {
      const res = await api.get(`/water/records/me/date/${today}`);
      const data = res.data;
      const recs: WaterRecord[] = data?.records || [];
      const total = data?.total_amount ?? recs.reduce((sum: number, r) => sum + (r.amount || 0), 0);
      setRecords(recs);
      setTodayTotal(total);
    } catch {
      // 忽略
    }
  }, [today]);

  useEffect(() => {
    loadTodayData();
  }, [loadTodayData]);

  const handleAddWater = async (amount: number) => {
    if (loading) return;

    // 检查是否超过上限
    if (todayTotal + amount > MAX_AMOUNT) {
      setShowMessage(`已达到每日上限 ${MAX_AMOUNT}ml，不能再加啦~`);
      setTimeout(() => setShowMessage(''), 2500);
      return;
    }

    setLoading(true);
    try {
      await api.post(`/water/records/quick?amount=${amount}`);
      setLastAdded(amount);
      setShowSuccess(true);
      setTimeout(() => setShowSuccess(false), 2000);
      await loadTodayData();
    } catch {
      // 忽略
    } finally {
      setLoading(false);
    }
  };

  const handleUndo = async () => {
    if (loading || records.length === 0) return;
    setLoading(true);
    try {
      const lastRecord = records[records.length - 1];
      await api.delete(`/water/records/${lastRecord.id}`);
      setShowMessage(`已撤回 ${lastRecord.amount}ml`);
      setTimeout(() => setShowMessage(''), 2000);
      await loadTodayData();
    } catch {
      // 忽略
    } finally {
      setLoading(false);
    }
  };

  const fillPercent = Math.min(100, (todayTotal / DAILY_TARGET) * 100);
  const isCompleted = todayTotal >= DAILY_TARGET;
  const isMaxed = todayTotal >= MAX_AMOUNT;

  return (
    <div className="flex flex-col items-center px-6 py-8 min-h-full">
      {/* 标题 */}
      <h1 className="text-3xl font-bold text-purple-600 mb-2">💧 今日喝水</h1>
      <p className="text-lg text-gray-500 mb-8">
        目标：{DAILY_TARGET}ml / 已喝：{todayTotal}ml
      </p>

      {/* 水杯动画 */}
      <div className="relative w-48 h-72 mb-8">
        {/* 杯子外框 */}
        <div className="absolute inset-0 rounded-b-3xl rounded-t-xl border-4 border-blue-200 bg-blue-50/30 overflow-hidden">
          {/* 水位 */}
          <div
            className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-blue-400 to-cyan-300 transition-all duration-1000 ease-out rounded-b-2xl"
            style={{ height: `${fillPercent}%` }}
          >
            {/* 水波纹 */}
            <div className="absolute top-0 left-0 right-0 h-4 overflow-hidden">
              <div className="w-[200%] h-4 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-pulse" />
            </div>
          </div>
        </div>
        {/* 百分比显示 */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`text-4xl font-bold ${fillPercent > 50 ? 'text-white' : 'text-blue-400'}`}>
            {Math.round(fillPercent)}%
          </span>
        </div>
      </div>

      {/* 完成提示 */}
      {isCompleted && (
        <div className="mb-6 px-6 py-3 bg-green-100 border-2 border-green-300 rounded-2xl text-center">
          <span className="text-2xl">🎉</span>
          <p className="text-lg font-bold text-green-600">太棒了！今天的喝水目标完成了！</p>
        </div>
      )}

      {/* 上限提示 / 成功提示 / 消息 */}
      {showMessage && (
        <div className="mb-4 px-6 py-3 bg-yellow-100 border-2 border-yellow-300 rounded-2xl">
          <span className="text-lg font-bold text-yellow-700">{showMessage}</span>
        </div>
      )}
      {showSuccess && !showMessage && (
        <div className="mb-4 px-6 py-3 bg-blue-100 border-2 border-blue-300 rounded-2xl animate-bounce">
          <span className="text-lg font-bold text-blue-600">
            💧 +{lastAdded}ml 已记录！
          </span>
        </div>
      )}

      {/* 快捷按钮 */}
      <div className="flex gap-6">
        {WATER_AMOUNTS.map(item => {
          const wouldExceed = todayTotal + item.amount > MAX_AMOUNT;
          return (
            <button
              key={item.amount}
              onClick={() => handleAddWater(item.amount)}
              disabled={loading || isMaxed}
              className={`flex flex-col items-center gap-3 px-8 py-6 bg-white rounded-3xl shadow-lg border-2 transition-all active:scale-95 ${
                isMaxed || wouldExceed
                  ? 'border-gray-200 opacity-50 cursor-not-allowed'
                  : 'border-blue-100 hover:border-blue-300 hover:shadow-xl'
              } ${loading ? 'opacity-50' : ''}`}
            >
              <span className="text-5xl">{item.icon}</span>
              <span className="text-lg font-bold text-gray-700">{item.label}</span>
              <span className="text-base text-blue-500 font-medium">{item.amount}ml</span>
            </button>
          );
        })}
      </div>

      {/* 撤回按钮 */}
      {records.length > 0 && (
        <button
          onClick={handleUndo}
          disabled={loading}
          className="mt-6 flex items-center gap-2 px-6 py-3 bg-white border-2 border-orange-200 rounded-full text-base font-bold text-orange-500 hover:border-orange-400 active:scale-95 transition-all shadow-sm"
        >
          <span>↩️</span>
          撤回上一杯（{records[records.length - 1]?.amount}ml）
        </button>
      )}

      {/* 上限说明 */}
      {isMaxed && (
        <p className="mt-4 text-base text-gray-400">
          今日已达上限 {MAX_AMOUNT}ml，喝太多也不好哦~
        </p>
      )}
    </div>
  );
}
