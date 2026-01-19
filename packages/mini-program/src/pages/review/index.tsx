/**
 * 每日复盘页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Input, Textarea } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getTodayReview, getDailyReview, updateDailyReview, refreshDailyReview, getReviewStreak } from '../../services/api';
import './index.scss';

interface DailyReviewData {
  id: number;
  review_date: string;
  
  // 自动汇总数据
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
  
  // 用户输入
  mood_score: number | null;
  energy_score: number | null;
  productivity_score: number | null;
  highlights: string | null;
  challenges: string | null;
  learnings: string | null;
  gratitude: string | null;
  tomorrow_plan: string | null;
  summary: string | null;
  
  is_completed: boolean;
}

export default function ReviewPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reviewData, setReviewData] = useState<DailyReviewData | null>(null);
  const [streak, setStreak] = useState({ current_streak: 0, total_reviews: 0 });
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  
  // 用户输入状态
  const [moodScore, setMoodScore] = useState<number>(3);
  const [energyScore, setEnergyScore] = useState<number>(3);
  const [productivityScore, setProductivityScore] = useState<number>(3);
  const [highlights, setHighlights] = useState('');
  const [challenges, setChallenges] = useState('');
  const [learnings, setLearnings] = useState('');
  const [gratitude, setGratitude] = useState('');
  const [tomorrowPlan, setTomorrowPlan] = useState('');
  const [summary, setSummary] = useState('');

  useEffect(() => {
    loadData();
  }, [selectedDate]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [review, streakData] = await Promise.all([
        getDailyReview(selectedDate),
        getReviewStreak()
      ]);
      
      setReviewData(review);
      setStreak(streakData);
      
      // 填充用户输入
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
    } catch (e) {
      console.error('加载复盘数据失败:', e);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (markComplete: boolean = false) => {
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
        is_completed: markComplete || reviewData?.is_completed,
      });
      
      Taro.showToast({ 
        title: markComplete ? '复盘已完成' : '保存成功', 
        icon: 'success' 
      });
      
      // 重新加载数据
      loadData();
    } catch (e) {
      console.error('保存失败:', e);
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSaving(false);
    }
  };

  const handleRefresh = async () => {
    Taro.showLoading({ title: '刷新中...' });
    try {
      await refreshDailyReview(selectedDate);
      await loadData();
      Taro.showToast({ title: '刷新成功', icon: 'success' });
    } catch (e) {
      Taro.showToast({ title: '刷新失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
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

  return (
    <ScrollView className="review-page" scrollY>
      {/* 头部 */}
      <View className="header">
        <View className="header-top">
          <Text className="title">📝 每日复盘</Text>
          <View className="streak-badge">
            <Text className="streak-icon">🔥</Text>
            <Text className="streak-num">{streak.current_streak}</Text>
            <Text className="streak-label">天</Text>
          </View>
        </View>
        <View className="date-row">
          <Text className="date-text">{selectedDate}</Text>
          {reviewData?.is_completed && (
            <View className="completed-badge">
              <Text>✓ 已完成</Text>
            </View>
          )}
        </View>
      </View>

      {/* 健康数据汇总 */}
      <View className="section">
        <View className="section-header">
          <Text className="section-title">📊 今日数据汇总</Text>
          <View className="refresh-btn" onClick={handleRefresh}>
            <Text>↻ 刷新</Text>
          </View>
        </View>
        
        <View className="data-grid">
          {/* 睡眠 */}
          <View className="data-card">
            <Text className="card-icon">😴</Text>
            <Text className="card-title">昨晚睡眠</Text>
            <Text className="card-value">
              {reviewData?.sleep_score ?? '--'}分 / {reviewData?.sleep_duration_hours?.toFixed(1) ?? '--'}h
            </Text>
          </View>
          
          {/* 运动 */}
          <View className="data-card">
            <Text className="card-icon">🏃</Text>
            <Text className="card-title">运动</Text>
            <Text className="card-value">
              {reviewData?.workout_count || 0}次 / {reviewData?.workout_calories || 0}卡
            </Text>
          </View>
          
          {/* 步数 */}
          <View className="data-card">
            <Text className="card-icon">👟</Text>
            <Text className="card-title">步数</Text>
            <Text className="card-value">{reviewData?.steps?.toLocaleString() || 0}</Text>
          </View>
          
          {/* 饮食 */}
          <View className="data-card">
            <Text className="card-icon">🍽️</Text>
            <Text className="card-title">饮食</Text>
            <Text className="card-value">
              {reviewData?.meals_count || 0}餐 / {reviewData?.total_calories_in || 0}卡
            </Text>
          </View>
          
          {/* 饮水 */}
          <View className="data-card">
            <Text className="card-icon">💧</Text>
            <Text className="card-title">饮水</Text>
            <Text className="card-value">
              {reviewData?.water_intake_ml || 0}ml
              {reviewData?.water_goal_met && ' ✓'}
            </Text>
          </View>
          
          {/* 洗鼻 */}
          <View className="data-card">
            <Text className="card-icon">🫧</Text>
            <Text className="card-title">洗鼻</Text>
            <Text className="card-value">
              {reviewData?.nasal_wash_count || 0}次
              {reviewData?.nasal_wash_done && ' ✓'}
            </Text>
          </View>
          
          {/* 打卡 */}
          <View className="data-card">
            <Text className="card-icon">✅</Text>
            <Text className="card-title">打卡</Text>
            <Text className="card-value">
              {reviewData?.checkin_completed || 0}/{reviewData?.checkin_total || 0}
            </Text>
          </View>
          
          {/* 补剂 */}
          <View className="data-card">
            <Text className="card-icon">💊</Text>
            <Text className="card-title">补剂</Text>
            <Text className="card-value">{reviewData?.supplements_taken || 0}种</Text>
          </View>
        </View>
        
        {/* 身体状态 */}
        <View className="body-status">
          <View className="status-item">
            <Text className="status-label">身体电量</Text>
            <Text className="status-value">
              {reviewData?.body_battery_low ?? '--'} ~ {reviewData?.body_battery_high ?? '--'}
            </Text>
          </View>
          <View className="status-item">
            <Text className="status-label">压力指数</Text>
            <Text className="status-value">{reviewData?.stress_avg ?? '--'}</Text>
          </View>
          <View className="status-item">
            <Text className="status-label">静息心率</Text>
            <Text className="status-value">{reviewData?.resting_hr ?? '--'} bpm</Text>
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
          <Text className="input-label">📝 总结</Text>
          <Textarea
            className="input-textarea large"
            value={summary}
            onInput={(e) => setSummary(e.detail.value)}
            placeholder="用几句话总结今天..."
            maxlength={1000}
          />
        </View>
      </View>

      {/* 操作按钮 */}
      <View className="action-buttons">
        <View 
          className="btn btn-secondary" 
          onClick={() => handleSave(false)}
        >
          <Text>{saving ? '保存中...' : '💾 保存草稿'}</Text>
        </View>
        <View 
          className="btn btn-primary" 
          onClick={() => handleSave(true)}
        >
          <Text>{saving ? '保存中...' : '✅ 完成复盘'}</Text>
        </View>
      </View>
      
      {/* 底部间距 */}
      <View style={{ height: '100px' }} />
    </ScrollView>
  );
}
