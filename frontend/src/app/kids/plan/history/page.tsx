'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import { kidsPlanApi, KidsPlanHistoryResponse, KidsPlanDaySummary } from '@/services/api';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, parseISO, subMonths, addMonths } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type RangeType = 'week' | 'month' | 'year';

const RANGE_OPTIONS: { key: RangeType; label: string }[] = [
  { key: 'week', label: '最近一周' },
  { key: 'month', label: '最近一月' },
  { key: 'year', label: '最近一年' },
];

const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六'];

function getRateColor(rate: number, totalItems: number): string {
  if (totalItems === 0) return 'bg-gray-100';
  if (rate >= 0.8) return 'bg-green-300';
  if (rate >= 0.5) return 'bg-yellow-300';
  return 'bg-red-300';
}

function getRateColorText(rate: number, totalItems: number): string {
  if (totalItems === 0) return 'text-gray-300';
  if (rate >= 0.8) return 'text-green-600';
  if (rate >= 0.5) return 'text-yellow-600';
  return 'text-red-500';
}

export default function KidsPlanHistoryPage() {
  const router = useRouter();
  const { theme, points } = useKidsTheme();

  const [range, setRange] = useState<RangeType>('week');
  const [history, setHistory] = useState<KidsPlanHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState<KidsPlanDaySummary | null>(null);
  const [selectedDayItems, setSelectedDayItems] = useState<any[]>([]);
  const [loadingDayDetail, setLoadingDayDetail] = useState(false);
  const [reviewText, setReviewText] = useState('');
  const [reviewLoading, setReviewLoading] = useState(false);

  // 年视图月份导航
  const [yearViewMonth, setYearViewMonth] = useState(new Date());

  const loadHistory = useCallback(async (r: RangeType) => {
    setLoading(true);
    setReviewText('');
    try {
      const res = await kidsPlanApi.getHistory(r);
      setHistory(res.data);
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory(range);
  }, [range, loadHistory]);

  // 日历数据（月视图 / 周视图）
  const dayMap = useMemo(() => {
    if (!history) return new Map<string, KidsPlanDaySummary>();
    const m = new Map<string, KidsPlanDaySummary>();
    for (const day of history.days) {
      m.set(day.plan_date, day);
    }
    return m;
  }, [history]);

  // 月历网格
  const calendarGrid = useMemo(() => {
    if (range === 'year') {
      // 年视图：显示当前选中月的日历
      const start = startOfMonth(yearViewMonth);
      const end = endOfMonth(yearViewMonth);
      const days = eachDayOfInterval({ start, end });
      const startDow = getDay(start);
      const padding: null[] = Array.from({ length: startDow }, () => null);
      return [...padding, ...days];
    }
    if (range === 'month' && history) {
      const startDate = parseISO(history.start_date);
      const start = startOfMonth(startDate);
      const endDate = parseISO(history.end_date);
      const end = endOfMonth(endDate);
      const days = eachDayOfInterval({ start, end });
      const startDow = getDay(start);
      const padding: null[] = Array.from({ length: startDow }, () => null);
      return [...padding, ...days];
    }
    // 周视图：直接用 7 天
    if (history) {
      return history.days.map(d => parseISO(d.plan_date));
    }
    return [];
  }, [history, range, yearViewMonth]);

  const handleDayClick = async (day: KidsPlanDaySummary) => {
    if (day.total_items === 0) return;
    setSelectedDay(day);
    setLoadingDayDetail(true);
    try {
      const res = await kidsPlanApi.getPlan(day.plan_date);
      setSelectedDayItems(res.data.items || []);
    } catch {
      setSelectedDayItems([]);
    } finally {
      setLoadingDayDetail(false);
    }
  };

  const handleGenerateReview = async () => {
    setReviewLoading(true);
    try {
      const res = await kidsPlanApi.getReview(range);
      setReviewText(res.data.review_text);
    } catch (err) {
      console.error('Failed to generate review:', err);
      setReviewText('生成失败，请稍后再试～');
    } finally {
      setReviewLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-5xl mb-3 animate-bounce">📊</div>
          <p className="text-gray-400 text-lg">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 顶栏 */}
      <div className={`px-6 py-4 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="flex items-center justify-between max-w-2xl mx-auto">
          <button onClick={() => router.push('/kids/plan')} className="text-2xl">
            ←
          </button>
          <h1 className={`text-xl font-bold ${theme.accent} flex items-center gap-2`}>
            <span>📊</span> 计划回顾
          </h1>
          <span className="text-amber-400 text-sm font-bold">⭐{points}</span>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-2xl mx-auto space-y-5">

          {/* 范围切换 */}
          <div className="flex gap-2 justify-center">
            {RANGE_OPTIONS.map(opt => (
              <button
                key={opt.key}
                onClick={() => setRange(opt.key)}
                className={`px-4 py-2 rounded-full text-sm font-bold transition-all active:scale-95 ${
                  range === opt.key
                    ? `bg-gradient-to-r ${theme.btnGrad} text-white shadow-md`
                    : `border-2 ${theme.cardBorder} text-gray-500`
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* 统计卡片 */}
          {history && (
            <div className="grid grid-cols-3 gap-3">
              <div className={`bg-white rounded-2xl p-4 border-2 ${theme.cardBorder} text-center`}>
                <div className={`text-2xl font-bold ${theme.accent}`}>
                  {history.total_plan_days}
                </div>
                <div className="text-xs text-gray-400 mt-1">有计划天数</div>
              </div>
              <div className={`bg-white rounded-2xl p-4 border-2 ${theme.cardBorder} text-center`}>
                <div className={`text-2xl font-bold ${theme.accent}`}>
                  {(history.avg_completion_rate * 100).toFixed(0)}%
                </div>
                <div className="text-xs text-gray-400 mt-1">平均完成率</div>
              </div>
              <div className={`bg-white rounded-2xl p-4 border-2 ${theme.cardBorder} text-center`}>
                <div className={`text-2xl font-bold ${theme.accent}`}>
                  {history.current_streak}天
                </div>
                <div className="text-xs text-gray-400 mt-1">连续完成</div>
              </div>
            </div>
          )}

          {/* 日历网格 */}
          {history && (
            <div className={`bg-white rounded-2xl p-4 border-2 ${theme.cardBorder}`}>
              <div className="flex items-center justify-between mb-3">
                <h3 className={`font-bold ${theme.accent}`}>完成日历</h3>
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <span className="w-3 h-3 rounded-sm bg-green-300 inline-block" /> ≥80%
                  <span className="w-3 h-3 rounded-sm bg-yellow-300 inline-block" /> 50-79%
                  <span className="w-3 h-3 rounded-sm bg-red-300 inline-block" /> &lt;50%
                </div>
              </div>

              {/* 年视图月份导航 */}
              {range === 'year' && (
                <div className="flex items-center justify-center gap-4 mb-3">
                  <button
                    onClick={() => setYearViewMonth(subMonths(yearViewMonth, 1))}
                    className="text-gray-400 hover:text-gray-600 text-lg"
                  >
                    ‹
                  </button>
                  <span className="text-sm font-medium text-gray-600">
                    {format(yearViewMonth, 'yyyy年M月')}
                  </span>
                  <button
                    onClick={() => setYearViewMonth(addMonths(yearViewMonth, 1))}
                    className="text-gray-400 hover:text-gray-600 text-lg"
                  >
                    ›
                  </button>
                </div>
              )}

              {/* 星期头 */}
              {(range === 'month' || range === 'year') && (
                <div className="grid grid-cols-7 gap-1 mb-1">
                  {WEEKDAY_LABELS.map(w => (
                    <div key={w} className="text-center text-xs text-gray-400 font-medium py-1">
                      {w}
                    </div>
                  ))}
                </div>
              )}

              {/* 周视图 */}
              {range === 'week' && history && (
                <div>
                  <div className="grid grid-cols-7 gap-1 mb-1">
                    {history.days.map(day => {
                      const d = parseISO(day.plan_date);
                      return (
                        <div key={day.plan_date} className="text-center text-xs text-gray-400 font-medium py-1">
                          {WEEKDAY_LABELS[getDay(d)]}
                        </div>
                      );
                    })}
                  </div>
                  <div className="grid grid-cols-7 gap-1">
                    {history.days.map(day => {
                      const d = parseISO(day.plan_date);
                      const bg = getRateColor(day.completion_rate, day.total_items);
                      const isToday = day.plan_date === format(new Date(), 'yyyy-MM-dd');
                      return (
                        <button
                          key={day.plan_date}
                          onClick={() => handleDayClick(day)}
                          disabled={day.total_items === 0}
                          className={`aspect-square rounded-xl flex flex-col items-center justify-center ${bg} transition-all ${
                            day.total_items > 0 ? 'active:scale-90 cursor-pointer' : 'cursor-default'
                          } ${isToday ? 'ring-2 ring-offset-1 ring-purple-400' : ''}`}
                        >
                          <span className="text-sm font-bold">{format(d, 'd')}</span>
                          {day.total_items > 0 && (
                            <span className={`text-[10px] font-medium ${getRateColorText(day.completion_rate, day.total_items)}`}>
                              {day.done_count}/{day.total_items}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 月/年 日历网格 */}
              {(range === 'month' || range === 'year') && (
                <div className="grid grid-cols-7 gap-1">
                  {calendarGrid.map((cell, idx) => {
                    if (!cell) {
                      return <div key={`pad-${idx}`} className="aspect-square" />;
                    }
                    const dateStr = format(cell, 'yyyy-MM-dd');
                    const day = dayMap.get(dateStr);
                    const totalItems = day?.total_items || 0;
                    const rate = day?.completion_rate || 0;
                    const bg = getRateColor(rate, totalItems);
                    const isToday = dateStr === format(new Date(), 'yyyy-MM-dd');
                    const inRange = history && dateStr >= history.start_date && dateStr <= history.end_date;

                    return (
                      <button
                        key={dateStr}
                        onClick={() => day && day.total_items > 0 && handleDayClick(day)}
                        disabled={!day || day.total_items === 0}
                        className={`aspect-square rounded-lg flex flex-col items-center justify-center text-xs transition-all ${
                          inRange ? bg : 'bg-gray-50 opacity-40'
                        } ${
                          day && day.total_items > 0 ? 'active:scale-90 cursor-pointer' : 'cursor-default'
                        } ${isToday ? 'ring-2 ring-offset-1 ring-purple-400' : ''}`}
                      >
                        <span className="font-medium">{format(cell, 'd')}</span>
                        {day && day.total_items > 0 && (
                          <span className={`text-[9px] ${getRateColorText(rate, totalItems)}`}>
                            {day.done_count}/{day.total_items}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 常做的事情 Top 5 */}
          {history && history.top_activities.length > 0 && (
            <div className={`bg-white rounded-2xl p-4 border-2 ${theme.cardBorder}`}>
              <h3 className={`font-bold ${theme.accent} mb-3`}>常做的事情</h3>
              <div className="space-y-2">
                {history.top_activities.map((act, i) => {
                  const maxCount = history.top_activities[0].count;
                  const pct = maxCount > 0 ? (act.count / maxCount) * 100 : 0;
                  return (
                    <div key={i} className="flex items-center gap-3">
                      <span className="text-xl flex-shrink-0">{act.emoji}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-gray-700 truncate">{act.text}</span>
                          <span className="text-xs text-gray-400 flex-shrink-0 ml-2">{act.count}次</span>
                        </div>
                        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full bg-gradient-to-r ${theme.btnGrad} transition-all duration-500`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI 复盘 */}
          <div className={`bg-white rounded-2xl p-4 border-2 ${theme.cardBorder}`}>
            <h3 className={`font-bold ${theme.accent} mb-3`}>🤖 AI 复盘</h3>
            {reviewText ? (
              <div className="text-sm text-gray-700 leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {reviewText}
                </ReactMarkdown>
              </div>
            ) : (
              <button
                onClick={handleGenerateReview}
                disabled={reviewLoading || !history || history.total_plan_days === 0}
                className={`w-full py-3 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white font-bold shadow-md active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2`}
              >
                {reviewLoading ? (
                  <>
                    <span className="animate-spin">⏳</span>
                    生成中...
                  </>
                ) : (
                  <>
                    <span>✨</span>
                    生成复盘报告
                  </>
                )}
              </button>
            )}
            {reviewText && (
              <button
                onClick={() => { setReviewText(''); handleGenerateReview(); }}
                disabled={reviewLoading}
                className="mt-3 w-full py-2 rounded-xl border-2 border-gray-200 text-sm font-medium text-gray-400 active:scale-95 transition-all"
              >
                🔄 重新生成
              </button>
            )}
          </div>

          {/* 无数据提示 */}
          {history && history.total_plan_days === 0 && (
            <div className="text-center py-8">
              <div className="text-5xl mb-3">📋</div>
              <p className="text-gray-400 text-lg">这段时间还没有计划记录哦～</p>
              <p className="text-gray-400 text-sm mt-1">快去添加今天的计划吧！</p>
            </div>
          )}
        </div>
      </div>

      {/* 某天详情弹窗 */}
      {selectedDay && (
        <div
          className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center bg-black/30 px-0 sm:px-4"
          onClick={() => setSelectedDay(null)}
        >
          <div
            className="bg-white rounded-t-3xl sm:rounded-3xl p-6 shadow-2xl w-full sm:max-w-sm max-h-[70vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className={`text-lg font-bold ${theme.accent}`}>
                📅 {selectedDay.plan_date}
              </h3>
              <div className={`text-lg font-bold ${
                selectedDay.completion_rate >= 0.8 ? 'text-green-500' :
                selectedDay.completion_rate >= 0.5 ? 'text-yellow-500' : 'text-red-400'
              }`}>
                {selectedDay.done_count}/{selectedDay.total_items}
              </div>
            </div>

            {loadingDayDetail ? (
              <div className="text-center py-8">
                <div className="text-3xl animate-bounce">📋</div>
                <p className="text-gray-400 text-sm mt-2">加载中...</p>
              </div>
            ) : (
              <div className="space-y-2">
                {selectedDayItems.map((item: any) => (
                  <div
                    key={item.id}
                    className={`flex items-center gap-3 p-3 rounded-xl border-2 ${
                      item.done ? 'border-green-200 bg-green-50' : 'border-gray-200'
                    }`}
                  >
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
                      item.done ? 'bg-green-400 text-white' : 'border-2 border-gray-300'
                    }`}>
                      {item.done && <span className="text-xs font-bold">✓</span>}
                    </span>
                    <span className="text-lg flex-shrink-0">{item.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <span className={`text-sm font-medium ${item.done ? 'line-through text-gray-400' : 'text-gray-700'}`}>
                        {item.text}
                      </span>
                      {(item.startTime || item.endTime) && (
                        <div className="text-[10px] text-gray-400">
                          ⏰ {item.startTime}{item.endTime ? ` → ${item.endTime}` : ''}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => setSelectedDay(null)}
              className="mt-4 w-full py-3 rounded-2xl border-2 border-gray-200 text-lg font-bold text-gray-400 active:scale-95 transition-all"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
