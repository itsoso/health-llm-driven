'use client'

import { useEffect, useState } from 'react'
import { dietRecommendationApi } from '@/services/api'
import { 
  ChartBarIcon, 
  FireIcon, 
  HeartIcon, 
  ExclamationTriangleIcon,
  LightBulbIcon,
  BeakerIcon,
  ChevronDownIcon,
  ChevronUpIcon
} from '@heroicons/react/24/outline'

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
  const [showDebugInfo, setShowDebugInfo] = useState(false)

  useEffect(() => {
    loadRecommendation()
  }, [])

  const loadRecommendation = async () => {
    try {
      setLoading(true)
      const res = await dietRecommendationApi.getMyRecommendation()
      console.log('饮食推荐数据:', res.data)
      
      // 检查返回的数据是否有效
      if (!res.data || !res.data.success) {
        console.error('饮食推荐失败:', res.data?.error || '未知错误')
        alert(res.data?.error || '获取饮食推荐失败，请先完善个人信息')
        setRecommendation(null)
        return
      }
      
      setRecommendation(res.data)
    } catch (error) {
      console.error('加载饮食推荐失败:', error)
      alert('加载饮食推荐失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const getWeightGoalText = (goal: string) => {
    const map: Record<string, string> = {
      'lose': '减重',
      'maintain': '维持',
      'gain': '增重'
    }
    return map[goal] || goal
  }

  const getActivityLevelText = (level: string) => {
    const map: Record<string, string> = {
      'sedentary': '久坐',
      'lightly_active': '轻度活动',
      'moderately_active': '中度活动',
      'very_active': '高度活动',
      'extra_active': '极度活动'
    }
    return map[level] || level
  }

  const getPriorityColor = (priority: string) => {
    const map: Record<string, string> = {
      'high': 'bg-red-100 text-red-800 border-red-200',
      'medium': 'bg-orange-100 text-orange-800 border-orange-200',
      'low': 'bg-blue-100 text-blue-800 border-blue-200'
    }
    return map[priority] || 'bg-gray-100 text-gray-800 border-gray-200'
  }

  const getPriorityText = (priority: string) => {
    const map: Record<string, string> = {
      'high': '重要',
      'medium': '推荐',
      'low': '可选'
    }
    return map[priority] || priority
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 to-blue-50 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">加载中...</p>
          </div>
        </div>
      </div>
    )
  }

  if (!recommendation) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 to-blue-50 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center py-20">
            <p className="text-gray-600">暂无推荐数据</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-blue-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* 页面标题 */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 mb-2">智能饮食推荐</h1>
            <p className="text-gray-600">基于您的健康数据和目标的个性化营养建议</p>
          </div>
          {/* Debug 模式开关 */}
          <button
            onClick={() => setShowDebugInfo(!showDebugInfo)}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-white rounded-lg transition-colors"
          >
            {showDebugInfo ? '隐藏详细数据' : '显示详细数据'}
          </button>
        </div>

        {/* 第一行：今日营养进度 */}
        <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center">
              <ChartBarIcon className="h-6 w-6 text-purple-600 mr-2" />
              <h2 className="text-2xl font-bold text-gray-900">今日营养进度</h2>
            </div>
            <span className="text-sm text-gray-600">({recommendation.today_intake.meals_count}餐)</span>
          </div>

          <div className="space-y-6">
            {/* 热量 */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-lg font-semibold text-gray-900">热量</span>
                <span className="text-sm text-gray-600">
                  {recommendation.today_intake.calories} / {recommendation.daily_target.calories} kcal
                </span>
              </div>
              <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="absolute h-full bg-gradient-to-r from-red-500 to-orange-500 transition-all duration-500"
                  style={{ width: `${Math.min(recommendation.progress.calories_percent, 100)}%` }}
                />
              </div>
              <div className="text-right mt-1">
                <span className="text-sm font-medium text-gray-700">
                  {recommendation.progress.calories_percent}%
                </span>
              </div>
            </div>

            {/* 蛋白质 */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-lg font-semibold text-gray-900">蛋白质</span>
                <span className="text-sm text-gray-600">
                  {recommendation.today_intake.protein_g} / {recommendation.daily_target.protein_g} g
                </span>
              </div>
              <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="absolute h-full bg-gradient-to-r from-teal-500 to-green-500 transition-all duration-500"
                  style={{ width: `${Math.min(recommendation.progress.protein_percent, 100)}%` }}
                />
              </div>
              <div className="text-right mt-1">
                <span className="text-sm font-medium text-gray-700">
                  {recommendation.progress.protein_percent}%
                </span>
              </div>
            </div>

            {/* 碳水化合物 */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-lg font-semibold text-gray-900">碳水化合物</span>
                <span className="text-sm text-gray-600">
                  {recommendation.today_intake.carbs_g} / {recommendation.daily_target.carbs_g} g
                </span>
              </div>
              <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="absolute h-full bg-gradient-to-r from-yellow-500 to-orange-500 transition-all duration-500"
                  style={{ width: `${Math.min(recommendation.progress.carbs_percent, 100)}%` }}
                />
              </div>
              <div className="text-right mt-1">
                <span className="text-sm font-medium text-gray-700">
                  {recommendation.progress.carbs_percent}%
                </span>
              </div>
            </div>

            {/* 脂肪 */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-lg font-semibold text-gray-900">脂肪</span>
                <span className="text-sm text-gray-600">
                  {recommendation.today_intake.fat_g} / {recommendation.daily_target.fat_g} g
                </span>
              </div>
              <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="absolute h-full bg-gradient-to-r from-blue-400 to-blue-600 transition-all duration-500"
                  style={{ width: `${Math.min(recommendation.progress.fat_percent, 100)}%` }}
                />
              </div>
              <div className="text-right mt-1">
                <span className="text-sm font-medium text-gray-700">
                  {recommendation.progress.fat_percent}%
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 第二行：警告和提示 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* 警告 */}
          {recommendation.warnings && recommendation.warnings.length > 0 && (
            <div className="bg-red-50 border-2 border-red-200 rounded-2xl shadow-lg p-6">
              <div className="flex items-center mb-4">
                <ExclamationTriangleIcon className="h-6 w-6 text-red-600 mr-2" />
                <h2 className="text-2xl font-bold text-red-900">重要提醒</h2>
              </div>
              <div className="space-y-3">
                {recommendation.warnings.map((warning, index) => (
                  <div key={index} className="bg-white border border-red-200 rounded-lg p-4">
                    <p className="text-red-800">{warning}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 提示 */}
          {recommendation.tips && recommendation.tips.length > 0 && (
            <div className="bg-green-50 border-2 border-green-200 rounded-2xl shadow-lg p-6">
              <div className="flex items-center mb-4">
                <LightBulbIcon className="h-6 w-6 text-green-600 mr-2" />
                <h2 className="text-2xl font-bold text-green-900">健康提示</h2>
              </div>
              <div className="space-y-3">
                {recommendation.tips.map((tip, index) => (
                  <div key={index} className="bg-white border border-green-200 rounded-lg p-4">
                    <p className="text-green-800">{tip}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 第三行：食物推荐 */}
        {recommendation.food_recommendations && recommendation.food_recommendations.length > 0 && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
            <div className="flex items-center mb-6">
              <span className="text-2xl mr-2">🍽️</span>
              <h2 className="text-2xl font-bold text-gray-900">食物推荐</h2>
            </div>
            <div className="space-y-6">
              {recommendation.food_recommendations.map((category, index) => (
                <div key={index} className="border border-gray-200 rounded-lg p-6">
                  <div className="flex items-center mb-3">
                    <span className={`px-3 py-1 rounded-full text-sm font-semibold mr-3 border ${getPriorityColor(category.priority)}`}>
                      {getPriorityText(category.priority)}
                    </span>
                    <h3 className="text-xl font-bold text-gray-900">{category.category}</h3>
                  </div>
                  <p className="text-gray-600 mb-4">{category.reason}</p>
                  <div className="flex flex-wrap gap-2">
                    {category.foods.map((food, foodIndex) => (
                      <span 
                        key={foodIndex}
                        className="px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-full text-sm font-medium"
                      >
                        {food}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Debug 模式：详细数据 */}
        {showDebugInfo && (
          <div className="space-y-6 mb-6">
            {/* 个人信息 */}
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <div className="flex items-center mb-6">
                <HeartIcon className="h-6 w-6 text-purple-600 mr-2" />
                <h2 className="text-2xl font-bold text-gray-900">个人信息</h2>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">年龄</p>
                  <p className="text-2xl font-bold text-gray-900">{recommendation.user_info.age}岁</p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">性别</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {recommendation.user_info.gender === 'male' ? '男' : '女'}
                  </p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">身高</p>
                  <p className="text-2xl font-bold text-gray-900">{recommendation.user_info.height_cm}cm</p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">体重</p>
                  <p className="text-2xl font-bold text-gray-900">{recommendation.user_info.current_weight_kg}kg</p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">目标</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {getWeightGoalText(recommendation.user_info.weight_goal)}
                  </p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">活动</p>
                  <p className="text-xl font-bold text-gray-900">
                    {getActivityLevelText(recommendation.user_info.activity_level)}
                  </p>
                </div>
              </div>
            </div>

            {/* 代谢信息 */}
            <div className="bg-gradient-to-br from-purple-600 to-blue-600 rounded-2xl shadow-lg p-6 text-white">
              <div className="flex items-center mb-6">
                <FireIcon className="h-6 w-6 mr-2" />
                <h2 className="text-2xl font-bold">代谢信息</h2>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="text-center">
                  <p className="text-sm opacity-90 mb-2">基础代谢 (BMR)</p>
                  <p className="text-5xl font-bold mb-1">{recommendation.metabolism.bmr}</p>
                  <p className="text-sm opacity-75">kcal/天</p>
                </div>
                <div className="text-center">
                  <p className="text-sm opacity-90 mb-2">总消耗 (TDEE)</p>
                  <p className="text-5xl font-bold mb-1">{recommendation.metabolism.tdee}</p>
                  <p className="text-sm opacity-75">kcal/天</p>
                </div>
              </div>
            </div>

            {/* 健康状态 */}
            {recommendation.health_status && Object.keys(recommendation.health_status).length > 0 && (
              <div className="bg-white rounded-2xl shadow-lg p-6">
                <div className="flex items-center mb-6">
                  <HeartIcon className="h-6 w-6 text-purple-600 mr-2" />
                  <h2 className="text-2xl font-bold text-gray-900">健康状态</h2>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {recommendation.health_status.sleep_score !== undefined && (
                    <div className="text-center p-4 bg-purple-50 rounded-lg">
                      <p className="text-3xl mb-2">😴</p>
                      <p className="text-sm text-gray-600 mb-1">睡眠评分</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {recommendation.health_status.sleep_score}/100
                      </p>
                    </div>
                  )}
                  {recommendation.health_status.body_battery !== undefined && (
                    <div className="text-center p-4 bg-green-50 rounded-lg">
                      <p className="text-3xl mb-2">🔋</p>
                      <p className="text-sm text-gray-600 mb-1">身体电量</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {recommendation.health_status.body_battery}/100
                      </p>
                    </div>
                  )}
                  {recommendation.health_status.stress_level !== undefined && (
                    <div className="text-center p-4 bg-blue-50 rounded-lg">
                      <p className="text-3xl mb-2">😌</p>
                      <p className="text-sm text-gray-600 mb-1">压力水平</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {recommendation.health_status.stress_level}/100
                      </p>
                    </div>
                  )}
                  {recommendation.health_status.resting_hr !== undefined && (
                    <div className="text-center p-4 bg-red-50 rounded-lg">
                      <p className="text-3xl mb-2">❤️</p>
                      <p className="text-sm text-gray-600 mb-1">静息心率</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {recommendation.health_status.resting_hr} bpm
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 科学依据 */}
        {recommendation.scientific_insights?.available && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
            <button
              onClick={() => setShowScientific(!showScientific)}
              className="w-full flex items-center justify-between mb-4 hover:bg-gray-50 p-2 rounded-lg transition-colors"
            >
              <div className="flex items-center">
                <BeakerIcon className="h-6 w-6 text-purple-600 mr-2" />
                <h2 className="text-2xl font-bold text-gray-900">科学依据</h2>
              </div>
              {showScientific ? (
                <ChevronUpIcon className="h-6 w-6 text-gray-600" />
              ) : (
                <ChevronDownIcon className="h-6 w-6 text-gray-600" />
              )}
            </button>
            
            {showScientific && (
              <div className="space-y-6 pt-4">
                {recommendation.scientific_insights.bmr_tdee_explanation && (
                  <div>
                    <h3 className="text-lg font-bold text-purple-600 mb-2">BMR/TDEE 计算原理</h3>
                    <p className="text-gray-700 leading-relaxed">
                      {recommendation.scientific_insights.bmr_tdee_explanation}
                    </p>
                  </div>
                )}
                
                {recommendation.scientific_insights.macronutrient_rationale && (
                  <div>
                    <h3 className="text-lg font-bold text-purple-600 mb-2">营养素分配依据</h3>
                    <p className="text-gray-700 leading-relaxed">
                      {recommendation.scientific_insights.macronutrient_rationale}
                    </p>
                  </div>
                )}
                
                {recommendation.scientific_insights.diet_mode_guidance && (
                  <div>
                    <h3 className="text-lg font-bold text-purple-600 mb-2">饮食模式指导</h3>
                    <p className="text-gray-700 leading-relaxed">
                      {recommendation.scientific_insights.diet_mode_guidance}
                    </p>
                  </div>
                )}
                
                {recommendation.scientific_insights.chronic_disease_guidance && 
                 recommendation.scientific_insights.chronic_disease_guidance.length > 0 && (
                  <div>
                    <h3 className="text-lg font-bold text-purple-600 mb-2">慢性病饮食管理</h3>
                    {recommendation.scientific_insights.chronic_disease_guidance.map((item, index) => (
                      <div key={index} className="mb-4">
                        <h4 className="font-semibold text-gray-900 mb-1">{item.condition}：</h4>
                        <p className="text-gray-700 leading-relaxed">{item.guidance}</p>
                      </div>
                    ))}
                  </div>
                )}
                
                {recommendation.scientific_insights.sleep_nutrition && (
                  <div>
                    <h3 className="text-lg font-bold text-purple-600 mb-2">睡眠营养建议</h3>
                    <p className="text-gray-700 leading-relaxed">
                      {recommendation.scientific_insights.sleep_nutrition}
                    </p>
                  </div>
                )}
                
                {recommendation.scientific_insights.stress_nutrition && (
                  <div>
                    <h3 className="text-lg font-bold text-purple-600 mb-2">压力营养建议</h3>
                    <p className="text-gray-700 leading-relaxed">
                      {recommendation.scientific_insights.stress_nutrition}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
