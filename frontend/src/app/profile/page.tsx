'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';

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
  exercise_frequency: string | null;
  diet_preference: string | null;
  smoking_status: string | null;
  alcohol_consumption: string | null;
  usual_sleep_time: string | null;
  usual_wake_time: string | null;
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
  updated_at: string;
}

export default function ProfilePage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  
  const [formData, setFormData] = useState<Partial<UserProfile>>({});
  const [newCondition, setNewCondition] = useState('');
  const [newAllergy, setNewAllergy] = useState('');
  const [activeTab, setActiveTab] = useState<'basic' | 'health' | 'lifestyle' | 'goals'>('basic');

  // 获取用户画像
  const { data: profile, isLoading } = useQuery<UserProfile>({
    queryKey: ['userProfile'],
    queryFn: async () => {
      const response = await api.get('/profile/me');
      return response.data;
    },
    enabled: !!user,
  });

  // 更新用户画像
  const updateMutation = useMutation({
    mutationFn: async (data: Partial<UserProfile>) => {
      const response = await api.put('/profile/me', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userProfile'] });
      alert('保存成功！');
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || '保存失败');
    },
  });

  useEffect(() => {
    if (profile) {
      setFormData(profile);
    }
  }, [profile]);

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-400"></div>
      </div>
    );
  }

  if (!user) {
    router.push('/login');
    return null;
  }

  const handleChange = (field: keyof UserProfile, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    updateMutation.mutate(formData);
  };

  const addCondition = () => {
    if (newCondition.trim()) {
      const conditions = [...(formData.chronic_conditions || []), newCondition.trim()];
      handleChange('chronic_conditions', conditions);
      setNewCondition('');
    }
  };

  const removeCondition = (condition: string) => {
    const conditions = (formData.chronic_conditions || []).filter(c => c !== condition);
    handleChange('chronic_conditions', conditions);
  };

  const addAllergy = () => {
    if (newAllergy.trim()) {
      const allergies = [...(formData.allergies || []), newAllergy.trim()];
      handleChange('allergies', allergies);
      setNewAllergy('');
    }
  };

  const removeAllergy = (allergy: string) => {
    const allergies = (formData.allergies || []).filter(a => a !== allergy);
    handleChange('allergies', allergies);
  };

  const tabs = [
    { id: 'basic', label: '基本信息', icon: '👤' },
    { id: 'health', label: '健康状况', icon: '🏥' },
    { id: 'lifestyle', label: '生活习惯', icon: '🌟' },
    { id: 'goals', label: '健康目标', icon: '🎯' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* 头部 */}
      <header className="bg-black/20 backdrop-blur-sm border-b border-white/10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="text-white/70 hover:text-white transition-colors"
            >
              ← 返回
            </button>
            <h1 className="text-xl font-bold text-white">个人画像设置</h1>
          </div>
          <button
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {updateMutation.isPending ? '保存中...' : '💾 保存'}
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        {/* BMI 卡片 */}
        {formData.bmi && (
          <div className="bg-gradient-to-r from-purple-600/30 to-pink-600/30 rounded-2xl p-6 mb-6 border border-purple-500/30">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-white/70 text-sm mb-1">身体质量指数 (BMI)</h3>
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-bold text-white">{formData.bmi}</span>
                  <span className={`text-lg font-medium ${
                    formData.bmi_category === '正常' ? 'text-green-400' :
                    formData.bmi_category === '偏瘦' ? 'text-blue-400' :
                    formData.bmi_category === '超重' ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {formData.bmi_category}
                  </span>
                </div>
              </div>
              {formData.age && (
                <div className="text-right">
                  <span className="text-white/70 text-sm">年龄</span>
                  <div className="text-2xl font-bold text-white">{formData.age}岁</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 导航 */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium whitespace-nowrap transition-all ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab 内容 */}
        <div className="bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
          {/* 基本信息 */}
          {activeTab === 'basic' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-white/70 text-sm mb-2">性别</label>
                  <select
                    value={formData.gender || ''}
                    onChange={e => handleChange('gender', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="male">男</option>
                    <option value="female">女</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">出生日期</label>
                  <input
                    type="date"
                    value={formData.birth_date || ''}
                    onChange={e => handleChange('birth_date', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">身高 (cm)</label>
                  <input
                    type="number"
                    value={formData.height_cm || ''}
                    onChange={e => handleChange('height_cm', e.target.value ? Number(e.target.value) : null)}
                    placeholder="例如: 175"
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">血型</label>
                  <select
                    value={formData.blood_type || ''}
                    onChange={e => handleChange('blood_type', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="A">A型</option>
                    <option value="B">B型</option>
                    <option value="AB">AB型</option>
                    <option value="O">O型</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">当前体重 (kg)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.current_weight_kg || ''}
                    onChange={e => handleChange('current_weight_kg', e.target.value ? Number(e.target.value) : null)}
                    placeholder="例如: 70"
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">所在城市</label>
                  <input
                    type="text"
                    value={formData.city || ''}
                    onChange={e => handleChange('city', e.target.value || null)}
                    placeholder="例如: 杭州"
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">时区</label>
                  <select
                    value={formData.timezone || 'Asia/Shanghai'}
                    onChange={e => handleChange('timezone', e.target.value)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="Asia/Shanghai">中国标准时间 (UTC+8)</option>
                    <option value="Asia/Hong_Kong">香港时间 (UTC+8)</option>
                    <option value="Asia/Taipei">台北时间 (UTC+8)</option>
                    <option value="Asia/Singapore">新加坡时间 (UTC+8)</option>
                    <option value="Asia/Tokyo">东京时间 (UTC+9)</option>
                    <option value="Asia/Seoul">首尔时间 (UTC+9)</option>
                    <option value="America/New_York">美国东部时间 (UTC-5/-4)</option>
                    <option value="America/Los_Angeles">美国太平洋时间 (UTC-8/-7)</option>
                    <option value="Europe/London">伦敦时间 (UTC+0/+1)</option>
                    <option value="Europe/Paris">巴黎时间 (UTC+1/+2)</option>
                    <option value="Australia/Sydney">悉尼时间 (UTC+10/+11)</option>
                    <option value="UTC">协调世界时 (UTC)</option>
                  </select>
                  <span className="text-white/40 text-xs mt-1">系统将根据此时区计算周起始日等</span>
                </div>
              </div>
            </div>
          )}

          {/* 健康状况 */}
          {activeTab === 'health' && (
            <div className="space-y-6">
              {/* 慢性病 */}
              <div>
                <label className="block text-white/70 text-sm mb-2">慢性病史</label>
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={newCondition}
                    onChange={e => setNewCondition(e.target.value)}
                    onKeyPress={e => e.key === 'Enter' && addCondition()}
                    placeholder="输入慢性病名称"
                    className="flex-1 bg-white/10 border border-white/20 rounded-lg px-4 py-2 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                  <button
                    onClick={addCondition}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
                  >
                    添加
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(formData.chronic_conditions || []).map(condition => (
                    <span
                      key={condition}
                      className="inline-flex items-center gap-2 px-3 py-1 bg-red-500/20 border border-red-500/30 text-red-300 rounded-full text-sm"
                    >
                      {condition}
                      <button
                        onClick={() => removeCondition(condition)}
                        className="hover:text-white"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {(formData.chronic_conditions || []).length === 0 && (
                    <span className="text-white/30 text-sm">暂无记录</span>
                  )}
                </div>
              </div>

              {/* 过敏源 */}
              <div>
                <label className="block text-white/70 text-sm mb-2">过敏源</label>
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={newAllergy}
                    onChange={e => setNewAllergy(e.target.value)}
                    onKeyPress={e => e.key === 'Enter' && addAllergy()}
                    placeholder="输入过敏源"
                    className="flex-1 bg-white/10 border border-white/20 rounded-lg px-4 py-2 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                  <button
                    onClick={addAllergy}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
                  >
                    添加
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(formData.allergies || []).map(allergy => (
                    <span
                      key={allergy}
                      className="inline-flex items-center gap-2 px-3 py-1 bg-orange-500/20 border border-orange-500/30 text-orange-300 rounded-full text-sm"
                    >
                      {allergy}
                      <button
                        onClick={() => removeAllergy(allergy)}
                        className="hover:text-white"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {(formData.allergies || []).length === 0 && (
                    <span className="text-white/30 text-sm">暂无记录</span>
                  )}
                </div>
              </div>

              {/* 家族病史 */}
              <div>
                <label className="block text-white/70 text-sm mb-2">家族病史</label>
                <div className="flex flex-wrap gap-2">
                  {['糖尿病', '高血压', '心脏病', '癌症', '过敏体质'].map(condition => (
                    <button
                      key={condition}
                      onClick={() => {
                        const history = formData.family_history || [];
                        if (history.includes(condition)) {
                          handleChange('family_history', history.filter(h => h !== condition));
                        } else {
                          handleChange('family_history', [...history, condition]);
                        }
                      }}
                      className={`px-3 py-1 rounded-full text-sm transition-colors ${
                        (formData.family_history || []).includes(condition)
                          ? 'bg-purple-600 text-white'
                          : 'bg-white/10 text-white/70 hover:bg-white/20'
                      }`}
                    >
                      {condition}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 生活习惯 */}
          {activeTab === 'lifestyle' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-white/70 text-sm mb-2">运动频率</label>
                  <select
                    value={formData.exercise_frequency || ''}
                    onChange={e => handleChange('exercise_frequency', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="never">从不运动</option>
                    <option value="occasionally">偶尔运动</option>
                    <option value="weekly">每周1-2次</option>
                    <option value="regularly">每周3-5次</option>
                    <option value="daily">每天运动</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">饮食偏好</label>
                  <select
                    value={formData.diet_preference || ''}
                    onChange={e => handleChange('diet_preference', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="normal">正常饮食</option>
                    <option value="vegetarian">素食</option>
                    <option value="low_carb">低碳水</option>
                    <option value="keto">生酮饮食</option>
                    <option value="mediterranean">地中海饮食</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">吸烟状态</label>
                  <select
                    value={formData.smoking_status || ''}
                    onChange={e => handleChange('smoking_status', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="never">从不吸烟</option>
                    <option value="former">已戒烟</option>
                    <option value="current">吸烟中</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">饮酒情况</label>
                  <select
                    value={formData.alcohol_consumption || ''}
                    onChange={e => handleChange('alcohol_consumption', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="never">从不饮酒</option>
                    <option value="occasionally">偶尔</option>
                    <option value="moderate">适量</option>
                    <option value="heavy">经常</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">通常入睡时间</label>
                  <input
                    type="time"
                    value={formData.usual_sleep_time || ''}
                    onChange={e => handleChange('usual_sleep_time', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">通常起床时间</label>
                  <input
                    type="time"
                    value={formData.usual_wake_time || ''}
                    onChange={e => handleChange('usual_wake_time', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">工作类型</label>
                  <select
                    value={formData.work_type || ''}
                    onChange={e => handleChange('work_type', e.target.value || null)}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">未设置</option>
                    <option value="office">办公室</option>
                    <option value="remote">远程办公</option>
                    <option value="physical">体力劳动</option>
                    <option value="mixed">混合</option>
                  </select>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">每日久坐时长 (小时)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={formData.sitting_hours_per_day || ''}
                    onChange={e => handleChange('sitting_hours_per_day', e.target.value ? Number(e.target.value) : null)}
                    placeholder="例如: 8"
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* 健康目标 */}
          {activeTab === 'goals' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-white/70 text-sm mb-2">目标步数</label>
                  <input
                    type="number"
                    value={formData.target_steps || 8000}
                    onChange={e => handleChange('target_steps', Number(e.target.value))}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                  <span className="text-white/40 text-xs mt-1">推荐: 8000-10000步/天</span>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">目标睡眠时长 (小时)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={formData.target_sleep_hours || 7.5}
                    onChange={e => handleChange('target_sleep_hours', Number(e.target.value))}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                  <span className="text-white/40 text-xs mt-1">推荐: 7-9小时</span>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">目标饮水量 (ml)</label>
                  <input
                    type="number"
                    step="100"
                    value={formData.target_water_ml || 2000}
                    onChange={e => handleChange('target_water_ml', Number(e.target.value))}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                  <span className="text-white/40 text-xs mt-1">推荐: 1500-2500ml/天</span>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">目标运动时长 (分钟/天)</label>
                  <input
                    type="number"
                    value={formData.target_exercise_minutes || 30}
                    onChange={e => handleChange('target_exercise_minutes', Number(e.target.value))}
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  />
                  <span className="text-white/40 text-xs mt-1">推荐: 30分钟以上</span>
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">目标体重 (kg)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.target_weight_kg || ''}
                    onChange={e => handleChange('target_weight_kg', e.target.value ? Number(e.target.value) : null)}
                    placeholder="设置你的目标体重"
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-white/70 text-sm mb-2">目标卡路里消耗</label>
                  <input
                    type="number"
                    value={formData.target_calories_burn || ''}
                    onChange={e => handleChange('target_calories_burn', e.target.value ? Number(e.target.value) : null)}
                    placeholder="例如: 500"
                    className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
