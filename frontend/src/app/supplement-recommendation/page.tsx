'use client'

import { useEffect, useState } from 'react'
import { supplementApi } from '@/services/api/records';
import {
  SparklesIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  HeartIcon,
  BoltIcon,
  MoonIcon,
  FireIcon,
  ChevronDownIcon,
  ChevronUpIcon
} from '@heroicons/react/24/outline'
import { useAuth } from '@/contexts/AuthContext'
import ProtectedRoute from '@/components/ProtectedRoute'

interface SupplementRecommendation {
  success: boolean
  rating: {
    score: number
    level: string
    emoji: string
    message: string
  }
  analysis: {
    sleep_quality: string
    stress_level: string
    exercise_intensity: string
    nutrition_status: string
    key_factors: string[]
  }
  recommendations: Array<{
    category: string
    name: string
    reason: string
    dosage: string
    timing: string
    priority: string
    icon: string
    products?: Array<{
      id: number
      name: string
      brand?: string
      image_url?: string
      platform: string
      affiliate_url: string
      price_display?: string
      currency?: string
      gene_match?: boolean
      gene_description?: string
      match_score?: number
    }>
  }>
  timing_suggestions: {
    morning?: string[]
    noon?: string[]
    evening?: string[]
    bedtime?: string[]
  }
  precautions: string[]
  debug_info?: any
}

