'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, subDays, startOfMonth, endOfMonth, eachDayOfInterval, getDay } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';
import ProtectedRoute from '@/components/ProtectedRoute';
import { moodApi, MoodRecord, MoodStats } from '@/services/api';

// 情绪 Emoji 映射
const MOOD_EMOJIS: Record<number, { emoji: string; label: string; color: string }> = {
  1: { emoji: '😢', label: '很差', color: '#ef4444' },
  2: { emoji: '😟', label: '较差', color: '#f97316' },
  3: { emoji: '😐', label: '一般', color: '#eab308' },
  4: { emoji: '😊', label: '较好', color: '#22c55e' },
  5: { emoji: '😄', label: '很好', color: '#10b981' },
};

// 预定义标签
const MOOD_TAG_OPTIONS = ['开心', '平静', '感恩', '兴奋', '焦虑', '疲惫', '烦躁', '悲伤', '孤独', '压力大'];
const TRIGGER_OPTIONS = ['工作', '运动', '社交', '天气', '睡眠', '饮食', '家庭', '健康', '财务', '学习'];
const COPING_OPTIONS = ['运动', '冥想', '社交', '音乐', '阅读', '散步', '深呼吸', '写日记', '休息', '倾诉'];

function MoodContent() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingRecord, setEditingRecord] = useState<MoodRecord | null>(null);
  const [statsDays, setStatsDays] = useState(7);
  const [activeTab, setActiveTab] = useState<'record' | 'stats' | 'calendar'>('record');
  const [calendarDate, setCalendarDate] = useState(new Date());
  const [formData, setFormData] = useState({
    mood_score: 3,
    mood_tags: [] as string[],
    energy_level: 3,
    stress_level: 3,
    anxiety_level: undefined as number | undefined,
    sleep_quality: undefined as number | undefined,
    journal: '',
    triggers: [] as string[],
    coping_methods: [] as string[],
  });

  // 查询数据
  const { data: records, isLoading } = useQuery({
    queryKey: ['mood-records'],
    queryFn: async () => {
      const res = await moodApi.getMyRecords(undefined, undefined, 30);
      return res.data;
    },
  });

  const { data: todayRecord } = useQuery({
    queryKey: ['mood-today'],
    queryFn: async () => {
      const res = await moodApi.getTodayRecord();
      return res.data;
    },
  });

  const { data: stats } = useQuery({
    queryKey: ['mood-stats', statsDays],
    queryFn: async () => {
      const res = await moodApi.getStats(statsDays);
      return res.data;
    },
  });

  const { data: calendar } = useQuery({
    queryKey: ['mood-calendar', calendarDate.getFullYear(), calendarDate.getMonth() + 1],
    queryFn: async () => {
      const res = await moodApi.getCalendar(calendarDate.getFullYear(), calendarDate.getMonth() + 1);
      return res.data;
    },
  });

  // 创建/更新
  const saveMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      const payload = {
        record_date: format(new Date(), 'yyyy-MM-dd'),
        mood_score: data.mood_score,
        mood_tags: data.mood_tags,
        energy_level: data.energy_level,
        stress_level: data.stress_level,
        anxiety_level: data.anxiety_level,
        sleep_quality: data.sleep_quality,
        journal: data.journal || undefined,
        triggers: data.triggers,
        coping_methods: data.coping_methods,
      };

      if (editingRecord) {
        return moodApi.updateRecord(editingRecord.id, payload);
      }
      return moodApi.createRecord(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mood-records'] });
      queryClient.invalidateQueries({ queryKey: ['mood-today'] });
      queryClient.invalidateQueries({ queryKey: ['mood-stats'] });
      queryClient.invalidateQueries({ queryKey: ['mood-calendar'] });
      setShowForm(false);
      setEditingRecord(null);
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => moodApi.deleteRecord(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mood-records'] });
      queryClient.invalidateQueries({ queryKey: ['mood-today'] });
      queryClient.invalidateQueries({ queryKey: ['mood-stats'] });
      queryClient.invalidateQueries({ queryKey: ['mood-calendar'] });
    },
  });

  const resetForm = () => {
    setFormData({
      mood_score: 3,
      mood_tags: [],
      energy_level: 3,
      stress_level: 3,
      anxiety_level: undefined,
      sleep_quality: undefined,
      journal: '',
      triggers: [],
      coping_methods: [],
    });
  };

  const openEditForm = (record: MoodRecord) => {
    setEditingRecord(record);
    setFormData({
      mood_score: record.mood_score,
      mood_tags: record.mood_tags || [],
      energy_level: record.energy_level || 3,
      stress_level: record.stress_level || 3,
      anxiety_level: record.anxiety_level || undefined,
      sleep_quality: record.sleep_quality || undefined,
      journal: record.journal || '',
      triggers: record.triggers || [],
      coping_methods: record.coping_methods || [],
    });
    setShowForm(true);
  };

  const toggleTag = (tag: string, field: 'mood_tags' | 'triggers' | 'coping_methods') => {
    setFormData(prev => ({
      ...prev,
      [field]: prev[field].includes(tag)
        ? prev[field].filter((t: string) => t !== tag)
        : [...prev[field], tag],
    }));
  };

  // 趋势图数据
  const trendData = useMemo(() => {
    if (!stats?.daily_trend) return [];
    return stats.daily_trend.map(d => ({
      date: format(new Date(d.date), 'MM/dd'),
      mood: d.mood_score,
      energy: d.energy_level,
      stress: d.stress_level,
    }));
  }, [stats]);

  // 分布图数据
  const distributionData = useMemo(() => {
    if (!stats?.mood_distribution) return [];
    return [1, 2, 3, 4, 5].map(score => ({
      name: MOOD_EMOJIS[score].label,
      emoji: MOOD_EMOJIS[score].emoji,
      count: stats.mood_distribution[score] || 0,
      color: MOOD_EMOJIS[score].color,
    }));
  }, [stats]);

  // 日历数据
  const calendarDays = useMemo(() => {
    const start = startOfMonth(calendarDate);
    const end = endOfMonth(calendarDate);
    const days = eachDayOfInterval({ start, end });
    const startDayOfWeek = getDay(start);
    const padding = Array.from({ length: startDayOfWeek }, (_, i) => null);
    return [...padding, ...days];
  }, [calendarDate]);

  const recordsList = Array.isArray(records) ? records : [];

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-pink-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto mb-4"></div>
          <p className="text-gray-800 text-lg font-medium">加载中...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-pink-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 页面标题 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">情绪追踪</h1>
            <p className="text-gray-500 mt-1">记录你的情绪变化，了解身心状态</p>
          </div>
          <button
            onClick={() => {
              resetForm();
              setEditingRecord(null);
              setShowForm(true);
            }}
            className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 transition-colors"
          >
            + 记录情绪
          </button>
        </div>

        {/* 今日情绪概览 */}
        {todayRecord && (
          <div className="bg-white rounded-2xl shadow-sm border border-purple-100 p-6 mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3">今日情绪</h3>
            <div className="flex items-center gap-6">
              <div className="text-5xl">{MOOD_EMOJIS[todayRecord.mood_score]?.emoji}</div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl font-bold" style={{ color: MOOD_EMOJIS[todayRecord.mood_score]?.color }}>
                    {MOOD_EMOJIS[todayRecord.mood_score]?.label}
                  </span>
                  {todayRecord.mood_tags?.map(tag => (
                    <span key={tag} className="bg-purple-100 text-purple-700 text-xs px-2 py-0.5 rounded-full">{tag}</span>
                  ))}
                </div>
                <div className="flex gap-4 text-sm text-gray-600">
                  {todayRecord.energy_level && <span>精力: {todayRecord.energy_level}/5</span>}
                  {todayRecord.stress_level && <span>压力: {todayRecord.stress_level}/5</span>}
                  {todayRecord.sleep_quality && <span>睡眠: {todayRecord.sleep_quality}/5</span>}
                </div>
                {todayRecord.journal && (
                  <p className="text-gray-600 mt-2 text-sm line-clamp-2">{todayRecord.journal}</p>
                )}
              </div>
              <button
                onClick={() => openEditForm(todayRecord)}
                className="text-purple-600 hover:text-purple-800 text-sm"
              >
                编辑
              </button>
            </div>
          </div>
        )}

        {/* Tab 切换 */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6">
          {[
            { key: 'record' as const, label: '记录列表' },
            { key: 'stats' as const, label: '统计分析' },
            { key: 'calendar' as const, label: '情绪日历' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-white text-purple-700 shadow-sm'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 记录列表 */}
        {activeTab === 'record' && (
          <div className="space-y-3">
            {recordsList.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm border p-12 text-center">
                <p className="text-gray-400 text-lg mb-4">还没有情绪记录</p>
                <button
                  onClick={() => setShowForm(true)}
                  className="text-purple-600 hover:text-purple-800 font-medium"
                >
                  开始记录第一条
                </button>
              </div>
            ) : (
              recordsList.map((record: MoodRecord) => (
                <div key={record.id} className="bg-white rounded-xl shadow-sm border p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    <div className="text-3xl">{MOOD_EMOJIS[record.mood_score]?.emoji}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold" style={{ color: MOOD_EMOJIS[record.mood_score]?.color }}>
                          {MOOD_EMOJIS[record.mood_score]?.label}
                        </span>
                        <span className="text-gray-400 text-sm">{format(new Date(record.record_date), 'MM月dd日')}</span>
                      </div>
                      {record.mood_tags?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-1">
                          {record.mood_tags.map(tag => (
                            <span key={tag} className="bg-purple-50 text-purple-600 text-xs px-2 py-0.5 rounded-full">{tag}</span>
                          ))}
                        </div>
                      )}
                      {record.journal && (
                        <p className="text-gray-600 text-sm line-clamp-2">{record.journal}</p>
                      )}
                      <div className="flex gap-3 mt-2 text-xs text-gray-400">
                        {record.energy_level && <span>精力 {record.energy_level}/5</span>}
                        {record.stress_level && <span>压力 {record.stress_level}/5</span>}
                        {record.triggers?.length > 0 && <span>触发: {record.triggers.join(', ')}</span>}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => openEditForm(record)} className="text-gray-400 hover:text-purple-600 text-sm">编辑</button>
                      <button
                        onClick={() => { if (confirm('确定删除这条记录？')) deleteMutation.mutate(record.id); }}
                        className="text-gray-400 hover:text-red-600 text-sm"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* 统计分析 */}
        {activeTab === 'stats' && stats && (
          <div className="space-y-6">
            {/* 时间范围选择 */}
            <div className="flex gap-2">
              {[7, 14, 30].map(d => (
                <button
                  key={d}
                  onClick={() => setStatsDays(d)}
                  className={`px-3 py-1 rounded-full text-sm ${
                    statsDays === d ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {d}天
                </button>
              ))}
            </div>

            {/* 概览卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[
                { label: '平均情绪', value: stats.avg_mood_score?.toFixed(1), emoji: stats.avg_mood_score ? MOOD_EMOJIS[Math.round(stats.avg_mood_score)]?.emoji : '—' },
                { label: '平均精力', value: stats.avg_energy_level?.toFixed(1) || '—' },
                { label: '平均压力', value: stats.avg_stress_level?.toFixed(1) || '—' },
                { label: '记录天数', value: stats.total_records },
                { label: '情绪-精力相关', value: stats.mood_energy_correlation?.toFixed(2) || '—' },
              ].map((item, i) => (
                <div key={i} className="bg-white rounded-xl shadow-sm border p-4 text-center">
                  {item.emoji && <div className="text-2xl mb-1">{item.emoji}</div>}
                  <div className="text-xl font-bold text-gray-900">{item.value}</div>
                  <div className="text-xs text-gray-500 mt-1">{item.label}</div>
                </div>
              ))}
            </div>

            {/* 趋势图 */}
            {trendData.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm border p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">情绪趋势</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis domain={[1, 5]} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="mood" name="情绪" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="energy" name="精力" stroke="#22c55e" strokeWidth={1.5} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="stress" name="压力" stroke="#ef4444" strokeWidth={1.5} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* 分布图 */}
            {distributionData.some(d => d.count > 0) && (
              <div className="bg-white rounded-2xl shadow-sm border p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">情绪分布</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={distributionData}>
                    <XAxis dataKey="emoji" tick={{ fontSize: 20 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(value: number) => [`${value} 次`, '记录数']} />
                    <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                      {distributionData.map((entry, index) => (
                        <Cell key={index} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* 标签和触发因素排行 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { title: '常见情绪', data: stats.top_mood_tags, color: 'purple' },
                { title: '触发因素', data: stats.top_triggers, color: 'orange' },
                { title: '应对方式', data: stats.top_coping_methods, color: 'green' },
              ].map((section) => (
                <div key={section.title} className="bg-white rounded-2xl shadow-sm border p-4">
                  <h4 className="font-semibold text-gray-900 mb-3">{section.title}</h4>
                  {Object.keys(section.data || {}).length === 0 ? (
                    <p className="text-gray-400 text-sm">暂无数据</p>
                  ) : (
                    <div className="space-y-2">
                      {Object.entries(section.data || {}).slice(0, 5).map(([tag, count]) => (
                        <div key={tag} className="flex justify-between items-center">
                          <span className="text-sm text-gray-700">{tag}</span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full bg-${section.color}-100 text-${section.color}-700`}>
                            {count}次
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 情绪日历 */}
        {activeTab === 'calendar' && (
          <div className="bg-white rounded-2xl shadow-sm border p-6">
            <div className="flex justify-between items-center mb-6">
              <button
                onClick={() => setCalendarDate(new Date(calendarDate.getFullYear(), calendarDate.getMonth() - 1))}
                className="p-2 hover:bg-gray-100 rounded-lg"
              >
                &lt;
              </button>
              <h3 className="text-lg font-semibold text-gray-900">
                {format(calendarDate, 'yyyy年MM月', { locale: zhCN })}
                {calendar && (
                  <span className="text-sm font-normal text-gray-500 ml-2">
                    记录 {calendar.recorded_days}/{calendar.total_days} 天
                    {calendar.avg_mood_score && ` · 平均 ${calendar.avg_mood_score.toFixed(1)}`}
                  </span>
                )}
              </h3>
              <button
                onClick={() => setCalendarDate(new Date(calendarDate.getFullYear(), calendarDate.getMonth() + 1))}
                className="p-2 hover:bg-gray-100 rounded-lg"
              >
                &gt;
              </button>
            </div>

            <div className="grid grid-cols-7 gap-1">
              {['日', '一', '二', '三', '四', '五', '六'].map(d => (
                <div key={d} className="text-center text-sm text-gray-500 py-2">{d}</div>
              ))}
              {calendarDays.map((day, i) => {
                if (!day) return <div key={`empty-${i}`} />;
                const dayNum = day.getDate();
                const dayData = calendar?.days?.[dayNum];
                return (
                  <div
                    key={dayNum}
                    className={`aspect-square flex flex-col items-center justify-center rounded-lg text-sm ${
                      dayData ? 'cursor-pointer hover:bg-purple-50' : ''
                    }`}
                    style={dayData ? { backgroundColor: `${MOOD_EMOJIS[dayData.mood_score]?.color}15` } : {}}
                  >
                    <span className={`${dayData ? 'font-medium' : 'text-gray-400'}`}>{dayNum}</span>
                    {dayData && (
                      <span className="text-base leading-none mt-0.5">
                        {MOOD_EMOJIS[dayData.mood_score]?.emoji}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 新建/编辑表单 Modal */}
        {showForm && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
            <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
              <div className="sticky top-0 bg-white border-b px-6 py-4 rounded-t-2xl flex justify-between items-center">
                <h3 className="text-lg font-semibold">{editingRecord ? '编辑情绪记录' : '记录今日情绪'}</h3>
                <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
              </div>

              <div className="p-6 space-y-6">
                {/* 情绪评分 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">你现在感觉怎么样？</label>
                  <div className="flex justify-between">
                    {[1, 2, 3, 4, 5].map(score => (
                      <button
                        key={score}
                        onClick={() => setFormData(prev => ({ ...prev, mood_score: score }))}
                        className={`flex flex-col items-center gap-1 p-3 rounded-xl transition-all ${
                          formData.mood_score === score
                            ? 'bg-purple-50 ring-2 ring-purple-500 scale-110'
                            : 'hover:bg-gray-50'
                        }`}
                      >
                        <span className="text-3xl">{MOOD_EMOJIS[score].emoji}</span>
                        <span className="text-xs text-gray-600">{MOOD_EMOJIS[score].label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* 情绪标签 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">情绪标签</label>
                  <div className="flex flex-wrap gap-2">
                    {MOOD_TAG_OPTIONS.map(tag => (
                      <button
                        key={tag}
                        onClick={() => toggleTag(tag, 'mood_tags')}
                        className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                          formData.mood_tags.includes(tag)
                            ? 'bg-purple-100 border-purple-300 text-purple-700'
                            : 'bg-white border-gray-200 text-gray-600 hover:border-purple-200'
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 精力和压力 */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">精力等级</label>
                    <div className="flex gap-1">
                      {[1, 2, 3, 4, 5].map(v => (
                        <button
                          key={v}
                          onClick={() => setFormData(prev => ({ ...prev, energy_level: v }))}
                          className={`flex-1 py-2 rounded text-sm ${
                            formData.energy_level === v ? 'bg-green-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-green-50'
                          }`}
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">压力等级</label>
                    <div className="flex gap-1">
                      {[1, 2, 3, 4, 5].map(v => (
                        <button
                          key={v}
                          onClick={() => setFormData(prev => ({ ...prev, stress_level: v }))}
                          className={`flex-1 py-2 rounded text-sm ${
                            formData.stress_level === v ? 'bg-red-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-red-50'
                          }`}
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 触发因素 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">触发因素</label>
                  <div className="flex flex-wrap gap-2">
                    {TRIGGER_OPTIONS.map(tag => (
                      <button
                        key={tag}
                        onClick={() => toggleTag(tag, 'triggers')}
                        className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                          formData.triggers.includes(tag)
                            ? 'bg-orange-100 border-orange-300 text-orange-700'
                            : 'bg-white border-gray-200 text-gray-600 hover:border-orange-200'
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 应对方式 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">应对方式</label>
                  <div className="flex flex-wrap gap-2">
                    {COPING_OPTIONS.map(tag => (
                      <button
                        key={tag}
                        onClick={() => toggleTag(tag, 'coping_methods')}
                        className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                          formData.coping_methods.includes(tag)
                            ? 'bg-green-100 border-green-300 text-green-700'
                            : 'bg-white border-gray-200 text-gray-600 hover:border-green-200'
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 情绪日记 */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">情绪日记（可选）</label>
                  <textarea
                    value={formData.journal}
                    onChange={e => setFormData(prev => ({ ...prev, journal: e.target.value }))}
                    placeholder="记录一下此刻的感受..."
                    rows={3}
                    maxLength={2000}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                  />
                </div>

                {/* 提交 */}
                <button
                  onClick={() => saveMutation.mutate(formData)}
                  disabled={saveMutation.isPending}
                  className="w-full bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors"
                >
                  {saveMutation.isPending ? '保存中...' : (editingRecord ? '更新记录' : '保存记录')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default function MoodPage() {
  return <ProtectedRoute><MoodContent /></ProtectedRoute>;
}
