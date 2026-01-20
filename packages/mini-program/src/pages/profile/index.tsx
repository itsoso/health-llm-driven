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
  target_steps: number;
  target_sleep_hours: number;
  target_water_ml: number;
  target_exercise_minutes: number;
  chronic_conditions: string[];
  allergies: string[];
  family_history: string[];
  exercise_frequency: string | null;
  diet_preference: string | null;
  city: string | null;
  timezone: string;
  age: number | null;
  bmi: number | null;
  bmi_category: string | null;
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
    if (profile) {
      setProfile({ ...profile, [field]: value });
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
              <Input
                type="number"
                value={profile.height_cm?.toString() || ''}
                onInput={e => updateField('height_cm', e.detail.value ? Number(e.detail.value) : null)}
                placeholder="输入身高"
                className="form-input"
              />
            </View>

            <View className="form-item">
              <Text className="form-label">当前体重 (kg)</Text>
              <Input
                type="digit"
                value={profile.current_weight_kg?.toString() || ''}
                onInput={e => updateField('current_weight_kg', e.detail.value ? Number(e.detail.value) : null)}
                placeholder="输入体重"
                className="form-input"
              />
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
                value={profile.city || ''}
                onInput={e => updateField('city', e.detail.value || null)}
                placeholder="输入城市"
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
              <Input
                type="number"
                value={profile.target_steps?.toString() || '8000'}
                onInput={e => updateField('target_steps', Number(e.detail.value) || 8000)}
                className="form-input"
              />
              <Text className="form-hint">推荐: 8000-10000步</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标睡眠 (小时/天)</Text>
              <Input
                type="digit"
                value={profile.target_sleep_hours?.toString() || '7.5'}
                onInput={e => updateField('target_sleep_hours', Number(e.detail.value) || 7.5)}
                className="form-input"
              />
              <Text className="form-hint">推荐: 7-9小时</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标饮水 (ml/天)</Text>
              <Input
                type="number"
                value={profile.target_water_ml?.toString() || '2000'}
                onInput={e => updateField('target_water_ml', Number(e.detail.value) || 2000)}
                className="form-input"
              />
              <Text className="form-hint">推荐: 1500-2500ml</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标运动 (分钟/天)</Text>
              <Input
                type="number"
                value={profile.target_exercise_minutes?.toString() || '30'}
                onInput={e => updateField('target_exercise_minutes', Number(e.detail.value) || 30)}
                className="form-input"
              />
              <Text className="form-hint">推荐: 30分钟以上</Text>
            </View>

            <View className="form-item">
              <Text className="form-label">目标体重 (kg)</Text>
              <Input
                type="digit"
                value={profile.target_weight_kg?.toString() || ''}
                onInput={e => updateField('target_weight_kg', e.detail.value ? Number(e.detail.value) : null)}
                placeholder="设置目标体重"
                className="form-input"
              />
            </View>
          </View>
        )}
      </ScrollView>

      {/* 保存按钮 */}
      <View className="save-btn" onClick={saveProfile}>
        {saving ? '保存中...' : '💾 保存设置'}
      </View>
    </View>
  );
}
