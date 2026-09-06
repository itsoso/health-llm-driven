'use client';
import { requireAiConsent } from '@/services/aiConsent';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { WEB_SESSION_TOKEN } from '@/services/api/client';

// 使用相对路径，依赖 Nginx 反向代理
const API_BASE = '/api';

type ViewMode = 'daily' | 'weekly' | 'monthly';

interface DailyReviewData {
  id: number;
  review_date: string;
  sleep_score: number | null;
  sleep_duration_hours: number | null;
  workout_count: number;
  workout_duration_minutes: number;
  workout_calories: number;
  steps: number;
  active_calories: number;
  meals_count: number;
  total_calories_in: number;
  total_protein: number;
  total_carbs: number;
  total_fat: number;
  water_intake_ml: number;
  water_goal_met: boolean;
  nasal_wash_done: boolean;
  nasal_wash_count: number;
  checkin_completed: number;
  checkin_total: number;
  supplements_taken: number;
  body_battery_high: number | null;
  body_battery_low: number | null;
  stress_avg: number | null;
  resting_hr: number | null;
  mood_score: number | null;
  energy_score: number | null;
  productivity_score: number | null;
  highlights: string | null;
  challenges: string | null;
  learnings: string | null;
  gratitude: string | null;
  tomorrow_plan: string | null;
  summary: string | null;
  ai_summary: string | null;
  is_completed: boolean;
}

interface PeriodReviewData {
  id: number;
  period_type: string;
  period_label: string;
  start_date: string;
  end_date: string;
  avg_sleep_score: number | null;
  avg_sleep_duration: number | null;
  total_workouts: number;
  total_workout_minutes: number;
  total_workout_calories: number;
  workout_days: number;
  total_steps: number;
  avg_steps: number;
  avg_calories_in: number;
  avg_protein: number;
  avg_water_intake: number;
  water_goal_days: number;
  avg_checkin_rate: number | null;
  perfect_days: number;
  review_days: number;
  total_days: number;
  achievements: string | null;
  challenges: string | null;
  learnings: string | null;
  goals_review: string | null;
  next_period_goals: string | null;
  summary: string | null;
  ai_summary: string | null;
  is_completed: boolean;
}