function SupplementRecommendationContent() {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [recommendation, setRecommendation] = useState<SupplementRecommendation | null>(null)
  const [showDebugInfo, setShowDebugInfo] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadRecommendation()
  }, [])

  const loadRecommendation = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await supplementApi.getScientificRecommendation(undefined, showDebugInfo)

      console.log('[补剂推荐] API 返回数据:', response.data)

      // 验证并添加默认值
      const validatedData = {
        ...response.data,
        rating: response.data.rating || {
          score: 0,
          level: '评估中',
          emoji: '⭐',
          message: '正在分析您的补剂方案'
        },
        analysis: response.data.analysis || {
          sleep_quality: '未知',
          stress_level: '未知',
          exercise_intensity: '未知',
          nutrition_status: '未知',
          key_factors: []
        },
        recommendations: response.data.recommendations || [],
        timing_suggestions: response.data.timing_suggestions || {
          morning: [],
          noon: [],
          evening: [],
          bedtime: []
        },
        precautions: response.data.precautions || []
      }

      setRecommendation(validatedData)
    } catch (err: any) {
      console.error('加载补剂推荐失败:', err)
      setError(err.response?.data?.detail || '加载推荐失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case '高':
        return 'bg-red-100 border-red-300 text-red-700'
      case '中':
        return 'bg-yellow-100 border-yellow-300 text-yellow-700'
      case '低':
        return 'bg-gray-100 border-gray-300 text-gray-700'
      default:
        return 'bg-gray-100 border-gray-300 text-gray-700'
    }
  }

  const getTimingIcon = (timing: string) => {
    if (timing.includes('morning')) return '🌅'
    if (timing.includes('noon')) return '☀️'
    if (timing.includes('evening')) return '🌆'
    if (timing.includes('bedtime')) return '🌙'
    return '⏰'
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-pink-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-purple-600 mx-auto mb-6"></div>
          <p className="text-gray-700 font-medium text-lg">✨ AI 正在分析您的健康数据...</p>
          <p className="text-gray-500 text-sm mt-2">这可能需要几秒钟</p>
        </div>
      </main>
    )
  }

  if (error) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-pink-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="text-6xl mb-4">😔</div>
          <h3 className="text-xl font-bold text-gray-800 mb-2">加载失败</h3>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={loadRecommendation}
            className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-700 hover:to-pink-700 shadow-md transition-all"
          >
            重新加载
          </button>
        </div>
      </main>
    )
  }

  if (!recommendation) {
    return null
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-pink-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 页面标题 */}
        <div className="mb-6 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">✨ 补剂科学推荐</h1>
            <p className="text-gray-600">基于您的健康数据和运动状态的个性化补剂建议</p>
          </div>
          <button
            onClick={loadRecommendation}
            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 shadow-sm transition-all"
          >
            🔄 刷新推荐
          </button>
        </div>

        {/* 评分卡片 */}
        {recommendation.rating && (
          <div className="bg-gradient-to-r from-purple-600 to-pink-600 rounded-2xl shadow-xl p-8 mb-6 text-white">
            <div className="text-center">
              <div className="text-7xl mb-4">{recommendation.rating.emoji || '⭐'}</div>
              <div className="text-5xl font-bold mb-2">{recommendation.rating.score || 0}</div>
              <div className="text-2xl font-semibold mb-2">{recommendation.rating.level || '评估中'}</div>
              <p className="text-purple-100 text-lg">{recommendation.rating.message || '正在分析您的补剂方案'}</p>
            </div>
          </div>
        )}

        {/* 健康分析 */}
        {recommendation.analysis && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-200">
            <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
              <ChartBarIcon className="w-6 h-6 text-purple-600" />
              健康状态分析
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4 border border-blue-200">
                <div className="flex items-center gap-2 mb-2">
                  <MoonIcon className="w-5 h-5 text-blue-600" />
                  <span className="font-semibold text-gray-800">睡眠质量</span>
                </div>
                <div className="text-2xl font-bold text-blue-700">{recommendation.analysis.sleep_quality || '未知'}</div>
              </div>
              <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl p-4 border border-orange-200">
                <div className="flex items-center gap-2 mb-2">
                  <BoltIcon className="w-5 h-5 text-orange-600" />
                  <span className="font-semibold text-gray-800">压力水平</span>
                </div>
                <div className="text-2xl font-bold text-orange-700">{recommendation.analysis.stress_level || '未知'}</div>
              </div>
              <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-4 border border-green-200">
                <div className="flex items-center gap-2 mb-2">
                  <FireIcon className="w-5 h-5 text-green-600" />
                  <span className="font-semibold text-gray-800">运动强度</span>
                </div>
                <div className="text-2xl font-bold text-green-700">{recommendation.analysis.exercise_intensity || '未知'}</div>
              </div>
              <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4 border border-purple-200">
                <div className="flex items-center gap-2 mb-2">
                  <HeartIcon className="w-5 h-5 text-purple-600" />
                  <span className="font-semibold text-gray-800">营养状态</span>
                </div>
                <div className="text-2xl font-bold text-purple-700">{recommendation.analysis.nutrition_status || '未知'}</div>
              </div>
            </div>

          {/* 关键因素 */}
          {recommendation.analysis.key_factors && recommendation.analysis.key_factors.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <h3 className="font-semibold text-gray-800 mb-2">🎯 关键影响因素</h3>
              <div className="flex flex-wrap gap-2">
                {recommendation.analysis.key_factors.map((factor, idx) => (
                  <span
                    key={idx}
                    className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium"
                  >
                    {factor}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
        )}

        {/* 推荐补剂 */}
        {recommendation.recommendations && recommendation.recommendations.length > 0 && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-200">
            <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
              <SparklesIcon className="w-6 h-6 text-purple-600" />
              推荐补剂清单
            </h2>
            <div className="space-y-4">
              {recommendation.recommendations.map((rec, idx) => (
              <div
                key={idx}
                className={`rounded-xl p-5 border-2 transition-all hover:shadow-md ${
                  rec.priority === '高'
                    ? 'bg-red-50 border-red-300'
                    : rec.priority === '中'
                    ? 'bg-yellow-50 border-yellow-300'
                    : 'bg-gray-50 border-gray-300'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl">{rec.icon}</span>
                    <div>
                      <h3 className="text-lg font-bold text-gray-900">{rec.name}</h3>
                      <span className={`inline-block px-2 py-1 rounded-full text-xs font-semibold ${getPriorityColor(rec.priority)}`}>
                        {rec.priority}优先
                      </span>
                    </div>
                  </div>
                </div>
                <p className="text-gray-700 mb-3">{rec.reason}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                  <div className="flex items-center gap-2 text-gray-600">
                    <span className="font-semibold">💊 推荐剂量:</span>
                    <span>{rec.dosage}</span>
                  </div>
                  <div className="flex items-center gap-2 text-gray-600">
                    <span className="font-semibold">⏰ 服用时间:</span>
                    <span>{rec.timing}</span>
                  </div>
                </div>
                {/* 推荐产品 */}
                {rec.products && rec.products.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <div className="text-xs font-semibold text-gray-500 mb-2">🛒 推荐产品</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {rec.products.map(p => (
                        <a
                          key={p.id}
                          href={p.affiliate_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-3 transition-all hover:border-teal-400 hover:shadow-sm"
                        >
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-lg">
                            {p.platform === 'iherb' ? '🌿' : p.platform === 'jd' ? '🔴' : '🛒'}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-gray-900 truncate">{p.name}</div>
                            <div className="flex items-center gap-2 mt-0.5">
                              {p.price_display && <span className="text-sm font-bold text-teal-600">{p.price_display}</span>}
                              <span className="text-[10px] text-gray-400 uppercase">{p.platform}</span>
                              {p.gene_match && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-medium">
                                  🧬 适合您的基因型
                                </span>
                              )}
                            </div>
                          </div>
                          <span className="text-gray-400 text-sm shrink-0">→</span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              ))}
            </div>
          </div>
        )}

        {/* 服用时机建议 */}
        {recommendation.timing_suggestions && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-200">
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
            <ClockIcon className="w-6 h-6 text-purple-600" />
            每日服用时间表
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {recommendation.timing_suggestions.morning && recommendation.timing_suggestions.morning.length > 0 && (
              <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl p-4 border border-orange-200">
                <div className="text-2xl mb-2">🌅</div>
                <h3 className="font-bold text-gray-900 mb-2">早晨</h3>
                <ul className="space-y-1 text-sm text-gray-700">
                  {recommendation.timing_suggestions.morning.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-1">
                      <span className="text-orange-600">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recommendation.timing_suggestions.noon && recommendation.timing_suggestions.noon.length > 0 && (
              <div className="bg-gradient-to-br from-yellow-50 to-yellow-100 rounded-xl p-4 border border-yellow-200">
                <div className="text-2xl mb-2">☀️</div>
                <h3 className="font-bold text-gray-900 mb-2">中午</h3>
                <ul className="space-y-1 text-sm text-gray-700">
                  {recommendation.timing_suggestions.noon.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-1">
                      <span className="text-yellow-600">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recommendation.timing_suggestions.evening && recommendation.timing_suggestions.evening.length > 0 && (
              <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4 border border-purple-200">
                <div className="text-2xl mb-2">🌆</div>
                <h3 className="font-bold text-gray-900 mb-2">晚上</h3>
                <ul className="space-y-1 text-sm text-gray-700">
                  {recommendation.timing_suggestions.evening.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-1">
                      <span className="text-purple-600">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recommendation.timing_suggestions.bedtime && recommendation.timing_suggestions.bedtime.length > 0 && (
              <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 rounded-xl p-4 border border-indigo-200">
                <div className="text-2xl mb-2">🌙</div>
                <h3 className="font-bold text-gray-900 mb-2">睡前</h3>
                <ul className="space-y-1 text-sm text-gray-700">
                  {recommendation.timing_suggestions.bedtime.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-1">
                      <span className="text-indigo-600">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          </div>
        )}

        {/* 注意事项 */}
        {recommendation.precautions && recommendation.precautions.length > 0 && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-gray-200">
            <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
              <ExclamationTriangleIcon className="w-6 h-6 text-orange-600" />
              重要注意事项
            </h2>
            <div className="space-y-2">
              {recommendation.precautions.map((precaution, idx) => (
                <div key={idx} className="flex items-start gap-3 p-3 bg-orange-50 rounded-lg border border-orange-200">
                  <span className="text-orange-600 font-bold text-lg">⚠️</span>
                  <p className="text-gray-700 flex-1">{precaution}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Debug 信息 */}
        {recommendation.debug_info && (
          <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-200">
            <button
              onClick={() => setShowDebugInfo(!showDebugInfo)}
              className="w-full flex items-center justify-between text-left"
            >
              <h2 className="text-lg font-bold text-gray-900">🔍 调试信息</h2>
              {showDebugInfo ? (
                <ChevronUpIcon className="w-5 h-5 text-gray-600" />
              ) : (
                <ChevronDownIcon className="w-5 h-5 text-gray-600" />
              )}
            </button>
            {showDebugInfo && (
              <pre className="mt-4 p-4 bg-gray-50 rounded-lg text-xs overflow-auto max-h-96 text-gray-700">
                {JSON.stringify(recommendation.debug_info, null, 2)}
              </pre>
            )}
          </div>
        )}

        {/* 免责声明 */}
        <div className="mt-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
          <p className="text-sm text-gray-600 text-center">
            ⚕️ 本推荐仅供参考，不构成医疗建议。如有健康问题，请咨询专业医生。
          </p>
        </div>
      </div>
    </main>
  )
}

export default function SupplementRecommendationPage() {
  return (
    <ProtectedRoute>
      <SupplementRecommendationContent />
    </ProtectedRoute>
  )
}
