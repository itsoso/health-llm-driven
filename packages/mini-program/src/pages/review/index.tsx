/**
 * 每日复盘页面 - 支持日/周/月视图
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Textarea, Picker } from '@tarojs/components';
import Taro from '@tarojs/taro';
import {
  getTodayReview,
  getDailyReview,
  updateDailyReview,
  refreshDailyReview,
  getReviewStreak,
  getCurrentWeekReview,
  getCurrentMonthReview,
  generateAIReviewSummary
} from '../../services/api';
import './index.scss';

type ViewMode = 'daily' | 'weekly' | 'monthly';

interface DailyReviewData {
  id: number;
  review_date: string;
  sleep_score: number | null;
  sleep_duration_hours: number | null;
  workout_count: number;
  workout_duration_minutes: number;
  workout_calories: number;
  workout_types: string | null;
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
  const [viewMode, setViewMode] = useState<ViewMode>('daily');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [generatingAI, setGeneratingAI] = useState(false);

  // 每日复盘数据
  const [dailyData, setDailyData] = useState<DailyReviewData | null>(null);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);

  // 周期复盘数据
  const [periodData, setPeriodData] = useState<PeriodReviewData | null>(null);

  // 统计数据
  const [streak, setStreak] = useState({ current_streak: 0, total_reviews: 0 });

  // 用户输入状态（每日）
  const [moodScore, setMoodScore] = useState<number>(3);
  const [energyScore, setEnergyScore] = useState<number>(3);
  const [productivityScore, setProductivityScore] = useState<number>(3);
  const [highlights, setHighlights] = useState('');
  const [challenges, setChallenges] = useState('');
  const [learnings, setLearnings] = useState('');
  const [gratitude, setGratitude] = useState('');
  const [tomorrowPlan, setTomorrowPlan] = useState('');
  const [summary, setSummary] = useState('');

  // 周期复盘输入
  const [periodAchievements, setPeriodAchievements] = useState('');
  const [periodChallenges, setPeriodChallenges] = useState('');
  const [periodLearnings, setPeriodLearnings] = useState('');
  const [periodGoalsReview, setPeriodGoalsReview] = useState('');
  const [periodNextGoals, setPeriodNextGoals] = useState('');
  const [periodSummary, setPeriodSummary] = useState('');

  useEffect(() => {
    // 检查登录状态
    const token = Taro.getStorageSync('access_token');
    if (!token) {
      Taro.switchTab({ url: '/pages/index/index' });
      return;
    }
    loadData();
  }, [viewMode, selectedDate]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      // 先尝试获取连续天数统计
      try {
        const streakData = await getReviewStreak();
        setStreak(streakData);
      } catch (e) {
        console.warn('获取连续天数失败:', e);
        // 不阻塞主流程
      }

      if (viewMode === 'daily') {
        try {
          const review = await getDailyReview(selectedDate);
          setDailyData(review);
          fillDailyInputs(review);
        } catch (e) {
          console.warn('获取每日复盘失败，使用空数据:', e);
          // 即使获取失败，也显示空表单让用户可以填写
          setDailyData(null);
          // 重置输入状态
          setMoodScore(3);
          setEnergyScore(3);
          setProductivityScore(3);
          setHighlights('');
          setChallenges('');
          setLearnings('');
          setGratitude('');
          setTomorrowPlan('');
          setSummary('');
        }
      } else if (viewMode === 'weekly') {
        const review = await getCurrentWeekReview();
        setPeriodData(review);
        fillPeriodInputs(review);
      } else if (viewMode === 'monthly') {
        const review = await getCurrentMonthReview();
        setPeriodData(review);
        fillPeriodInputs(review);
      }
    } catch (e: any) {
      console.error('加载复盘数据失败:', e);
      const errorMsg = e?.message || '加载失败，请稍后重试';
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const fillDailyInputs = (review: DailyReviewData | null) => {
    if (review) {
      setMoodScore(review.mood_score || 3);
      setEnergyScore(review.energy_score || 3);
      setProductivityScore(review.productivity_score || 3);
      setHighlights(review.highlights || '');
      setChallenges(review.challenges || '');
      setLearnings(review.learnings || '');
      setGratitude(review.gratitude || '');
      setTomorrowPlan(review.tomorrow_plan || '');
      setSummary(review.summary || '');
    }
  };

  const fillPeriodInputs = (review: PeriodReviewData | null) => {
    if (review) {
      setPeriodAchievements(review.achievements || '');
      setPeriodChallenges(review.challenges || '');
      setPeriodLearnings(review.learnings || '');
      setPeriodGoalsReview(review.goals_review || '');
      setPeriodNextGoals(review.next_period_goals || '');
      setPeriodSummary(review.summary || '');
    }
  };

  const handleSaveDaily = async (markComplete: boolean = false) => {
    setSaving(true);
    try {
      await updateDailyReview(selectedDate, {
        mood_score: moodScore,
        energy_score: energyScore,
        productivity_score: productivityScore,
        highlights: highlights || null,
        challenges: challenges || null,
        learnings: learnings || null,
        gratitude: gratitude || null,
        tomorrow_plan: tomorrowPlan || null,
        summary: summary || null,
        is_completed: markComplete || dailyData?.is_completed,
      });

      Taro.showToast({
        title: markComplete ? '复盘已完成' : '保存成功',
        icon: 'success'
      });
      loadData();
    } catch (e) {
      console.error('保存失败:', e);
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateAISummary = async () => {
    setGeneratingAI(true);
    try {
      const result = await generateAIReviewSummary(
        viewMode === 'daily' ? selectedDate : periodData?.start_date || '',
        viewMode
      );

      if (result?.ai_summary) {
        if (viewMode === 'daily') {
          setSummary(result.ai_summary);
        } else {
          setPeriodSummary(result.ai_summary);
        }
        Taro.showToast({ title: '智能总结已生成', icon: 'success' });
      }
    } catch (e) {
      console.error('AI生成失败:', e);
      Taro.showToast({ title: '智能生成失败', icon: 'none' });
    } finally {
      setGeneratingAI(false);
    }
  };

  const handleRefresh = async () => {
    Taro.showLoading({ title: '刷新中...' });
    try {
      if (viewMode === 'daily') {
        await refreshDailyReview(selectedDate);
      }
      await loadData();
      Taro.showToast({ title: '刷新成功', icon: 'success' });
    } catch (e) {
      Taro.showToast({ title: '刷新失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  };

  const handleDateChange = (e: any) => {
    setSelectedDate(e.detail.value);
  };

  const renderScoreSelector = (
    label: string,
    value: number,
    onChange: (v: number) => void,
    emojis: string[]
  ) => (
    <View className="score-selector">
      <Text className="score-label">{label}</Text>
      <View className="score-options">
        {[1, 2, 3, 4, 5].map(score => (
          <View
            key={score}
            className={`score-item ${value === score ? 'active' : ''}`}
            onClick={() => onChange(score)}
          >
            <Text className="score-emoji">{emojis[score - 1]}</Text>
            <Text className="score-num">{score}</Text>
          </View>
        ))}
      </View>
    </View>
  );

  if (loading) {
    return (
      <View className="review-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  // 错误状态
  if (error) {
    return (
      <View className="review-page error-state">
        <Text className="error-icon">😔</Text>
        <Text className="error-text">{error}</Text>
        <View className="retry-btn" onClick={loadData}>
          <Text className="retry-text">点击重试</Text>
        </View>
      </View>
    );
  }

  return (
    <ScrollView className="review-page" scrollY>
      {/* 头部 */}
      <View className="header">
        <View className="header-top">
          <Text className="title">📝 复盘</Text>
          <View className="streak-badge">
            <Text className="streak-icon">🔥</Text>
            <Text className="streak-num">{streak.current_streak}</Text>
            <Text className="streak-label">天</Text>
          </View>
        </View>

        {/* 视图切换 */}
        <View className="view-tabs">
          <View
            className={`tab ${viewMode === 'daily' ? 'active' : ''}`}
            onClick={() => setViewMode('daily')}
          >
            <Text>每日</Text>
          </View>
          <View
            className={`tab ${viewMode === 'weekly' ? 'active' : ''}`}
            onClick={() => setViewMode('weekly')}
          >
            <Text>本周</Text>
          </View>
          <View
            className={`tab ${viewMode === 'monthly' ? 'active' : ''}`}
            onClick={() => setViewMode('monthly')}
          >
            <Text>本月</Text>
          </View>
        </View>

        {/* 日期选择（仅每日模式） */}
        {viewMode === 'daily' && (
          <View className="date-row">
            <Picker mode="date" value={selectedDate} onChange={handleDateChange}>
              <View className="date-picker">
                <Text className="date-text">{selectedDate}</Text>
                <Text className="date-arrow">▼</Text>
              </View>
            </Picker>
            {dailyData?.is_completed && (
              <View className="completed-badge">
                <Text>✓ 已完成</Text>
              </View>
            )}
          </View>
        )}

        {/* 周期标签 */}
        {viewMode !== 'daily' && periodData && (
          <View className="period-info">
            <Text className="period-label">{periodData.period_label}</Text>
            <Text className="period-range">
              {periodData.start_date} ~ {periodData.end_date}
            </Text>
          </View>
        )}
      </View>

      {/* 每日复盘内容 */}
      {viewMode === 'daily' && (
        <>
          {/* 健康数据汇总 */}
          <View className="section">
            <View className="section-header">
              <Text className="section-title">📋 今日数据汇总</Text>
              <View className="refresh-btn" onClick={handleRefresh}>
                <Text>↻ 刷新</Text>
              </View>
            </View>

            <View className="data-grid">
              <View className="data-card">
                <Text className="card-icon">😴</Text>
                <Text className="card-title">昨晚睡眠</Text>
                <Text className="card-value">
                  {dailyData?.sleep_score ?? '--'}分 / {dailyData?.sleep_duration_hours?.toFixed(1) ?? '--'}h
                </Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">🏃</Text>
                <Text className="card-title">运动</Text>
                <Text className="card-value">
                  {dailyData?.workout_count || 0}次 / {dailyData?.workout_calories || 0}卡
                </Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">👟</Text>
                <Text className="card-title">步数</Text>
                <Text className="card-value">{dailyData?.steps?.toLocaleString() || 0}</Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">🍽️</Text>
                <Text className="card-title">饮食</Text>
                <Text className="card-value">
                  {dailyData?.meals_count || 0}餐 / {dailyData?.total_calories_in || 0}卡
                </Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">💧</Text>
                <Text className="card-title">饮水</Text>
                <Text className="card-value">
                  {dailyData?.water_intake_ml || 0}ml
                  {dailyData?.water_goal_met && ' ✓'}
                </Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">🫧</Text>
                <Text className="card-title">洗鼻</Text>
                <Text className="card-value">
                  {dailyData?.nasal_wash_count || 0}次
                  {dailyData?.nasal_wash_done && ' ✓'}
                </Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">✅</Text>
                <Text className="card-title">打卡</Text>
                <Text className="card-value">
                  {dailyData?.checkin_completed || 0}/{dailyData?.checkin_total || 0}
                </Text>
              </View>

              <View className="data-card">
                <Text className="card-icon">💊</Text>
                <Text className="card-title">补剂</Text>
                <Text className="card-value">{dailyData?.supplements_taken || 0}种</Text>
              </View>
            </View>

            <View className="body-status">
              <View className="status-item">
                <Text className="status-label">身体电量</Text>
                <Text className="status-value">
                  {dailyData?.body_battery_low ?? '--'} ~ {dailyData?.body_battery_high ?? '--'}
                </Text>
              </View>
              <View className="status-item">
                <Text className="status-label">压力指数</Text>
                <Text className="status-value">{dailyData?.stress_avg ?? '--'}</Text>
              </View>
              <View className="status-item">
                <Text className="status-label">静息心率</Text>
                <Text className="status-value">{dailyData?.resting_hr ?? '--'} bpm</Text>
              </View>
            </View>
          </View>

          {/* 主观评分 */}
          <View className="section">
            <Text className="section-title">🎯 今日评分</Text>
            {renderScoreSelector('心情', moodScore, setMoodScore, ['😢', '😔', '😐', '😊', '😄'])}
            {renderScoreSelector('精力', energyScore, setEnergyScore, ['😩', '😫', '😐', '💪', '⚡'])}
            {renderScoreSelector('效率', productivityScore, setProductivityScore, ['📉', '📊', '📈', '🚀', '🎯'])}
          </View>

          {/* 文字复盘 */}
          <View className="section">
            <Text className="section-title">✍️ 今日复盘</Text>

            <View className="input-group">
              <Text className="input-label">🌟 今日亮点/成就</Text>
              <Textarea
                className="input-textarea"
                value={highlights}
                onInput={(e) => setHighlights(e.detail.value)}
                placeholder="今天做得好的事情..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">⚠️ 遇到的挑战</Text>
              <Textarea
                className="input-textarea"
                value={challenges}
                onInput={(e) => setChallenges(e.detail.value)}
                placeholder="今天遇到的困难..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">💡 收获与学习</Text>
              <Textarea
                className="input-textarea"
                value={learnings}
                onInput={(e) => setLearnings(e.detail.value)}
                placeholder="今天学到了什么..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">🙏 感恩的事</Text>
              <Textarea
                className="input-textarea"
                value={gratitude}
                onInput={(e) => setGratitude(e.detail.value)}
                placeholder="今天感恩的事情..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">📋 明日计划</Text>
              <Textarea
                className="input-textarea"
                value={tomorrowPlan}
                onInput={(e) => setTomorrowPlan(e.detail.value)}
                placeholder="明天要做的事情..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <View className="input-label-row">
                <Text className="input-label">📝 总结</Text>
                <View
                  className="ai-btn"
                  onClick={handleGenerateAISummary}
                >
                  <Text>{generatingAI ? '生成中...' : '✨ 智能生成'}</Text>
                </View>
              </View>
              <Textarea
                className="input-textarea large"
                value={summary}
                onInput={(e) => setSummary(e.detail.value)}
                placeholder="用几句话总结今天..."
                maxlength={1000}
              />
            </View>

            {dailyData?.ai_summary && (
              <View className="ai-summary-card">
                <Text className="ai-summary-title">✨ 智能总结</Text>
                <Text className="ai-summary-text">{dailyData.ai_summary}</Text>
              </View>
            )}
          </View>

          {/* 操作按钮 */}
          <View className="action-buttons">
            <View className="btn btn-secondary" onClick={() => handleSaveDaily(false)}>
              <Text>{saving ? '保存中...' : '💾 保存草稿'}</Text>
            </View>
            <View className="btn btn-primary" onClick={() => handleSaveDaily(true)}>
              <Text>{saving ? '保存中...' : '✅ 完成复盘'}</Text>
            </View>
          </View>
        </>
      )}

      {/* 周期复盘内容 */}
      {viewMode !== 'daily' && periodData && (
        <>
          {/* 周期统计 */}
          <View className="section">
            <View className="section-header">
              <Text className="section-title">📈 {viewMode === 'weekly' ? '本周' : '本月'}统计</Text>
              <View className="refresh-btn" onClick={handleRefresh}>
                <Text>↻ 刷新</Text>
              </View>
            </View>

            <View className="stats-summary">
              <View className="stat-row">
                <Text className="stat-label">复盘完成</Text>
                <Text className="stat-value">{periodData.review_days}/{periodData.total_days} 天</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">平均睡眠分数</Text>
                <Text className="stat-value">{periodData.avg_sleep_score?.toFixed(1) ?? '--'} 分</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">平均睡眠时长</Text>
                <Text className="stat-value">{periodData.avg_sleep_duration?.toFixed(1) ?? '--'} 小时</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">运动天数</Text>
                <Text className="stat-value">{periodData.workout_days} 天</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">总运动时长</Text>
                <Text className="stat-value">{periodData.total_workout_minutes} 分钟</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">总运动消耗</Text>
                <Text className="stat-value">{periodData.total_workout_calories} 卡</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">平均步数</Text>
                <Text className="stat-value">{periodData.avg_steps?.toLocaleString() ?? '--'}</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">平均摄入热量</Text>
                <Text className="stat-value">{periodData.avg_calories_in} 卡</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">饮水达标天数</Text>
                <Text className="stat-value">{periodData.water_goal_days} 天</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">打卡完成率</Text>
                <Text className="stat-value">{periodData.avg_checkin_rate?.toFixed(1) ?? '--'}%</Text>
              </View>
              <View className="stat-row">
                <Text className="stat-label">完美天数</Text>
                <Text className="stat-value">{periodData.perfect_days} 天</Text>
              </View>
            </View>
          </View>

          {/* 周期复盘输入 */}
          <View className="section">
            <Text className="section-title">✍️ {viewMode === 'weekly' ? '本周' : '本月'}复盘</Text>

            <View className="input-group">
              <Text className="input-label">🏆 本周期成就</Text>
              <Textarea
                className="input-textarea"
                value={periodAchievements}
                onInput={(e) => setPeriodAchievements(e.detail.value)}
                placeholder="这段时间取得的成就..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">⚠️ 遇到的挑战</Text>
              <Textarea
                className="input-textarea"
                value={periodChallenges}
                onInput={(e) => setPeriodChallenges(e.detail.value)}
                placeholder="这段时间遇到的困难..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">💡 收获与学习</Text>
              <Textarea
                className="input-textarea"
                value={periodLearnings}
                onInput={(e) => setPeriodLearnings(e.detail.value)}
                placeholder="这段时间学到了什么..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">🎯 目标回顾</Text>
              <Textarea
                className="input-textarea"
                value={periodGoalsReview}
                onInput={(e) => setPeriodGoalsReview(e.detail.value)}
                placeholder="之前设定的目标完成情况..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <Text className="input-label">📋 下周期目标</Text>
              <Textarea
                className="input-textarea"
                value={periodNextGoals}
                onInput={(e) => setPeriodNextGoals(e.detail.value)}
                placeholder="下一阶段的目标..."
                maxlength={500}
              />
            </View>

            <View className="input-group">
              <View className="input-label-row">
                <Text className="input-label">📝 总结</Text>
                <View className="ai-btn" onClick={handleGenerateAISummary}>
                  <Text>{generatingAI ? '生成中...' : '✨ 智能生成'}</Text>
                </View>
              </View>
              <Textarea
                className="input-textarea large"
                value={periodSummary}
                onInput={(e) => setPeriodSummary(e.detail.value)}
                placeholder="总结这段时间..."
                maxlength={1000}
              />
            </View>

            {periodData.ai_summary && (
              <View className="ai-summary-card">
                <Text className="ai-summary-title">✨ 智能总结</Text>
                <Text className="ai-summary-text">{periodData.ai_summary}</Text>
              </View>
            )}
          </View>

          {/* 操作按钮 */}
          <View className="action-buttons">
            <View className="btn btn-secondary">
              <Text>💾 保存草稿</Text>
            </View>
            <View className="btn btn-primary">
              <Text>✅ 完成复盘</Text>
            </View>
          </View>
        </>
      )}

      <View style={{ height: '100px' }} />
    </ScrollView>
  );
}
