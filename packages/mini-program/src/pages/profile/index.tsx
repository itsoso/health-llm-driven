import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Input, Picker } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { request } from '../../services/request';
import './index.scss';

interface UserProfile {
  id: number;
  user_id: number;
  gender: string | null;
  birth_date: string | null;
  height_cm: number | null;
  blood_type: string | null;
  current_weight_kg: number | null;
  target_weight_kg: number | null;
  body_fat_percentage: number | null;
  muscle_mass_kg: number | null;
  target_steps: number;
  target_sleep_hours: number;
  target_water_ml: number;
  target_calories_burn: number | null;
  target_exercise_minutes: number;
  chronic_conditions: string[];
  allergies: string[];
  family_history: string[];
  surgeries: any[];
  current_medications: any[];
  exercise_frequency: string | null;
  diet_preference: string | null;
  smoking_status: string | null;
  alcohol_consumption: string | null;
  usual_sleep_time: string | null;
  usual_wake_time: string | null;
  sleep_environment: Record<string, any>;
  work_type: string | null;
  work_hours_per_day: number | null;
  sitting_hours_per_day: number | null;
  city: string | null;
  timezone: string;
  devices: string[];
  age: number | null;
  bmi: number | null;
  bmi_category: string | null;
  created_at: string;
  updated_at: string | null;
}

const genderOptions = ['未设置', '男', '女'];
const genderValues = [null, 'male', 'female'];

const bloodTypeOptions = ['未设置', 'A型', 'B型', 'AB型', 'O型'];
const bloodTypeValues = [null, 'A', 'B', 'AB', 'O'];

const exerciseOptions = ['未设置', '从不运动', '偶尔运动', '每周1-2次', '每周3-5次', '每天运动'];
const exerciseValues = [null, 'never', 'occasionally', 'weekly', 'regularly', 'daily'];

const dietOptions = ['未设置', '正常饮食', '素食', '低碳水', '生酮饮食'];
const dietValues = [null, 'normal', 'vegetarian', 'low_carb', 'keto'];

const timezoneOptions = [
  '中国标准时间 (UTC+8)',
  '香港时间 (UTC+8)',
  '台北时间 (UTC+8)',
  '新加坡时间 (UTC+8)',
  '东京时间 (UTC+9)',
  '首尔时间 (UTC+9)',
  '美国东部时间 (UTC-5/-4)',
  '美国太平洋时间 (UTC-8/-7)',
  '伦敦时间 (UTC+0/+1)',
  '巴黎时间 (UTC+1/+2)',
  '悉尼时间 (UTC+10/+11)',
  '协调世界时 (UTC)',
];
const timezoneValues = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Asia/Seoul',
  'America/New_York',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Australia/Sydney',
  'UTC',
];

const commonConditions = ['鼻炎', '咽炎', '高血压', '糖尿病', '胃病', '失眠'];
const commonAllergies = ['花粉', '海鲜', '牛奶', '花生', '青霉素', '灰尘'];

