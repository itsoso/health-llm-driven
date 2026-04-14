'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { onboardingApi } from '@/services/api/user';

const DEFAULT_TEMPLATES = [
  { name: '俯卧撑', icon: '💪', category: 'exercise' },
  { name: '深蹲', icon: '🦵', category: 'exercise' },
  { name: '仰卧起坐', icon: '🏋️', category: 'exercise' },
  { name: '平板支撑', icon: '🧘', category: 'exercise' },
  { name: '跳绳', icon: '🏃', category: 'exercise' },
  { name: '爬楼梯', icon: '🏢', category: 'exercise' },
  { name: '洗鼻', icon: '👃', category: 'health' },
  { name: '测血压', icon: '🩺', category: 'health' },
  { name: '测血糖', icon: '🩸', category: 'health' },
  { name: '称体重', icon: '⚖️', category: 'health' },
  { name: '早睡', icon: '🌙', category: 'habit' },
  { name: '冥想', icon: '🧘‍♂️', category: 'habit' },
  { name: '阅读', icon: '📚', category: 'habit' },
  { name: '拉伸', icon: '🤸', category: 'habit' },
  { name: '喝水', icon: '💧', category: 'habit' },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const { showToast } = useToast();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);

  // Step 1 fields
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [gender, setGender] = useState('');
  const [birthDate, setBirthDate] = useState('');

  // Step 2 fields
  const [targetSteps, setTargetSteps] = useState(8000);
  const [targetSleepHours, setTargetSleepHours] = useState(7.5);
  const [targetWaterMl, setTargetWaterMl] = useState(2000);
  const [targetExerciseMinutes, setTargetExerciseMinutes] = useState(30);

  // Step 3 fields
  const [selectedTemplates, setSelectedTemplates] = useState<Set<string>>(
    new Set(DEFAULT_TEMPLATES.map(t => t.name))
  );

  // Fetch existing profile data and pre-fill
  useEffect(() => {
    if (user?.onboarding_completed) {
      router.replace('/dashboard');
      return;
    }
    onboardingApi.getStatus().then(res => {
      const p = res.data.profile_data;
      if (!p) return;
      if (p.height_cm) setHeightCm(String(p.height_cm));
      if (p.current_weight_kg) setWeightKg(String(p.current_weight_kg));
      if (p.gender) setGender(p.gender);
      if (p.birth_date) setBirthDate(p.birth_date);
      setTargetSteps(p.target_steps);
      setTargetSleepHours(p.target_sleep_hours);
      setTargetWaterMl(p.target_water_ml);
      setTargetExerciseMinutes(p.target_exercise_minutes);
    }).catch(() => {});
  }, [user, router]);

  const handleStep1 = async () => {
    setLoading(true);
    try {
      const data: any = {};
      if (heightCm) data.height_cm = parseFloat(heightCm);
      if (weightKg) data.current_weight_kg = parseFloat(weightKg);
      if (gender) data.gender = gender;
      if (birthDate) data.birth_date = birthDate;
      await onboardingApi.saveStep1(data);
      setStep(2);
    } catch {
      showToast('保存失败，请重试', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleStep2 = async () => {
    setLoading(true);
    try {
      await onboardingApi.saveStep2({
        target_steps: targetSteps,
        target_sleep_hours: targetSleepHours,
        target_water_ml: targetWaterMl,
        target_exercise_minutes: targetExerciseMinutes,
      });
      setStep(3);
    } catch {
      showToast('保存失败，请重试', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = async () => {
    setLoading(true);
    try {
      await onboardingApi.complete({
        init_default_templates: selectedTemplates.size > 0,
        selected_template_names: Array.from(selectedTemplates),
      });
      await refreshUser();
      setStep(4); // 进入探索页
    } catch {
      showToast('完成引导失败，请重试', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = () => {
    onboardingApi.skip();
    router.replace('/dashboard');
  };

  const toggleTemplate = (name: string) => {
    setSelectedTemplates(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const selectAllTemplates = () => {
    setSelectedTemplates(new Set(DEFAULT_TEMPLATES.map(t => t.name)));
  };

  const deselectAllTemplates = () => {
    setSelectedTemplates(new Set());
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl p-8">
        {/* Progress */}
        {step <= 3 && (
          <div className="flex items-center justify-center gap-2 mb-8">
            {[1, 2, 3].map(s => (
              <div key={s} className="flex items-center gap-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                  s === step ? 'bg-indigo-600 text-white' : s < step ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'
                }`}>
                  {s < step ? '✓' : s}
                </div>
                {s < 3 && <div className={`w-8 h-0.5 ${s < step ? 'bg-green-500' : 'bg-gray-200'}`} />}
              </div>
            ))}
          </div>
        )}

        {/* Step 1: Basic Info */}
        {step === 1 && (
          <div>
            <h2 className="text-xl font-bold text-center mb-2">基本信息</h2>
            <p className="text-gray-500 text-center text-sm mb-6">帮助我们更好地了解你</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">身高 (cm)</label>
                <input
                  type="number"
                  value={heightCm}
                  onChange={e => setHeightCm(e.target.value)}
                  placeholder="170"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">体重 (kg)</label>
                <input
                  type="number"
                  value={weightKg}
                  onChange={e => setWeightKg(e.target.value)}
                  placeholder="70"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">性别</label>
                <div className="flex gap-3">
                  {[
                    { value: 'male', label: '男', icon: '♂' },
                    { value: 'female', label: '女', icon: '♀' },
                  ].map(g => (
                    <button
                      key={g.value}
                      onClick={() => setGender(g.value)}
                      className={`flex-1 py-2.5 rounded-xl border text-sm font-medium transition ${
                        gender === g.value
                          ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                          : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      {g.icon} {g.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">出生日期</label>
                <input
                  type="date"
                  value={birthDate}
                  onChange={e => setBirthDate(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-8">
              <button
                onClick={() => { setStep(2); }}
                className="flex-1 py-2.5 text-gray-500 text-sm hover:text-gray-700"
              >
                跳过
              </button>
              <button
                onClick={handleStep1}
                disabled={loading}
                className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? '保存中...' : '下一步'}
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Health Goals */}
        {step === 2 && (
          <div>
            <h2 className="text-xl font-bold text-center mb-2">健康目标</h2>
            <p className="text-gray-500 text-center text-sm mb-6">设置你的每日健康目标</p>

            <div className="space-y-5">
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-sm font-medium text-gray-700">每日步数</label>
                  <span className="text-sm font-bold text-indigo-600">{targetSteps.toLocaleString()} 步</span>
                </div>
                <input
                  type="range"
                  min={3000}
                  max={30000}
                  step={1000}
                  value={targetSteps}
                  onChange={e => setTargetSteps(Number(e.target.value))}
                  className="w-full accent-indigo-600"
                />
              </div>
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-sm font-medium text-gray-700">睡眠时长</label>
                  <span className="text-sm font-bold text-indigo-600">{targetSleepHours} 小时</span>
                </div>
                <input
                  type="range"
                  min={5}
                  max={10}
                  step={0.5}
                  value={targetSleepHours}
                  onChange={e => setTargetSleepHours(Number(e.target.value))}
                  className="w-full accent-indigo-600"
                />
              </div>
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-sm font-medium text-gray-700">每日饮水</label>
                  <span className="text-sm font-bold text-indigo-600">{targetWaterMl} ml</span>
                </div>
                <input
                  type="range"
                  min={1000}
                  max={5000}
                  step={250}
                  value={targetWaterMl}
                  onChange={e => setTargetWaterMl(Number(e.target.value))}
                  className="w-full accent-indigo-600"
                />
              </div>
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-sm font-medium text-gray-700">运动时长</label>
                  <span className="text-sm font-bold text-indigo-600">{targetExerciseMinutes} 分钟</span>
                </div>
                <input
                  type="range"
                  min={10}
                  max={120}
                  step={5}
                  value={targetExerciseMinutes}
                  onChange={e => setTargetExerciseMinutes(Number(e.target.value))}
                  className="w-full accent-indigo-600"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-8">
              <button
                onClick={() => setStep(1)}
                className="flex-1 py-2.5 text-gray-500 text-sm hover:text-gray-700"
              >
                上一步
              </button>
              <button
                onClick={handleStep2}
                disabled={loading}
                className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? '保存中...' : '下一步'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Checkin Templates */}
        {step === 3 && (
          <div>
            <h2 className="text-xl font-bold text-center mb-2">打卡项目</h2>
            <p className="text-gray-500 text-center text-sm mb-4">选择你想追踪的习惯</p>

            <div className="flex justify-end gap-2 mb-3">
              <button onClick={selectAllTemplates} className="text-xs text-indigo-600 hover:underline">全选</button>
              <span className="text-gray-300">|</span>
              <button onClick={deselectAllTemplates} className="text-xs text-gray-500 hover:underline">全不选</button>
            </div>

            <div className="grid grid-cols-3 gap-2 max-h-[40vh] overflow-y-auto">
              {DEFAULT_TEMPLATES.map(t => (
                <button
                  key={t.name}
                  onClick={() => toggleTemplate(t.name)}
                  className={`flex flex-col items-center gap-1 p-3 rounded-xl border transition text-center ${
                    selectedTemplates.has(t.name)
                      ? 'border-indigo-500 bg-indigo-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <span className="text-2xl">{t.icon}</span>
                  <span className="text-xs font-medium">{t.name}</span>
                </button>
              ))}
            </div>

            <p className="text-center text-xs text-gray-400 mt-3">
              已选 {selectedTemplates.size} / {DEFAULT_TEMPLATES.length} 项
            </p>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setStep(2)}
                className="flex-1 py-2.5 text-gray-500 text-sm hover:text-gray-700"
              >
                上一步
              </button>
              <button
                onClick={handleComplete}
                disabled={loading}
                className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? '完成中...' : '完成设置'}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: 开始探索 */}
        {step === 4 && (
          <div>
            <div className="text-center mb-6">
              <div className="text-4xl mb-3">🎉</div>
              <h2 className="text-xl font-bold mb-2">设置完成！</h2>
              <p className="text-gray-500 text-sm">接下来，连接你的数据让 AI 更懂你</p>
            </div>

            <div className="space-y-3">
              <button
                onClick={() => router.push('/settings#garmin')}
                className="w-full flex items-center gap-4 p-4 rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 transition text-left"
              >
                <span className="text-2xl">⌚</span>
                <div className="flex-1">
                  <div className="font-medium text-gray-900">连接 Garmin 手表</div>
                  <div className="text-xs text-gray-500">自动同步运动、睡眠、心率数据</div>
                </div>
                <span className="text-gray-400">→</span>
              </button>

              <button
                onClick={() => router.push('/family/reports')}
                className="w-full flex items-center gap-4 p-4 rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 transition text-left"
              >
                <span className="text-2xl">📋</span>
                <div className="flex-1">
                  <div className="font-medium text-gray-900">上传体检报告</div>
                  <div className="text-xs text-gray-500">AI 智能分析异常指标和健康趋势</div>
                </div>
                <span className="text-gray-400">→</span>
              </button>

              <button
                onClick={() => router.push('/ai-assistant')}
                className="w-full flex items-center gap-4 p-4 rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 transition text-left"
              >
                <span className="text-2xl">🤖</span>
                <div className="flex-1">
                  <div className="font-medium text-gray-900">和 AI 助理对话</div>
                  <div className="text-xs text-gray-500">问任何健康问题，获取个性化建议</div>
                </div>
                <span className="text-gray-400">→</span>
              </button>

              <button
                onClick={() => router.push('/diet')}
                className="w-full flex items-center gap-4 p-4 rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 transition text-left"
              >
                <span className="text-2xl">🍽️</span>
                <div className="flex-1">
                  <div className="font-medium text-gray-900">记录饮食</div>
                  <div className="text-xs text-gray-500">拍照识别食物，AI 计算热量</div>
                </div>
                <span className="text-gray-400">→</span>
              </button>
            </div>

            <button
              onClick={() => router.replace('/dashboard')}
              className="w-full mt-6 py-3 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700"
            >
              进入主页
            </button>
          </div>
        )}

        {/* Skip link */}
        {step <= 3 && (
          <div className="mt-4 text-center">
            <button onClick={handleSkip} className="text-xs text-gray-400 hover:text-gray-600">
              跳过引导，稍后设置
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
