import { useState, useEffect } from 'react';
import Taro from '@tarojs/taro';
import { View, Text, Image, ScrollView, Input, Picker } from '@tarojs/components';
import { request } from '../../services/request';
import { API_ENDPOINTS } from '@health-shared/api';
import './index.scss';

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

interface DietRecord {
  id: number;
  meal_type: string;
  food_items: string;
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  ai_recognized?: number;
  health_tips?: string;
  notes?: string;
  image_url?: string;  // 食物图片URL
}

interface DailySummary {
  record_date: string;
  total_calories: number;
  total_protein: number;
  total_carbs: number;
  total_fat: number;
  meals_count: number;
  meals: DietRecord[];
}

const MEAL_TYPES = [
  { value: 'breakfast', label: '早餐', icon: '🌅' },
  { value: 'lunch', label: '午餐', icon: '☀️' },
  { value: 'dinner', label: '晚餐', icon: '🌙' },
  { value: 'snack', label: '加餐', icon: '🍎' },
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

export default function DietPage() {
  const [selectedDate, setSelectedDate] = useState(formatDate(new Date()));
  const [mealType, setMealType] = useState(getDefaultMealType());
  const [dailySummary, setDailySummary] = useState<DailySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [recognitionResult, setRecognitionResult] = useState<RecognitionResult | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);  // 文字分析loading
  const [isSaving, setIsSaving] = useState(false);  // 保存loading，防止重复提交
  const [formData, setFormData] = useState({
    food_items: '',
    calories: '',
    protein: '',
    carbs: '',
    fat: '',
    notes: '',
  });

  function formatDate(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  // 加载当日饮食数据
  const loadDailySummary = async () => {
    setLoading(true);
    try {
      const data = await request<DailySummary>({
        url: `/diet/records/me/date/${selectedDate}`,
        method: 'GET',
      });
      setDailySummary(data);
    } catch (error) {
      console.error('加载饮食数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDailySummary();
  }, [selectedDate]);

  // 拍照或选择图片
  const handleChooseImage = () => {
    Taro.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempFilePath = res.tempFilePaths[0];
        setImagePreview(tempFilePath);
        setRecognitionResult(null);
      },
      fail: (err) => {
        console.error('选择图片失败:', err);
      },
    });
  };

  // AI识别食物
  const handleRecognize = async () => {
    if (!imagePreview) {
      Taro.showToast({ title: '请先选择图片', icon: 'none' });
      return;
    }

    setIsRecognizing(true);
    try {
      // 读取图片为Base64
      const fs = Taro.getFileSystemManager();
      const base64 = fs.readFileSync(imagePreview, 'base64') as string;

      // 调用AI识别API
      const result = await request<RecognitionResult>({
        url: '/diet/recognize',
        method: 'POST',
        data: {
          image_base64: base64,
          image_type: 'jpeg',
        },
      });

      setRecognitionResult(result);

      if (result.success && result.foods?.length > 0) {
        // 自动填充表单
        const foodNames = result.foods.map(f => 
          `${f.name}${f.quantity ? ` (${f.quantity})` : ''}`
        ).join(', ');

        setFormData({
          food_items: foodNames,
          calories: result.total_calories?.toString() || '',
          protein: result.total_protein?.toFixed(1) || '',
          carbs: result.total_carbs?.toFixed(1) || '',
          fat: result.total_fat?.toFixed(1) || '',
          notes: result.health_tips || '',
        });

        Taro.showToast({ title: '识别成功！', icon: 'success' });
      } else {
        Taro.showToast({ title: result.error || '识别失败', icon: 'none' });
      }
    } catch (error) {
      console.error('智能识别失败:', error);
      Taro.showToast({ title: '识别失败，请重试', icon: 'none' });
    } finally {
      setIsRecognizing(false);
    }
  };

  // 一键识别并保存
  const handleRecognizeAndSave = async () => {
    if (!imagePreview) {
      Taro.showToast({ title: '请先选择图片', icon: 'none' });
      return;
    }

    if (isSaving) {
      return; // 防止重复提交
    }

    setIsSaving(true);
    setIsRecognizing(true);
    try {
      const fs = Taro.getFileSystemManager();
      const base64 = fs.readFileSync(imagePreview, 'base64') as string;

      await request({
        url: '/diet/recognize-and-save',
        method: 'POST',
        data: {
          image_base64: base64,
          image_type: 'jpeg',
          record_date: selectedDate,
          meal_type: mealType,
          notes: formData.notes || null,
        },
      });

      Taro.showToast({ title: '保存成功！', icon: 'success' });
      resetForm();
      loadDailySummary();
    } catch (error: any) {
      console.error('保存失败:', error);
      Taro.showToast({ title: error.message || '保存失败', icon: 'none' });
    } finally {
      setIsRecognizing(false);
      setIsSaving(false);
    }
  };

  // 文字智能分析营养
  const handleTextAnalyze = async () => {
    const text = formData.food_items.trim();
    if (!text) {
      Taro.showToast({ title: '请先输入食物内容', icon: 'none' });
      return;
    }

    setIsAnalyzing(true);
    try {
      const result = await request<RecognitionResult>({
        url: `/diet/estimate-nutrition?food_description=${encodeURIComponent(text)}`,
        method: 'POST',
      });

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
        Taro.showToast({ title: '分析成功！', icon: 'success' });
      } else {
        Taro.showToast({ title: result.error || '分析失败', icon: 'none' });
      }
    } catch (error: any) {
      console.error('文字分析失败:', error);
      Taro.showToast({ title: '分析失败，请重试', icon: 'none' });
    } finally {
      setIsAnalyzing(false);
    }
  };

  // 手动保存
  const handleManualSave = async () => {
    if (!formData.food_items.trim()) {
      Taro.showToast({ title: '请输入食物内容', icon: 'none' });
      return;
    }

    if (isSaving) {
      return; // 防止重复提交
    }

    setIsSaving(true);
    try {
      // 如果有图片，读取为Base64
      let imageBase64: string | null = null;
      if (imagePreview) {
        try {
          const fs = Taro.getFileSystemManager();
          imageBase64 = fs.readFileSync(imagePreview, 'base64') as string;
        } catch (e) {
          console.warn('读取图片失败:', e);
        }
      }

      console.log('[饮食记录] 准备保存:', {
        record_date: selectedDate,
        meal_type: mealType,
        food_items: formData.food_items.substring(0, 50),
        has_image: !!imageBase64,
      });

      await request({
        url: '/diet/records',
        method: 'POST',
        data: {
          record_date: selectedDate,
          meal_type: mealType,
          food_items: formData.food_items,
          calories: formData.calories ? parseFloat(formData.calories) : null,
          protein: formData.protein ? parseFloat(formData.protein) : null,
          carbs: formData.carbs ? parseFloat(formData.carbs) : null,
          fat: formData.fat ? parseFloat(formData.fat) : null,
          notes: formData.notes || null,
          image_base64: imageBase64,
          image_type: imageBase64 ? 'jpeg' : null,
        },
      });

      console.log('[饮食记录] 保存成功');
      Taro.showToast({ title: '保存成功！', icon: 'success' });
      resetForm();
      loadDailySummary();
    } catch (error: any) {
      console.error('[饮食记录] 保存失败:', error);
      const errorMsg = error?.message || error?.errMsg || '保存失败';
      Taro.showToast({ title: errorMsg.substring(0, 30), icon: 'none', duration: 3000 });
    } finally {
      setIsSaving(false);
    }
  };

  // 删除记录
  const handleDelete = async (recordId: number) => {
    Taro.showModal({
      title: '确认删除',
      content: '确定要删除这条记录吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await request({
              url: `/diet/records/${recordId}`,
              method: 'DELETE',
            });
            Taro.showToast({ title: '删除成功', icon: 'success' });
            loadDailySummary();
          } catch (error) {
            Taro.showToast({ title: '删除失败', icon: 'none' });
          }
        }
      },
    });
  };

  const resetForm = () => {
    setShowForm(false);
    setImagePreview(null);
    setRecognitionResult(null);
    setFormData({
      food_items: '',
      calories: '',
      protein: '',
      carbs: '',
      fat: '',
      notes: '',
    });
  };

  const getMealInfo = (type: string) => {
    return MEAL_TYPES.find(m => m.value === type) || MEAL_TYPES[0];
  };

  return (
    <View className="diet-page">
      {/* 头部 */}
      <View className="header">
        <View className="header-title">
          <Text className="title-icon">🍽️</Text>
          <Text className="title-text">饮食记录</Text>
        </View>
        <Picker
          mode="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.detail.value)}
        >
          <View className="date-picker">{selectedDate}</View>
        </Picker>
      </View>

      <ScrollView scrollY className="content-scroll">
        {/* 今日统计 */}
        <View className="stats-section">
          <View className="stat-card orange">
            <Text className="stat-value">{dailySummary?.total_calories || 0}</Text>
            <Text className="stat-label">热量(kcal)</Text>
          </View>
          <View className="stat-card red">
            <Text className="stat-value">{dailySummary?.total_protein?.toFixed(1) || 0}</Text>
            <Text className="stat-label">蛋白质(g)</Text>
          </View>
          <View className="stat-card yellow">
            <Text className="stat-value">{dailySummary?.total_carbs?.toFixed(1) || 0}</Text>
            <Text className="stat-label">碳水(g)</Text>
          </View>
          <View className="stat-card purple">
            <Text className="stat-value">{dailySummary?.total_fat?.toFixed(1) || 0}</Text>
            <Text className="stat-label">脂肪(g)</Text>
          </View>
        </View>

        {/* 添加按钮 */}
        {!showForm && (
          <View className="add-section">
            <View className="add-btn" onClick={() => setShowForm(true)}>
              <Text className="add-icon">📸</Text>
              <Text className="add-text">拍照记录饮食</Text>
            </View>
          </View>
        )}

        {/* 添加表单 */}
        {showForm && (
          <View className="form-section">
            <View className="form-header">
              <Text className="form-title">📸 智能识别</Text>
              <Text className="form-close" onClick={resetForm}>✕</Text>
            </View>

            {/* 餐食类型选择 */}
            <View className="meal-types">
              {MEAL_TYPES.map(meal => (
                <View
                  key={meal.value}
                  className={`meal-type-btn ${mealType === meal.value ? 'active' : ''}`}
                  onClick={() => setMealType(meal.value)}
                >
                  <Text>{meal.icon} {meal.label}</Text>
                </View>
              ))}
            </View>

            {/* 方式一：图片识别（可选） */}
            <View className="section-block">
              <Text className="block-title">📷 拍照识别（可选）</Text>
              <View className="image-section">
                {imagePreview ? (
                  <View className="image-preview-wrap">
                    <Image
                      src={imagePreview}
                      mode="aspectFill"
                      className="image-preview"
                    />
                    <View className="image-remove" onClick={() => {
                      setImagePreview(null);
                      setRecognitionResult(null);
                    }}>×</View>
                  </View>
                ) : (
                  <View className="image-placeholder" onClick={handleChooseImage}>
                    <Text className="placeholder-icon">📷</Text>
                    <Text className="placeholder-text">点击拍照或选择图片</Text>
                  </View>
                )}
              </View>

              {/* 图片操作按钮 */}
              {imagePreview && (
                <View className="action-buttons">
                  <View
                    className={`action-btn recognize ${isRecognizing || isSaving ? 'disabled' : ''}`}
                    onClick={isRecognizing || isSaving ? undefined : handleRecognize}
                  >
                    <Text>{isRecognizing ? '🔍 识别中...' : '🔍 智能识别'}</Text>
                  </View>
                  <View
                    className={`action-btn save ${isSaving ? 'disabled' : ''}`}
                    onClick={isSaving ? undefined : handleRecognizeAndSave}
                  >
                    <Text>{isSaving ? '⏳ 保存中...' : '✨ 一键保存'}</Text>
                  </View>
                </View>
              )}
            </View>

            {/* 识别/分析结果 */}
            {recognitionResult && recognitionResult.success && (
              <View className="recognition-result">
                <Text className="result-title">✅ 智能分析结果</Text>
                {recognitionResult.foods?.map((food, idx) => (
                  <View key={idx} className="food-item">
                    <Text className="food-name">{food.name} {food.quantity && `(${food.quantity})`}</Text>
                    <Text className="food-calories">{food.calories} kcal</Text>
                  </View>
                ))}
                <View className="result-total">
                  <Text>总计: {recognitionResult.total_calories} kcal</Text>
                </View>
                {recognitionResult.health_tips && (
                  <View className="health-tips">
                    <Text>💡 {recognitionResult.health_tips}</Text>
                  </View>
                )}
              </View>
            )}

            {/* 方式二：文字输入 */}
            <View className="manual-input">
              <Text className="manual-title">📝 文字记录（无需图片）：</Text>
              <View className="input-row-with-btn">
                <Input
                  className="input-field flex-1"
                  placeholder="输入食物，如：一个鸡蛋，一碗米饭"
                  value={formData.food_items}
                  onInput={(e) => setFormData({ ...formData, food_items: e.detail.value })}
                />
                <View 
                  className={`analyze-btn ${isAnalyzing || !formData.food_items.trim() ? 'disabled' : ''}`}
                  onClick={isAnalyzing || !formData.food_items.trim() ? undefined : handleTextAnalyze}
                >
                  <Text>{isAnalyzing ? '⏳' : '🤖'}</Text>
                </View>
              </View>
              <Text className="input-hint">💡 输入食物后点击🤖自动分析营养成分</Text>
              <View className="input-grid">
                <View className="input-item">
                  <Text className="input-label">热量</Text>
                  <Input
                    type="number"
                    className="input-field small"
                    placeholder="kcal"
                    value={formData.calories}
                    onInput={(e) => setFormData({ ...formData, calories: e.detail.value })}
                  />
                </View>
                <View className="input-item">
                  <Text className="input-label">蛋白质</Text>
                  <Input
                    type="digit"
                    className="input-field small"
                    placeholder="g"
                    value={formData.protein}
                    onInput={(e) => setFormData({ ...formData, protein: e.detail.value })}
                  />
                </View>
                <View className="input-item">
                  <Text className="input-label">碳水</Text>
                  <Input
                    type="digit"
                    className="input-field small"
                    placeholder="g"
                    value={formData.carbs}
                    onInput={(e) => setFormData({ ...formData, carbs: e.detail.value })}
                  />
                </View>
                <View className="input-item">
                  <Text className="input-label">脂肪</Text>
                  <Input
                    type="digit"
                    className="input-field small"
                    placeholder="g"
                    value={formData.fat}
                    onInput={(e) => setFormData({ ...formData, fat: e.detail.value })}
                  />
                </View>
              </View>
              <View 
                className={`save-manual-btn ${isSaving ? 'disabled' : ''}`} 
                onClick={isSaving ? undefined : handleManualSave}
              >
                <Text>{isSaving ? '⏳ 保存中...' : '保存记录'}</Text>
              </View>
            </View>
          </View>
        )}

        {/* 今日记录列表 */}
        <View className="records-section">
          <Text className="section-title">📋 今日饮食</Text>
          {loading ? (
            <View className="loading">
              <Text>加载中...</Text>
            </View>
          ) : !dailySummary?.meals?.length ? (
            <View className="empty">
              <Text className="empty-icon">🍽️</Text>
              <Text className="empty-text">今天还没有饮食记录</Text>
            </View>
          ) : (
            dailySummary.meals.map(meal => {
              const mealInfo = getMealInfo(meal.meal_type);
              // 构建完整的图片URL
              const fullImageUrl = meal.image_url 
                ? (meal.image_url.startsWith('http') 
                    ? meal.image_url 
                    : `https://health.westwetlandtech.com${meal.image_url}`)
                : null;
              return (
                <View key={meal.id} className="record-card">
                  <View className="record-header">
                    <View className="meal-tag">
                      <Text>{mealInfo.icon} {mealInfo.label}</Text>
                    </View>
                    {meal.calories && (
                      <Text className="record-calories">{meal.calories} kcal</Text>
                    )}
                    {meal.ai_recognized === 1 && (
                      <Text className="ai-tag">🤖 智能</Text>
                    )}
                  </View>
                  {/* 显示食物图片 */}
                  {fullImageUrl && (
                    <View className="record-image-wrap">
                      <Image 
                        src={fullImageUrl} 
                        mode="aspectFill" 
                        className="record-image"
                        onClick={() => {
                          Taro.previewImage({
                            current: fullImageUrl,
                            urls: [fullImageUrl]
                          });
                        }}
                      />
                    </View>
                  )}
                  <Text className="record-foods">{meal.food_items}</Text>
                  <View className="record-nutrition">
                    {meal.protein && <Text>蛋白质: {meal.protein}g</Text>}
                    {meal.carbs && <Text>碳水: {meal.carbs}g</Text>}
                    {meal.fat && <Text>脂肪: {meal.fat}g</Text>}
                  </View>
                  {meal.health_tips && (
                    <View className="record-tips">
                      <Text>💡 {meal.health_tips}</Text>
                    </View>
                  )}
                  <View className="record-delete" onClick={() => handleDelete(meal.id)}>
                    <Text>删除</Text>
                  </View>
                </View>
              );
            })
          )}
        </View>
      </ScrollView>
    </View>
  );
}
