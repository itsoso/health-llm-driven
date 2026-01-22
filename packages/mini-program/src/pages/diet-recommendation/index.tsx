import { View, Text, ScrollView } from '@tarojs/components'
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { request } from '../../utils/request'
import './index.scss'

interface DietRecommendation {
  success: boolean
  user_info: {
    age: number
    gender: string
    height_cm: number
    current_weight_kg: number
    target_weight_kg: number
    weight_goal: string
    diet_preference: string
    activity_level: string
  }
  metabolism: {
    bmr: number
    tdee: number
    avg_exercise_calories: number
  }
  daily_target: {
    calories: number
    protein_g: number
    carbs_g: number
    fat_g: number
  }
  today_intake: {
    calories: number
    protein_g: number
    carbs_g: number
    fat_g: number
    meals_count: number
  }
  remaining: {
    calories: number
    protein_g: number
    carbs_g: number
    fat_g: number
  }
  progress: {
    calories_percent: number
    protein_percent: number
    carbs_percent: number
    fat_percent: number
  }
  health_status?: {
    sleep_score?: number
    sleep_hours?: number
    body_battery?: number
    stress_level?: number
    resting_hr?: number
    hrv?: number
  }
  warnings: string[]
  tips: string[]
  food_recommendations: Array<{
    category: string
    foods: string[]
    reason: string
    priority: string
  }>
  scientific_insights?: {
    available: boolean
    bmr_tdee_explanation?: string
    macronutrient_rationale?: string
    diet_mode_guidance?: string
    chronic_disease_guidance?: Array<{
      condition: string
      guidance: string
    }>
    sleep_nutrition?: string
    stress_nutrition?: string
    references?: string[]
  }
}

