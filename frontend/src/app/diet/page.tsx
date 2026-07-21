'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { voiceDraftToDietForm, type VoiceFoodParseResponse } from '@/components/diet/voiceFoodDraft';
import { dietRecordPhotoUrls } from '@/components/diet/dietPhotoAssets';
import { WEB_SESSION_TOKEN } from '@/services/api/client';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

const MEAL_TYPES = [
  { value: 'breakfast', label: '早餐', icon: '🌅', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'lunch', label: '午餐', icon: '☀️', color: 'bg-orange-100 text-orange-800' },
  { value: 'dinner', label: '晚餐', icon: '🌙', color: 'bg-indigo-100 text-indigo-800' },
  { value: 'snack', label: '加餐', icon: '🍎', color: 'bg-green-100 text-green-800' },
];

/**
 * 根据北京时间自动选择默认餐食类型
 */
function getDefaultMealType(): string {
  // 获取北京时间
  const now = new Date();
  const utcTime = now.getTime() + now.getTimezoneOffset() * 60 * 1000;
  const beijingTime = new Date(utcTime + 8 * 60 * 60 * 1000);
  const hour = beijingTime.getHours();

  if (hour >= 6 && hour < 10) {
    return 'breakfast';  // 6:00-10:00 早餐
  } else if (hour >= 10 && hour < 14) {
    return 'lunch';      // 10:00-14:00 午餐
  } else if (hour >= 17 && hour < 21) {
    return 'dinner';     // 17:00-21:00 晚餐
  } else {
    return 'snack';      // 其他时间 加餐
  }
}

interface RecognizedFood {
  name: string;
  quantity?: string;
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  confidence?: number;
}

interface RecognitionResult {
  success: boolean;
  foods: RecognizedFood[];
  meal_description?: string;
  health_tips?: string;
  total_calories?: number;
  total_protein?: number;
  total_carbs?: number;
  total_fat?: number;
  error?: string;
}

function DietContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const { showToast } = useToast();

  useEffect(() => { document.title = '饮食记录 | 健康管理'; }, []);
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [formData, setFormData] = useState({
    meal_type: getDefaultMealType(),
    food_items: '',
    calories: '',
    protein: '',
    carbs: '',
    fat: '',
    notes: '',
  });

  // 图片识别相关状态
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isVoiceParsing, setIsVoiceParsing] = useState(false);
  const [recognitionResult, setRecognitionResult] = useState<RecognitionResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const token = WEB_SESSION_TOKEN;

  // 获取某日饮食记录
  const { data: dailySummary, isLoading } = useQuery({
    queryKey: ['diet-summary', selectedDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/diet/records/me/date/${selectedDate}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 获取统计
  const { data: stats } = useQuery({
    queryKey: ['diet-stats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/diet/records/me/stats?days=7`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  // 创建记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      console.log('[饮食保存] 开始请求:', data);
      const res = await fetch(`${API_BASE}/diet/records`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      console.log('[饮食保存] 响应状态:', res.status);
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        console.error('[饮食保存] 错误详情:', errorData);
        throw new Error(errorData.detail || `保存失败: ${res.status}`);
      }
      const result = await res.json();
      console.log('[饮食保存] 成功:', result);
      return result;
    },
    onSuccess: () => {
      console.log('[饮食保存] 刷新数据');
      queryClient.invalidateQueries({ queryKey: ['diet-summary'] });
      queryClient.invalidateQueries({ queryKey: ['diet-stats'] });
      resetForm();
      showToast('保存成功！', 'success');
    },
    onError: (error: Error) => {
      console.error('[饮食保存] 失败:', error);
      showToast(`保存失败: ${error.message}`, 'error');
    },
  });

  // AI识别并保存
  const recognizeAndSaveMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/diet/recognize-and-save`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `保存失败: ${res.status}`);
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diet-summary'] });
      queryClient.invalidateQueries({ queryKey: ['diet-stats'] });
      resetForm();
      showToast('识别并保存成功！', 'success');
    },
    onError: (error: Error) => {
      showToast(`保存失败: ${error.message}`, 'error');
    },
  });

  // 删除记录
  const deleteMutation = useMutation({
    mutationFn: async (recordId: number) => {
      const res = await fetch(`${API_BASE}/diet/records/${recordId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diet-summary'] });
      queryClient.invalidateQueries({ queryKey: ['diet-stats'] });
    },
  });

  // 重置表单
  const resetForm = () => {
    setShowForm(false);
    setFormData({ meal_type: 'breakfast', food_items: '', calories: '', protein: '', carbs: '', fat: '', notes: '' });
    setImagePreview(null);
    setImageBase64(null);
    setRecognitionResult(null);
  };

  // 处理图片选择
  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 检查文件类型
    if (!file.type.startsWith('image/')) {
      showToast('请选择图片文件', 'warning');
      return;
    }

    // 检查文件大小（限制10MB）
    if (file.size > 10 * 1024 * 1024) {
      showToast('图片大小不能超过10MB', 'warning');
      return;
    }

    // 读取图片并转为Base64
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result as string;
      setImagePreview(result);
      // 提取Base64数据（去掉前缀）
      const base64Data = result.split(',')[1];
      setImageBase64(base64Data);
      setRecognitionResult(null);
    };
    reader.readAsDataURL(file);
  };

  // AI识别图片
  const handleRecognize = async () => {
    if (!imageBase64) {
      showToast('请先选择图片', 'warning');
      return;
    }

    setIsRecognizing(true);
    try {
      const res = await fetch(`${API_BASE}/diet/recognize`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          image_base64: imageBase64,
          image_type: 'jpeg',
        }),
      });

      const result = await res.json();
      setRecognitionResult(result);

      if (result.success && result.foods?.length > 0) {
        // 自动填充表单
        const foodNames = result.foods.map((f: RecognizedFood) =>
          `${f.name}${f.quantity ? ` (${f.quantity})` : ''}`
        ).join(', ');

        setFormData({
          ...formData,
          food_items: foodNames,
          calories: result.total_calories?.toString() || '',
          protein: result.total_protein?.toFixed(1) || '',
          carbs: result.total_carbs?.toFixed(1) || '',
          fat: result.total_fat?.toFixed(1) || '',
          notes: result.health_tips || '',
        });
      }
    } catch (error) {
      console.error('识别失败:', error);
      showToast('识别失败，请重试', 'error');
    } finally {
      setIsRecognizing(false);
    }
  };

  // 一键识别并保存
  const handleRecognizeAndSave = async () => {
    if (!imageBase64) {
      showToast('请先选择图片', 'warning');
      return;
    }

    recognizeAndSaveMutation.mutate({
      image_base64: imageBase64,
      image_type: 'jpeg',
      record_date: selectedDate,
      meal_type: formData.meal_type,
      notes: formData.notes || null,
    });
  };

  // 文字智能分析营养
  const handleTextAnalyze = async () => {
    const text = formData.food_items.trim();
    if (!text) {
      showToast('请先输入食物内容', 'warning');
      return;
    }

    setIsAnalyzing(true);
    try {
      const res = await fetch(`${API_BASE}/diet/estimate-nutrition?food_description=${encodeURIComponent(text)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });

      const result = await res.json();

      if (result.success && result.foods?.length > 0) {
        // 自动填充营养数据
        setFormData(prev => ({
          ...prev,
          calories: result.total_calories?.toString() || prev.calories,
          protein: result.total_protein?.toFixed(1) || prev.protein,
          carbs: result.total_carbs?.toFixed(1) || prev.carbs,
          fat: result.total_fat?.toFixed(1) || prev.fat,
          notes: result.health_tips || prev.notes,
        }));

        // 显示识别结果
        setRecognitionResult(result);
        showToast('分析成功！营养数据已自动填充', 'success');
      } else {
        showToast(result.error || '分析失败，请重试', 'error');
      }
    } catch (error: any) {
      console.error('文字分析失败:', error);
      showToast('分析失败，请重试', 'error');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleVoiceParse = async () => {
    const text = formData.food_items.trim();
    if (!text) {
      showToast('请先输入或粘贴语音转写文本', 'warning');
      return;
    }

    setIsVoiceParsing(true);
    try {
      const res = await fetch(`${API_BASE}/diet/voice/parse`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          raw_text: text,
          meal_type: formData.meal_type,
        }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `语音解析失败: ${res.status}`);
      }
      const draft = await res.json() as VoiceFoodParseResponse;
      const patch = voiceDraftToDietForm(draft);
      setFormData(prev => ({ ...prev, ...patch }));
      setRecognitionResult(null);
      showToast(
        draft.needs_confirmation
          ? (draft.clarifying_question || '语音草稿已填入，请确认份量后保存')
          : '语音草稿已填入，确认后保存',
        draft.needs_confirmation ? 'info' : 'success',
      );
    } catch (error: any) {
      showToast(error.message || '语音草稿解析失败，请稍后重试', 'error');
    } finally {
      setIsVoiceParsing(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.food_items.trim()) {
      showToast('请输入食物内容', 'warning');
      return;
    }

    const submitData = {
      record_date: selectedDate,
      meal_type: formData.meal_type,
      food_items: formData.food_items,
      calories: formData.calories ? parseInt(formData.calories) : null,
      protein: formData.protein ? parseFloat(formData.protein) : null,
      carbs: formData.carbs ? parseFloat(formData.carbs) : null,
      fat: formData.fat ? parseFloat(formData.fat) : null,
      notes: formData.notes || null,
      image_base64: imageBase64 || undefined,
      image_type: imageBase64 ? 'jpeg' : undefined,
    };

    console.log('[饮食保存] 提交数据:', submitData);
    createMutation.mutate(submitData);
  };

  const getMealInfo = (mealType: string) => {
    return MEAL_TYPES.find(m => m.value === mealType) || MEAL_TYPES[0];
  };

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-800 text-lg font-medium">加载中...</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-4">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-orange-500"
            />
            <p className="text-gray-600 text-sm">📸 拍照识别食物，AI自动计算热量</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-red-500 text-white font-semibold rounded-lg hover:from-orange-600 hover:to-red-600 shadow-md transition-all"
          >
            {showForm ? '取消' : '+ 添加饮食'}
          </button>
        </div>

        {/* 今日统计 */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
            <p className="text-sm text-gray-600 mb-1">今日热量</p>
            <p className="text-2xl font-bold text-orange-600">{dailySummary?.total_calories || 0} <span className="text-sm">kcal</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-red-100">
            <p className="text-sm text-gray-600 mb-1">蛋白质</p>
            <p className="text-2xl font-bold text-red-600">{dailySummary?.total_protein?.toFixed(1) || 0} <span className="text-sm">g</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-yellow-100">
            <p className="text-sm text-gray-600 mb-1">碳水</p>
            <p className="text-2xl font-bold text-yellow-600">{dailySummary?.total_carbs?.toFixed(1) || 0} <span className="text-sm">g</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-purple-100">
            <p className="text-sm text-gray-600 mb-1">脂肪</p>
            <p className="text-2xl font-bold text-purple-600">{dailySummary?.total_fat?.toFixed(1) || 0} <span className="text-sm">g</span></p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
            <p className="text-sm text-gray-600 mb-1">餐数</p>
            <p className="text-2xl font-bold text-green-600">{dailySummary?.meals_count || 0} <span className="text-sm">餐</span></p>
          </div>
        </div>

        {/* 7天平均 */}
        {stats && stats.days_recorded > 0 && (
          <div className="bg-gradient-to-r from-orange-50 to-red-50 rounded-xl p-4 mb-6 border border-orange-200">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">📈 7天平均摄入</h4>
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-gray-700">热量: <strong className="text-orange-600">{stats.average_daily_calories?.toFixed(0)}</strong> kcal</span>
              <span className="text-gray-700">蛋白质: <strong className="text-red-600">{stats.average_daily_protein?.toFixed(1)}</strong> g</span>
              <span className="text-gray-700">碳水: <strong className="text-yellow-600">{stats.average_daily_carbs?.toFixed(1)}</strong> g</span>
              <span className="text-gray-700">脂肪: <strong className="text-purple-600">{stats.average_daily_fat?.toFixed(1)}</strong> g</span>
            </div>
          </div>
        )}

        {/* 添加饮食表单 */}
        {showForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-orange-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">🍽️ 添加饮食记录</h3>

            {/* 图片上传区域 */}
            <div className="mb-6 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl border-2 border-dashed border-blue-300">
              <h4 className="text-lg font-semibold text-gray-800 mb-3">📸 AI智能识别</h4>

              <div className="flex flex-col md:flex-row gap-4">
                {/* 图片预览 */}
                <div className="flex-1">
                  {imagePreview ? (
                    <div className="relative">
                      <img
                        src={imagePreview}
                        alt="食物图片"
                        className="w-full h-48 object-cover rounded-lg shadow-md"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setImagePreview(null);
                          setImageBase64(null);
                          setRecognitionResult(null);
                        }}
                        className="absolute top-2 right-2 bg-red-500 text-white w-6 h-6 rounded-full text-sm hover:bg-red-600"
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full h-48 bg-gray-100 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:bg-gray-200 transition-colors"
                    >
                      <span className="text-4xl mb-2">📷</span>
                      <span className="text-gray-600">点击上传食物图片</span>
                      <span className="text-gray-400 text-sm">支持 JPG、PNG 格式</span>
                    </div>
                  )}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleImageSelect}
                    className="hidden"
                  />
                </div>

                {/* 识别结果 */}
                <div className="flex-1">
                  {recognitionResult ? (
                    <div className="h-48 overflow-auto">
                      {recognitionResult.success ? (
                        <div>
                          <p className="text-green-600 font-semibold mb-2">✅ 识别成功！</p>
                          <div className="space-y-1 text-sm">
                            {recognitionResult.foods?.map((food, idx) => (
                              <div key={idx} className="flex justify-between bg-white p-2 rounded">
                                <span className="text-gray-800">{food.name} {food.quantity && `(${food.quantity})`}</span>
                                <span className="text-orange-600">{food.calories} kcal</span>
                              </div>
                            ))}
                          </div>
                          <div className="mt-2 pt-2 border-t text-sm">
                            <p className="text-gray-600">总计: <strong className="text-orange-600">{recognitionResult.total_calories}</strong> kcal</p>
                          </div>
                          {recognitionResult.health_tips && (
                            <p className="mt-2 text-xs text-blue-600 bg-blue-50 p-2 rounded">
                              💡 {recognitionResult.health_tips}
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="text-red-600">
                          <p>❌ 识别失败</p>
                          <p className="text-sm">{recognitionResult.error}</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="h-48 flex items-center justify-center text-gray-400">
                      <p>上传图片后点击"AI识别"</p>
                    </div>
                  )}
                </div>
              </div>

              {/* 操作按钮 */}
              <div className="flex gap-3 mt-4">
                <button
                  type="button"
                  onClick={handleRecognize}
                  disabled={!imageBase64 || isRecognizing}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isRecognizing ? '🔍 识别中...' : '🔍 AI识别'}
                </button>
                <button
                  type="button"
                  onClick={handleRecognizeAndSave}
                  disabled={!imageBase64 || recognizeAndSaveMutation.isPending}
                  className="flex-1 px-4 py-2 bg-gradient-to-r from-green-500 to-teal-500 text-white rounded-lg hover:from-green-600 hover:to-teal-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {recognizeAndSaveMutation.isPending ? '⏳ 保存中...' : '✨ 一键识别并保存'}
                </button>
              </div>
            </div>

            <div className="border-t border-gray-200 pt-4 mt-4">
              <p className="text-sm text-gray-500 mb-4">📝 文字记录（输入食物后点击 ✨ AI分析自动计算营养）：</p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">餐食类型</label>
                  <div className="flex flex-wrap gap-2">
                    {MEAL_TYPES.map(meal => (
                      <button
                        key={meal.value}
                        type="button"
                        onClick={() => setFormData({ ...formData, meal_type: meal.value })}
                        className={`px-4 py-2 rounded-lg font-medium transition-all ${
                          formData.meal_type === meal.value
                            ? 'bg-orange-500 text-white shadow-md'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        {meal.icon} {meal.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">食物列表 *</label>
                  <div className="flex gap-2">
                    <textarea
                      required
                      value={formData.food_items}
                      onChange={(e) => setFormData({ ...formData, food_items: e.target.value })}
                      className="flex-1 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                      rows={2}
                      placeholder="例如: 鸡蛋2个, 全麦面包1片, 牛奶200ml"
                    />
                    <button
                      type="button"
                      onClick={handleTextAnalyze}
                      disabled={isAnalyzing || isVoiceParsing || !formData.food_items.trim()}
                      className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:from-purple-600 hover:to-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-1 self-start"
                      title="AI智能分析营养成分"
                    >
                      {isAnalyzing ? '⏳' : '✨'}
                      <span className="text-sm">{isAnalyzing ? '分析中' : 'AI分析'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleVoiceParse}
                      disabled={isVoiceParsing || isAnalyzing || !formData.food_items.trim()}
                      className="px-4 py-2 bg-gradient-to-r from-sky-500 to-teal-500 text-white rounded-lg hover:from-sky-600 hover:to-teal-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-1 self-start"
                      title="解析语音转写饮食草稿"
                    >
                      <span>{isVoiceParsing ? '⏳' : '🎙️'}</span>
                      <span className="text-sm">{isVoiceParsing ? '解析中' : '语音草稿'}</span>
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">💡 输入食物后可做营养分析；粘贴 Apple Watch/Siri 转写文本可先生成语音草稿再确认保存</p>

                  {/* 文字分析结果显示 */}
                  {recognitionResult && recognitionResult.success && !imageBase64 && (
                    <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
                      <p className="text-green-700 font-semibold mb-2">✅ AI分析结果</p>
                      <div className="space-y-1 text-sm">
                        {recognitionResult.foods?.map((food, idx) => (
                          <div key={idx} className="flex justify-between">
                            <span className="text-gray-700">{food.name} {food.quantity && `(${food.quantity})`}</span>
                            <span className="text-orange-600 font-medium">{food.calories} kcal</span>
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 pt-2 border-t border-green-200 text-sm">
                        <p className="text-gray-700">
                          总计: <strong className="text-orange-600">{recognitionResult.total_calories}</strong> kcal |
                          蛋白质: <strong className="text-red-600">{recognitionResult.total_protein?.toFixed(1)}</strong>g |
                          碳水: <strong className="text-yellow-600">{recognitionResult.total_carbs?.toFixed(1)}</strong>g |
                          脂肪: <strong className="text-purple-600">{recognitionResult.total_fat?.toFixed(1)}</strong>g
                        </p>
                      </div>
                      {recognitionResult.health_tips && (
                        <p className="mt-2 text-xs text-blue-600 bg-blue-50 p-2 rounded">
                          💡 {recognitionResult.health_tips}
                        </p>
                      )}
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-800 mb-2">热量 (kcal)</label>
                    <input
                      type="number"
                      value={formData.calories}
                      onChange={(e) => setFormData({ ...formData, calories: e.target.value })}
                      className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                      placeholder="300"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-800 mb-2">蛋白质 (g)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.protein}
                      onChange={(e) => setFormData({ ...formData, protein: e.target.value })}
                      className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                      placeholder="20"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-800 mb-2">碳水 (g)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.carbs}
                      onChange={(e) => setFormData({ ...formData, carbs: e.target.value })}
                      className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                      placeholder="30"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-800 mb-2">脂肪 (g)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.fat}
                      onChange={(e) => setFormData({ ...formData, fat: e.target.value })}
                      className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                      placeholder="10"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
                  <input
                    type="text"
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-gray-900"
                    placeholder="可选备注..."
                  />
                </div>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="w-full bg-gradient-to-r from-orange-500 to-red-500 text-white py-3 rounded-lg font-semibold hover:from-orange-600 hover:to-red-600 disabled:opacity-50 shadow-md transition-all"
                >
                  {createMutation.isPending ? '保存中...' : '✓ 保存记录'}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* 今日饮食记录 */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-200">
          <h3 className="text-xl font-bold text-gray-900 mb-4">📋 {selectedDate} 饮食记录</h3>
          {!dailySummary?.meals?.length ? (
            <div className="text-center py-10 text-gray-500">
              <p className="text-4xl mb-2">🍽️</p>
              <p>今天还没有饮食记录</p>
              <p className="text-sm mt-2">点击"添加饮食"开始记录</p>
            </div>
          ) : (
            <div className="space-y-4">
              {dailySummary.meals.map((meal: any) => {
                const mealInfo = getMealInfo(meal.meal_type);
                const photoUrls = dietRecordPhotoUrls(meal);
                return (
                  <div key={meal.id} className="flex gap-4 p-4 bg-gray-50 rounded-lg border border-gray-100">
                    {/* 食物图片 */}
                    {photoUrls.length > 0 && (
                      <div className="grid w-32 shrink-0 grid-cols-2 gap-1 self-start" aria-label={`${meal.food_items} 照片`}>
                        {photoUrls.slice(0, 4).map((photoUrl, index) => (
                          <button
                            key={photoUrl}
                            type="button"
                            onClick={() => window.open(photoUrl, '_blank', 'noopener,noreferrer')}
                            className="relative aspect-square overflow-hidden rounded-md border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                            title={`查看第 ${index + 1} 张餐食照片`}
                            aria-label={`查看第 ${index + 1} 张餐食照片`}
                          >
                            <img
                              src={photoUrl}
                              alt={`${meal.food_items} · 照片 ${index + 1}`}
                              className="h-full w-full object-cover transition-transform hover:scale-105"
                            />
                            {index === 3 && photoUrls.length > 4 && (
                              <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-sm font-semibold text-white">
                                +{photoUrls.length - 4}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* 食物信息 */}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${mealInfo.color}`}>
                          {mealInfo.icon} {mealInfo.label}
                        </span>
                        {meal.calories && (
                          <span className="text-sm text-orange-600 font-medium">{meal.calories} kcal</span>
                        )}
                        {meal.ai_recognized === 1 && (
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-600 text-xs rounded-full">✨ AI识别</span>
                        )}
                      </div>
                      <p className="text-gray-900 font-medium">{meal.food_items}</p>
                      <div className="flex gap-4 mt-2 text-xs text-gray-500">
                        {meal.protein && <span>蛋白质: {meal.protein}g</span>}
                        {meal.carbs && <span>碳水: {meal.carbs}g</span>}
                        {meal.fat && <span>脂肪: {meal.fat}g</span>}
                      </div>
                      {meal.health_tips && (
                        <p className="text-xs text-blue-600 mt-2 bg-blue-50 p-2 rounded">💡 {meal.health_tips}</p>
                      )}
                      {meal.notes && !meal.health_tips && (
                        <p className="text-sm text-gray-500 mt-1">{meal.notes}</p>
                      )}
                    </div>

                    {/* 删除按钮 */}
                    <button
                      onClick={() => deleteMutation.mutate(meal.id)}
                      className="text-red-500 hover:text-red-700 text-sm self-start"
                    >
                      删除
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function DietPage() {
  return (
    <ProtectedRoute>
      <DietContent />
    </ProtectedRoute>
  );
}