export default function ProfilePage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [activeTab, setActiveTab] = useState<'basic' | 'health' | 'goals'>('basic');

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      setLoading(true);
      const res = await request<UserProfile>({
        url: '/profile/me',
        method: 'GET',
      });
      console.log('[Profile] 原始响应:', JSON.stringify(res));
      console.log('[Profile] height_cm:', res?.height_cm, '类型:', typeof res?.height_cm);
      console.log('[Profile] current_weight_kg:', res?.current_weight_kg, '类型:', typeof res?.current_weight_kg);
      // request 直接返回响应数据，不需要再取 .data
      setProfile(res as UserProfile);
    } catch (error) {
      console.error('加载失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const saveProfile = async () => {
    if (!profile) return;

    try {
      setSaving(true);
      await request({
        url: '/profile/me',
        method: 'PUT',
        data: profile,
      });
      Taro.showToast({ title: '保存成功', icon: 'success' });
    } catch (error) {
      console.error('保存失败:', error);
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSaving(false);
    }
  };

  const updateField = (field: keyof UserProfile, value: any) => {
    console.log('[Profile] 更新字段:', field, '=', value, '类型:', typeof value);
    if (profile) {
      const newProfile = { ...profile, [field]: value };
      console.log('[Profile] 更新后的profile:', JSON.stringify(newProfile));
      setProfile(newProfile);
    }
  };

  const toggleCondition = (condition: string) => {
    if (!profile) return;
    const conditions = profile.chronic_conditions || [];
    if (conditions.includes(condition)) {
      updateField('chronic_conditions', conditions.filter(c => c !== condition));
    } else {
      updateField('chronic_conditions', [...conditions, condition]);
    }
  };

  const toggleAllergy = (allergy: string) => {
    if (!profile) return;
    const allergies = profile.allergies || [];
    if (allergies.includes(allergy)) {
      updateField('allergies', allergies.filter(a => a !== allergy));
    } else {
      updateField('allergies', [...allergies, allergy]);
    }
  };

  if (loading) {
    return (
      <View className="profile-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  if (!profile) {
    return (
      <View className="profile-page error">
        <Text className="error-text">加载失败</Text>
      </View>
    );
  }

  return (
    <View className="profile-page">
      {/* BMI 卡片 */}
      {profile.bmi && (
        <View className="bmi-card">
          <View className="bmi-left">
            <Text className="bmi-label">BMI</Text>
            <Text className="bmi-value">{profile.bmi}</Text>
            <Text className={`bmi-category ${
              profile.bmi_category === '正常' ? 'normal' :
              profile.bmi_category === '偏瘦' ? 'thin' :
              profile.bmi_category === '超重' ? 'overweight' : 'obese'
            }`}>
              {profile.bmi_category}
            </Text>
          </View>
          {profile.age && (
            <View className="bmi-right">
              <Text className="age-label">年龄</Text>
              <Text className="age-value">{profile.age}岁</Text>
            </View>
          )}
        </View>
      )}

      {/* Tab 导航 */}
      <View className="tab-nav">
        <View
          className={`tab-item ${activeTab === 'basic' ? 'active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          👤 基本信息
        </View>
        <View
          className={`tab-item ${activeTab === 'health' ? 'active' : ''}`}
          onClick={() => setActiveTab('health')}
        >
          🏥 健康状况
        </View>
        <View
          className={`tab-item ${activeTab === 'goals' ? 'active' : ''}`}
          onClick={() => setActiveTab('goals')}
        >
          🎯 目标设置
        </View>
      </View>

      <ScrollView scrollY className="content-scroll">
        {/* 基本信息 */}
        {activeTab === 'basic' && (
          <View className="tab-content">
            <View className="form-item">
              <Text className="form-label">性别</Text>
              <Picker
                mode="selector"
                range={genderOptions}
                value={genderValues.indexOf(profile.gender) || 0}
                onChange={e => updateField('gender', genderValues[Number(e.detail.value)])}
              >
                <View className="picker-value">
                  {genderOptions[genderValues.indexOf(profile.gender) || 0]} ▼
                </View>
              </Picker>
            </View>

            <View className="form-item">
              <Text className="form-label">身高 (cm)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '输入身高 (cm)',
                    editable: true,
                    placeholderText: '50-300',
                    content: profile.height_cm ? String(profile.height_cm) : '',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (numValue >= 50 && numValue <= 300) {
                          updateField('height_cm', numValue);
                        } else if (numValue > 300) {
                          Taro.showToast({ title: '身高不能超过300cm', icon: 'none' });
                          updateField('height_cm', 300);
                        } else if (numValue < 50) {
                          Taro.showToast({ title: '身高不能小于50cm', icon: 'none' });
                          updateField('height_cm', 50);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      } else if (res.confirm && !res.content) {
                        updateField('height_cm', null);
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.height_cm ? `${profile.height_cm} cm` : '点击输入身高'}
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
            </View>

            <View className="form-item">
              <Text className="form-label">当前体重 (kg)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '输入体重 (kg)',
                    editable: true,
                    placeholderText: '20-300',
                    content: profile.current_weight_kg ? String(profile.current_weight_kg) : '',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (numValue >= 20 && numValue <= 300) {
                          updateField('current_weight_kg', numValue);
                        } else if (numValue > 300) {
                          Taro.showToast({ title: '体重不能超过300kg', icon: 'none' });
                          updateField('current_weight_kg', 300);
                        } else if (numValue < 20) {
                          Taro.showToast({ title: '体重不能小于20kg', icon: 'none' });
                          updateField('current_weight_kg', 20);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      } else if (res.confirm && !res.content) {
                        updateField('current_weight_kg', null);
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.current_weight_kg ? `${profile.current_weight_kg} kg` : '点击输入体重'}
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
            </View>

            <View className="form-item">
              <Text className="form-label">血型</Text>
              <Picker
                mode="selector"
                range={bloodTypeOptions}
                value={bloodTypeValues.indexOf(profile.blood_type) || 0}
                onChange={e => updateField('blood_type', bloodTypeValues[Number(e.detail.value)])}
              >
                <View className="picker-value">
                  {bloodTypeOptions[bloodTypeValues.indexOf(profile.blood_type) || 0]} ▼
                </View>
              </Picker>
            </View>

            <View className="form-item">
              <Text className="form-label">所在城市</Text>
              <Input
                type="text"
                value={profile.city || ''}
                onInput={e => updateField('city', e.detail.value || null)}
                placeholder="输入城市"
                placeholderStyle="color: rgba(255, 255, 255, 0.4)"
                className="form-input"
              />
            </View>

            <View className="form-item">
              <Text className="form-label">时区</Text>
              <Picker
                mode="selector"
                range={timezoneOptions}
                value={timezoneValues.indexOf(profile.timezone) >= 0 ? timezoneValues.indexOf(profile.timezone) : 0}
                onChange={e => updateField('timezone', timezoneValues[Number(e.detail.value)])}
              >
                <View className="picker-value">
                  {timezoneOptions[timezoneValues.indexOf(profile.timezone) >= 0 ? timezoneValues.indexOf(profile.timezone) : 0]} ▼
                </View>
              </Picker>
              <Text className="form-hint">系统将根据此时区计算周起始日等</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">运动频率</Text>
              <Picker
                mode="selector"
                range={exerciseOptions}
                value={exerciseValues.indexOf(profile.exercise_frequency) || 0}
                onChange={e => updateField('exercise_frequency', exerciseValues[Number(e.detail.value)])}
              >
                <View className="picker-value">
                  {exerciseOptions[exerciseValues.indexOf(profile.exercise_frequency) || 0]} ▼
                </View>
              </Picker>
            </View>

            <View className="form-item">
              <Text className="form-label">饮食偏好</Text>
              <Picker
                mode="selector"
                range={dietOptions}
                value={dietValues.indexOf(profile.diet_preference) || 0}
                onChange={e => updateField('diet_preference', dietValues[Number(e.detail.value)])}
              >
                <View className="picker-value">
                  {dietOptions[dietValues.indexOf(profile.diet_preference) || 0]} ▼
                </View>
              </Picker>
            </View>
          </View>
        )}

        {/* 健康状况 */}
        {activeTab === 'health' && (
          <View className="tab-content">
            <View className="section">
              <Text className="section-title">慢性病史</Text>
              <View className="tag-list">
                {commonConditions.map(condition => (
                  <View
                    key={condition}
                    className={`tag ${(profile.chronic_conditions || []).includes(condition) ? 'active' : ''}`}
                    onClick={() => toggleCondition(condition)}
                  >
                    {condition}
                  </View>
                ))}
              </View>
              {(profile.chronic_conditions || []).length > 0 && (
                <View className="selected-tags">
                  已选: {profile.chronic_conditions?.join('、')}
                </View>
              )}
            </View>

            <View className="section">
              <Text className="section-title">过敏源</Text>
              <View className="tag-list">
                {commonAllergies.map(allergy => (
                  <View
                    key={allergy}
                    className={`tag orange ${(profile.allergies || []).includes(allergy) ? 'active' : ''}`}
                    onClick={() => toggleAllergy(allergy)}
                  >
                    {allergy}
                  </View>
                ))}
              </View>
              {(profile.allergies || []).length > 0 && (
                <View className="selected-tags orange">
                  已选: {profile.allergies?.join('、')}
                </View>
              )}
            </View>
          </View>
        )}

        {/* 目标设置 */}
        {activeTab === 'goals' && (
          <View className="tab-content">
            <View className="form-item">
              <Text className="form-label">目标步数 (步/天)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '目标步数 (步/天)',
                    editable: true,
                    placeholderText: '8000',
                    content: profile.target_steps ? String(profile.target_steps) : '8000',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (!isNaN(numValue) && numValue > 0) {
                          updateField('target_steps', numValue);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.target_steps || 8000} 步
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
              <Text className="form-hint">推荐: 8000-10000步</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标睡眠 (小时/天)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '目标睡眠 (小时/天)',
                    editable: true,
                    placeholderText: '7.5',
                    content: profile.target_sleep_hours ? String(profile.target_sleep_hours) : '7.5',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (!isNaN(numValue) && numValue > 0) {
                          updateField('target_sleep_hours', numValue);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.target_sleep_hours || 7.5} 小时
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
              <Text className="form-hint">推荐: 7-9小时</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标饮水 (ml/天)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '目标饮水 (ml/天)',
                    editable: true,
                    placeholderText: '2000',
                    content: profile.target_water_ml ? String(profile.target_water_ml) : '2000',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (!isNaN(numValue) && numValue > 0) {
                          updateField('target_water_ml', numValue);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.target_water_ml || 2000} ml
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
              <Text className="form-hint">推荐: 1500-2500ml</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标运动 (分钟/天)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '目标运动 (分钟/天)',
                    editable: true,
                    placeholderText: '30',
                    content: profile.target_exercise_minutes ? String(profile.target_exercise_minutes) : '30',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (!isNaN(numValue) && numValue > 0) {
                          updateField('target_exercise_minutes', numValue);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.target_exercise_minutes || 30} 分钟
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
              <Text className="form-hint">推荐: 30分钟以上</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标体重 (kg)</Text>
              <View 
                className="form-input-display"
                onClick={() => {
                  Taro.showModal({
                    title: '目标体重 (kg)',
                    editable: true,
                    placeholderText: '输入目标体重',
                    content: profile.target_weight_kg ? String(profile.target_weight_kg) : '',
                    success: (res) => {
                      if (res.confirm && res.content) {
                        const numValue = Number(res.content);
                        if (!isNaN(numValue) && numValue > 0) {
                          updateField('target_weight_kg', numValue);
                        } else {
                          Taro.showToast({ title: '请输入有效数字', icon: 'none' });
                        }
                      } else if (res.confirm && !res.content) {
                        updateField('target_weight_kg', null);
                      }
                    }
                  });
                }}
              >
                <Text className="form-input-text">
                  {profile.target_weight_kg ? `${profile.target_weight_kg} kg` : '点击设置目标体重'}
                </Text>
                <Text className="form-input-arrow">›</Text>
              </View>
            </View>
          </View>
        )}
      </ScrollView>

      {/* 保存按钮 */}
      <View 
        className={`save-btn ${saving ? 'disabled' : ''}`} 
        onClick={saving ? undefined : saveProfile}
      >
        {saving ? '⏳ 保存中...' : '💾 保存设置'}
      </View>
    </View>
  );
}
