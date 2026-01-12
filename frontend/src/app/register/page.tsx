'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';

export default function RegisterPage() {
  const router = useRouter();
  const { register, isAuthenticated } = useAuth();
  
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    name: '',
    inviteCode: '',
  });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  // 如果已登录，重定向到首页
  if (isAuthenticated) {
    router.push('/');
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // 验证密码
    if (formData.password !== formData.confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }

    if (formData.password.length < 6) {
      setError('密码至少需要6个字符');
      return;
    }

    setIsLoading(true);

    // 验证邀请码
    if (!formData.inviteCode.trim()) {
      setError('请输入邀请码');
      setIsLoading(false);
      return;
    }

    const result = await register({
      username: formData.username,
      email: formData.email,
      password: formData.password,
      name: formData.name,
      invite_code: formData.inviteCode.trim().toUpperCase(),
    });
    
    if (result.success) {
      // 显示成功弹窗，提示等待审核
      setShowSuccessModal(true);
    } else {
      setError(result.error || '注册失败');
    }
    
    setIsLoading(false);
  };

  const handleGoToSettings = () => {
    router.push('/settings#garmin');
  };

  const handleGoToDashboard = () => {
    router.push('/');
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center space-x-2">
            <span className="text-4xl">🏥</span>
            <span className="text-2xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
              健康自律靠AI
            </span>
          </Link>
        </div>

        {/* 注册表单 */}
        <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
          <h1 className="text-2xl font-bold text-gray-900 text-center mb-6">创建账号</h1>
          
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              ❌ {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                姓名 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入您的姓名"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                用户名 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                minLength={3}
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入用户名（至少3个字符）"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                邮箱 <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入邮箱地址"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                密码 <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                required
                minLength={6}
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入密码（至少6个字符）"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                确认密码 <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                required
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请再次输入密码"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                邀请码 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                value={formData.inviteCode}
                onChange={(e) => setFormData({ ...formData, inviteCode: e.target.value.toUpperCase() })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900 uppercase"
                placeholder="请输入邀请码"
                maxLength={20}
              />
              <p className="text-xs text-gray-500 mt-1">注册后需要管理员审核通过才能登录</p>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 transition-all shadow-md"
            >
              {isLoading ? '注册中...' : '立即注册'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-gray-600">
              已有账号？{' '}
              <Link href="/login" className="text-indigo-600 hover:text-indigo-700 font-semibold">
                立即登录
              </Link>
            </p>
          </div>
        </div>

        {/* 返回首页 */}
        <div className="text-center mt-6">
          <Link href="/" className="text-gray-500 hover:text-gray-700 text-sm">
            ← 返回首页
          </Link>
        </div>
      </div>

      {/* 注册成功弹窗 */}
      {showSuccessModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 transform animate-in fade-in zoom-in duration-300">
            {/* 成功图标 */}
            <div className="text-center mb-6">
              <div className="w-20 h-20 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg">
                <span className="text-4xl">🎉</span>
              </div>
              <h2 className="text-2xl font-bold text-gray-900">注册成功！</h2>
              <p className="text-gray-600 mt-2">您的账号已提交审核</p>
            </div>

            {/* 审核提示 */}
            <div className="bg-gradient-to-r from-yellow-50 to-orange-50 rounded-xl p-5 mb-6 border border-yellow-200">
              <div className="flex items-start gap-3">
                <span className="text-3xl">⏳</span>
                <div>
                  <h3 className="font-semibold text-gray-900">等待管理员审核</h3>
                  <p className="text-gray-600 text-sm mt-1">
                    您的账号已成功注册，但需要管理员审核通过后才能登录使用。审核通过后，您将可以正常登录并配置 Garmin 账号。
                  </p>
                </div>
              </div>
            </div>

            {/* 按钮 */}
            <div className="space-y-3">
              <button
                onClick={() => router.push('/login')}
                className="w-full py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-xl hover:from-indigo-700 hover:to-purple-700 transition-all shadow-md"
              >
                前往登录页面
              </button>
            </div>

            <p className="text-center text-gray-400 text-xs mt-4">
              审核通过后，您将收到通知
            </p>
          </div>
        </div>
      )}
    </main>
  );
}