export default function ReviewPage() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<ViewMode>('daily');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generatingAI, setGeneratingAI] = useState(false);

  const [dailyData, setDailyData] = useState<DailyReviewData | null>(null);
  const [periodData, setPeriodData] = useState<PeriodReviewData | null>(null);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [streak, setStreak] = useState({ current_streak: 0, total_reviews: 0 });

  // 用户输入
  const [moodScore, setMoodScore] = useState(3);
  const [energyScore, setEnergyScore] = useState(3);
  const [productivityScore, setProductivityScore] = useState(3);
  const [highlights, setHighlights] = useState('');
  const [challenges, setChallenges] = useState('');
  const [learnings, setLearnings] = useState('');
  const [gratitude, setGratitude] = useState('');
  const [tomorrowPlan, setTomorrowPlan] = useState('');
  const [summary, setSummary] = useState('');

  useEffect(() => {
    loadData();
  }, [viewMode, selectedDate]);

  const getToken = () => WEB_SESSION_TOKEN;

  const loadData = async () => {
    setLoading(true);
    const token = getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    try {
      // 获取连续天数
      const streakRes = await fetch(`${API_BASE}/review/stats/streak`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (streakRes.ok) {
        setStreak(await streakRes.json());
      } else if (streakRes.status === 401) {
        router.push('/login');
        return;
      }

      if (viewMode === 'daily') {
        const res = await fetch(`${API_BASE}/review/daily/${selectedDate}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setDailyData(data);
          fillDailyInputs(data);
        } else if (res.status === 401) {
          router.push('/login');
          return;
        } else {
          // 即使API返回错误，也设置默认数据
          setDailyData({
            id: 0,
            review_date: selectedDate,
            sleep_score: null,
            sleep_duration_hours: null,
            workout_count: 0,
            workout_duration_minutes: 0,
            workout_calories: 0,
            steps: 0,
            active_calories: 0,
            meals_count: 0,
            total_calories_in: 0,
            total_protein: 0,
            total_carbs: 0,
            total_fat: 0,
            water_intake_ml: 0,
            water_goal_met: false,
            nasal_wash_done: false,
            nasal_wash_count: 0,
            checkin_completed: 0,
            checkin_total: 0,
            supplements_taken: 0,
            body_battery_high: null,
            body_battery_low: null,
            stress_avg: null,
            resting_hr: null,
            mood_score: null,
            energy_score: null,
            productivity_score: null,
            highlights: null,
            challenges: null,
            learnings: null,
            gratitude: null,
            tomorrow_plan: null,
            summary: null,
            ai_summary: null,
            is_completed: false,
          });
        }
      } else if (viewMode === 'weekly') {
        const res = await fetch(`${API_BASE}/review/period/week/current`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          setPeriodData(await res.json());
        } else if (res.status === 401) {
          router.push('/login');
          return;
        }
      } else if (viewMode === 'monthly') {
        const res = await fetch(`${API_BASE}/review/period/month/current`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          setPeriodData(await res.json());
        } else if (res.status === 401) {
          router.push('/login');
          return;
        }
      }
    } catch (e) {
      console.error('加载失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const fillDailyInputs = (data: DailyReviewData) => {
    setMoodScore(data.mood_score || 3);
    setEnergyScore(data.energy_score || 3);
    setProductivityScore(data.productivity_score || 3);
    setHighlights(data.highlights || '');
    setChallenges(data.challenges || '');
    setLearnings(data.learnings || '');
    setGratitude(data.gratitude || '');
    setTomorrowPlan(data.tomorrow_plan || '');
    setSummary(data.summary || '');
  };

  const handleSave = async (markComplete = false) => {
    setSaving(true);
    const token = getToken();

    try {
      const res = await fetch(`${API_BASE}/review/daily/${selectedDate}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          mood_score: moodScore,
          energy_score: energyScore,
          productivity_score: productivityScore,
          highlights: highlights || null,
          challenges: challenges || null,
          learnings: learnings || null,
          gratitude: gratitude || null,
          tomorrow_plan: tomorrowPlan || null,
          summary: summary || null,
          is_completed: markComplete || dailyData?.is_completed
        })
      });

      if (res.ok) {
        alert(markComplete ? '复盘已完成！' : '保存成功！');
        loadData();
      }
    } catch (e) {
      console.error('保存失败:', e);
      alert('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateAI = async () => {
    setGeneratingAI(true);
    const token = getToken();

    try {
      await requireAiConsent();
      const res = await fetch(`${API_BASE}/review/ai-summary`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          date: selectedDate,
          period: viewMode
        })
      });

      if (res.ok) {
        const data = await res.json();
        setSummary(data.ai_summary);
        alert('AI 总结已生成！');
      }
    } catch (e) {
      console.error('AI生成失败:', e);
      alert(e instanceof Error ? e.message : 'AI 总结未生成，请稍后重试。');
    } finally {
      setGeneratingAI(false);
    }
  };

  const ScoreSelector = ({
    label,
    value,
    onChange,
    emojis
  }: {
    label: string;
    value: number;
    onChange: (v: number) => void;
    emojis: string[]
  }) => (
    <div className="mb-4">
      <label className="block text-sm text-gray-400 mb-2">{label}</label>
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map(score => (
          <button
            key={score}
            onClick={() => onChange(score)}
            className={`flex-1 py-3 rounded-lg flex flex-col items-center transition-all ${
              value === score
                ? 'bg-purple-600 text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            <span className="text-xl mb-1">{emojis[score - 1]}</span>
            <span className="text-xs">{score}</span>
          </button>
        ))}
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-background-dark">
        <div className="flex items-center justify-center h-[60vh]">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background-dark text-gray-100">

      <main className="max-w-4xl mx-auto px-4 py-6">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold">📝 复盘</h1>
            <p className="text-gray-400 text-sm mt-1">记录每一天，成就更好的自己</p>
          </div>
          <div className="flex items-center gap-2 bg-orange-500/20 px-4 py-2 rounded-full">
            <span className="text-xl">🔥</span>
            <span className="text-orange-400 font-bold">{streak.current_streak}</span>
            <span className="text-orange-400 text-sm">天</span>
          </div>
        </div>

        {/* 视图切换 */}
        <div className="flex bg-white/5 rounded-full p-1 mb-6">
          {(['daily', 'weekly', 'monthly'] as ViewMode[]).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`flex-1 py-2 rounded-full text-sm font-medium transition-all ${
                viewMode === mode
                  ? 'bg-purple-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {mode === 'daily' ? '每日' : mode === 'weekly' ? '本周' : '本月'}
            </button>
          ))}
        </div>

        {/* 日期选择（每日模式） */}
        {viewMode === 'daily' && (
          <div className="flex items-center gap-4 mb-6">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white"
            />
            {dailyData?.is_completed && (
              <span className="bg-green-500/20 text-green-400 px-3 py-1 rounded-full text-sm">
                ✓ 已完成
              </span>
            )}
          </div>
        )}

        {/* 周期信息 */}
        {viewMode !== 'daily' && periodData && (
          <div className="mb-6">
            <h2 className="text-xl font-bold">{periodData.period_label}</h2>
            <p className="text-gray-400 text-sm">{periodData.start_date} ~ {periodData.end_date}</p>
          </div>
        )}

        {/* 每日复盘内容 */}
        {viewMode === 'daily' && dailyData && (
          <>
            {/* 数据汇总 */}
            <div className="bg-card-dark rounded-2xl p-6 mb-6 border border-card-border">
              <h3 className="text-lg font-bold mb-4">📋 今日数据汇总</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <DataCard icon="😴" title="睡眠" value={`${dailyData.sleep_score ?? '--'}分 / ${dailyData.sleep_duration_hours?.toFixed(1) ?? '--'}h`} />
                <DataCard icon="🏃" title="运动" value={`${dailyData.workout_count}次 / ${dailyData.workout_calories}卡`} />
                <DataCard icon="👟" title="步数" value={dailyData.steps?.toLocaleString() || '0'} />
                <DataCard icon="🍽️" title="饮食" value={`${dailyData.meals_count}餐 / ${dailyData.total_calories_in}卡`} />
                <DataCard icon="💧" title="饮水" value={`${dailyData.water_intake_ml}ml ${dailyData.water_goal_met ? '✓' : ''}`} />
                <DataCard icon="🫧" title="洗鼻" value={`${dailyData.nasal_wash_count}次 ${dailyData.nasal_wash_done ? '✓' : ''}`} />
                <DataCard icon="✅" title="打卡" value={`${dailyData.checkin_completed}/${dailyData.checkin_total}`} />
                <DataCard icon="💊" title="补剂" value={`${dailyData.supplements_taken}种`} />
              </div>

              <div className="flex justify-around mt-4 pt-4 border-t border-white/10">
                <div className="text-center">
                  <div className="text-gray-400 text-xs">身体电量</div>
                  <div className="font-bold">{dailyData.body_battery_low ?? '--'} ~ {dailyData.body_battery_high ?? '--'}</div>
                </div>
                <div className="text-center">
                  <div className="text-gray-400 text-xs">压力指数</div>
                  <div className="font-bold">{dailyData.stress_avg ?? '--'}</div>
                </div>
                <div className="text-center">
                  <div className="text-gray-400 text-xs">静息心率</div>
                  <div className="font-bold">{dailyData.resting_hr ?? '--'} bpm</div>
                </div>
              </div>
            </div>

            {/* 主观评分 */}
            <div className="bg-card-dark rounded-2xl p-6 mb-6 border border-card-border">
              <h3 className="text-lg font-bold mb-4">🎯 今日评分</h3>
              <ScoreSelector label="心情" value={moodScore} onChange={setMoodScore} emojis={['😢', '😔', '😐', '😊', '😄']} />
              <ScoreSelector label="精力" value={energyScore} onChange={setEnergyScore} emojis={['😩', '😫', '😐', '💪', '⚡']} />
              <ScoreSelector label="效率" value={productivityScore} onChange={setProductivityScore} emojis={['📉', '📊', '📈', '🚀', '🎯']} />
            </div>

            {/* 文字复盘 */}
            <div className="bg-card-dark rounded-2xl p-6 mb-6 border border-card-border">
              <h3 className="text-lg font-bold mb-4">✍️ 今日复盘</h3>

              <TextInput label="🌟 今日亮点/成就" value={highlights} onChange={setHighlights} placeholder="今天做得好的事情..." />
              <TextInput label="⚠️ 遇到的挑战" value={challenges} onChange={setChallenges} placeholder="今天遇到的困难..." />
              <TextInput label="💡 收获与学习" value={learnings} onChange={setLearnings} placeholder="今天学到了什么..." />
              <TextInput label="🙏 感恩的事" value={gratitude} onChange={setGratitude} placeholder="今天感恩的事情..." />
              <TextInput label="📋 明日计划" value={tomorrowPlan} onChange={setTomorrowPlan} placeholder="明天要做的事情..." />

              <div className="mb-4">
                <div className="flex justify-between items-center mb-2">
                  <label className="text-sm text-gray-400">📝 总结</label>
                  <button
                    onClick={handleGenerateAI}
                    disabled={generatingAI}
                    className="bg-gradient-to-r from-purple-600 to-indigo-600 px-3 py-1 rounded-full text-xs font-medium hover:opacity-90 disabled:opacity-50"
                  >
                    {generatingAI ? '生成中...' : '✨ AI生成'}
                  </button>
                </div>
                <textarea
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  onKeyDown={(e) => {
                    // 确保回车键正常工作，不会意外提交
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      // Ctrl+Enter 或 Cmd+Enter 可以用于快速保存（可选功能）
                      return;
                    }
                  }}
                  placeholder="用几句话总结今天..."
                  className="w-full bg-black/30 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-gray-500 min-h-[120px] resize-none"
                />
              </div>

              {dailyData.ai_summary && (
                <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-4 mt-4">
                  <div className="text-purple-400 font-medium text-sm mb-2">✨ AI 总结</div>
                  <p className="text-gray-300 text-sm leading-relaxed">{dailyData.ai_summary}</p>
                </div>
              )}
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-4">
              <button
                onClick={() => handleSave(false)}
                disabled={saving}
                className="flex-1 bg-white/10 border border-white/20 py-3 rounded-xl font-medium hover:bg-white/20 disabled:opacity-50"
              >
                {saving ? '保存中...' : '💾 保存草稿'}
              </button>
              <button
                onClick={() => handleSave(true)}
                disabled={saving}
                className="flex-1 bg-gradient-to-r from-purple-600 to-indigo-600 py-3 rounded-xl font-medium hover:opacity-90 disabled:opacity-50"
              >
                {saving ? '保存中...' : '✅ 完成复盘'}
              </button>
            </div>
          </>
        )}

        {/* 周期复盘内容 */}
        {viewMode !== 'daily' && periodData && (
          <>
            <div className="bg-card-dark rounded-2xl p-6 mb-6 border border-card-border">
              <h3 className="text-lg font-bold mb-4">📈 {viewMode === 'weekly' ? '本周' : '本月'}统计</h3>
              <div className="space-y-3">
                <StatRow label="复盘完成" value={`${periodData.review_days}/${periodData.total_days} 天`} />
                <StatRow label="平均睡眠分数" value={`${periodData.avg_sleep_score?.toFixed(1) ?? '--'} 分`} />
                <StatRow label="平均睡眠时长" value={`${periodData.avg_sleep_duration?.toFixed(1) ?? '--'} 小时`} />
                <StatRow label="运动天数" value={`${periodData.workout_days} 天`} />
                <StatRow label="总运动时长" value={`${periodData.total_workout_minutes} 分钟`} />
                <StatRow label="总运动消耗" value={`${periodData.total_workout_calories} 卡`} />
                <StatRow label="平均步数" value={periodData.avg_steps?.toLocaleString() ?? '--'} />
                <StatRow label="平均摄入热量" value={`${periodData.avg_calories_in} 卡`} />
                <StatRow label="饮水达标天数" value={`${periodData.water_goal_days} 天`} />
                <StatRow label="打卡完成率" value={`${periodData.avg_checkin_rate?.toFixed(1) ?? '--'}%`} />
                <StatRow label="完美天数" value={`${periodData.perfect_days} 天`} />
              </div>
            </div>

            {periodData.ai_summary && (
              <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-4 mb-6">
                <div className="text-purple-400 font-medium text-sm mb-2">✨ AI 总结</div>
                <p className="text-gray-300 text-sm leading-relaxed">{periodData.ai_summary}</p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function DataCard({ icon, title, value }: { icon: string; title: string; value: string }) {
  return (
    <div className="bg-white/5 rounded-xl p-3 text-center">
      <div className="text-xl mb-1">{icon}</div>
      <div className="text-gray-400 text-xs mb-1">{title}</div>
      <div className="font-medium text-sm">{value}</div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-white/5 last:border-0">
      <span className="text-gray-400">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function TextInput({
  label,
  value,
  onChange,
  placeholder
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string
}) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 确保回车键在 textarea 中正常工作，不会触发表单提交或其他行为
    // Ctrl+Enter 或 Cmd+Enter 可以用于快速保存（可选功能）
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      // 可以在这里添加快速保存功能
      return;
    }
    // 普通回车键应该正常工作（插入换行），不做任何处理
  };

  return (
    <div className="mb-4">
      <label className="block text-sm text-gray-400 mb-2">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="w-full bg-black/30 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-gray-500 min-h-[80px] resize-none"
      />
    </div>
  );
}