export default function DietRecommendationPage() {
  const [loading, setLoading] = useState(true)
  const [recommendation, setRecommendation] = useState<DietRecommendation | null>(null)
  const [showScientific, setShowScientific] = useState(false)

  useEffect(() => {
    loadRecommendation()
  }, [])

  const loadRecommendation = async () => {
    try {
      setLoading(true)
      const res = await request({
        url: '/diet-recommendation/me',
        method: 'GET'
      })
      
      if (res.success) {
        setRecommendation(res)
      } else {
        Taro.showToast({
          title: res.error || '加载失败',
          icon: 'none'
        })
      }
    } catch (error) {
      console.error('加载饮食推荐失败:', error)
      Taro.showToast({
        title: '加载失败',
        icon: 'none'
      })
    } finally {
      setLoading(false)
    }
  }

  const getWeightGoalText = (goal: string) => {
    const map = {
      'lose': '减重',
      'maintain': '维持',
      'gain': '增重'
    }
    return map[goal] || goal
  }

  const getActivityLevelText = (level: string) => {
    const map = {
      'sedentary': '久坐',
      'lightly_active': '轻度活动',
      'moderately_active': '中度活动',
      'very_active': '高度活动',
      'extra_active': '极度活动'
    }
    return map[level] || level
  }

  const getPriorityColor = (priority: string) => {
    const map = {
      'high': '#ff6b6b',
      'medium': '#ffa500',
      'low': '#4ecdc4'
    }
    return map[priority] || '#999'
  }

  if (loading) {
    return (
      <View className="diet-recommendation-page">
        <View className="loading">加载中...</View>
      </View>
    )
  }

  if (!recommendation) {
    return (
      <View className="diet-recommendation-page">
        <View className="empty">暂无推荐数据</View>
      </View>
    )
  }

  return (
    <ScrollView className="diet-recommendation-page" scrollY>
      {/* 用户信息卡片 */}
      <View className="card user-info-card">
        <View className="card-title">
          <Text className="title-icon">👤</Text>
          <Text className="title-text">个人信息</Text>
        </View>
        <View className="info-grid">
          <View className="info-item">
            <Text className="info-label">年龄</Text>
            <Text className="info-value">{recommendation.user_info.age}岁</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">性别</Text>
            <Text className="info-value">{recommendation.user_info.gender === 'male' ? '男' : '女'}</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">身高</Text>
            <Text className="info-value">{recommendation.user_info.height_cm}cm</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">体重</Text>
            <Text className="info-value">{recommendation.user_info.current_weight_kg}kg</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">目标</Text>
            <Text className="info-value">{getWeightGoalText(recommendation.user_info.weight_goal)}</Text>
          </View>
          <View className="info-item">
            <Text className="info-label">活动</Text>
            <Text className="info-value">{getActivityLevelText(recommendation.user_info.activity_level)}</Text>
          </View>
        </View>
      </View>

      {/* 代谢信息卡片 */}
      <View className="card metabolism-card">
        <View className="card-title">
          <Text className="title-icon">🔥</Text>
          <Text className="title-text">代谢信息</Text>
        </View>
        <View className="metabolism-grid">
          <View className="metabolism-item">
            <Text className="metabolism-label">基础代谢 (BMR)</Text>
            <Text className="metabolism-value">{recommendation.metabolism.bmr}</Text>
            <Text className="metabolism-unit">kcal/天</Text>
          </View>
          <View className="metabolism-item">
            <Text className="metabolism-label">总消耗 (TDEE)</Text>
            <Text className="metabolism-value">{recommendation.metabolism.tdee}</Text>
            <Text className="metabolism-unit">kcal/天</Text>
          </View>
        </View>
      </View>

      {/* 营养进度卡片 */}
      <View className="card progress-card">
        <View className="card-title">
          <Text className="title-icon">📊</Text>
          <Text className="title-text">今日营养进度</Text>
          <Text className="meals-count">({recommendation.today_intake.meals_count}餐)</Text>
        </View>
        
        {/* 卡路里进度 */}
        <View className="progress-item">
          <View className="progress-header">
            <Text className="progress-label">热量</Text>
            <Text className="progress-values">
              {recommendation.today_intake.calories} / {recommendation.daily_target.calories} kcal
            </Text>
          </View>
          <View className="progress-bar">
            <View 
              className="progress-fill calories"
              style={{ width: `${Math.min(recommendation.progress.calories_percent, 100)}%` }}
            />
          </View>
          <Text className="progress-percent">{recommendation.progress.calories_percent}%</Text>
        </View>

        {/* 蛋白质进度 */}
        <View className="progress-item">
          <View className="progress-header">
            <Text className="progress-label">蛋白质</Text>
            <Text className="progress-values">
              {recommendation.today_intake.protein_g} / {recommendation.daily_target.protein_g} g
            </Text>
          </View>
          <View className="progress-bar">
            <View 
              className="progress-fill protein"
              style={{ width: `${Math.min(recommendation.progress.protein_percent, 100)}%` }}
            />
          </View>
          <Text className="progress-percent">{recommendation.progress.protein_percent}%</Text>
        </View>

        {/* 碳水进度 */}
        <View className="progress-item">
          <View className="progress-header">
            <Text className="progress-label">碳水化合物</Text>
            <Text className="progress-values">
              {recommendation.today_intake.carbs_g} / {recommendation.daily_target.carbs_g} g
            </Text>
          </View>
          <View className="progress-bar">
            <View 
              className="progress-fill carbs"
              style={{ width: `${Math.min(recommendation.progress.carbs_percent, 100)}%` }}
            />
          </View>
          <Text className="progress-percent">{recommendation.progress.carbs_percent}%</Text>
        </View>

        {/* 脂肪进度 */}
        <View className="progress-item">
          <View className="progress-header">
            <Text className="progress-label">脂肪</Text>
            <Text className="progress-values">
              {recommendation.today_intake.fat_g} / {recommendation.daily_target.fat_g} g
            </Text>
          </View>
          <View className="progress-bar">
            <View 
              className="progress-fill fat"
              style={{ width: `${Math.min(recommendation.progress.fat_percent, 100)}%` }}
            />
          </View>
          <Text className="progress-percent">{recommendation.progress.fat_percent}%</Text>
        </View>
      </View>

      {/* 健康状态卡片 */}
      {recommendation.health_status && Object.keys(recommendation.health_status).length > 0 && (
        <View className="card health-status-card">
          <View className="card-title">
            <Text className="title-icon">💪</Text>
            <Text className="title-text">健康状态</Text>
          </View>
          <View className="health-grid">
            {recommendation.health_status.sleep_score !== undefined && (
              <View className="health-item">
                <Text className="health-icon">😴</Text>
                <Text className="health-label">睡眠评分</Text>
                <Text className="health-value">{recommendation.health_status.sleep_score}/100</Text>
              </View>
            )}
            {recommendation.health_status.body_battery !== undefined && (
              <View className="health-item">
                <Text className="health-icon">🔋</Text>
                <Text className="health-label">身体电量</Text>
                <Text className="health-value">{recommendation.health_status.body_battery}/100</Text>
              </View>
            )}
            {recommendation.health_status.stress_level !== undefined && (
              <View className="health-item">
                <Text className="health-icon">😌</Text>
                <Text className="health-label">压力水平</Text>
                <Text className="health-value">{recommendation.health_status.stress_level}/100</Text>
              </View>
            )}
            {recommendation.health_status.resting_hr !== undefined && (
              <View className="health-item">
                <Text className="health-icon">❤️</Text>
                <Text className="health-label">静息心率</Text>
                <Text className="health-value">{recommendation.health_status.resting_hr} bpm</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* 警告卡片 */}
      {recommendation.warnings && recommendation.warnings.length > 0 && (
        <View className="card warnings-card">
          <View className="card-title">
            <Text className="title-icon">⚠️</Text>
            <Text className="title-text">重要提醒</Text>
          </View>
          {recommendation.warnings.map((warning, index) => (
            <View key={index} className="warning-item">
              <Text className="warning-text">{warning}</Text>
            </View>
          ))}
        </View>
      )}

      {/* 健康提示卡片 */}
      {recommendation.tips && recommendation.tips.length > 0 && (
        <View className="card tips-card">
          <View className="card-title">
            <Text className="title-icon">💡</Text>
            <Text className="title-text">健康提示</Text>
          </View>
          {recommendation.tips.map((tip, index) => (
            <View key={index} className="tip-item">
              <Text className="tip-text">{tip}</Text>
            </View>
          ))}
        </View>
      )}

      {/* 食物推荐卡片 */}
      {recommendation.food_recommendations && recommendation.food_recommendations.length > 0 && (
        <View className="card food-recommendations-card">
          <View className="card-title">
            <Text className="title-icon">🍽️</Text>
            <Text className="title-text">食物推荐</Text>
          </View>
          {recommendation.food_recommendations.map((category, index) => (
            <View key={index} className="food-category">
              <View className="category-header">
                <View 
                  className="priority-badge"
                  style={{ backgroundColor: getPriorityColor(category.priority) }}
                >
                  <Text className="priority-text">
                    {category.priority === 'high' ? '重要' : category.priority === 'medium' ? '推荐' : '可选'}
                  </Text>
                </View>
                <Text className="category-name">{category.category}</Text>
              </View>
              <Text className="category-reason">{category.reason}</Text>
              <View className="foods-list">
                {category.foods.map((food, foodIndex) => (
                  <View key={foodIndex} className="food-tag">
                    <Text className="food-text">{food}</Text>
                  </View>
                ))}
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 科学见解卡片 */}
      {recommendation.scientific_insights?.available && (
        <View className="card scientific-card">
          <View 
            className="card-title clickable"
            onClick={() => setShowScientific(!showScientific)}
          >
            <Text className="title-icon">🔬</Text>
            <Text className="title-text">科学依据</Text>
            <Text className="toggle-icon">{showScientific ? '▼' : '▶'}</Text>
          </View>
          
          {showScientific && (
            <View className="scientific-content">
              {recommendation.scientific_insights.bmr_tdee_explanation && (
                <View className="scientific-section">
                  <Text className="scientific-subtitle">BMR/TDEE 计算原理</Text>
                  <Text className="scientific-text">
                    {recommendation.scientific_insights.bmr_tdee_explanation}
                  </Text>
                </View>
              )}
              
              {recommendation.scientific_insights.macronutrient_rationale && (
                <View className="scientific-section">
                  <Text className="scientific-subtitle">营养素分配依据</Text>
                  <Text className="scientific-text">
                    {recommendation.scientific_insights.macronutrient_rationale}
                  </Text>
                </View>
              )}
              
              {recommendation.scientific_insights.diet_mode_guidance && (
                <View className="scientific-section">
                  <Text className="scientific-subtitle">饮食模式指导</Text>
                  <Text className="scientific-text">
                    {recommendation.scientific_insights.diet_mode_guidance}
                  </Text>
                </View>
              )}
              
              {recommendation.scientific_insights.chronic_disease_guidance && 
               recommendation.scientific_insights.chronic_disease_guidance.length > 0 && (
                <View className="scientific-section">
                  <Text className="scientific-subtitle">慢性病饮食管理</Text>
                  {recommendation.scientific_insights.chronic_disease_guidance.map((item, index) => (
                    <View key={index} className="disease-guidance">
                      <Text className="disease-name">{item.condition}：</Text>
                      <Text className="scientific-text">{item.guidance}</Text>
                    </View>
                  ))}
                </View>
              )}
              
              {recommendation.scientific_insights.sleep_nutrition && (
                <View className="scientific-section">
                  <Text className="scientific-subtitle">睡眠营养建议</Text>
                  <Text className="scientific-text">
                    {recommendation.scientific_insights.sleep_nutrition}
                  </Text>
                </View>
              )}
              
              {recommendation.scientific_insights.stress_nutrition && (
                <View className="scientific-section">
                  <Text className="scientific-subtitle">压力营养建议</Text>
                  <Text className="scientific-text">
                    {recommendation.scientific_insights.stress_nutrition}
                  </Text>
                </View>
              )}
            </View>
          )}
        </View>
      )}

      {/* 底部间距 */}
      <View className="bottom-spacer" />
    </ScrollView>
  )
}
