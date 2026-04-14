'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

// 健康目标选项
const HEALTH_GOALS = ['减脂塑形', '增肌增重', '提升睡眠', '改善体能', '管理慢性病', '健康监测'];
// 慢性病选项
const CHRONIC_CONDITIONS = ['无', '慢性鼻炎', '慢性咽炎', '高血压', '糖尿病', '其他'];
// 穿戴设备选项
const WEARABLE_DEVICES = ['Garmin 手表', 'Apple Watch', '华为手表/手环', '小米手环', '华为体脂秤', '其他'];
// 运动频率选项
const EXERCISE_FREQUENCIES = ['几乎不运动', '每周1-2次', '每周3-4次', '每周5次以上', '每天运动'];

export default function RegisterPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  
  const [step, setStep] = useState(1); // 1: 基本信息, 2: 健康问卷
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    confirmPassword: '',
    inviteCode: '',
  });
  const [questionnaire, setQuestionnaire] = useState({
    age: '',
    gender: '',
    height_cm: '',
    weight_kg: '',
    health_goals: [] as string[],
    chronic_conditions: [] as string[],
    wearable_devices: [] as string[],
    exercise_frequency: '',
    why_join: '',
  });
  
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({ password: '', confirmPassword: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [inviteCodeStatus, setInviteCodeStatus] = useState<'idle' | 'checking' | 'valid' | 'invalid'>('idle');
  const [inviteCodeMessage, setInviteCodeMessage] = useState('');

  // 如果已登录，重定向到首页
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, router]);

  // 验证邀请码
  const verifyInviteCode = async (code: string) => {
    if (!code || code.length < 4) {
      setInviteCodeStatus('idle');
      setInviteCodeMessage('');
      return;
    }

    setInviteCodeStatus('checking');
    try {
      const response = await api.post('/invitation/codes/verify', { code: code.toUpperCase() });
      if (response.data.valid) {
        setInviteCodeStatus('valid');
        setInviteCodeMessage(`邀请码有效，剩余 ${response.data.remaining_uses} 次使用机会`);
      } else {
        setInviteCodeStatus('invalid');
        setInviteCodeMessage(response.data.message);
      }
    } catch {
      setInviteCodeStatus('invalid');
      setInviteCodeMessage('验证失败，请稍后重试');
    }
  };

  // 邀请码输入防抖
  useEffect(() => {
    const timer = setTimeout(() => {
      if (formData.inviteCode) {
        verifyInviteCode(formData.inviteCode);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [formData.inviteCode]);

  const validatePasswordFields = () => {
    const errors = { password: '', confirmPassword: '' };
    let valid = true;
    if (formData.password.length > 0 && formData.password.length < 6) {
      errors.password = '密码至少需要6个字符';
      valid = false;
    }
    if (formData.confirmPassword.length > 0 && formData.password !== formData.confirmPassword) {
      errors.confirmPassword = '密码不一致';
      valid = false;
    }
    setFieldErrors(errors);
    return valid;
  };

  const handleStep1Submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Inline validation
    const errors = { password: '', confirmPassword: '' };
    let hasError = false;
    if (formData.password.length < 6) {
      errors.password = '密码至少需要6个字符';
      hasError = true;
    }
    if (formData.password !== formData.confirmPassword) {
      errors.confirmPassword = '密码不一致';
      hasError = true;
    }
    setFieldErrors(errors);
    if (hasError) return;

    if (inviteCodeStatus !== 'valid') {
      setError('请输入有效的邀请码');
      return;
    }

    // 进入第二步
    setStep(2);
  };

  const handleFinalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      // 构建健康问卷数据
      const healthQuestionnaire = {
        age: questionnaire.age ? parseInt(questionnaire.age) : null,
        gender: questionnaire.gender || null,
        height_cm: questionnaire.height_cm ? parseFloat(questionnaire.height_cm) : null,
        weight_kg: questionnaire.weight_kg ? parseFloat(questionnaire.weight_kg) : null,
        health_goals: questionnaire.health_goals,
        chronic_conditions: questionnaire.chronic_conditions.filter(c => c !== '无'),
        wearable_devices: questionnaire.wearable_devices,
        exercise_frequency: questionnaire.exercise_frequency || null,
        why_join: questionnaire.why_join || null,
      };

      // 提交申请
      await api.post('/invitation/apply', {
        email: formData.email,
        name: formData.name,
        phone: formData.phone || null,
        invitation_code: formData.inviteCode.toUpperCase(),
        password: formData.password,
        health_questionnaire: healthQuestionnaire,
      });

      setShowSuccessModal(true);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || '提交失败，请稍后重试');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleArrayItem = (
    array: string[],
    item: string,
    setter: (value: string[]) => void
  ) => {
    if (array.includes(item)) {
      setter(array.filter(i => i !== item));
    } else {
      setter([...array, item]);
    }
  };

  if (isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center space-x-2">
            <span className="text-4xl">🚀</span>
            <span className="text-2xl font-bold text-white">
              Executor Life
            </span>
          </Link>
          <p className="text-purple-300 mt-2 text-sm">AI驱动的个人健康管理系统</p>
        </div>

        {/* 步骤指示器 */}
        <div className="flex items-center justify-center mb-6">
          <div className={`flex items-center ${step >= 1 ? 'text-purple-400' : 'text-gray-500'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step >= 1 ? 'bg-purple-500 text-white' : 'bg-gray-700 text-gray-400'
            }`}>
              1
            </div>
            <span className="ml-2 text-sm hidden sm:inline">基本信息</span>
          </div>
          <div className={`w-12 h-0.5 mx-2 ${step >= 2 ? 'bg-purple-500' : 'bg-gray-700'}`} />
          <div className={`flex items-center ${step >= 2 ? 'text-purple-400' : 'text-gray-500'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step >= 2 ? 'bg-purple-500 text-white' : 'bg-gray-700 text-gray-400'
            }`}>
              2
            </div>
            <span className="ml-2 text-sm hidden sm:inline">健康画像</span>
          </div>
        </div>

        {/* 表单卡片 */}
        <div className="bg-white/10 backdrop-blur-lg rounded-2xl shadow-2xl p-8 border border-white/20">
          <h1 className="text-2xl font-bold text-white text-center mb-6">
            {step === 1 ? '创建账号' : '完善健康画像'}
          </h1>
          
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">
              ❌ {error}
            </div>
          )}

          {step === 1 ? (
            /* 第一步：基本信息 */
            <form onSubmit={handleStep1Submit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">
                  姓名 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="请输入您的姓名"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">
                  邮箱 <span className="text-red-400">*</span>
                </label>
                <input
                  type="email"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="请输入邮箱地址"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">
                  手机号 <span className="text-gray-400">(选填)</span>
                </label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="请输入手机号"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-purple-200 mb-2">
                    密码 <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={formData.password}
                    onChange={(e) => {
                      setFormData({ ...formData, password: e.target.value });
                      if (fieldErrors.password) setFieldErrors(prev => ({ ...prev, password: '' }));
                    }}
                    onBlur={validatePasswordFields}
                    className={`w-full p-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent ${fieldErrors.password ? 'border-red-500' : 'border-white/20'}`}
                    placeholder="至少6个字符"
                  />
                  {fieldErrors.password && (
                    <p className="text-red-400 text-xs mt-1">{fieldErrors.password}</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-purple-200 mb-2">
                    确认密码 <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="password"
                    required
                    value={formData.confirmPassword}
                    onChange={(e) => {
                      setFormData({ ...formData, confirmPassword: e.target.value });
                      if (fieldErrors.confirmPassword) setFieldErrors(prev => ({ ...prev, confirmPassword: '' }));
                    }}
                    onBlur={validatePasswordFields}
                    className={`w-full p-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent ${fieldErrors.confirmPassword ? 'border-red-500' : 'border-white/20'}`}
                    placeholder="再次输入"
                  />
                  {fieldErrors.confirmPassword && (
                    <p className="text-red-400 text-xs mt-1">{fieldErrors.confirmPassword}</p>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">
                  邀请码 <span className="text-red-400">*</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={formData.inviteCode}
                    onChange={(e) => setFormData({ ...formData, inviteCode: e.target.value.toUpperCase() })}
                    className={`w-full p-3 bg-white/10 border rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent uppercase ${
                      inviteCodeStatus === 'valid' ? 'border-green-500' : 
                      inviteCodeStatus === 'invalid' ? 'border-red-500' : 'border-white/20'
                    }`}
                    placeholder="请输入邀请码"
                    maxLength={20}
                  />
                  {inviteCodeStatus === 'checking' && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-purple-400">
                      ⏳
                    </span>
                  )}
                  {inviteCodeStatus === 'valid' && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-green-400">
                      ✓
                    </span>
                  )}
                  {inviteCodeStatus === 'invalid' && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-red-400">
                      ✗
                    </span>
                  )}
                </div>
                {inviteCodeMessage && (
                  <p className={`text-xs mt-1 ${
                    inviteCodeStatus === 'valid' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {inviteCodeMessage}
                  </p>
                )}
              </div>

              <button
                type="submit"
                disabled={inviteCodeStatus !== 'valid'}
                className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-700 hover:to-pink-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg"
              >
                下一步：完善健康画像
              </button>
            </form>
          ) : (
            /* 第二步：健康问卷 */
            <form onSubmit={handleFinalSubmit} className="space-y-4">
              <p className="text-gray-300 text-sm mb-4">
                以下信息将帮助 AI 更好地为您提供个性化的健康建议（选填）
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-purple-200 mb-2">年龄</label>
                  <input
                    type="number"
                    min={1}
                    max={120}
                    value={questionnaire.age}
                    onChange={(e) => setQuestionnaire({ ...questionnaire, age: e.target.value })}
                    className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500"
                    placeholder="例：30"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-purple-200 mb-2">性别</label>
                  <select
                    value={questionnaire.gender}
                    onChange={(e) => setQuestionnaire({ ...questionnaire, gender: e.target.value })}
                    className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="" className="bg-gray-800">请选择</option>
                    <option value="male" className="bg-gray-800">男</option>
                    <option value="female" className="bg-gray-800">女</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-purple-200 mb-2">身高 (cm)</label>
                  <input
                    type="number"
                    min={50}
                    max={250}
                    value={questionnaire.height_cm}
                    onChange={(e) => setQuestionnaire({ ...questionnaire, height_cm: e.target.value })}
                    className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500"
                    placeholder="例：175"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-purple-200 mb-2">体重 (kg)</label>
                  <input
                    type="number"
                    min={20}
                    max={300}
                    value={questionnaire.weight_kg}
                    onChange={(e) => setQuestionnaire({ ...questionnaire, weight_kg: e.target.value })}
                    className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500"
                    placeholder="例：70"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">健康目标（可多选）</label>
                <div className="flex flex-wrap gap-2">
                  {HEALTH_GOALS.map((goal) => (
                    <button
                      key={goal}
                      type="button"
                      onClick={() => toggleArrayItem(
                        questionnaire.health_goals,
                        goal,
                        (v) => setQuestionnaire({ ...questionnaire, health_goals: v })
                      )}
                      className={`px-3 py-1.5 rounded-full text-sm transition-all ${
                        questionnaire.health_goals.includes(goal)
                          ? 'bg-purple-500 text-white'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      {goal}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">慢性病情况（可多选）</label>
                <div className="flex flex-wrap gap-2">
                  {CHRONIC_CONDITIONS.map((condition) => (
                    <button
                      key={condition}
                      type="button"
                      onClick={() => toggleArrayItem(
                        questionnaire.chronic_conditions,
                        condition,
                        (v) => setQuestionnaire({ ...questionnaire, chronic_conditions: v })
                      )}
                      className={`px-3 py-1.5 rounded-full text-sm transition-all ${
                        questionnaire.chronic_conditions.includes(condition)
                          ? 'bg-purple-500 text-white'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      {condition}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">穿戴设备（可多选）</label>
                <div className="flex flex-wrap gap-2">
                  {WEARABLE_DEVICES.map((device) => (
                    <button
                      key={device}
                      type="button"
                      onClick={() => toggleArrayItem(
                        questionnaire.wearable_devices,
                        device,
                        (v) => setQuestionnaire({ ...questionnaire, wearable_devices: v })
                      )}
                      className={`px-3 py-1.5 rounded-full text-sm transition-all ${
                        questionnaire.wearable_devices.includes(device)
                          ? 'bg-purple-500 text-white'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      {device}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">运动频率</label>
                <select
                  value={questionnaire.exercise_frequency}
                  onChange={(e) => setQuestionnaire({ ...questionnaire, exercise_frequency: e.target.value })}
                  className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white focus:ring-2 focus:ring-purple-500"
                >
                  <option value="" className="bg-gray-800">请选择</option>
                  {EXERCISE_FREQUENCIES.map((freq) => (
                    <option key={freq} value={freq} className="bg-gray-800">{freq}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">为什么想加入？</label>
                <textarea
                  value={questionnaire.why_join}
                  onChange={(e) => setQuestionnaire({ ...questionnaire, why_join: e.target.value })}
                  className="w-full p-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 resize-none"
                  rows={3}
                  placeholder="简单介绍一下您希望通过这个系统达成什么目标..."
                />
              </div>

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="flex-1 py-3 bg-white/10 text-white font-semibold rounded-lg hover:bg-white/20 transition-all"
                >
                  上一步
                </button>
                <button
                  type="submit"
                  disabled={isLoading}
                  className="flex-1 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-700 hover:to-pink-700 disabled:opacity-50 transition-all shadow-lg"
                >
                  {isLoading ? '提交中...' : '提交申请'}
                </button>
              </div>
            </form>
          )}

          <div className="mt-6 text-center">
            <p className="text-gray-400">
              已有账号？{' '}
              <Link href="/login" className="text-purple-400 hover:text-purple-300 font-semibold">
                立即登录
              </Link>
            </p>
          </div>
        </div>

        {/* 返回首页 */}
        <div className="text-center mt-6">
          <Link href="/" className="text-gray-400 hover:text-gray-300 text-sm">
            ← 返回首页
          </Link>
        </div>
      </div>

      {/* 注册成功弹窗 */}
      {showSuccessModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl shadow-2xl max-w-md w-full p-8 border border-purple-500/30">
            {/* 成功图标 */}
            <div className="text-center mb-6">
              <div className="w-20 h-20 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-purple-500/30">
                <span className="text-4xl">🎉</span>
              </div>
              <h2 className="text-2xl font-bold text-white">申请已提交！</h2>
              <p className="text-purple-300 mt-2">请等待管理员审核</p>
            </div>

            {/* 审核提示 */}
            <div className="bg-purple-500/10 rounded-xl p-5 mb-6 border border-purple-500/20">
              <div className="flex items-start gap-3">
                <span className="text-3xl">⏳</span>
                <div>
                  <h3 className="font-semibold text-white">审核中</h3>
                  <p className="text-gray-300 text-sm mt-1">
                    您的申请已成功提交，管理员会在 24 小时内完成审核。
                    审核通过后，您将可以使用邮箱和密码登录系统。
                  </p>
                </div>
              </div>
            </div>

            {/* 查询状态提示 */}
            <div className="bg-slate-700/50 rounded-lg p-4 mb-6">
              <p className="text-gray-300 text-sm">
                💡 您可以随时访问登录页面，输入邮箱查询审核状态。
              </p>
            </div>

            {/* 按钮 */}
            <button
              onClick={() => router.push('/login')}
              className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-xl hover:from-purple-700 hover:to-pink-700 transition-all shadow-lg"
            >
              前往登录页面
            </button>

            <p className="text-center text-gray-500 text-xs mt-4">
              审核结果将通过邮件通知您
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
